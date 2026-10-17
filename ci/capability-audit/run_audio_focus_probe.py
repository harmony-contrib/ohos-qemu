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
from audio_capture_runtime import BOOT_SCRIPT, CleanupBootError, cleanup_boot_prefix, require_cleanup_boot
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


def stop_owned(shell, bundle, *, boot_id=None):
    if bundle not in BUNDLES:
        raise ValueError('cannot stop an application outside the two owned probe bundles')
    if boot_id is not None: require_cleanup_boot(shell, boot_id, 'focus-stop-boot-before-' + bundle)
    script = (cleanup_boot_prefix(boot_id) if boot_id is not None else '') + 'aa force-stop ' + bundle
    reply = shell(script, 'stop-owned-' + bundle, accepted_failure=True).strip()
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
            if boot_id is not None: require_cleanup_boot(shell, boot_id, 'focus-stop-boot-after-' + bundle)
            return dict(bundle=bundle, reply=reply, kernel_and_ability_absent=True,
                        scope='owned_test_lifecycle_cleanup_NOT_focus_or_permission_evidence')
        time.sleep(0.25)
    raise ValueError('owned previous application did not drain')


def cleanup_owned_applications(shell, command, hdc, target, boot_id, *, bundles=BUNDLES,
                               commands=None, receipt=None, confirmed_installed=None, host_only_reason=None):
    """Uninstall only this run's attempted HAPs after runtime evidence is saved.

    Original command receipts remain in the parent table. Observation.raw is
    Focus shell's body with its exact outer footer removed; command_index binds
    it to that original stdout/stderr pair. This is lifecycle cleanup only.
    """
    bundles = tuple(bundles)
    if not bundles or len(set(bundles)) != len(bundles) or any(b not in BUNDLES for b in bundles):
        raise ValueError('only unique attempted Focus bundles may be cleaned up')
    if not isinstance(commands, list): raise ValueError('actual Focus cleanup command receipts required')
    confirmed = tuple(bundles if confirmed_installed is None else confirmed_installed)
    if len(set(confirmed)) != len(confirmed) or not set(confirmed) <= set(bundles):
        raise ValueError('confirmed Focus installations must belong to this run')
    result = receipt if receipt is not None else {}
    result.update(scope='owned_Focus_HAP_lifecycle_cleanup_NOT_public_Stop_Release_evidence',
        boot_id=boot_id, bundles=list(bundles), confirmed_installed=list(confirmed),
        complete=False, roles=[], observations=[], uninstalls=[])
    def observe(script, label, **kwargs):
        index = len(commands) if commands is not None else None
        raw = shell(script, label, **kwargs)
        result['observations'].append(dict(script=script, label=label, command_index=index, raw=raw))
        return raw
    result['errors'] = []
    def error(stage, failure):
        result['errors'].append(dict(stage=stage, error=str(failure)))
    def boot_ok(label):
        try:
            require_cleanup_boot(observe, boot_id, label)
            return True
        except Exception as failure:
            error(label, failure)
            return False
    if host_only_reason: error('guest-identity', host_only_reason)
    guest_ok = False if host_only_reason else boot_ok('focus-application-cleanup-boot-before')
    for bundle in (bundles if guest_ok else ()):
        try:
            lifecycle = stop_owned(observe, bundle, boot_id=boot_id)
            result['roles'].append(lifecycle)
            require_cleanup_boot(observe, boot_id, 'focus-uninstall-boot-before-' + bundle)
            argv = [str(hdc), '-t', target, 'uninstall', bundle]
            index = len(commands)
            reply = command(argv, 'focus-uninstall-owned-' + bundle, accepted_failure=True)
            uninstall = dict(bundle=bundle, argv=argv, command_index=index, raw=reply)
            result['uninstalls'].append(uninstall)
            actual = commands[index] if index < len(commands) else {}
            if (actual.get('argv') != argv or type(actual.get('exit_code')) is not int or
                    actual['exit_code'] != 0 or actual.get('timed_out')):
                raise ValueError('actual owned Focus uninstall command failed: ' + bundle)
            success = (re.search(r'uninstall bundle successfully', reply, re.I) is not None and
                       re.search(r'\[Fail\]|failed', reply, re.I) is None)
            already_absent = (bundle not in confirmed and 'Error Code:10104002' in lifecycle['reply'] and
                'The application corresponding to the specified package name is not installed.' in lifecycle['reply'] and
                'code:9568386 error: uninstall missing installed bundle.' in reply)
            if hdc_failed(reply, '') or not (success or already_absent):
                raise ValueError('actual owned Focus uninstall failed: ' + bundle)
            uninstall['already_absent_after_failed_install'] = already_absent
            observe('test ! -d /data/app/el2/100/base/' + bundle + ' && test -z "$(pidof ' + bundle + ')"',
                    'focus-uninstalled-data-and-process-absent-' + bundle)
        except CleanupBootError as failure:
            error(bundle, failure)
            guest_ok = False
            break
        except Exception as failure:
            error(bundle, failure)
            # A local cleanup failure does not excuse abandoning our other HAP.
            # A changed/unknown kernel forbids all further guest operations.
            guest_ok = boot_ok('focus-cleanup-error-boot-' + bundle)
            if not guest_ok: break
    if guest_ok:
        try:
            bms = observe('bm dump -a', 'focus-cleanup-full-BMS-list')
            if 'com.ohos.' not in bms or hdc_failed(bms, '') or any(re.search(
                    r'(?<![A-Za-z0-9_.])' + re.escape(b) + r'(?![A-Za-z0-9_.])', bms) for b in bundles):
                raise ValueError('actual full BMS does not prove owned Focus bundles absent')
        except Exception as failure:
            error('BMS', failure)
            guest_ok = boot_ok('focus-cleanup-BMS-error-boot')
    if guest_ok:
        try:
            ams = observe('aa dump -a -u 100', 'focus-cleanup-full-AA-list')
            if (not re.search(r'^User ID #100\s*$', ams, re.M) or 'AppRunningRecords:' not in ams or
                    hdc_failed(ams, '') or any(re.search(r'(?<![A-Za-z0-9_.])' + re.escape(b) +
                        r'(?![A-Za-z0-9_.])', ams) for b in bundles)):
                raise ValueError('actual full AMS does not prove owned Focus sessions absent')
        except Exception as failure:
            error('AMS', failure)
            guest_ok = boot_ok('focus-cleanup-AMS-error-boot')
    if guest_ok: boot_ok('focus-application-cleanup-boot-after')
    if result['errors']:
        raise ValueError('owned Focus application cleanup failed: ' + '; '.join(r['error'] for r in result['errors']))
    result['complete'] = True
    return result


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
    guest_cleanup_lost = None
    install_attempts = []
    confirmed_installed = []
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
        report['previous_owned_cleanup'] = [stop_owned(shell, bundle, boot_id=args.boot_id) for bundle in BUNDLES]
        for role, actor in actors.items():
            require_cleanup_boot(shell, args.boot_id, 'focus-previous-uninstall-boot-before-' + role)
            command([args.hdc, '-t', args.target, 'uninstall', actor['bundle']],
                    'uninstall-only-previous-' + role, accepted_failure=True)
            require_cleanup_boot(shell, args.boot_id, 'focus-install-boot-before-' + role)
            install_attempts.append(actor['bundle'])
            reply = command([args.hdc, '-t', args.target, 'install', actor['hap_path']], 'install-fresh-' + role)
            if not re.search('success', reply, re.I) or re.search(r'\[Fail\]|failed to install', reply, re.I):
                raise ValueError('actual signed ordinary HAP installation failed')
            text = shell('bm dump -n ' + actor['bundle'], 'actual-ordinary-identity-' + role)
            path = args.output / role / 'application-identity.json';path.write_text(text)
            actor.update(uid=normal_uid(text, actor['bundle']), identity_path=str(path), identity_sha256=sha(path))
            confirmed_installed.append(actor['bundle'])
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
        if isinstance(error, CleanupBootError): guest_cleanup_lost = str(error)
        report['failures'].append(type(error).__name__ + ': ' + str(error))
        if runtime is not None:
            runtime.value['failures'].append(report['failures'][-1]);runtime.value['status'] = 'fail'
        for script, label in ([('hilog -x', 'failure-hilog'), ('aa dump -a -u 100', 'failure-abilities'),
                              ('hidumper -s 1903 -a "-C --all"', 'failure-background'),
                              ('hidumper -s 3203 -a "--active"', 'failure-notifications')]
                             if owned_boot and not guest_cleanup_lost else []):
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
        if owned_boot and install_attempts:
            cleanup = {}
            report['owned_application_cleanup'] = cleanup
            if runtime is not None: runtime.value['owned_application_cleanup'] = cleanup
            try:
                cleanup_owned_applications(shell, command, args.hdc, args.target, args.boot_id,
                    bundles=install_attempts, commands=report['commands'], receipt=cleanup,
                    confirmed_installed=confirmed_installed,
                    host_only_reason=guest_cleanup_lost or (runtime.capture.value.get('cleanup_boot_failure')
                        if runtime is not None else None))
                report['owned_bundle_cleanup'] = cleanup['roles']
                if runtime is not None:
                    runtime.value['owned_bundle_cleanup'] = cleanup['roles']
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
