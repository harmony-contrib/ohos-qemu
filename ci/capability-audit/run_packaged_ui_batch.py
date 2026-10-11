#!/usr/bin/env python3
"""Fresh-archive Arc/layout, luminance and blink regression; never full gate."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from boot_package import QemuGuest
from run_application_home_probe import run as run_home
from run_normal_hap_probe import run as run_normal, stop_previous_probe
from run_luminance_probe import run as run_luminance
from run_screen_blink_probe import run as run_blink
from run_packaged_qemu_suite import unused_port
from run_root_probe import digest
from run_with_owned_hdc import run as owned_hdc

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from power_test_policy import power_timeout, verify_restoration


def run(args):
    args.output.mkdir(parents=True, exist_ok=False)
    report = dict(status='fail', failures=[], checks={},
        scope='fresh_archive_three_UI_probes_ONLY_NOT_full_gate', first_artifact_behavior_gate_passed=False)
    guest = None
    override = False
    policy = {}
    def save(): (args.output / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    try:
        guest = QemuGuest(argparse.Namespace(archive=args.archive, output=args.output / 'boot', hdc=args.hdc,
            hdc_port=unused_port(), accel='auto', resolution='1280x800', purpose='acceptance',
            wait_seconds=1800, stable_seconds=60, kernel_diagnostic=None, power_diagnostic_wakeup=False, hold=False)).start()
        report.update(archive=str(args.archive), archive_sha256=digest(args.archive),
                      test_environment=guest.report['test_environment'])
        save()
        if run_home(argparse.Namespace(boot=args.output / 'boot/boot.json', output=args.output / 'home',
                                      hdc=args.hdc))['status'] != 'pass':
            raise ValueError('actual packaged home setup failed')
        policy['before'] = power_timeout(guest.shell('hidumper -s 3301 -a "-a"', 'ui-power-before'))
        if policy['before']['override_ms'] is not None:
            raise ValueError('cannot replace another PowerMgr client override')
        override = True
        if guest.shell('power-shell timeout -o 86400000', 'ui-power-setup').strip() != 'Override screen off time to 86400000':
            raise ValueError('finite development test override rejected')
        policy['setup'] = power_timeout(guest.shell('hidumper -s 3301 -a "-a"', 'ui-power-readback'))
        if policy['setup'] != dict(policy['before'], override_ms=86400000):
            raise ValueError('finite development override not retained')
        common = dict(archive=args.archive, sdk=args.sdk, arch=guest.arch, device=guest.device,
            boot_id=guest.report['test_environment']['boot_id'], target=guest.target, udid=guest.udid,
            hdc=args.hdc, wait_seconds=180, source_volume=os.environ.get('DOCKER_SOURCE_VOLUME', 'ohos-qemu-7_0-release-source'),
            docker_image=os.environ.get('QEMU_TEST_DOCKER_IMAGE', 'ohos-qemu-m144-build-env:7.0-release'))
        for name, runner in (('arkui-components', run_normal), ('luminance-sampler', run_luminance), ('screen-blink', run_blink)):
            guest.healthy()
            extra = dict(persona=name, boot=args.output / 'boot/boot.json') if name == 'arkui-components' else {}
            result = runner(argparse.Namespace(**common, **extra, output=args.output / name))
            path = args.output / name / 'evidence.json'
            report['checks'][name] = dict(status=result['status'], evidence=str(path), sha256=digest(path))
            if result['status'] != 'pass': report['failures'].append(name + ': ' + '; '.join(result['failures']))
            save()
            if name == 'arkui-components':
                report['ordinary_caller_cleanup'] = stop_previous_probe(
                    lambda script, label, accepted_failure=False: guest.shell(script, label))
            elif result.get('cleanup_verified') is not True:
                raise ValueError(name + ' cleanup unproven; do not reuse guest')
            guest.healthy()
            if guest.shell('cat /proc/sys/kernel/random/boot_id', name + '-boot-after').strip() != common['boot_id']:
                raise ValueError('packaged UI boot identity changed')
        if not report['failures']: report['status'] = 'pass'
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        report['failures'].append(str(error))
    finally:
        if guest is not None:
            if override:
                try:
                    guest.wake_for_interaction('ui-power-restore')
                    reply = guest.shell('power-shell timeout -r', 'ui-power-restore')
                    policy['restored'] = power_timeout(guest.shell('hidumper -s 3301 -a "-a"', 'ui-power-restored'))
                    policy['restoration'] = verify_restoration(reply, policy['before'], policy['setup'], policy['restored'])
                except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
                    report['failures'].append('owned PowerMgr restoration failed: ' + str(error))
            guest.close()
        report['power_policy'] = policy
        if report['failures']: report['status'] = 'fail'
        save()
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'sdk', 'output'): parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--owned-child', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    args.hdc = shutil.which(os.environ.get('HDC', 'hdc'))
    if args.hdc is None: parser.error('actual HDC executable required')
    if not args.owned_child:
        raise SystemExit(owned_hdc([sys.executable, Path(__file__).resolve(), *sys.argv[1:], '--owned-child'],
                                  args.output.with_name(args.output.name + '-transport'), args.hdc))
    if not os.environ.get('OHOS_HDC_SERVER_PORT') or not os.environ.get('TMPDIR', '').startswith('/tmp/oq-hdc-'):
        parser.error('private owned HDC transport required')
    result = run(args)
    print(json.dumps(dict(status=result['status'], failures=result['failures'])))
    raise SystemExit(result['status'] != 'pass')
