#!/usr/bin/env python3
"""Validate one packaged archive through ordinary public C++/ArkTS kernel traces."""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
for name in ('archive', 'output', 'sdk', 'hdc'):
    parser.add_argument('--' + name, type=Path, required=True)
parser.add_argument('--owned-child', action='store_true', help=argparse.SUPPRESS)
parser.add_argument('--boot', type=Path, help='Use the enclosing acceptance guest; do not boot, stop or change its power policy')
args = parser.parse_args()
if args.boot and not args.owned_child:
    parser.error('--boot requires the enclosing suite transport (--owned-child)')
ARCHIVE, OUTPUT, SDK, HDC = args.archive.resolve(), args.output.resolve(), args.sdk.resolve(), args.hdc.resolve()
BASE = OUTPUT.parent
BOOT_INPUTS = ROOT  # Acceptance boot verifies this checkout matches the packaged frozen inputs.
BUNDLE = 'org.harmonycontrib.hitraceaudit'
os.environ.update(LC_ALL='en_US.UTF-8', LC_CTYPE='en_US.UTF-8', LANG='en_US.UTF-8')
sys.path.insert(0, str(BOOT_INPUTS / 'ci/capability-audit'))
from boot_package import QemuGuest, checksum
from power_test_policy import power_timeout, verify_restoration
from run_with_owned_hdc import run as isolated_run
sys.path.insert(0, str(ROOT / 'ci/capability-audit'))
from hitrace_kernel_contract import trace_configuration, verify_restored_configuration, verify_rows, verify_trace
from run_normal_hap_probe import require_normal_identity
from run_root_probe import require_signer_executor, TRUSTED_SIGNER_IMAGE_ID, TRUSTED_SIGNER_SOURCE_VOLUME
from hitrace_failure_snapshot import capture as capture_failure

require_signer_executor(os.environ.get('QEMU_TEST_DOCKER_IMAGE', TRUSTED_SIGNER_IMAGE_ID),
                        os.environ.get('QEMU_TEST_SOURCE_VOLUME', TRUSTED_SIGNER_SOURCE_VOLUME))

if not args.owned_child:
    BASE.mkdir(parents=True, exist_ok=True)
    assert shutil.disk_usage(BASE).free >= 12 * 1024**3
    raise SystemExit(isolated_run([sys.executable, str(Path(__file__).resolve()), *sys.argv[1:], '--owned-child'],
        OUTPUT.with_name(OUTPUT.name + '-transport'), HDC))
assert ARCHIVE.is_file() and not ARCHIVE.is_symlink()
OUTPUT.mkdir(exist_ok=False)
with socket.socket() as reservation:
    reservation.bind(('127.0.0.1', 0))
    port = reservation.getsockname()[1]
if args.boot:
    from enclosing_acceptance_guest import EnclosingAcceptanceGuest
    guest = EnclosingAcceptanceGuest(args.boot, ARCHIVE, HDC, OUTPUT / 'guest-commands')
else:
    guest = QemuGuest(argparse.Namespace(archive=ARCHIVE, output=OUTPUT / 'boot', hdc=str(HDC),
        hdc_port=port, accel='auto', resolution='1280x800', purpose='acceptance', wait_seconds=1800,
        stable_seconds=60, kernel_diagnostic=None, power_diagnostic_wakeup=False, hold=False))
nonce = secrets.token_hex(16)
report = dict(status='fail', scope='fresh_archive_ordinary_Cxx_ArkTS_kernel_trace_NOT_all_API_or_full_gate',
    run_id=nonce, archive=str(ARCHIVE), archive_sha256=checksum(ARCHIVE), runner_sha256=checksum(Path(__file__)),
    verifier_sha256=checksum(ROOT / 'ci/capability-audit/hitrace_kernel_contract.py'),
    closed=[], first_artifact_behavior_gate_passed=False, failures=[], commands=[])
override = tracing = False
before = setup = trace_before = None
remote = '/data/app/el2/100/base/' + BUNDLE + '/files/hitrace-' + nonce + '-results.log'

def command(argv, label, timeout=1800):
    result = subprocess.run(list(map(str, argv)), capture_output=True, text=True, timeout=timeout)
    log = OUTPUT / (label + '.log')
    log.write_text(result.stdout + result.stderr)
    report['commands'].append(dict(argv=list(map(str, argv)), exit_code=result.returncode,
        log=str(log), sha256=checksum(log)))
    if result.returncode or '[Fail]' in result.stdout:
        raise ValueError('actual diagnostic command failed: ' + label)
    return result.stdout

def trace_state(label):
    text = guest.shell('cat /sys/kernel/tracing/tracing_on /sys/kernel/tracing/current_tracer '
        '/sys/kernel/tracing/buffer_size_kb /sys/kernel/tracing/trace_clock; '
        'param get debug.hitrace.tags.enableflags; param get debug.hitrace.app_pid', label)
    return trace_configuration(text)

try:
    guest.start()
    env = guest.report['test_environment']
    report['test_environment'] = env
    report.update(boot_id=env['boot_id'], arch=env['guest_arch'], device=env['device_type'])
    if not args.boot:
        command([sys.executable, BOOT_INPUTS / 'ci/capability-audit/run_application_home_probe.py',
            '--boot', OUTPUT / 'boot/boot.json', '--output', OUTPUT / 'home', '--hdc', HDC], 'actual-home')
    else:
        report.update(enclosing_boot=str(args.boot.resolve()), enclosing_boot_sha256=checksum(args.boot))
    before = power_timeout(guest.shell('hidumper -s 3301 -a "-a"', 'power-before'))
    if not args.boot:
        assert before['override_ms'] is None
        override = True
        assert guest.shell('power-shell timeout -o 86400000', 'power-setup').strip() == 'Override screen off time to 86400000'
        setup = power_timeout(guest.shell('hidumper -s 3301 -a "-a"', 'power-confirm'))
        assert setup == dict(before, override_ms=86400000)
    packages = guest.shell('bm dump -a', 'installed-packages-before')
    if re.search(r'(?<![A-Za-z0-9_.])' + re.escape(BUNDLE) + r'(?![A-Za-z0-9_.])', packages):
        raise ValueError('dedicated trace caller already installed; refuse to overwrite')
    command([sys.executable, ROOT / 'ci/capability-audit/build_hitrace_app_probe.py', '--sdk', SDK,
        '--arch', env['guest_arch'], '--run-id', nonce, '--arkdown', os.environ.get('ARKDOWN', 'arkdown'),
        '--output', OUTPUT / 'project'], 'build-actual-SDK-callers')
    command(['docker', 'run', '--rm', '--platform', 'linux/amd64',
        '--mount', 'type=volume,src=ohos-qemu-7_0-release-source,dst=/ohos,readonly',
        '--mount', 'type=bind,src=' + str(ROOT) + ',dst=/work,readonly',
        '--mount', 'type=bind,src=' + str(OUTPUT) + ',dst=/probe',
        TRUSTED_SIGNER_IMAGE_ID, 'python3', '/work/ci/capability-audit/sign_web_probe.py',
        '--signer-dist', '/ohos/developtools/hapsigner/dist',
        '--jar', '/ohos/prebuilts/ohos-sdk/linux/26.0.0/toolchains/lib/hap-sign-tool.jar',
        '--unsigned', '/probe/project/entry/build/default/outputs/default/entry-default-unsigned.hap',
        '--output', '/probe/ordinary-signed.hap', '--bundle-name', BUNDLE,
        '--udid', guest.udid, '--sign-code', '1'], 'sign-ordinary-no-permissions', 300)
    installed = command([HDC, '-t', env['target'], 'install', OUTPUT / 'ordinary-signed.hap'], 'install-ordinary')
    assert re.search('success', installed, re.I)
    identity = guest.shell('bm dump -n ' + BUNDLE, 'actual-ordinary-identity')
    uid = require_normal_identity(identity, BUNDLE)
    (OUTPUT / 'ordinary-identity.json').write_text(identity)
    trace_before = trace_state('trace-before')
    page_sizes = set(re.findall(r'^KernelPageSize:\s+([0-9]+) kB$',
        guest.shell('cat /proc/self/smaps', 'actual-kernel-page-size'), re.M))
    assert page_sizes == {'4'}
    report['actual_kernel_page_size'] = 4096
    assert trace_before['on'] == '0' and trace_before['tags'] == '0' and trace_before['pid'] == '-1'
    report['trace_before'] = trace_before
    tracing = True
    guest.shell('hitrace --trace_begin -b 4096 app', 'owned-public-trace-start')
    actual = trace_state('trace-enabled')
    assert actual['on'] == '1' and int(actual['tags']) & (1 << 62)
    report['trace_enabled'] = actual
    assert guest.shell('if test -e ' + remote + '; then echo STALE; else echo ABSENT; fi', 'nonce-absent').strip() == 'ABSENT'
    reply = guest.shell('aa start -a EntryAbility -b ' + BUNDLE, 'launch-real-ordinary-app')
    assert 'start ability successfully' in reply
    deadline = time.monotonic() + 90
    while True:
        result = guest.shell('if test -f ' + remote + '; then cat ' + remote + '; fi', 'read-own-result-' + str(time.monotonic_ns()))
        if '"summary"' in result or '"failed"' in result:
            break
        if time.monotonic() >= deadline:
            raise ValueError('ordinary trace caller did not finish')
        time.sleep(1)
    (OUTPUT / 'actual-results.log').write_text(result)
    guest.shell('echo 0 > /sys/kernel/tracing/tracing_on', 'freeze-owned-capture')
    trace = guest.shell('cat /sys/kernel/tracing/trace', 'actual-kernel-trace')
    (OUTPUT / 'actual-kernel-trace.log').write_text(trace)
    pid, tid = verify_rows(result, nonce, uid)
    assert f'Uid:\t{uid}\t{uid}\t{uid}\t{uid}' in guest.shell('cat /proc/' + str(pid) + '/task/' + str(tid) + '/status', 'actual-kernel-thread-identity')
    report['result'] = verify_trace(trace, nonce, pid, tid)
    assert guest.shell('cat /proc/sys/kernel/random/boot_id', 'final-same-boot').strip() == env['boot_id']
    report.update(compiled_inputs_sha256=checksum(OUTPUT / 'project/hitrace-probe-inputs.json'),
                  signed_hap_sha256=checksum(OUTPUT / 'ordinary-signed.hap'))
    report.update(status='pass', actual_results_sha256=checksum(OUTPUT / 'actual-results.log'),
        kernel_trace_sha256=checksum(OUTPUT / 'actual-kernel-trace.log'), ordinary_identity_sha256=checksum(OUTPUT / 'ordinary-identity.json'))
except Exception as error:
    report['failures'].append(type(error).__name__ + ': ' + str(error))
    try:
        if guest.shell('cat /proc/sys/kernel/random/boot_id', 'failure-same-boot').strip() != report['boot_id']:
            raise ValueError('failure capture refused a changed guest kernel')
        report['failure_snapshot'] = capture_failure(guest.shell, remote)
    except Exception as diagnostic_error:
        report['diagnostic_error'] = str(diagnostic_error)
finally:
    if tracing:
        try:
            guest.shell('hitrace --trace_finish_nodump', 'finish-owned-public-trace')
            guest.shell('echo ' + trace_before['buffer'] + ' > /sys/kernel/tracing/buffer_size_kb; '
                'echo ' + trace_before['clock'] + ' > /sys/kernel/tracing/trace_clock; '
                'param set debug.hitrace.tags.enableflags ' + trace_before['tags'] + '; '
                'param set debug.hitrace.app_pid ' + trace_before['pid'], 'restore-owned-trace-settings')
            report['trace_restored'] = trace_state('trace-restored')
            report['trace_restoration'] = verify_restored_configuration(trace_before,
                report['trace_restored'], report['actual_kernel_page_size'], env['guest_arch'])
        except Exception as error:
            report['failures'].append('trace restoration: ' + str(error))
    if override:
        try:
            reply = guest.shell('power-shell timeout -r', 'power-restore')
            restored = power_timeout(guest.shell('hidumper -s 3301 -a "-a"', 'power-restored'))
            report['power_restoration'] = verify_restoration(reply, before, setup, restored)
        except Exception as error:
            report['failures'].append('power restoration: ' + str(error))
    if args.boot and before is not None:
        try:
            restored = power_timeout(guest.shell('hidumper -s 3301 -a "-a"', 'enclosing-power-unchanged'))
            if restored != before:
                raise ValueError('enclosing power policy changed')
            if guest.shell('cat /proc/sys/kernel/random/boot_id', 'enclosing-final-boot').strip() != env['boot_id']:
                raise ValueError('enclosing guest changed during restoration')
            report.update(power_before=before, power_after=restored, power_restoration='unchanged_enclosing_policy')
        except Exception as error:
            report['failures'].append('enclosing guest restoration: ' + str(error))
    guest.close()
    if args.boot:
        report['enclosing_guest_preserved'] = True
        report['guest_commands'] = guest.report['commands']
    else:
        report['disposable_guest_closed'] = guest.process is None or guest.process.poll() is not None
    if report['failures']:
        report['status'] = 'fail'
    (OUTPUT / 'diagnostic.json').write_text(json.dumps(report, indent=2) + '\n')
print(report['status'])
raise SystemExit(0 if report['status'] == 'pass' else 1)
