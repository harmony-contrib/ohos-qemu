#!/usr/bin/env python3
"""Prepare independent full-product guests on a real QEMU stream Ethernet wire.

Preparation never starts QEMU. `observe` is an explicit later guest operation;
its evidence cannot close service discovery/account-authentication requirements.
"""
import argparse
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import shutil
import socket
import stat
import subprocess
import time
import tarfile
import uuid

ROLES = ('listener', 'connector')
PRODUCTS = {'arm64_virt': 'virt', 'armv7a_virt': 'virt', 'x86_64_virt': 'q35'}
SAFE_PATH = re.compile(r'/[A-Za-z0-9_./-]+\Z')
UDID = re.compile(r'[0-9a-fA-F]{64}\Z')
BOOT = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\Z')


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def dump(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


def ports(hdc, vnc, peer):
    if type(vnc) is not int or vnc < 0:
        raise ValueError('VNC display must be a non-negative integer')
    values = [hdc, hdc + 1, 5900 + vnc, 5901 + vnc, peer]
    if any(type(port) is not int or not 1024 <= port <= 65535 for port in values) or len(set(values)) != len(values):
        raise ValueError('five distinct unprivileged HDC/VNC/peer TCP ports are required')
    return values


def subnet(value):
    network = ipaddress.IPv4Network(value, strict=True)
    private = any(network.subnet_of(ipaddress.IPv4Network(block))
                  for block in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))
    if network.prefixlen != 30 or not private or network.overlaps(ipaddress.IPv4Network('10.0.2.0/24')):
        raise ValueError('peer data subnet must be a private /30 outside QEMU management 10.0.2.0/24')
    return network


def preflight_qemu(binary, machine):
    binary = Path(shutil.which(str(binary)) or binary).resolve(strict=True)
    results = []
    for arguments in (['--version'], ['-M', machine, '-netdev', 'help']):
        value = subprocess.run([str(binary), *arguments], capture_output=True, timeout=10, check=False)
        results.append(dict(argv=[str(binary), *arguments], exit_code=value.returncode,
                            stdout=value.stdout.decode(), stderr=value.stderr.decode()))
        if value.returncode:
            raise ValueError('selected QEMU help failed; no VM was started')
    if 'stream' not in results[1]['stdout'].splitlines() or 'user' not in results[1]['stdout'].splitlines():
        raise ValueError('selected QEMU must advertise real stream and management user backends')
    return dict(path=str(binary), sha256=sha(binary), help=results)


def make_plan(package, output, *, qemu, hdc_port=5558, vnc_display=41, peer_port=24680,
              network='172.27.77.0/30', run=None):
    package, output = Path(package).resolve(strict=True), Path(output).resolve()
    if not SAFE_PATH.fullmatch(str(output)) or output == package or package in output.parents or output in package.parents:
        raise ValueError('use separate shell-safe source and instance directories')
    manifest = json.loads((package / 'manifest.json').read_text())
    product = manifest['product']
    if product not in PRODUCTS:
        raise ValueError('peer LAN supports the three full PCI-virtio products only')
    launcher = package / 'launch/qemu_run.sh'
    if '# QEMU_PEER_LAN_V1' not in launcher.read_text():
        raise ValueError('package needs the peer LAN launcher rewrite before preparation')
    ports(hdc_port, vnc_display, peer_port)
    network = subnet(network)
    run = run or secrets.token_hex(16)
    if not re.fullmatch('[0-9a-f]{32}', run):
        raise ValueError('fresh 32-hex run ID required')
    control = Path('/tmp') / ('ohos-peer-' + run)
    if control.exists() or control.is_symlink():
        raise ValueError('fresh private control socket directory required')
    identities, macs = {}, set()
    for index, role in enumerate(ROLES):
        raw = hashlib.sha256((run + ':' + role).encode()).hexdigest()
        mgmt = '02:' + ':'.join(raw[n:n+2] for n in range(0, 10, 2))
        peer = '02:' + ':'.join(raw[n:n+2] for n in range(10, 20, 2))
        macs.update((mgmt, peer))
        path = output / role
        env = dict(QEMU_PEER_MODE='listen' if index == 0 else 'connect', QEMU_PEER_PORT=str(peer_port),
            QEMU_PEER_MAC=peer, QEMU_MGMT_MAC=mgmt, QEMU_INSTANCE_UUID=str(uuid.uuid4()),
            QEMU_GUEST_SERIAL=raw[:20], QEMU_PEER_CAPTURE_FILE=str(path / 'peer-lan.pcap'),
            QEMU_HDC_HOST_PORT=str(hdc_port + index), QEMU_VNC_DISPLAY=str(vnc_display + index),
            QEMU_QMP_SOCKET=str(control / (role + '.sock')), QEMU_EXTRA_ARGS='', QEMU_ACCEL='tcg',
            QEMU_BIN=str(Path(qemu).resolve()), QEMU_DISPLAY='none')
        identities[role] = dict(path=str(path), environment=env, target='127.0.0.1:' + str(hdc_port + index),
            address=str(network.network_address + index + 1), peer_address=str(network.network_address + 2 - index),
            prefix=network.prefixlen, qmp_socket=env['QEMU_QMP_SOCKET'], management_mac=mgmt, peer_mac=peer)
    if len(macs) != 4:
        raise ValueError('all four actual NIC MACs must be distinct')
    return dict(schema_version=1, status='prepared_candidate_not_booted', run_id=run, product=product,
        source_package=str(package), source_manifest_sha256=sha(package / 'manifest.json'),
        source_launcher_sha256=sha(launcher), output=str(output), control_directory=str(control),
        network=str(network), peer_backend='QEMU stream Ethernet over host loopback TCP',
        instances=identities, disk_copies={}, commands=[], failures=[],
        service_validation='open: discovery, account authentication, nonce transfer, peer removal not yet observed',
        first_artifact_behavior_gate_passed=False)


def inventory(package):
    files = []
    for path in sorted(package.rglob('*')):
        mode = path.lstat().st_mode
        if stat.S_ISLNK(mode) or not (stat.S_ISDIR(mode) or stat.S_ISREG(mode)):
            raise ValueError('package must contain only regular files/directories; refusing linked or special image inputs')
        if stat.S_ISREG(mode):
            files.append(path)
    disks = [path for path in files if path.parent == package / 'images' and path.suffix == '.img']
    if not disks or not any(path.name == 'userdata.img' for path in disks) or any(path.stat().st_size == 0 for path in disks):
        raise ValueError('independent non-empty image files including userdata.img are required')
    return files, disks


def bind_archive(archive, sources):
    """Hash archive bytes directly; never extract links or traversal paths."""
    archived, seen = {}, set()
    with tarfile.open(archive, 'r:*') as source:
        members = source.getmembers()
        roots = [Path(member.name).parent.as_posix() for member in members
                 if member.isfile() and Path(member.name).name == 'manifest.json']
        if len(roots) != 1:
            raise ValueError('archive needs one unique package manifest')
        root = roots[0]
        for member in members:
            path = Path(member.name)
            if path.is_absolute() or '..' in path.parts or member.name in seen or not (member.isfile() or member.isdir()):
                raise ValueError('archive contains unsafe/duplicate/linked members')
            seen.add(member.name)
            if not member.isfile():
                continue
            try:
                relative = path.relative_to(root).as_posix()
            except ValueError:
                raise ValueError('archive has files outside its package root') from None
            if relative not in sources or member.size != sources[relative]['bytes']:
                raise ValueError('archive package file set/size differs from candidate directory')
            digest = hashlib.sha256()
            with source.extractfile(member) as content:
                for block in iter(lambda: content.read(1024 * 1024), b''):
                    digest.update(block)
            archived[relative] = digest.hexdigest()
    if set(archived) != set(sources) or any(archived[name] != row['sha256'] for name, row in sources.items()):
        raise ValueError('archive content differs from the package; repackage candidate launchers before preparing')


def prepare(args):
    package, output = args.package.resolve(strict=True), args.output.resolve()
    manifest = json.loads((package / 'manifest.json').read_text())
    qemu = preflight_qemu(args.qemu, PRODUCTS.get(manifest['product'], 'virt'))
    plan = make_plan(package, output, qemu=qemu['path'], hdc_port=args.hdc_port,
        vnc_display=args.vnc_display, peer_port=args.peer_port, network=args.subnet)
    files, disks = inventory(package)
    if args.archive:
        plan['archive_path'], plan['archive_sha256'] = str(args.archive.resolve(strict=True)), sha(args.archive)
    else:
        raise ValueError('actual representative package archive is required for later runtime provenance')
    plan['qemu'] = qemu
    # No socket is held across VM startup; QEMU must still bind successfully.
    for port in ports(args.hdc_port, args.vnc_display, args.peer_port):
        with socket.socket() as probe:
            probe.bind(('127.0.0.1', port))
    output.mkdir(mode=0o700, exist_ok=False)
    control = Path(plan['control_directory'])
    control.mkdir(mode=0o700, exist_ok=False)
    plan['control_directory_identity'] = dict(uid=control.stat().st_uid, inode=control.stat().st_ino, mode=700)
    try:
        sources = {str(path.relative_to(package)): dict(path=str(path), sha256=sha(path), bytes=path.stat().st_size)
                   for path in files}
        bind_archive(args.archive, sources)
        plan['source_files'] = sources
        for role, instance in plan['instances'].items():
            destination = Path(instance['path'])
            shutil.copytree(package, destination, symlinks=False)
            disk_rows = {}
            for disk in disks:
                relative = str(disk.relative_to(package))
                copied = destination / relative
                if os.path.samefile(disk, copied) or sha(copied) != sources[relative]['sha256']:
                    raise ValueError('disk must be a separate inode with exact original package bytes')
                if any(os.path.samefile(copied, Path(other['path']) / relative)
                       for name, other in plan['instances'].items() if name != role and (Path(other['path']) / relative).exists()):
                    raise ValueError('two instances cannot share a writable disk inode')
                disk_rows[relative] = dict(path=str(copied), sha256=sha(copied), bytes=copied.stat().st_size,
                    device=copied.stat().st_dev, inode=copied.stat().st_ino)
            plan['disk_copies'][role] = disk_rows
            qmp = shlex.quote(instance['qmp_socket'])
            script = '#!/usr/bin/env bash\nset -euo pipefail\numask 077\n'
            script += 'test ! -e ' + qmp + ' && test ! -L ' + qmp + '\n'
            script += 'exec env ' + ' '.join(shlex.quote(key + '=' + value) for key, value in instance['environment'].items())
            script += ' bash ' + shlex.quote(str(destination / 'launch/linux.sh')) + '\n'
            start = output / ('start-' + role + '.sh')
            start.write_text(script);start.chmod(0o700)
            instance['start_script'], instance['start_script_sha256'] = str(start), sha(start)
        # Detect source replacement during copy rather than declaring a mixed snapshot.
        if any(sha(Path(value['path'])) != value['sha256'] for value in sources.values()):
            raise ValueError('source package changed while cloning independent instances')
    except Exception as error:
        plan['status'] = 'fail'
        plan['failures'].append(str(error))
        raise
    finally:
        dump(output / 'peer-lan.json', plan)
    return plan


def identity(udid_text, boot_text, links, instance):
    lines = udid_text.strip().splitlines()
    if len(lines) != 2 or lines[0] != 'udid of current device is :' or UDID.fullmatch(lines[1]) is None:
        raise ValueError('real bm get --udid output is required')
    boot = boot_text.strip()
    if BOOT.fullmatch(boot) is None:
        raise ValueError('actual guest kernel boot UUID is required')
    interfaces = {}
    for line in links.splitlines():
        match = re.match(r'\d+: ([A-Za-z0-9_.-]+)(?:@[^: ]+)?: .*\blink/ether ([0-9a-fA-F:]{17})(?:\s|$)', line)
        if match:
            name, mac = match.group(1), match.group(2).lower()
            if mac in interfaces:
                raise ValueError('duplicate actual guest MAC')
            interfaces[mac] = name
    if instance['peer_mac'] not in interfaces or instance['management_mac'] not in interfaces:
        raise ValueError('configured peer and management MACs must be real separate guest NICs')
    return dict(udid=lines[1].lower(), boot_id=boot, peer_interface=interfaces[instance['peer_mac']],
                management_interface=interfaces[instance['management_mac']])


def validate_pair(identities):
    if set(identities) != set(ROLES):
        raise ValueError('both independently observed guests are required')
    if any(identities[ROLES[0]][key] == identities[ROLES[1]][key] for key in ('udid', 'boot_id')):
        raise ValueError('cloned/same guest identity is not a peer; unique boot serial is not proof of a unique UDID')
    if any(value['peer_interface'] == value['management_interface'] for value in identities.values()):
        raise ValueError('peer data and management cannot use the same actual interface')


def configure_script(instance, interface):
    if not re.fullmatch('[A-Za-z0-9_.-]+', interface):
        raise ValueError('actual safe NIC name required')
    address = str(ipaddress.IPv4Address(instance['address']))
    return ('test "$(id -u)" = 0 && test "$(cat /sys/class/net/' + interface + '/address)" = ' +
        shlex.quote(instance['peer_mac']) + ' && ip link set dev ' + interface + ' up && '
        'if ip -o -4 addr show dev ' + interface + ' | grep -q " inet "; then '
        'ip -o -4 addr show dev ' + interface + ' | grep -q " inet ' + address + '/30 "; '
        'else ip addr add ' + address + '/30 dev ' + interface + '; fi')


def route_check(text, instance, interface):
    words = text.split()
    if (not words or 'via' in words or words.count('dev') != 1 or words.count('src') != 1 or
            words.index('dev') + 1 >= len(words) or words.index('src') + 1 >= len(words) or
            words[words.index('dev') + 1] != interface or words[words.index('src') + 1] != instance['address'] or
            words[0] != instance['peer_address']):
        raise ValueError('actual peer route must be direct through its data NIC, never the user NAT NIC')


def validate_staging(plan):
    if set(plan['instances']) != set(ROLES) or not re.fullmatch('[0-9a-f]{32}', plan['run_id']):
        raise ValueError('fixed two-role prepared plan required')
    network = subnet(plan['network'])
    control = Path(plan['control_directory'])
    saved = plan['control_directory_identity']
    actual = control.lstat()
    if (control != Path('/tmp') / ('ohos-peer-' + plan['run_id']) or
            not stat.S_ISDIR(actual.st_mode) or actual.st_uid != saved['uid'] or actual.st_uid != os.getuid() or
            actual.st_ino != saved['inode'] or stat.S_IMODE(actual.st_mode) != 0o700):
        raise ValueError('private control directory identity changed')
    inodes, macs, targets = set(), set(), set()
    expected_disks = {name for name in plan['source_files'] if Path(name).parent == Path('images') and name.endswith('.img')}
    if 'images/userdata.img' not in expected_disks:
        raise ValueError('original non-empty image inventory including userdata is required')
    for index, role in enumerate(ROLES):
        instance = plan['instances'][role]
        if (set(plan['disk_copies'][role]) != expected_disks or
                instance['qmp_socket'] != str(control / (role + '.sock'))):
            raise ValueError('complete independent image set and private role QMP socket required')
        if (instance['address'] != str(network.network_address + index + 1) or
                instance['peer_address'] != str(network.network_address + 2 - index) or
                re.fullmatch(r'127\.0\.0\.1:[1-9][0-9]{0,4}', instance['target']) is None or
                not 1024 <= int(instance['target'].split(':')[1]) <= 65535):
            raise ValueError('fixed private peer IP/management target required')
        targets.add(instance['target'])
        for key in ('peer_mac', 'management_mac'):
            mac = instance[key]
            if re.fullmatch('[0-9a-f]{2}(:[0-9a-f]{2}){5}', mac) is None or int(mac[:2], 16) & 3 != 2:
                raise ValueError('prepared locally administered unicast MAC required')
            macs.add(mac)
        for relative, disk in plan['disk_copies'][role].items():
            expected = Path(plan['output']) / role / relative
            if Path(disk['path']) != expected or Path(relative).is_absolute() or '..' in Path(relative).parts:
                raise ValueError('disk escaped its independent instance directory')
            observed = expected.lstat()
            identity = (observed.st_dev, observed.st_ino)
            if (not stat.S_ISREG(observed.st_mode) or identity != (disk['device'], disk['inode']) or identity in inodes):
                raise ValueError('independent private disk identity changed or became shared')
            inodes.add(identity)
    if len(macs) != 4 or len(targets) != 2:
        raise ValueError('all actual MACs and both management targets must be distinct')


def observe(args):
    path = args.plan.resolve(strict=True)
    args.output = args.output.resolve()
    plan = json.loads(path.read_text())
    evidence = dict(schema_version=1, status='fail', plan_path=str(path), plan_sha256=sha(path),
        run_id=plan['run_id'], archive_sha256=plan['archive_sha256'], commands=[], identities={}, failures=[],
        service_validation=plan['service_validation'], first_artifact_behavior_gate_passed=False)
    args.output.mkdir(mode=0o700, exist_ok=False)
    def actual(role, label, script):
        marker = '__PEER_EXIT_' + secrets.token_hex(16) + '__='
        wrapped = script + '; peer_rc=$?; printf "\n' + marker + '%s\n" "$peer_rc"'
        argv = [str(args.hdc), '-t', plan['instances'][role]['target'], 'shell', wrapped]
        start = time.monotonic_ns()
        timed_out = False
        try:
            result = subprocess.run(argv, capture_output=True, timeout=30, check=False)
            stdout, stderr, exit_code = result.stdout, result.stderr, result.returncode
        except subprocess.TimeoutExpired as error:
            stdout, stderr, exit_code, timed_out = error.stdout or b'', error.stderr or b'', None, True
        prefix = args.output / (str(len(evidence['commands'])).zfill(3) + '-' + role + '-' + label)
        prefix.with_suffix('.stdout').write_bytes(stdout)
        prefix.with_suffix('.stderr').write_bytes(stderr)
        evidence['commands'].append(dict(argv=argv, host_interval_ns=[start, time.monotonic_ns()],
            host_exit=exit_code, timed_out=timed_out, stdout_path=str(prefix.with_suffix('.stdout')),
            stdout_sha256=sha(prefix.with_suffix('.stdout')), stderr_path=str(prefix.with_suffix('.stderr')),
            stderr_sha256=sha(prefix.with_suffix('.stderr'))))
        text = stdout.decode('utf-8')
        match = re.search(r'(?:^|\n)' + marker + r'(\d+)\s*$', text)
        if timed_out or exit_code != 0 or not match or match.group(1) != '0':
            raise ValueError('actual guest command failed: ' + role + '/' + label)
        return text[:match.start()].rstrip('\n')
    try:
        if sha(plan['archive_path']) != plan['archive_sha256'] or plan['status'] != 'prepared_candidate_not_booted':
            raise ValueError('plan must bind the immutable actual representative archive')
        validate_staging(plan)
        for role, instance in plan['instances'].items():
            udid = actual(role, 'udid', 'bm get --udid')
            boot = actual(role, 'boot', 'cat /proc/sys/kernel/random/boot_id')
            links = actual(role, 'links', 'ip -o link show')
            evidence['identities'][role] = identity(udid, boot, links, instance)
        validate_pair(evidence['identities'])
        for role, instance in plan['instances'].items():
            nic = evidence['identities'][role]['peer_interface']
            if args.configure:
                actual(role, 'configure-private-peer-ipv4', configure_script(instance, nic))
            addresses = actual(role, 'addresses', 'ip -o -4 addr show dev ' + nic)
            if re.findall(r'\binet ([0-9.]+/\d+)\s', addresses) != [instance['address'] + '/30']:
                raise ValueError('actual peer NIC must have exactly the configured private /30 IPv4')
            evidence.setdefault('addresses', {})[role] = addresses
            route = actual(role, 'route', 'ip -o route get ' + instance['peer_address'])
            route_check(route, instance, nic)
            evidence.setdefault('routes', {})[role] = route
        for role, instance in plan['instances'].items():
            nic = evidence['identities'][role]['peer_interface']
            actual(role, 'peer-ping', 'ping -I ' + nic + ' -c 2 -W 2 ' + instance['peer_address'])
            neighbors = actual(role, 'neighbors', 'ip neigh show dev ' + nic)
            matching = [line.split() for line in neighbors.splitlines() if line.split() and
                        line.split()[0] == instance['peer_address']]
            other_role = 'connector' if role == 'listener' else 'listener'
            other = plan['instances'][other_role]['peer_mac']
            if (len(matching) != 1 or 'lladdr' not in matching[0] or matching[0].index('lladdr') + 1 >= len(matching[0]) or
                    matching[0][matching[0].index('lladdr') + 1].lower() != other or
                    matching[0][-1] not in ('REACHABLE', 'STALE', 'DELAY', 'PROBE')):
                raise ValueError('actual neighbor resolution must find the other data NIC MAC')
            evidence.setdefault('neighbors', {})[role] = neighbors
            # Re-read real identity after traffic to catch HDC target/process swaps.
            after = identity(actual(role, 'final-udid', 'bm get --udid'),
                actual(role, 'final-boot', 'cat /proc/sys/kernel/random/boot_id'),
                actual(role, 'final-links', 'ip -o link show'), instance)
            if after != evidence['identities'][role]:
                raise ValueError('peer guest identity changed during observation')
        evidence['status'] = 'kernel_l2_candidate_observed_not_service_acceptance'
    except Exception as error:
        evidence['failures'].append(str(error))
    finally:
        dump(args.output / 'observations.json', evidence)
    return evidence


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='operation', required=True)
    command = commands.add_parser('prepare', help='copy independent disks and write launch scripts; never boots a VM')
    for name in ('package', 'archive', 'output', 'qemu'):
        command.add_argument('--' + name, type=Path, required=True)
    command.add_argument('--hdc-port', type=int, default=5558)
    command.add_argument('--vnc-display', type=int, default=41)
    command.add_argument('--peer-port', type=int, default=24680)
    command.add_argument('--subnet', default='172.27.77.0/30')
    command = commands.add_parser('observe', help='explicit later HDC/root kernel-level observation, not service acceptance')
    for name in ('plan', 'output', 'hdc'):
        command.add_argument('--' + name, type=Path, required=True)
    command.add_argument('--configure', action='store_true', help='explicitly set only each peer NIC /30 IPv4; preserve management/default route')
    args = parser.parse_args()
    value = prepare(args) if args.operation == 'prepare' else observe(args)
    print(json.dumps(dict(status=value['status'], first_artifact_behavior_gate_passed=False)))
    return 1 if value['status'] == 'fail' else 0


if __name__ == '__main__':
    raise SystemExit(main())
