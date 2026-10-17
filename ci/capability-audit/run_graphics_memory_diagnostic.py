#!/usr/bin/env python3
"""Exercise public graphics accounting in an existing suite-owned ordinary guest."""
import argparse
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import time

from build_graphics_memory_app_probe import BUNDLE
from enclosing_acceptance_guest import EnclosingAcceptanceGuest
from power_test_policy import power_timeout
from run_normal_hap_probe import require_normal_identity
from run_root_probe import (digest, require_signer_executor, TRUSTED_SIGNER_IMAGE_ID,
                            TRUSTED_SIGNER_SOURCE_VOLUME)
from verify_graphics_memory_results import verify
from graphics_memory_kernel_contract import verify_samples

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
for name in ('archive', 'boot', 'sdk', 'hdc', 'output'):
    parser.add_argument('--' + name, type=Path, required=True)
parser.add_argument('--owned-child', action='store_true')
args = parser.parse_args()
if not args.owned_child:
    parser.error('use the owning acceptance suite transport')
require_signer_executor(os.environ.get('QEMU_TEST_DOCKER_IMAGE', TRUSTED_SIGNER_IMAGE_ID),
                        os.environ.get('QEMU_TEST_SOURCE_VOLUME', TRUSTED_SIGNER_SOURCE_VOLUME))
output = args.output.resolve()
output.mkdir(exist_ok=False)
guest = EnclosingAcceptanceGuest(args.boot.resolve(), args.archive, args.hdc, output / 'guest-commands')
nonce = secrets.token_hex(16)
report = dict(status='fail', scope='ordinary_public_graphics_memory_NOT_kernel_gap_or_full_gate',
    archive_sha256=digest(args.archive), runner_sha256=digest(Path(__file__)),
    verifier_sha256=digest(Path(__file__).with_name('verify_graphics_memory_results.py')),
    kernel_verifier_sha256=digest(Path(__file__).with_name('graphics_memory_kernel_contract.py')),
    run_id=nonce, commands=[], failures=[], closed=[], first_artifact_behavior_gate_passed=False)
before = None


def command(argv, label, timeout=1800):
    result = subprocess.run(list(map(str, argv)), capture_output=True, text=True, timeout=timeout)
    path = output / (label + '.log')
    path.write_text(result.stdout + result.stderr)
    report['commands'].append(dict(argv=list(map(str, argv)), exit_code=result.returncode,
                                   log=str(path), sha256=digest(path)))
    if result.returncode or '[Fail]' in result.stdout:
        raise ValueError('graphics memory diagnostic command failed: ' + label)
    return result.stdout


try:
    guest.start()
    env = guest.env
    report.update(test_environment=env, boot_id=env['boot_id'], arch=env['guest_arch'], device=env['device_type'],
                  enclosing_boot=str(args.boot.resolve()), enclosing_boot_sha256=digest(args.boot))
    before = power_timeout(guest.shell('hidumper -s 3301 -a "-a"', 'power-before'))
    packages = guest.shell('bm dump -a', 'installed-packages-before')
    if re.search(r'(?<![A-Za-z0-9_.])' + re.escape(BUNDLE) + r'(?![A-Za-z0-9_.])', packages):
        raise ValueError('refuse to overwrite an existing graphics memory test application')
    command([sys.executable, ROOT / 'ci/capability-audit/build_graphics_memory_app_probe.py',
        '--sdk', args.sdk, '--arch', env['guest_arch'], '--run-id', nonce,
        '--arkdown', os.environ.get('ARKDOWN', 'arkdown'), '--output', output / 'project'], 'actual-SDK-build')
    command(['docker', 'run', '--rm', '--platform', 'linux/amd64',
        '--mount', 'type=volume,src=ohos-qemu-7_0-release-source,dst=/ohos,readonly',
        '--mount', 'type=bind,src=' + str(ROOT) + ',dst=/work,readonly',
        '--mount', 'type=bind,src=' + str(output) + ',dst=/probe',
        TRUSTED_SIGNER_IMAGE_ID, 'python3', '/work/ci/capability-audit/sign_web_probe.py',
        '--signer-dist', '/ohos/developtools/hapsigner/dist',
        '--jar', '/ohos/prebuilts/ohos-sdk/linux/26.0.0/toolchains/lib/hap-sign-tool.jar',
        '--unsigned', '/probe/project/entry/build/default/outputs/default/entry-default-unsigned.hap',
        '--output', '/probe/ordinary-signed.hap', '--bundle-name', BUNDLE,
        '--udid', guest.udid, '--sign-code', '1'], 'sign-ordinary-no-permissions', 300)
    installed = command([args.hdc, '-t', env['target'], 'install', output / 'ordinary-signed.hap'], 'install-ordinary')
    if re.search('success', installed, re.I) is None:
        raise ValueError('ordinary application was not installed')
    identity = guest.shell('bm dump -n ' + BUNDLE, 'actual-ordinary-identity')
    uid = require_normal_identity(identity, BUNDLE)
    (output / 'ordinary-identity.json').write_text(identity)
    kernel_samples = [guest.shell('cat /proc/process_dmabuf_info', 'kernel-before-allocations')]
    remote = '/data/app/el2/100/base/' + BUNDLE + '/files/graphics-memory-' + nonce + '-results.log'
    if guest.shell('if test -e ' + remote + '; then echo STALE; else echo ABSENT; fi', 'nonce-absent').strip() != 'ABSENT':
        raise ValueError('stale graphics memory result')
    if 'start ability successfully' not in guest.shell('aa start -a EntryAbility -b ' + BUNDLE, 'launch-ordinary'):
        raise ValueError('ordinary application did not launch')
    deadline = time.monotonic() + 180
    index = 0
    while True:
        result = guest.shell('if test -f ' + remote + '; then cat ' + remote + '; fi', 'result-' + str(index))
        (output / 'actual-results.log').write_text(result)
        kernel_samples.append(guest.shell('cat /proc/process_dmabuf_info', 'kernel-during-' + str(index)))
        index += 1
        if re.search(r'"phase"\s*:\s*(?:5|-1)', result):
            break
        if time.monotonic() >= deadline:
            raise ValueError('ordinary graphics accounting caller did not finish')
        time.sleep(0.5)
    report['result'] = verify(result, nonce, uid)
    pid = report['result']['pid']
    report['kernel_result'] = verify_samples(kernel_samples, pid, report['result']['allocation_kib'])
    if report['kernel_result']['baseline_bytes'] != report['result']['graph_kib'][0] * 1024:
        raise ValueError('public accounting baseline differs from actual kernel buffers')
    status = guest.shell('cat /proc/' + str(pid) + '/status', 'actual-process-identity')
    if re.findall(r'^Uid:\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)$', status, re.M) != [(str(uid),) * 4]:
        raise ValueError('results do not belong to the actual ordinary process')
    report.update(status='pass', actual_results_sha256=digest(output / 'actual-results.log'),
        ordinary_identity_sha256=digest(output / 'ordinary-identity.json'),
        signed_hap_sha256=digest(output / 'ordinary-signed.hap'),
        compiled_inputs_sha256=digest(output / 'project/graphicsmemory-probe-inputs.json'))
except Exception as error:
    report['failures'].append(type(error).__name__ + ': ' + str(error))
finally:
    try:
        after = power_timeout(guest.shell('hidumper -s 3301 -a "-a"', 'power-after'))
        if before is None or before != after:
            raise ValueError('enclosing power policy changed')
        if guest.shell('cat /proc/sys/kernel/random/boot_id', 'final-boot').strip() != guest.env['boot_id']:
            raise ValueError('enclosing kernel identity changed')
        report.update(power_before=before, power_after=after, power_restoration='unchanged_enclosing_policy')
    except Exception as error:
        report['failures'].append('restoration: ' + str(error))
    report.update(enclosing_guest_preserved=True, guest_commands=guest.report['commands'])
    if report['failures']:
        report['status'] = 'fail'
    (output / 'diagnostic.json').write_text(json.dumps(report, indent=2) + '\n')
raise SystemExit(0 if report['status'] == 'pass' else 1)
