#!/usr/bin/env python3
"""Root-only future collector on an existing acceptance VM; never builds/boots it.

No TLS peer or CONNECTED claim. Missing policy/API/worker observations fail.
"""
import argparse
import json
from pathlib import Path
import re
import secrets
import shlex
import subprocess
import sys
import time
import zipfile

import batch_network_openvpn_runtime_project as project
import batch_apps_contact_picker_coordinator as shared
from check_m144_core_package import verified_profile_content
from enclosing_acceptance_guest import EnclosingAcceptanceGuest
from hdc_transport import failed

HERE = Path(__file__).resolve().parent
require, sha, checked, load, descriptor = project.require, project.sha, project.checked, project.load, project.descriptor
quote = shlex.quote


def profile(value, role, udid, module):
    require(role == 'system' and re.fullmatch('[a-fA-F0-9]{64}', udid) and
            module['app']['bundleName'] == project.BUNDLE and
            module['module']['requestPermissions'] == [{'name': project.PERMISSION}], 'exact own system VPN caller required')
    value['bundle-info'].update({'bundle-name': project.BUNDLE, 'apl': 'system_core', 'app-feature': 'hos_system_app'})
    value['debug-info']['device-ids'] = [udid]
    value['acls']['allowed-acls'] = [project.PERMISSION]
    value['permissions']['restricted-permissions'] = [project.PERMISSION]
    return value


def verify_profile(value, udid):
    require(value['bundle-info']['bundle-name'] == project.BUNDLE and
            value['bundle-info']['apl'] == 'system_core' and value['bundle-info']['app-feature'] == 'hos_system_app' and
            value['debug-info']['device-ids'] == [udid] and
            value['acls']['allowed-acls'] == [project.PERMISSION] and
            value['permissions']['restricted-permissions'] == [project.PERMISSION], 'actual signature profile differs')


def verify_signed_payload(unsigned_path, signed_path):
    with zipfile.ZipFile(unsigned_path) as unsigned, zipfile.ZipFile(signed_path) as signed:
        before, after = unsigned.namelist(), signed.namelist()
        require(len(before) == len(set(before)) and len(after) == len(set(after)) and
                '.pages.info' not in before and set(after) == set(before) | {'.pages.info'},
                'signed HAP members differ from the compiled caller')
        bitmap = signed.read('.pages.info')
        require(bitmap and len(bitmap) % 8 == 0 and
                all(unsigned.read(name) == signed.read(name) for name in before),
                'signed HAP payload or executable page bitmap changed')


def parse_snapshot(raw):
    stats, processes, entries = {}, {}, []
    for line in raw.splitlines():
        tag, _, text = line.partition('|')
        if tag == 'S':
            value = project.proc_stat(text); stats[value['pid']] = value
        elif tag == 'P':
            pid, exe, uid, command = text.split('|')
            processes[int(pid)] = {'exe': exe, 'uid': int(uid), 'argv': bytes.fromhex(command).decode().rstrip('\0').split('\0')}
        elif tag == 'R':
            require(text.count('|') == 1, 'ambiguous private namespace entry')
            entries.append(text)
        elif tag == 'E': raise ValueError('unreadable live /proc entry: ' + text)
        else: raise ValueError('unexpected raw process snapshot record')
    for pid, row in processes.items():
        require(pid in stats, 'helper changed during snapshot'); row.update(stats[pid])
    require(1 in stats and stats[1]['ppid'] == 0, 'actual complete init /proc namespace required')
    return {'stats': stats, 'processes': processes, 'entries': entries}


SNAPSHOT = r'''
for task_vpn_proc in /proc/[0-9]*; do
  if task_vpn_stat=$(cat "$task_vpn_proc/stat" 2>/dev/null); then
    printf 'S|%s\n' "$task_vpn_stat"
  elif test -d "$task_vpn_proc"; then printf 'E|%s\n' "$task_vpn_proc"; fi
  task_vpn_exe=$(readlink "$task_vpn_proc/exe" 2>/dev/null) || continue
  case "$task_vpn_exe" in
    /system/bin/qemu_openvpn|/system/bin/qemu_openvpn_service|/system/bin/qemu_openvpn_tun)
      task_vpn_uid=$(sed -n 's/^Uid:[[:space:]]*\([0-9]*\).*/\1/p' "$task_vpn_proc/status") || exit 1
      task_vpn_hex=$(od -An -v -tx1 "$task_vpn_proc/cmdline" | tr -d ' \n') || exit 1
      printf 'P|%s|%s|%s|%s\n' "${task_vpn_proc##*/}" "$task_vpn_exe" "$task_vpn_uid" "$task_vpn_hex";;
  esac
done
if test -e /data/service/el1/public/vpn/qemu_openvpn; then
  test ! -L /data/service/el1/public/vpn/qemu_openvpn || exit 1
  for task_vpn_path in /data/service/el1/public/vpn/qemu_openvpn/* /data/service/el1/public/vpn/qemu_openvpn/.[!.]*; do
    if test -e "$task_vpn_path" || test -L "$task_vpn_path"; then
      printf 'R|%s|%s\n' "${task_vpn_path##*/}" "$(stat -c '%u:%g:%a:%F' "$task_vpn_path")"
    fi
  done
fi
'''


def claimed(snapshot, profile_sha):
    clients = [row for row in snapshot['processes'].values() if row['exe'] == '/system/bin/qemu_openvpn']
    require(len(clients) == 1, 'one real OpenVPN exec child required; no simulated claim')
    client = clients[0]; workers = snapshot['processes']; argv = client['argv']
    require(client['uid'] == 1098 and argv.count('--config') == 1, 'real owned client identity required')
    require(argv.index('--config') + 1 < len(argv), 'real config argv is truncated')
    config = argv[argv.index('--config') + 1]
    require(re.fullmatch(re.escape(project.ROOT) + r'/session-[A-Za-z0-9]{6}/client\.ovpn', config), 'exact private config required')
    marks = [argv[i+2] for i in range(len(argv)-2) if argv[i:i+2] == ['--setenv', 'OHOS_OPENVPN_SESSION']]
    require(len(marks) == 1 and re.fullmatch('[a-f0-9]{32}', marks[0]), 'real generation argv required')
    worker = workers.get(client['ppid']); require(worker is not None, 'actual worker parent missing')
    broker = workers.get(worker['ppid']); require(broker is not None, 'actual broker parent missing')
    require(worker['exe'] == broker['exe'] == '/system/bin/qemu_openvpn_service' and
            worker['uid'] == broker['uid'] == 1098 and worker['pgrp'] == worker['pid'] and
            client['pgrp'] == worker['pid'] and broker['ppid'] == 1, 'real init/broker/worker/group ancestry differs')
    require(len([e for e in snapshot['entries'] if e.startswith('session-')]) == 1, 'foreign or extra session present')
    return {'client': client, 'worker': worker, 'broker': broker, 'generation': marks[0],
            'directory': str(Path(config).parent), 'config': config, 'profile_sha256': profile_sha,
            'claim_proof': 'actual_client_exec_after_successful_production_NotifyConnectStage_claim_NOT_direct_claim_telemetry'}


def journal(raw, run, boot, uid, token):
    require(0 < len(raw.encode()) < 1048576 and raw.endswith('\n'), 'complete bounded app journal required')
    rows = [json.loads(line, object_pairs_hook=shared.unique) for line in raw.splitlines()]
    for index, row in enumerate(rows, 1):
        require(isinstance(row, dict) and set(row) == {'schema_version', 'run_id', 'boot_id', 'operation_id', 'action',
                'sequence', 'uid', 'pid', 'token_id', 'event', 'code', 'value'} and
                all(type(row[key]) is int for key in ('schema_version', 'sequence', 'uid', 'pid', 'token_id', 'code')) and
                re.fullmatch('[a-f0-9]{32}', row['operation_id']) and
                row['schema_version'] == 1 and row['sequence'] == index and row['run_id'] == run and
                row['boot_id'] == boot and row['uid'] == uid and row['token_id'] == token and row['pid'] > 1 and
                row['action'] in ('setup', 'destroy', 'inspect') and
                row['event'] in ('begin', 'permission', 'resolved', 'rejected', 'getters', 'getter-error', 'complete'),
                'foreign/reordered/malformed journal')
        require(row['event'] != 'getter-error', 'public getters failed')
        if row['event'] == 'permission': require(type(row['code']) is int and row['code'] == 0, 'actual MANAGE_VPN denied')
        if row['event'] == 'getters':
            require(json.loads(row['value']) == {'config_undefined': True, 'apps': []}, 'unexpected CONNECTED or foreign VPN')
    require(len({row['pid'] for row in rows}) == 1, 'caller restarted and lost its owned connection')
    return rows


class Collector:
    def __init__(self, args):
        self.args = args; self.output = args.output.resolve(); self.output.mkdir(parents=True, exist_ok=False)
        self.output.chmod(0o700)
        self.report = dict(schema_version=1, status='fail', scope=project.SCOPE, commands=[], phases=[], failures=[],
            cleanup_verified=False, first_artifact_behavior_gate_passed=False,
            gaps=['No observation of old-PGID signal delivery or forced PID reuse', 'No CONNECTED/TLS/TUN/data-plane proof',
                  'Single system owner only; no second-owner isolation proof', 'No real callback event stream coverage'])
        self.guest = None; self.install_attempted = False; self.installed = False
        self.fault = None; self.identity = None; self.started = False
        try:
            self.spec = load(args.inputs); self.data = project.binding(self.spec)
            self.report['inputs'] = descriptor(args.inputs); self.report['source'] = self.data
        except (ValueError, OSError, KeyError, TypeError) as error:
            self.report['failures'].append('input binding: ' + str(error)); raise
        finally: self.save()

    def save(self):
        if self.guest: self.report['guest'] = self.guest.report
        project.write(self.output / 'evidence.json', self.report)

    def command(self, argv, label):
        argv = list(map(str, argv)); self.guest.healthy()
        path = self.output / (str(len(self.report['commands'])).zfill(3) + '-' + label + '.log')
        try: result = subprocess.run(argv, capture_output=True, text=True, timeout=300)
        except subprocess.TimeoutExpired as error:
            def text(value): return value.decode(errors='replace') if isinstance(value, bytes) else value or ''
            path.write_text(text(error.stdout) + text(error.stderr))
            self.report['commands'].append({'argv': argv, 'exit_code': None, 'timed_out': True, 'raw': descriptor(path)})
            self.save(); raise ValueError('real command timed out; partial output preserved: ' + label) from error
        path.write_text(result.stdout + result.stderr)
        self.report['commands'].append({'argv': argv, 'exit_code': result.returncode, 'raw': descriptor(path)}); self.save()
        require(result.returncode == 0 and not failed(result.stdout + result.stderr), 'real command failed: ' + label)
        return result.stdout

    def shell(self, value, label):
        try:
            require(self.guest.shell('cat /proc/sys/kernel/random/boot_id', label + '-boot').strip() ==
                    self.guest.env['boot_id'], 'owned guest kernel boot changed')
            return self.guest.shell(value, label)
        finally: self.save()

    def snapshot(self, label): return parse_snapshot(self.shell(SNAPSHOT, label))

    def phase(self, action, expected='resolved'):
        operation = secrets.token_hex(16)
        request = dict(run_id=self.data['run_id'], boot_id=self.guest.env['boot_id'], operation_id=operation, action=action)
        launched = self.shell('aa start -a EntryAbility -b ' + project.BUNDLE + ' --ps request ' + quote(json.dumps(request)), 'launch-' + action)
        require('start ability successfully' in launched.lower(), 'actual QA Ability launch failed')
        deadline = time.monotonic() + 20
        while True:
            raw = self.shell('if test -f ' + quote(self.remote) + '; then cat ' + quote(self.remote) + '; fi', 'journal-' + action)
            if raw:
                rows = journal(raw, self.data['run_id'], self.guest.env['boot_id'], self.identity['uid'], self.identity['token'])
                current = [row for row in rows if row['operation_id'] == operation]
                if current and current[-1]['event'] == 'complete': break
            require(time.monotonic() < deadline, 'actual public API did not complete'); time.sleep(0.25)
        require([row['event'] for row in current] == ['begin', 'permission', expected, 'getters', 'complete'],
                'actual API outcome differs: ' + action)
        require(all(row['action'] == action for row in current), 'journal action differs from actual request')
        if expected == 'rejected': require(current[2]['code'] == 2200003, 'cleanup must fail with actual internal/backend error')
        self.report['phases'].append({'request': request, 'outcome': current[2], 'journal_command': len(self.guest.report['commands']) - 1})
        self.save(); return current

    def install(self):
        require(project.BUNDLE not in self.shell('bm dump -a', 'BMS-before'), 'fresh own QA bundle must be absent')
        dist, jar, _ = shared.signer_inputs(self.args.signer_dist, self.args.jar)
        signed = self.output / 'signed.hap'
        self.command([sys.executable, Path(__file__), 'sign', '--unsigned', checked(self.spec['unsigned_hap']),
            '--signer-dist', dist, '--jar', jar, '--udid', self.guest.udid, '--output', signed], 'sign-system-caller')
        verify_signed_payload(checked(self.spec['unsigned_hap']), signed)
        chain, embedded = self.output / 'chain.cer', self.output / 'embedded.p7b'
        log = self.command(['java', '-jar', jar, 'verify-app', '-inFile', signed, '-outCertChain', chain, '-outProfile', embedded], 'verify-app')
        require(all(v in log for v in ('verify codesign success', 'Digest verify result: true', 'verify permission sign success', 'verify-app success')), 'signature verify markers missing')
        shared.application_leaf(log)
        # Reuse fixed signer inputs and independently verify CMS with its fixed
        # leaf; do not weaken the shared ordinary/system_basic verifier.
        certs = re.findall(r'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----', (dist / 'OpenHarmonyProfileDebug.pem').read_text(), re.S)
        require(len(certs) == 3, 'fixed profile certificate chain differs')
        leaf = self.output / 'profile-leaf.pem'; leaf.write_text(certs[-1] + '\n')
        decoded = self.output / 'profile.json'
        self.command(['openssl', 'cms', '-verify', '-inform', 'DER', '-in', embedded, '-nointern', '-certfile', leaf, '-noverify', '-out', decoded], 'fixed-profile-CMS')
        verify_profile(verified_profile_content(load(decoded)), self.guest.udid)
        self.report['signed_hap'] = descriptor(signed)
        self.install_attempted = True
        reply = self.command([self.args.hdc, '-t', self.guest.target, 'install', signed], 'install')
        require('success' in reply.lower(), 'actual BMS install failed')
        self.installed = True
        raw = self.shell('bm dump -n ' + project.BUNDLE, 'BMS-installed')
        bms = json.JSONDecoder().raw_decode(raw[raw.find('{'):])[0]; app = bms['applicationInfo']
        require(app.get('isSystemApp') is True and app.get('appPrivilegeLevel') == 'system_core' and
                app['uid'] // 200000 == 100 and app['accessTokenId'] > 0, 'actual system UID/token/APL required')
        self.identity = {'uid': app['uid'], 'token': app['accessTokenId']}; self.report['identity'] = self.identity
        paths = {r['hapPath'] for r in shared.verifier.objects(bms) if isinstance(r.get('hapPath'), str) and r['hapPath'].startswith('/data/app/')}
        require(len(paths) == 1, 'one actual installed HAP path required')
        remote_hap = next(iter(paths))
        require(self.shell('sha256sum ' + quote(remote_hap), 'installed-HAP-hash').split() == [sha(signed), remote_hap], 'installed HAP differs')
        self.remote = '/data/app/el2/100/base/' + project.BUNDLE + '/files/openvpn-' + self.data['run_id'] + '.jsonl'

    def no_group(self, snapshot, old):
        require(not any(row['pgrp'] == old['worker']['pid'] for row in snapshot['stats'].values()), 'actual old process group remains')

    def wait_claim(self, label):
        deadline = time.monotonic() + 8
        while True:
            try:
                result = claimed(self.snapshot(label), self.data['profile_sha256'])
                break
            except ValueError as error:
                require(time.monotonic() < deadline, 'no actual worker/client/claim evidence: ' + str(error)); time.sleep(0.25)
        self.shell('test ! -L {p} && test "$(stat -c \'%u:%a\' {p})" = 1098:700'.format(p=quote(result['directory'])), label + '-directory')
        require(self.shell('sha256sum ' + quote(result['config']), label + '-profile-hash').split() ==
                [self.data['profile_sha256'], result['config']], 'worker config differs from actual owned input')
        return result

    def remove_fault(self):
        if not self.fault: return
        marker = 'openvpn-owned-' + self.data['run_id']
        script = ('if test ! -e {p} && test ! -L {p}; then :; else '
                  'test -f {p} && test ! -L {p} && test "$(stat -c \'%u:%a:%h\' {p})" = 0:600:1 && '
                  'test "$(cat {p})" = {m} && rm {p}; fi').format(p=quote(self.fault), m=quote(marker))
        self.shell(script, 'remove-only-own-fault'); self.fault = None

    def start_owned_session(self):
        self.phase('inspect')
        self.started = True
        self.phase('setup')

    def execute(self):
        self.guest = EnclosingAcceptanceGuest(self.args.boot, self.args.archive, self.args.hdc, self.output / 'guest')
        self.guest.start()
        self.report['boot'] = descriptor(self.args.boot)
        self.report['archive'] = {'path': str(self.args.archive.resolve()), 'sha256': load(self.args.boot)['archive_sha256']}
        self.report['tools'] = {name: descriptor(HERE / name) for name in
            ('batch_network_openvpn_runtime_project.py', 'batch_network_openvpn_runtime_collect.py',
             'enclosing_acceptance_guest.py', 'batch_apps_contact_picker_coordinator.py', 'sign_certificate_probe.py')}
        before = self.snapshot('before')
        require(len(before['processes']) <= 1 and (not before['processes'] or
                all(row['exe'] == '/system/bin/qemu_openvpn_service' and row['ppid'] == 1 for row in before['processes'].values())), 'foreign VPN client/worker present')
        require(all(row.startswith('backend.lock|') for row in before['entries']), 'foreign/unknown existing private root content')
        # An unused loopback UDP port is the controlled unreachable endpoint.
        hex_port = f'{self.data["port"]:04X}'
        nets = self.shell('cat /proc/net/udp /proc/net/udp6', 'unused-loopback-endpoint')
        require(not re.search(r':[0]*' + hex_port + r'\s', nets, re.I), 'controlled endpoint already has a UDP socket')
        self.install()
        # Inspect before any mutating request: a foreign non-OpenVPN connection
        # is not visible in our private helper/process namespace.
        self.start_owned_session()
        first = self.wait_claim('first-claim')
        self.report['first_claim'] = first; self.save()
        self.fault = first['directory'] + '/qa-' + self.data['run_id']
        marker = 'openvpn-owned-' + self.data['run_id']
        self.shell('test ! -e {p} && test ! -L {p} && (umask 077; set -C; printf "%s\\n" {m} > {p})'.format(p=quote(self.fault), m=quote(marker)), 'inject-only-own-unknown-file')
        self.shell('test ! -L {p} && test "$(stat -c \'%u:%a:%h\' {p})" = 0:600:1'.format(p=quote(self.fault)), 'own-fault-metadata')
        self.phase('destroy', 'rejected')
        stopped = self.snapshot('reaped-with-cleanup-blocked'); self.no_group(stopped, first)
        self.shell('test -d ' + quote(first['directory']) + ' && test -f ' + quote(self.fault), 'cleanup-reservation-retained')
        self.phase('setup', 'rejected')
        blocked = self.snapshot('restart-blocked'); self.no_group(blocked, first)
        require(all(row['exe'] == '/system/bin/qemu_openvpn_service' and row['ppid'] == 1
                    for row in blocked['processes'].values()) and
                [row.split('|')[0] for row in blocked['entries'] if row.startswith('session-')] == [Path(first['directory']).name],
                'conflicting setup created another worker/session while cleanup was blocked')
        self.remove_fault()
        deadline = time.monotonic() + 12
        while True:
            absent = self.shell('if test -e {p} || test -L {p}; then echo PRESENT; else echo ABSENT; fi'.format(p=quote(first['directory'])), 'reap-cleanup-retry').strip()
            if absent == 'ABSENT': break
            require(time.monotonic() < deadline, 'real periodic cleanup did not retry'); time.sleep(0.25)
        # Recreate proves operational release; absence of a PID alone does not.
        self.phase('setup')
        second = self.wait_claim('second-claim')
        require(second['generation'] != first['generation'] and second['worker']['start'] != first['worker']['start'], 'new real generation/worker required')
        self.report['second_claim'] = second; self.phase('destroy')
        after = self.snapshot('final-processes'); self.no_group(after, first); self.no_group(after, second)
        require(all(row.startswith('backend.lock|') for row in after['entries']) and
                all(row['exe'] == '/system/bin/qemu_openvpn_service' and row['ppid'] == 1 for row in after['processes'].values()),
                'private session artifacts or real worker/client remain')
        self.report['cleanup_verified'] = True; self.report['status'] = 'pass_narrow_guest_cleanup_NOT_full_gate'

    def cleanup(self):
        if not self.guest or not self.install_attempted:
            return
        if self.started:
            try:
                self.remove_fault()
                if not self.report['cleanup_verified']:
                    self.phase('destroy'); remaining = self.snapshot('failure-public-cleanup')
                    require(all(row.startswith('backend.lock|') for row in remaining['entries']) and
                            not any(row['exe'] != '/system/bin/qemu_openvpn_service' or row['ppid'] != 1 for row in remaining['processes'].values()),
                            'failed test still owns live/session resources')
                    self.report['cleanup_verified'] = True
            except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as error:
                self.report['status'] = 'fail'; self.report['failures'].append('native cleanup: ' + str(error))
            if not self.report['cleanup_verified']:
                self.report['status'] = 'fail'
                self.report['failures'].append('guest cannot be reused with unproved owner cleanup')
                return
        # No setup request was sent when install/identity/inspect failed. The
        # only possible installed bundle is ours, absent at the verified BMS
        # baseline; remove it independently of native cleanup verification.
        try:
            if self.installed:
                self.shell('aa force-stop ' + project.BUNDLE, 'stop-own-QA-Ability')
        except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as error:
            self.report['status'] = 'fail'; self.report['failures'].append('stop own QA: ' + str(error))
        try:
            present = project.BUNDLE in self.shell('bm dump -a', 'BMS-before-uninstall')
            if present:
                reply = self.command([self.args.hdc, '-t', self.guest.target, 'uninstall', project.BUNDLE], 'uninstall-own-QA')
                require('success' in reply.lower(), 'actual BMS uninstall failed')
            require(project.BUNDLE not in self.shell('bm dump -a', 'BMS-after-uninstall'), 'own QA bundle remains installed')
            self.report['qa_bundle_removed'] = True
        except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as error:
            self.report['status'] = 'fail'; self.report['failures'].append('uninstall own QA: ' + str(error))

    def run(self):
        try: self.execute()
        except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as error:
            self.report['failures'].append(str(error))
        finally:
            self.cleanup()
            self.save()
        return self.report


def main():
    parser = argparse.ArgumentParser(description=__doc__); sub = parser.add_subparsers(dest='mode', required=True)
    sign = sub.add_parser('sign')
    for name in ('unsigned', 'signer-dist', 'jar', 'output'): sign.add_argument('--' + name, type=Path, required=True)
    sign.add_argument('--udid', required=True)
    run = sub.add_parser('run')
    for name in ('boot', 'archive', 'inputs', 'signer-dist', 'jar', 'output'): run.add_argument('--' + name, type=Path, required=True)
    run.add_argument('--hdc', default='hdc'); args = parser.parse_args()
    if args.mode == 'sign':
        from sign_certificate_probe import sign as sign_hap
        args.role = 'system'; sign_hap(args, configure=profile); return 0
    result = Collector(args).run(); print(json.dumps({'status': result['status'], 'failures': result['failures']}))
    return result['status'] != 'pass_narrow_guest_cleanup_NOT_full_gate'


if __name__ == '__main__': raise SystemExit(main())
