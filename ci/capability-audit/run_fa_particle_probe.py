#!/usr/bin/env python3
"""Build a fresh ordinary FA caller on an enclosing package-bound guest.

Does not boot a VM, grant privileges, replace libraries, or attest Stage/full
closure. The enclosing suite must independently supply same-archive Stage tests.
"""
import argparse
import json
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

from run_root_probe import digest
from run_normal_hap_probe import require_normal_identity
from verify_fa_particle_results import BUNDLE, verify

ROOT = Path(__file__).resolve().parents[2]


def process_ids(text):
    if re.fullmatch(r'[1-9][0-9]*(?:\s+[1-9][0-9]*)*', text.strip()) is None:
        raise ValueError('actual FA process IDs required')
    ids = text.split()
    if len(ids) != len(set(ids)) or len(ids) > 8:
        raise ValueError('duplicate or excessive FA process IDs')
    return ids


def verify_process(status, uid):
    rows = re.findall(r'^Uid:\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*$', status, re.M)
    if len(rows) != 1 or list(map(int, rows[0])) != [uid] * 4:
        raise ValueError('FA page/service process is not the actual ordinary caller')


def verify_page(text, nonce):
    rows = [json.loads(line.split('QEMU_FA_PAGE:', 1)[1]) for line in text.splitlines()
            if 'QEMU_FA_PAGE:' in line]
    if rows != [{'nonce': nonce, 'status': 'pass'}]:
        raise ValueError('one fresh ordinary FA page must start its own service')


def run(args):
    args.output.mkdir(parents=True, exist_ok=False)
    report = {'status': 'fail', 'persona': 'fa-particle', 'commands': [], 'failures': [],
              'scope': 'fresh_FA_constant_and_existing_service_calls_NOT_Stage_or_full_gate',
              'first_artifact_behavior_gate_passed': False, 'closed': []}
    installed = False
    target = None

    def command(argv, label, timeout=60):
        argv = list(map(str, argv))
        path = args.output / (str(len(report['commands'])).zfill(3) + '-' + label + '.log')
        record = {'argv': argv, 'log': str(path)}
        report['commands'].append(record)
        with path.open('x') as stream:
            process = subprocess.Popen(argv, stdout=stream, stderr=subprocess.STDOUT,
                                       stdin=subprocess.DEVNULL, start_new_session=True)
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                import os
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
                record.update(timed_out=True, sha256=digest(path), exit_code=process.returncode)
                raise ValueError('FA command timed out: ' + label)
        record.update(exit_code=process.returncode, sha256=digest(path))
        text = path.read_text().replace('\r', '')
        if process.returncode or '[Fail]' in text or 'Device not found or connected' in text:
            raise ValueError('FA command failed: ' + label)
        return text

    def shell(script, label):
        return command([args.hdc, '-t', target, 'shell', script], label)

    try:
        boot = json.loads(args.boot.read_text())
        environment = boot['test_environment']
        archive_sha = digest(args.archive)
        if (boot.get('status') != 'pass' or boot.get('purpose') != 'acceptance' or
                boot.get('archive_sha256') != archive_sha or environment.get('external_keepalive') is not False):
            raise ValueError('actual fresh acceptance boot of the unchanged archive required')
        target, boot_id, udid = (environment[key] for key in ('target', 'boot_id', 'udid'))
        if (re.fullmatch(r'127\.0\.0\.1:[0-9]+', target) is None or
                re.fullmatch(r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}', boot_id) is None or
                re.fullmatch(r'[a-fA-F0-9]{64}', udid) is None):
            raise ValueError('invalid enclosing guest identity')
        report.update(archive_sha256=archive_sha, boot_id=boot_id, arch=environment['guest_arch'],
                      device=environment['device_type'], target=target)
        if shell('cat /proc/sys/kernel/random/boot_id', 'boot-before').strip() != boot_id:
            raise ValueError('FA test connected to a different VM')
        expected_cpu = {'arm64': 'aarch64', 'armv7a': 'armv7l', 'x86_64': 'x86_64'}[report['arch']]
        if shell('id -u; param get const.product.devicetype; uname -m', 'guest-role').split() != [
                '0', report['device'], expected_cpu]:
            raise ValueError('wrong actual guest architecture/profile')
        # Fresh VMs must not contain this dedicated caller. Do not overwrite an
        # existing application merely because it happens to share our name.
        bundles = shell('bm dump -a', 'packages-before')
        if re.search(r'(?<![A-Za-z0-9_.])' + re.escape(BUNDLE) + r'(?![A-Za-z0-9_.])', bundles):
            raise ValueError('FA test requires an absent dedicated caller')
        project = args.output / 'project'
        command([sys.executable, Path(__file__).with_name('build_fa_particle_probe.py'),
                 '--output', project, '--sdk', args.sdk, '--hvigor-home', args.hvigor_home,
                 '--node-home', args.node_home], 'compile-fresh-FA', timeout=1800)
        inputs_path = project / 'caller-inputs.json'
        inputs = json.loads(inputs_path.read_text())
        unsigned = Path(inputs['unsigned_hap'])
        if (not unsigned.resolve().is_relative_to(project.resolve()) or unsigned.is_symlink() or
                digest(unsigned) != inputs['unsigned_hap_sha256'] or inputs['bundle'] != BUNDLE or
                inputs['model'] != 'FA' or inputs['request_permissions'] != []):
            raise ValueError('fresh compiled ordinary FA inputs changed')
        report.update(nonce=inputs['nonce'], caller_inputs=str(inputs_path),
                      caller_inputs_sha256=digest(inputs_path))
        signed = args.output / 'ordinary-fa.hap'
        command(['docker', 'run', '--rm', '--platform', 'linux/amd64',
                 '--mount', 'type=volume,src=' + args.source_volume + ',dst=/ohos,readonly',
                 '--mount', 'type=bind,src=' + str(ROOT) + ',dst=/work,readonly',
                 '--mount', 'type=bind,src=' + str(args.output.resolve()) + ',dst=/probe',
                 args.docker_image, 'python3', '/work/ci/capability-audit/sign_web_probe.py',
                 '--signer-dist', '/ohos/developtools/hapsigner/dist',
                 '--jar', '/ohos/prebuilts/ohos-sdk/linux/26.0.0/toolchains/lib/hap-sign-tool.jar',
                 '--unsigned', '/probe/' + str(unsigned.relative_to(args.output)),
                 '--output', '/probe/' + signed.name, '--bundle-name', BUNDLE, '--udid', udid,
                 '--sign-code', '1', '--fa-no-permissions'], 'sign-and-verify-FA', timeout=300)
        report['signed_hap_sha256'] = digest(signed)
        reply = command([args.hdc, '-t', target, 'install', signed], 'install-own-FA')
        if 'success' not in reply.lower():
            raise ValueError('FA installation did not succeed')
        installed = True
        identity = shell('bm dump -n ' + BUNDLE, 'ordinary-FA-identity')
        uid = require_normal_identity(identity, BUNDLE)
        identity_path = args.output / 'identity.json'
        identity_path.write_text(identity)
        report.update(identity=str(identity_path), identity_sha256=digest(identity_path))
        reply = shell('aa start -a ' + BUNDLE + '.MainAbility -b ' + BUNDLE, 'start-own-FA-page')
        if 'start ability successfully' not in reply:
            raise ValueError('ordinary FA page did not start')
        deadline = time.monotonic() + 90
        text = ''
        while time.monotonic() < deadline:
            pids = shell('pidof ' + BUNDLE, 'own-FA-PIDs').strip()
            if not pids:
                time.sleep(1)
                continue
            text = ''
            report['processes'] = []
            for pid in process_ids(pids):
                status = shell('cat /proc/' + pid + '/status', 'own-FA-UID-' + pid)
                verify_process(status, uid)
                report['processes'].append({'pid': int(pid), 'uid': uid, 'status': status})
                text += shell('hilog -x -P ' + pid, 'own-FA-log-' + pid) + '\n'
            rows = [json.loads(line.split('QEMU_FA_PARTICLE:', 1)[1]) for line in text.splitlines()
                    if 'QEMU_FA_PARTICLE:' in line]
            if any(row.get('name') in ('complete', 'exception') for row in rows):
                break
            time.sleep(1)
        raw = args.output / 'results.log'
        raw.write_text(text)
        report.update(results=str(raw), results_sha256=digest(raw))
        verify_page(text, inputs['nonce'])
        report['result'] = verify(text, inputs['nonce'], identity)
        if shell('cat /proc/sys/kernel/random/boot_id', 'boot-after').strip() != boot_id:
            raise ValueError('guest changed during FA test')
        report['status'] = 'pass'
    except Exception as error:
        report['failures'].append(type(error).__name__ + ': ' + str(error))
    finally:
        if installed:
            try:
                if shell('cat /proc/sys/kernel/random/boot_id', 'cleanup-boot').strip() != report['boot_id']:
                    raise ValueError('refusing cleanup on a different guest')
                reply = shell('aa force-stop ' + BUNDLE, 'stop-own-FA')
                if reply.strip() != 'force stop process successfully.':
                    raise ValueError('own FA cleanup not confirmed')
                report['cleanup'] = reply.strip()
            except Exception as error:
                report['failures'].append('own FA cleanup: ' + str(error))
        if report['failures']:
            report['status'] = 'fail'
        (args.output / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'boot', 'output', 'sdk', 'hvigor-home', 'node-home'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--hdc', default='hdc')
    parser.add_argument('--source-volume', default='ohos-qemu-7_0-release-source')
    parser.add_argument('--docker-image', default='ohos-qemu-m144-build-env:7.0-release')
    args = parser.parse_args()
    args.output = args.output.resolve()
    return 0 if run(args)['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
