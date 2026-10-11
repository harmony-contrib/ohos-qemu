#!/usr/bin/env python3
"""Concentrated real SDK build/boundary batch; never a guest acceptance report."""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

from build_insight_decorator_probe import TEMPLATES
from run_root_probe import digest
from verify_insight_decorator_build import verify

HERE = Path(__file__).resolve().parent
ERRORS = {'duplicate-name': '10110012', 'orphan-method': '10110013',
          'invalid-page': '10110017', 'invalid-form': '10110023'}


def run(sdk, output, arkdown):
    output.mkdir(parents=True, exist_ok=False)
    inputs = [HERE / name for name in ('build_always_on_vpn_probe.py',
        'build_insight_decorator_probe.py', 'verify_insight_decorator_build.py',
        'check_insight_decorator_compilation.py')]
    inputs += sorted(TEMPLATES.glob('*.ets'))
    inputs += [sdk / 'ets/api' / name for name in (
        '@ohos.app.ability.InsightIntentDecorator.d.ts', '@ohos.app.ability.insightIntent.d.ts',
        '@ohos.app.ability.InsightIntentEntryExecutor.d.ts', '@ohos.app.form.FormExtensionAbility.d.ts',
        '@ohos.app.ability.UIAbility.d.ts', '@ohos.window.d.ts')]
    inputs += [sdk / name / 'oh-uni-package.json' for name in ('ets', 'native')]
    before = {str(path): digest(path) for path in inputs}
    report = {'status': 'fail', 'scope': 'real_API26_three_ABI_compile_and_negative_boundaries_NOT_guest',
        'first_artifact_behavior_gate_passed': False, 'source_sha256': before,
        'builds': [], 'failures': []}
    cases = [(arch, 'valid', None) for arch in ('arm64', 'armv7a', 'x86_64')]
    cases += [('arm64', case, code) for case, code in ERRORS.items()]
    for arch, case, code in cases:
        nonce = secrets.token_hex(16)
        project = output / (arch + '-' + case)
        log = output / (project.name + '.log')
        argv = [sys.executable, str(HERE / 'build_insight_decorator_probe.py'),
            '--sdk', str(sdk), '--arch', arch, '--case', case, '--run-id', nonce,
            '--output', str(project), '--arkdown', arkdown]
        row = {'arch': arch, 'case': case, 'run_id': nonce, 'command': argv, 'log': str(log)}
        report['builds'].append(row)
        try:
            with log.open('x') as stream:
                child = subprocess.run(argv, env=os.environ.copy(), stdout=stream,
                                       stderr=subprocess.STDOUT, timeout=300)
            row.update(exit_code=child.returncode, log_sha256=digest(log))
            if code is None:
                if child.returncode:
                    raise ValueError('real valid compilation failed')
                row['verified_build'] = verify(project, nonce)
            else:
                if child.returncode == 0 or ('[' + code + ']') not in log.read_text():
                    raise ValueError('expected compiler boundary not enforced: ' + code)
                if (project / 'entry/build/default/outputs/default/entry-default-unsigned.hap').exists():
                    raise ValueError('rejected input unexpectedly produced a HAP')
                row['expected_diagnostic'] = code
            row['status'] = 'pass'
        except Exception as error:
            row.update(status='fail', error=type(error).__name__ + ': ' + str(error))
            report['failures'].append(project.name + ': ' + row['error'])
    report['inputs_unchanged'] = before == {str(path): digest(path) for path in inputs}
    if not report['inputs_unchanged']:
        report['failures'].append('build inputs changed during actual compiler batch')
    if not report['failures']:
        report['status'] = 'pass'
    with (output / 'evidence.json').open('x') as stream:
        stream.write(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--arkdown', default=os.environ.get('ARKDOWN', 'arkdown'))
    args = parser.parse_args()
    report = run(args.sdk.resolve(), args.output.resolve(), args.arkdown)
    print(json.dumps({'status': report['status'], 'build_count': len(report['builds']),
                     'inputs_unchanged': report['inputs_unchanged'], 'failures': report['failures']}))
    raise SystemExit(report['status'] != 'pass')
