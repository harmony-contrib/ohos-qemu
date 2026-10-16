#!/usr/bin/env python3
"""Run two fresh ordinary HAPs on the enclosing owned acceptance VM.

Never boots an image or changes the normal runner. Independent verification is
required before this entry point can report pass.
"""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import signal
import subprocess
import sys
import time

from audio_focus_runtime import AudioFocusRuntime, SCOPE, strict_json
from audio_capture_contract import sha
from hdc_transport import failed as hdc_failed
from media_capture_contract import BUNDLES, verify_inputs, verify_hap
from spring_loading_input import binding, require_process

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def normal_uid(text, bundle):
    prefix = bundle + ':\n'
    if text.startswith(prefix):
        text = text[len(prefix):]
    info = strict_json(text)['applicationInfo']
    uid = info.get('uid')
    if (info.get('appPrivilegeLevel') != 'normal' or info.get('isSystemApp') is not False or
            type(uid) is not int or uid // 200000 != 100 or uid % 200000 < 10000):
        raise ValueError('two non-system ordinary account-100 applications required')
    return uid


def stop_owned(shell, bundle):
    if bundle not in BUNDLES:
        raise ValueError('cannot stop an application outside the two owned probe bundles')
    reply = shell('aa force-stop ' + bundle, 'stop-owned-' + bundle, accepted_failure=True).strip()
    absent = ('error: failed to force stop process.' in reply and 'Error Code:10104002' in reply and
              'The application corresponding to the specified package name is not installed.' in reply)
    if reply != 'force stop process successfully.' and not absent:
        raise ValueError('AA did not confirm the owned test-bundle stop')
    deadline = time.monotonic() + 30
    consecutive = 0
    while time.monotonic() < deadline:
        pids = shell('focus_pids=$(pidof ' + bundle + '); if test -n "$focus_pids"; '
                     'then printf "%s\\n" "$focus_pids"; else echo ABSENT; fi', 'owned-process-drain')
        abilities = shell('aa dump -a -u 100', 'owned-ability-drain')
        if not re.search(r'^User ID #100\s*$', abilities, re.M) or 'AppRunningRecords:' not in abilities:
            raise ValueError('actual account-100 ability dump unavailable')
        matches = re.search(r'(?<![A-Za-z0-9_.])' + re.escape(bundle) + r'(?=$|[^A-Za-z0-9_.])', abilities)
        consecutive = consecutive + 1 if pids.strip() == 'ABSENT' and not matches else 0
        if consecutive == 2:
            return dict(bundle=bundle, reply=reply, kernel_and_ability_absent=True,
                        scope='owned_test_lifecycle_cleanup_NOT_focus_or_permission_evidence')
        time.sleep(0.25)
    raise ValueError('owned previous application did not drain')


def build_actor(args, command, run, role, bundle, mode):
    directory = args.output / role
    directory.mkdir()
    project = directory / 'project'
    command([sys.executable, HERE / 'build_hap_probe.py', '--media-audio-event-only',
        '--media-audio-event-mode', str(mode), '--ordinary-bundle', bundle, '--probe-run-id', run,
        '--arch', args.arch, '--sdk', args.sdk, '--udid', args.udid, '--output', project],
        'build-fresh-' + role, timeout=1800)
    inputs = project / 'media-audio-event-probe-inputs.json'
    value = verify_inputs(strict_json(inputs.read_text()))
    if (value.get('run_id') != run or value.get('mode') != mode or value.get('bundle') != bundle or
            value.get('arch') != args.arch):
        raise ValueError('actual built HAP input role/run/ABI differs')
    unsigned = project / 'entry/build/default/outputs/default/entry-default-unsigned.hap'
    signed = directory / 'ordinary-probe-signed.hap'
    docker = ['docker', 'run', '--rm', '--platform', 'linux/amd64', '--network', 'none',
        '--cpus', '1', '--memory', '2g', '--pids-limit', '256',
        '--mount', 'type=volume,src=' + args.source_volume + ',dst=/ohos,readonly',
        '--mount', 'type=bind,src=' + str(ROOT) + ',dst=/work,readonly',
        '--mount', 'type=bind,src=' + str(args.output.resolve()) + ',dst=/probe', args.docker_image]
    def mounted(path):
        return '/probe/' + path.relative_to(args.output).as_posix()
    jar = '/ohos/prebuilts/ohos-sdk/linux/26.0.0/toolchains/lib/hap-sign-tool.jar'
    command(docker + ['python3', '/work/ci/capability-audit/sign_web_probe.py',
        '--signer-dist', '/ohos/developtools/hapsigner/dist', '--jar', jar,
        '--unsigned', mounted(unsigned), '--output', mounted(signed), '--bundle-name', bundle,
        '--udid', args.udid, '--sign-code', '1'], 'sign-normal-empty-ACL-' + role, timeout=300)
    verify_hap(signed, value)
    code = ('import sys; from pathlib import Path; '
        'sys.path.insert(0,"/work/ci/capability-audit"); '
        'from sign_web_probe import verify_signed_hap; '
        'verify_signed_hap(sys.argv[1],Path(sys.argv[2]),Path(sys.argv[3]))')
    command(docker + ['python3', '-c', code, jar, mounted(signed), mounted(directory)],
            'retain-actual-signature-proof-' + role, timeout=120)
    # The signer already verifies the chain and code. Decode its actual verified
    # profile content, preserving the P7B as well as the exported ordinary ACLs.
    profile = directory / 'verified-profile.json'
    command(docker + ['openssl', 'cms', '-verify', '-inform', 'DER', '-noverify',
        '-in', mounted(directory / 'verified-profile.p7b'), '-out', mounted(profile)],
        'decode-verified-normal-profile-' + role)
    actual = strict_json(profile.read_text())
    if (actual['bundle-info']['bundle-name'] != bundle or actual['bundle-info']['apl'] != 'normal' or
            actual['bundle-info']['app-feature'] != 'hos_normal_app' or
            actual['acls']['allowed-acls'] != [] or actual['permissions']['restricted-permissions'] != [] or
            actual['debug-info']['device-ids'] != [args.udid]):
        raise ValueError('actual signed HAP profile is not normal/empty ACL/this guest')
    return dict(bundle=bundle, mode=mode, hap_path=str(signed.resolve()), hap_sha256=sha(signed),
        inputs_path=str(inputs.resolve()), inputs_sha256=sha(inputs),
        signing_profile_path=str(profile.resolve()), signing_profile_sha256=sha(profile),
        signing_p7b_path=str((directory / 'verified-profile.p7b').resolve()),
        signing_p7b_sha256=sha(directory / 'verified-profile.p7b'))


def run(args):
    args.output = args.output.resolve()
    args.archive = args.archive.resolve()
    if hasattr(args, 'boot'):
        args.boot = args.boot.resolve()
    if hasattr(args, 'sdk'):
        args.sdk = args.sdk.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    runtime = None
    owned_boot = False
    report = dict(schema_version=1, status='fail', scope=SCOPE, persona='audio-focus',
        run_id=secrets.token_hex(16), archive=str(args.archive.resolve()), target=args.target,
        arch=args.arch, device=args.device, boot_id=args.boot_id, commands=[], failures=[],
        runner_sha256=sha(Path(__file__)), first_artifact_behavior_gate_passed=False)
    report_path = args.output / 'result.json'
    def save():
        report_path.write_text(json.dumps(report, indent=2) + '\n')
    def command(argv, label, timeout=60, accepted_failure=False, diagnostic_bytes=False):
        argv = list(map(str, argv))
        stem = str(len(report['commands'])).zfill(4) + '-' + re.sub('[^A-Za-z0-9_.-]', '_', label)
        record = dict(argv=argv, label=label, exit_code=None, host_before_ns=time.time_ns())
        report['commands'].append(record);save()
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, start_new_session=True)
        timed_out = False
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGTERM)
            try:
                stdout, stderr = process.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL);stdout, stderr = process.communicate()
        for name, raw in [('stdout', stdout), ('stderr', stderr)]:
            path = args.output / (stem + '.' + name + '.bin');path.write_bytes(raw)
            record[name + '_path'], record[name + '_sha256'] = str(path), sha(path)
        record.update(exit_code=process.returncode, timed_out=timed_out, host_after_ns=time.time_ns())
        save()
        if timed_out:
            raise ValueError('actual command timed out: ' + label)
        errors = 'replace' if diagnostic_bytes else 'strict'
        out, err = stdout.decode('utf-8', errors), stderr.decode('utf-8', errors)
        if not accepted_failure and (process.returncode or argv[0] == str(args.hdc) and hdc_failed(out, err)):
            raise ValueError('actual command failed: ' + label)
        return out.replace('\r', '')
    def shell(script, label, accepted_failure=False):
        marker = '__FOCUS_EXIT_' + secrets.token_hex(16) + '__='
        text = command([args.hdc, '-t', args.target, 'shell', script +
            '; focus_rc=$?; printf "\\n' + marker + '%s\\n" "$focus_rc"'], label,
            accepted_failure=accepted_failure)
        match = re.search(r'(?:^|\n)' + marker + r'(\d+)\s*$', text)
        if not match or not accepted_failure and match.group(1) != '0':
            raise ValueError('actual guest exit status missing or nonzero: ' + label)
        return text[:match.start()].rstrip('\n')
    try:
        verifier = HERE / 'verify_audio_focus_results.py'
        if not verifier.is_file() or verifier.is_symlink():
            raise ValueError('independent audio focus verifier must be installed before running')
        report['archive_sha256'] = sha(args.archive)
        boot = strict_json(args.boot.read_text())
        env, _ = binding(boot, report['archive_sha256'], args.boot_id, args.arch, args.device, args.target)
        require_process(command(['ps', '-p', str(env['qemu_pid']), '-o', 'pid=,pgid=,command='],
                                'same-owned-QEMU-before'), env)
        saved_boot = args.output / 'acceptance-boot.json'
        saved_boot.write_text(json.dumps(boot, indent=2) + '\n')
        args.boot = saved_boot
        report.update(boot_path=str(saved_boot), boot_sha256=sha(saved_boot),
                      verifier_sha256=sha(verifier), sdk={})
        for component in ('native', 'ets'):
            path = args.sdk / component / 'oh-uni-package.json';metadata = strict_json(path.read_text())
            if (metadata.get('apiVersion') != '26' or metadata.get('platformVersion') != '26.0.0' or
                    metadata.get('releaseType') != 'Release' or
                    re.fullmatch(r'26\.0\.0\.[0-9]+', metadata.get('version', '')) is None):
                raise ValueError('actual API26 Release SDK required')
            report['sdk'][component] = dict(path=str(path.resolve()), sha256=sha(path), metadata=metadata)
        expected_cpu = {'arm64': 'aarch64', 'armv7a': 'armv7l', 'x86_64': 'x86_64'}[args.arch]
        if shell('id -u; param get const.product.devicetype; uname -m', 'actual-guest-identity').split() != [
                '0', args.device, expected_cpu]:
            raise ValueError('actual guest role/profile/ABI differs')
        if shell('cat /proc/sys/kernel/random/boot_id', 'actual-boot-before').strip() != args.boot_id:
            raise ValueError('actual guest is not the enclosing fresh acceptance boot')
        owned_boot = True
        actors = {}
        for role, bundle, mode in [('owner', BUNDLES[0], 1), ('contender', BUNDLES[1], 2)]:
            actors[role] = build_actor(args, command, report['run_id'], role, bundle, mode)
        report['previous_owned_cleanup'] = [stop_owned(shell, bundle) for bundle in BUNDLES]
        for role, actor in actors.items():
            command([args.hdc, '-t', args.target, 'uninstall', actor['bundle']],
                    'uninstall-only-previous-' + role, accepted_failure=True)
            reply = command([args.hdc, '-t', args.target, 'install', actor['hap_path']], 'install-fresh-' + role)
            if not re.search('success', reply, re.I) or re.search(r'\[Fail\]|failed to install', reply, re.I):
                raise ValueError('actual signed ordinary HAP installation failed')
            text = shell('bm dump -n ' + actor['bundle'], 'actual-ordinary-identity-' + role)
            path = args.output / role / 'application-identity.json';path.write_text(text)
            actor.update(uid=normal_uid(text, actor['bundle']), identity_path=str(path), identity_sha256=sha(path))
            remote = '/data/app/el2/100/base/' + actor['bundle'] + '/files/'
            stale = shell('if test -d ' + remote + '; then find ' + remote +
                ' -maxdepth 1 -name "audio-event-' + report['run_id'] + '-*"; fi', 'fresh-own-run-files-absent')
            if stale.strip():
                raise ValueError('stale ordinary focus result or control file')
        if actors['owner']['uid'] == actors['contender']['uid']:
            raise ValueError('actual ordinary HAP UIDs are not distinct')
        runtime = AudioFocusRuntime(args, command, shell, report, report['run_id'], args.boot_id, actors)
        runtime.prepare()
        shell('power-shell wakeup', 'single-owned-test-wakeup')
        runtime.execute()
    except Exception as error:
        report['failures'].append(type(error).__name__ + ': ' + str(error))
        if runtime is not None:
            runtime.value['failures'].append(report['failures'][-1]);runtime.value['status'] = 'fail'
        for script, label in ([('hilog -x', 'failure-hilog'), ('aa dump -a -u 100', 'failure-abilities'),
                              ('hidumper -s 1903 -a "-C --all"', 'failure-background'),
                              ('hidumper -s 3203 -a "--active"', 'failure-notifications')] if owned_boot else []):
            try:
                command([args.hdc, '-t', args.target, 'shell', script], label,
                        timeout=30, accepted_failure=True, diagnostic_bytes=True)
            except Exception as diagnostic_error:
                report.setdefault('diagnostic_errors', []).append(str(diagnostic_error))
    finally:
        if runtime is not None:
            try:
                runtime.close()
            except Exception as error:
                report['failures'].append('runtime cleanup: ' + str(error))
        if owned_boot:
            try:
                cleanup = [stop_owned(shell, bundle) for bundle in BUNDLES]
                report['owned_bundle_cleanup'] = cleanup
                if runtime is not None:
                    runtime.value['owned_bundle_cleanup'] = cleanup
            except Exception as error:
                report['failures'].append('owned application cleanup: ' + str(error))
        if runtime is not None:
            if report['failures']:
                runtime.value['status'] = 'fail'
            path = runtime.save()
            report.update(runtime=str(path), runtime_sha256=sha(path))
        save()
    if not report['failures'] and runtime is not None:
        try:
            if shell('cat /proc/sys/kernel/random/boot_id', 'actual-same-boot-after').strip() != args.boot_id:
                raise ValueError('guest boot changed during focus test')
            require_process(command(['ps', '-p', str(env['qemu_pid']), '-o', 'pid=,pgid=,command='],
                                    'same-owned-QEMU-after'), env)
            verified = args.output / 'verified-result.json'
            command([sys.executable, verifier, '--runtime', report['runtime'], '--archive', args.archive,
                     '--boot-id', args.boot_id, '--arch', args.arch, '--output', verified],
                    'independent-focus-evidence-replay', timeout=180)
            result = strict_json(verified.read_text())
            if result.get('status') != 'pass':
                raise ValueError('independent audio focus verification did not pass')
            report.update(status='pass', result=str(verified), result_sha256=sha(verified))
        except Exception as error:
            report['failures'].append(type(error).__name__ + ': ' + str(error))
    save()
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'boot', 'sdk', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    for name in ('boot-id', 'udid', 'target'):
        parser.add_argument('--' + name, required=True)
    parser.add_argument('--arch', choices=('arm64', 'armv7a', 'x86_64'), required=True)
    parser.add_argument('--device', choices=('phone', '2in1'), required=True)
    parser.add_argument('--hdc', default='hdc')
    parser.add_argument('--source-volume', default='ohos-qemu-7_0-release-source')
    parser.add_argument('--out-volume', default='ohos-qemu-7_0-release-out')
    parser.add_argument('--docker-image', default='ohos-qemu-m144-build-env:7.0-release')
    parser.add_argument('--wait-seconds', type=int, default=120)
    args = parser.parse_args()
    if (re.fullmatch('[0-9A-Fa-f]{64}', args.udid) is None or
            re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', args.boot_id) is None):
        parser.error('actual UDID and enclosing kernel boot UUID required')
    value = run(args)
    print(json.dumps(dict(status=value['status'], run_id=value['run_id'], failures=value['failures'])))
    return 0 if value['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
