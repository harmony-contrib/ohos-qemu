#!/usr/bin/env python3
"""Own a fresh extraction/QEMU process; attest boot only, never all capabilities.

No periodic input, system-library substitution or shared HDC server restart.
An enclosing regression suite can keep this owned VM open with QemuGuest.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import signal
import shutil
import socket
import subprocess
import sys
import tarfile
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
sys.path.insert(0, str(ROOT / 'ci/qemu-smoke'))
from account_state import parse_snapshot
from run_root_probe import ARCHES, validate_identity
from snapshot_build_inputs import digest_files
from verify_first_artifact_gate import checksum

FATAL = re.compile(r'Kernel panic - not syncing|critical service crashed|ExecReboot panic|'
                   r'sysrq: Trigger a crash|(composer_host|render_service).*exit with signal\s*:\s*11', re.I)


def members_checked(members, name):
    seen = set()
    for member in members:
        parsed = PurePosixPath(member.name)
        normalized = parsed.as_posix().rstrip('/')
        if (parsed.is_absolute() or '..' in parsed.parts or '\\' in member.name or
                not parsed.parts or parsed.parts[0] != name or normalized in seen or
                not (member.isfile() or member.isdir()) or member.size > 8 * 1024**3):
            raise ValueError('unsafe, aliased, duplicated or oversized archive entry: ' + member.name)
        seen.add(normalized)
    if name + '/manifest.json' not in seen or name + '/build-inputs.json' not in seen:
        raise ValueError('package manifest/frozen input identity missing')


def verify_extracted_files(directory):
    observed = {}
    lines = (directory / 'SHA256SUMS').read_text().splitlines()
    if not lines:
        raise ValueError('empty package checksums')
    for line in lines:
        match = re.fullmatch(r'([a-f0-9]{64}) [ *](.+)', line)
        if not match:
            raise ValueError('malformed package checksum record')
        relative = PurePosixPath(match[2])
        name = relative.as_posix().removeprefix('./')
        if (relative.is_absolute() or '..' in relative.parts or '\\' in name or name in observed or
                any((directory / Path(*relative.parts[:i])).is_symlink()
                    for i in range(1, len(relative.parts) + 1))):
            raise ValueError('unsafe/duplicate package checksum path')
        path = directory / relative
        if not path.is_file() or checksum(path) != match[1]:
            raise ValueError('extracted package checksum mismatch: ' + name)
        observed[name] = match[1]
    mandatory = ('manifest.json', 'build-inputs.json', 'launch/linux.sh', 'launch/macos.command')
    images = [p.relative_to(directory).as_posix() for p in (directory / 'images').iterdir() if p.is_file()]
    if not images or not set((*mandatory, *images)).issubset(observed):
        raise ValueError('not all launchers/manifests/actual images have checksums')
    return observed


def check_guest_version(text):
    records = [line.strip() for line in text.replace('\r', '').splitlines()]
    if (len(records) != 5 or records[0] != '26' or re.fullmatch(r'OpenHarmony-7\.0\.0\.[0-9]+', records[1]) is None
            or records[2] != 'true' or records[3] != 'udid of current device is :' or
            re.fullmatch(r'[A-Fa-f0-9]{64}', records[4]) is None):
        raise ValueError('guest does not attest API26, boot completion and an unambiguous actual UDID')
    return records[4]


def port_available(port):
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError('private HDC host port must be 1024..65535')
    with socket.socket() as connection:
        connection.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        connection.bind(('127.0.0.1', port))


def kernel_sleeping(log):
    """Require an unmatched real kernel suspend entry, not QEMU CPU idling."""
    entry = log.rfind('PM: suspend entry (s2idle)')
    exit_ = log.rfind('PM: suspend exit')
    return entry >= 0 and entry > exit_


class QemuGuest:
    def __init__(self, args):
        self.args = args
        self.process = None
        self.qemu_log = None
        self.socket_directory = None
        self.diagnostic_process = None
        self.diagnostic_log = None
        self.report = {'schema_version': 1, 'scope': 'fresh_packaged_QEMU_boot_NOT_full_behavior_gate',
            'status': 'fail', 'purpose': args.purpose, 'archive': str(args.archive.resolve()),
            'test_environment': {'external_keepalive': False, 'host_system': platform.system(),
                                 'host_machine': platform.machine(), 'hdc_host_port': args.hdc_port,
                                 'hdc_server_port': os.environ.get('OHOS_HDC_SERVER_PORT', '8710')},
            'commands': [], 'failures': [], 'first_artifact_behavior_gate_passed': False}

    def save(self):
        (self.args.output / 'boot.json').write_text(json.dumps(self.report, indent=2) + '\n')

    def command(self, argv, label, timeout=30, allow_failure=False):
        argv = list(map(str, argv))
        log = self.args.output / (str(len(self.report['commands'])).zfill(3) + '-' + label + '.log')
        record = {'argv': argv, 'exit_code': None, 'log': str(log)}
        self.report['commands'].append(record)
        try:
            result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                    stdin=subprocess.DEVNULL, timeout=timeout, check=False)
        except subprocess.TimeoutExpired as error:
            log.write_bytes((error.stdout or b'') + (error.stderr or b''))
            record.update(timed_out=True, sha256=checksum(log))
            raise ValueError('boot command timed out: ' + label) from error
        log.write_text(result.stdout + result.stderr)
        record.update(exit_code=result.returncode, sha256=checksum(log))
        if result.returncode and not allow_failure:
            raise ValueError('boot command failed: ' + label)
        if (argv[0] == str(self.args.hdc) and not allow_failure and
                re.search(r'\[Fail\]|Device not found or connected', result.stdout)):
            raise ValueError('HDC transport/operation failed: ' + label)
        return result.stdout.replace('\r', '')

    def shell(self, script, label, allow_failure=False):
        return self.command([self.args.hdc, '-t', self.target, 'shell', script], label, allow_failure=allow_failure)

    def healthy(self):
        if self.process.poll() is not None:
            raise ValueError('owned QEMU exited before validation completed')
        if FATAL.search((self.args.output / 'qemu.log').read_text(errors='replace')):
            raise ValueError('guest fatal service/kernel failure, even though QEMU may still be running')

    def qmp(self, execute, arguments=None):
        with socket.socket(socket.AF_UNIX) as connection:
            connection.settimeout(10)
            connection.connect(str(self.qmp_path))
            with connection.makefile('rb') as stream:
                if 'QMP' not in json.loads(stream.readline()):
                    raise ValueError('bad QMP greeting')
                for identifier, name, parameters in (('capabilities', 'qmp_capabilities', None),
                                                     ('request', execute, arguments)):
                    request = {'execute': name, 'id': identifier}
                    if parameters is not None:
                        request['arguments'] = parameters
                    connection.sendall(json.dumps(request).encode() + b'\n')
                    while True:
                        line = stream.readline()
                        if not line:
                            raise ValueError('QMP disconnected')
                        reply = json.loads(line)
                        if reply.get('id') == identifier:
                            if 'error' in reply or 'return' not in reply:
                                raise ValueError('QMP failed: ' + json.dumps(reply))
                            break
                return reply['return']

    def wake_for_interaction(self, label):
        """One real key only if asleep, immediately before a requested test."""
        self.healthy()
        serial = self.args.output / 'qemu.log'
        if not kernel_sleeping(serial.read_text(errors='replace')):
            return False
        cycles = self.report.setdefault('interaction_power_cycles', [])
        row = {'label': label, 'scope': 'one_observed_sleep_wake_for_requested_test',
               'execute': 'system_powerdown', 'reply': self.qmp('system_powerdown')}
        cycles.append(row)
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            self.healthy()
            if not kernel_sleeping(serial.read_text(errors='replace')):
                break
            time.sleep(0.25)
        else:
            raise ValueError('real power key failed before requested interaction: ' + label)
        evidence = self.args.output / ('interaction-power-cycle-' + str(len(cycles)) + '.log')
        evidence.write_text(serial.read_text(errors='replace'))
        row.update(serial_evidence=str(evidence), serial_sha256=checksum(evidence))
        time.sleep(2)
        self.command([self.args.hdc, 'tconn', self.target], label + '-reconnect-after-real-key')
        self.save()
        return True

    def start(self):
        args = self.args
        args.output.mkdir(parents=True, exist_ok=False)
        try:
            port_available(args.hdc_port)
            self.report['archive_sha256'] = checksum(args.archive)
            name = args.archive.name.removesuffix('.tar.gz')
            extract = args.output / 'extract'
            extract.mkdir()
            with tarfile.open(args.archive, 'r:gz') as archive:
                members = archive.getmembers()
                members_checked(members, name)
                archive.extractall(extract, members=members, filter='data')
            self.directory = extract / name
            self.report['initial_package_file_sha256'] = verify_extracted_files(self.directory)
            manifest = json.loads((self.directory / 'manifest.json').read_text())
            self.arch, self.device = manifest['guest_arch'], manifest['device_type']
            if self.arch not in ARCHES or self.device not in ('phone', '2in1') or manifest.get(
                    'device_type_profile') != 'qemu_' + self.device + '_full_source':
                raise ValueError('a full-source supported architecture/profile package is required')
            if getattr(args, 'candidate_kernel', None):
                if args.purpose != 'diagnostic' or self.arch != 'arm64':
                    raise ValueError('a private candidate kernel can never satisfy package acceptance')
                candidate, evidence = args.candidate_kernel, args.candidate_kernel_evidence
                if candidate.is_symlink() or evidence is None or evidence.is_symlink():
                    raise ValueError('actual regular candidate kernel/build evidence required')
                build = json.loads(evidence.read_text())
                expected_patch = ROOT / 'patches/common/kernel/linux/linux_6_6/qemu_power_button/0001-mark-only-virt-platform-power-button-as-wakeup-source.patch'
                expected_gpu_patch = ROOT / 'patches/common/kernel/linux/linux_6_6/qemu_virtio_gpu_s2idle/0001-preserve-qemu-virtio-gpu-queues-during-s2idle.patch'
                if (build.get('status') != 'pass' or build.get('scope') !=
                        'isolated_ARM64_power_kernel_link_NOT_new_package_or_behavior_acceptance' or
                        build.get('image_sha256') != checksum(candidate) or
                        build.get('power_button_patch_sha256') != checksum(expected_patch) or
                        build.get('virtio_gpu_s2idle_patch_sha256') != checksum(expected_gpu_patch) or
                        build.get('seed_image_sha256') != checksum(self.directory / 'images/Image')):
                    raise ValueError('unknown, stale or differently seeded candidate kernel')
                with candidate.open('rb') as stream:
                    header = stream.read(64)
                if header[56:60] != b'ARM\x64':
                    raise ValueError('candidate kernel is not a real ARM64 Image')
                shutil.copy2(candidate, self.directory / 'images/Image')
                self.report['candidate_kernel'] = {'image': str(candidate.resolve()),
                    'image_sha256': checksum(candidate), 'build_evidence': str(evidence.resolve()),
                    'build_evidence_sha256': checksum(evidence),
                    'scope': 'private_kernel_on_old_package_NOT_new_archive_acceptance'}
            inputs = json.loads((self.directory / 'build-inputs.json').read_text())
            self.report['build_inputs_tree_sha256'] = inputs['tree_sha256']
            if args.purpose == 'acceptance':
                files = digest_files(ROOT)
                if (inputs.get('files_sha256') != files or inputs.get('tree_sha256') !=
                        hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()):
                    raise ValueError('acceptance boot requires the current exact frozen scripts/patches')
            host = platform.system()
            if host not in ('Darwin', 'Linux'):
                raise ValueError('this local boot runner supports macOS/Linux only')
            self.socket_directory = Path(tempfile.mkdtemp(prefix='oq-b-', dir='/tmp'))
            self.qmp_path = self.socket_directory / 'qmp.sock'
            launcher = self.directory / ('launch/macos.command' if host == 'Darwin' else 'launch/linux.sh')
            argv = ['bash', str(launcher), '--headless', '--a11y', '--hdc-port', str(args.hdc_port),
                    '--qmp-socket', str(self.qmp_path), '--accel', args.accel, '--resolution', args.resolution]
            if args.purpose == 'acceptance':
                argv += ['--kernel-log-level', '7']
            # A real independent USB-serial device, not the kernel console.
            # QEMU's default always-plugged=off maps host socket OPEN/CLOSE to
            # actual USB attach/detach. The test runner alone owns this private
            # endpoint; no connection/input exists during the quiet boot gate.
            serial_path = None
            if self.device == '2in1' and args.purpose == 'acceptance':
                serial_path = self.socket_directory / 'usb-serial.sock'
                argv += ['--', '-device', 'qemu-xhci,id=ohos_audit_xhci',
                    '-chardev', 'socket,id=ohos_audit_serial,path=' + str(serial_path) + ',server=on,wait=off',
                    '-device', 'usb-serial,id=ohos_audit_usb_serial,bus=ohos_audit_xhci.0,port=1,'
                               'chardev=ohos_audit_serial,serial=QEMUAPI26']
            environment_overrides = {}
            if getattr(args, 'kernel_diagnostic', None):
                if args.purpose != 'diagnostic':
                    raise ValueError('kernel-command-line diagnostics cannot satisfy an acceptance boot')
                wrapper = Path(__file__).with_name('qemu_kernel_diagnostic.py')
                executable = shutil.which({'arm64': 'qemu-system-aarch64', 'armv7a': 'qemu-system-arm',
                                          'x86_64': 'qemu-system-x86_64'}[self.arch])
                if not executable:
                    raise ValueError('actual diagnostic QEMU executable unavailable')
                environment_overrides = {'QEMU_DIAGNOSTIC_BINARY': executable,
                                         'QEMU_KERNEL_DIAGNOSTIC': args.kernel_diagnostic}
                argv += ['--qemu', str(wrapper)]
                self.report['kernel_command_line_diagnostic'] = {'mode': args.kernel_diagnostic,
                    'wrapper': str(wrapper), 'wrapper_sha256': checksum(wrapper), 'QEMU_binary': executable}
            self.target = '127.0.0.1:' + str(args.hdc_port)
            self.qemu_log = (args.output / 'qemu.log').open('wb')
            self.process = subprocess.Popen(argv, cwd=self.directory, stdout=self.qemu_log, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, start_new_session=True, umask=0o077,
                env={**os.environ, 'LC_ALL': 'C', 'LANG': 'C', **environment_overrides})
            self.report['qemu_launch_argv'] = argv
            environment = self.report['test_environment']
            environment.update(product=manifest['product'], device_type=self.device, guest_arch=self.arch,
                               launcher_pid=self.process.pid, qmp_socket=str(self.qmp_path), target=self.target,
                               freshly_extracted_directory=str(self.directory), accelerator_requested=args.accel)
            if serial_path is not None:
                environment['usb_serial_socket'] = str(serial_path)
                environment['usb_serial_hardware'] = {'controller': 'qemu-xhci', 'device': 'usb-serial',
                    'id': 'ohos_audit_usb_serial', 'serial': 'QEMUAPI26', 'always_plugged': False,
                    'scope': 'real_independent_USB_endpoint_not_console_or_mock_service'}
            self.command([args.hdc, 'start'], 'start-shared-hdc-without-restart')
            deadline = time.monotonic() + args.wait_seconds
            while time.monotonic() < deadline:
                self.healthy()
                self.command([args.hdc, 'tconn', self.target], 'connect-owned-forward', allow_failure=True)
                identity = self.shell('id -u; param get const.product.devicetype; uname -m', 'poll-identity', True)
                try:
                    validate_identity(identity, self.arch, self.device)
                except ValueError:
                    time.sleep(3)
                    continue
                if getattr(args, 'power_diagnostic_wakeup', False) and self.diagnostic_process is None:
                    self.report['test_environment']['external_keepalive'] = True
                    self.report['diagnostic_assistance'] = 'one RTC alarm and one scheduled power-shell wakeup; NOT acceptance'
                    self.shell('hilog -b D -D D002511,D002901; '
                        'echo 0 > /sys/class/rtc/rtc0/wakealarm; '
                        'echo +35 > /sys/class/rtc/rtc0/wakealarm; cat /sys/class/rtc/rtc0/wakealarm',
                        'one-owned-diagnostic-RTC-alarm')
                    self.diagnostic_log = (args.output / 'diagnostic-one-wakeup-power-history.log').open('wb')
                    # /proc/uptime includes suspended time. A single long
                    # guest sleep uses CLOCK_MONOTONIC and would remain asleep
                    # at the RTC wake; a new host HDC command loses transport
                    # when virtio-net resets. Keep one owned diagnostic reader.
                    self.diagnostic_process = subprocess.Popen([str(args.hdc), '-t', self.target, 'shell',
                        'task_diag_deadline=$(( $(cut -d. -f1 /proc/uptime) + 30 )); '
                        'while test "$(cut -d. -f1 /proc/uptime)" -lt "$task_diag_deadline"; do sleep 0.1; done; '
                        'hidumper -s 3301 -a "-a"; cat /sys/kernel/tracing/trace; power-shell wakeup; '
                        'hidumper -s 3301 -a "-a"; cat /sys/kernel/tracing/trace; '
                        'hilog -x | grep -E "C02901|C02511"'],
                        stdin=subprocess.DEVNULL, stdout=self.diagnostic_log, stderr=subprocess.STDOUT,
                        start_new_session=True)
                account = self.shell('echo "bootevent.account.ready=$(param get bootevent.account.ready)"; '
                    'hidumper -s AccountMgr -a "-os_account_infos"', 'poll-foreground-account', True)
                if all(parse_snapshot(account).values()):
                    # AccountMgr can be ready before SceneBoard publishes boot
                    # completion. Both must be observed on this same fresh VM.
                    version = self.shell('param get const.ohos.apiversion; param get const.ohos.fullname; '
                        'param get bootevent.boot.completed; bm get --udid', 'poll-actual-version-and-udid', True)
                    try:
                        self.udid = check_guest_version(version)
                    except ValueError:
                        time.sleep(3)
                        continue
                    break
                time.sleep(3)
            else:
                raise ValueError('fresh guest did not reach API26 boot completion and ready foreground account100 before timeout')
            environment['guest_identity'] = identity
            boot_id = self.shell('cat /proc/sys/kernel/random/boot_id', 'actual-boot-id').strip()
            if re.fullmatch(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', boot_id) is None:
                raise ValueError('missing actual fresh kernel boot identity')
            processes = self.command(['ps', '-axo', 'pid=,pgid=,comm='], 'actual-owned-qemu-process-group')
            candidates = []
            for line in processes.splitlines():
                fields = line.strip().split(None, 2)
                if len(fields) == 3 and fields[1] == str(self.process.pid) and 'qemu-system-' in fields[2]:
                    command = self.command(['ps', '-p', fields[0], '-o', 'command='], 'actual-own-qemu-command').strip()
                    if str(self.qmp_path) in command and str(self.directory / 'images') in command:
                        candidates.append((fields[0], fields[1], command))
            if len(candidates) != 1:
                raise ValueError('owned launch session does not contain exactly one package-bound QEMU process')
            environment.update(udid=self.udid, boot_id=boot_id, qemu_pid=int(candidates[0][0]),
                               qemu_command=candidates[0][2])
            self.report['qmp_running_state'] = self.qmp('query-status')
            if self.report['qmp_running_state'].get('running') is not True:
                raise ValueError('guest QEMU is not actually running')
            before = self.shell('pidof render_service', 'render-service-before-stability').strip()
            if re.fullmatch(r'[1-9][0-9]*', before) is None:
                raise ValueError('actual RenderService unavailable')
            if args.purpose == 'diagnostic':
                if getattr(args, 'kernel_diagnostic', None) == 'power-trace':
                    self.shell('hilog -b D -D D002511,D002901; '
                        'for trace in /sys/kernel/tracing /sys/kernel/debug/tracing; do '
                        'if [ -e "$trace/events/power/suspend_resume/enable" ]; then '
                        'echo 1 > "$trace/events/power/suspend_resume/enable"; '
                        'echo 1 > "$trace/tracing_on"; '
                        'echo __POWER_TRACE_ENABLED__; cat "$trace/events/power/suspend_resume/enable"; '
                        'break; fi; done', 'enable-owned-VM-diagnostic-power-trace', True)
                self.shell('hidumper -s 3301 -a "-a"; echo __KERNEL_POWER__; cat /sys/power/state; '
                    'cat /sys/power/autosleep; cat /proc/cmdline', 'read-only-boot-power-state', True)
                self.shell('hilog -x | grep -Ei "power.*(suspend|sleep|wake)|ForceSuspend|staS3|stpS3|StartSuspend|DoSuspend"',
                           'read-only-boot-power-history', True)
            deadline = time.monotonic() + args.stable_seconds
            while time.monotonic() < deadline:
                self.healthy()
                time.sleep(min(3, max(0, deadline - time.monotonic())))
            if getattr(args, 'power_button_after_quiet', False):
                if args.purpose != 'diagnostic' or not getattr(args, 'candidate_kernel', None):
                    raise ValueError('candidate power-button diagnosis cannot satisfy package acceptance')
                # Do not send an awake system a shutdown request. This
                # single real GPIO keypress is allowed only after the actual
                # kernel trace shows an unmatched machine_suspend begin.
                trace = (args.output / 'qemu.log').read_text(errors='replace')
                began = trace.rfind('suspend_resume: machine_suspend[1] begin')
                ended = trace.rfind('suspend_resume: machine_suspend[1] end')
                if not kernel_sleeping(trace) or (began >= 0 and began <= ended):
                    raise ValueError('kernel is not observably asleep; refusing an ambiguous power button')
                self.report['diagnostic_power_button'] = {'execute': 'system_powerdown',
                    'reply': self.qmp('system_powerdown'), 'count': 1,
                    'scope': 'actual_GPIO_key_after_observed_sleep_NOT_default_boot_acceptance'}
                time.sleep(3)
            elif args.purpose == 'acceptance':
                # A phone can legitimately sleep during a no-input interval.
                # One actual power-key wake is a regression case, not periodic
                # keepalive. Never send a power key to an observably awake VM.
                sleep_log = (args.output / 'qemu.log').read_text(errors='replace')
                if kernel_sleeping(sleep_log):
                    cycle = {'scope': 'one_real_power_key_after_observed_s2idle',
                             'execute': 'system_powerdown', 'count': 1,
                             'reply': self.qmp('system_powerdown')}
                    deadline = time.monotonic() + 30
                    while time.monotonic() < deadline:
                        self.healthy()
                        if not kernel_sleeping((args.output / 'qemu.log').read_text(errors='replace')):
                            break
                        time.sleep(0.25)
                    else:
                        raise ValueError('actual power key failed to resume packaged kernel')
                    cycle_log = args.output / 'finite-power-cycle.log'
                    cycle_log.write_text((args.output / 'qemu.log').read_text(errors='replace'))
                    cycle.update(serial_evidence=str(cycle_log), serial_sha256=checksum(cycle_log))
                    self.report['power_cycle'] = cycle
                    time.sleep(2)
            self.command([args.hdc, 'tconn', self.target], 'reconnect-owned-forward-after-quiet-stability')
            if self.shell('cat /proc/sys/kernel/random/boot_id', 'same-kernel-after-quiet-stability').strip() != boot_id:
                raise ValueError('kernel rebooted during no-input stability or power-key wake')
            if self.shell('pidof render_service', 'render-service-after-stability').strip() != before:
                raise ValueError('RenderService restarted during unassisted boot stability')
            self.healthy()
            self.report.update(status='pass', stable_seconds_without_external_keepalive=args.stable_seconds,
                               kernel_boot_id_unchanged=True,
                               ordinary_UI_and_capabilities_validated=False)
            self.save()
            return self
        except BaseException as error:
            # __exit__ is never entered if __enter__/start raises. In
            # particular, interrupting a boot must not leave its private QEMU
            # or trace process alive. Evidence-write failures must not prevent
            # cleanup either; all exceptions still propagate to the caller.
            self.report['failures'].append(str(error) or type(error).__name__)
            try:
                self.save()
            finally:
                self.close()
            raise

    def close(self):
        # start_new_session owns this process group, including a legacy
        # launcher's non-exec child. Never read a PID file or select a process
        # by name; do not kill a shared HDC server/another emulator.
        if self.diagnostic_process is not None and self.diagnostic_process.poll() is None:
            try:
                os.killpg(self.diagnostic_process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                self.diagnostic_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(self.diagnostic_process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                self.diagnostic_process.wait(timeout=10)
        if self.diagnostic_log is not None:
            self.diagnostic_log.close()
        if self.process is not None and self.process.poll() is None:
            try:
                os.killpg(self.process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(self.process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                self.process.wait(timeout=10)
        if self.qemu_log is not None:
            self.qemu_log.close()

    def __enter__(self):
        return self.start()

    def __exit__(self, *_):
        self.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--hdc', default='hdc')
    parser.add_argument('--hdc-port', type=int, default=5555)
    parser.add_argument('--accel', choices=('auto', 'hvf', 'kvm', 'tcg'), default='auto')
    parser.add_argument('--resolution', default='800x500')
    parser.add_argument('--purpose', choices=('acceptance', 'diagnostic'), default='acceptance')
    parser.add_argument('--kernel-diagnostic', choices=('verbose', 'idle-tick', 'power-trace'),
                        help='isolated diagnostic command-line only; never acceptance')
    parser.add_argument('--power-diagnostic-wakeup', action='store_true',
                        help='one diagnostic-only RTC/wakeup to retrieve the actual suspend cause')
    parser.add_argument('--candidate-kernel', type=Path, help='diagnostic only: a newly linked private power kernel')
    parser.add_argument('--candidate-kernel-evidence', type=Path)
    parser.add_argument('--power-button-after-quiet', action='store_true',
                        help='candidate diagnosis only: one GPIO power key after actual traced kernel sleep')
    parser.add_argument('--wait-seconds', type=int, default=1800)
    parser.add_argument('--stable-seconds', type=int, default=60)
    parser.add_argument('--hold', action='store_true', help='retain this owned VM until interrupted for separate diagnostics')
    args = parser.parse_args()
    if args.power_diagnostic_wakeup and (args.purpose != 'diagnostic' or args.kernel_diagnostic != 'power-trace'):
        parser.error('assisted power diagnosis requires diagnostic purpose and power-trace mode')
    if args.power_button_after_quiet and (args.purpose != 'diagnostic' or args.kernel_diagnostic not in ('power-trace', 'verbose') or
                                         args.candidate_kernel is None):
        parser.error('single power-key diagnosis requires an evidenced candidate and actual kernel suspend logging')
    if (re.fullmatch(r'[1-9][0-9]{2,3}x[1-9][0-9]{2,3}', args.resolution) is None or
            not 60 <= args.wait_seconds <= 7200 or not 30 <= args.stable_seconds <= 600):
        parser.error('resolution must be 3..4 digit WxH; wait60..7200/stability30..600 seconds')
    guest = None
    try:
        with QemuGuest(args) as guest:
            print(json.dumps({'status': 'pass', 'scope': guest.report['scope'], 'target': guest.target,
                              'udid': guest.udid, 'evidence': str(args.output / 'boot.json')}), flush=True)
            if args.hold:
                while True:
                    guest.healthy()
                    time.sleep(3)
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, KeyError, subprocess.SubprocessError, tarfile.TarError) as error:
        if guest is not None:
            guest.report['status'] = 'fail'
            guest.report['failures'].append(str(error))
            guest.save()
        print(json.dumps({'status': 'fail', 'reason': str(error)}))
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
