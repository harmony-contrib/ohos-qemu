#!/usr/bin/env python3
"""Actual Curve strings, real interpolation, clamping and independent-object checks."""
import argparse
import json
import math
from pathlib import Path
import re
import sys

from curve_contract import PRESETS, ROOT, SCOPE, TIMES, verify_inputs
sys.path.insert(0, str(ROOT / 'ci/capability-audit'))
from run_normal_hap_probe import require_normal_identity
from run_root_probe import digest
from verify_runtime_enum_results import verified_native


def cubic(a, b, fraction):
    return 3 * a * (1 - fraction) ** 2 * fraction + 3 * b * (1 - fraction) * fraction ** 2 + fraction ** 3


def bezier(points, time):
    if time <= 0:
        return 0.
    if time >= 1:
        return 1.
    low, high = 0., 1.
    for _ in range(60):
        middle = (low + high) / 2
        if cubic(points[0], points[2], middle) < time:
            low = middle
        else:
            high = middle
    return cubic(points[1], points[3], (low + high) / 2)


def finite_values(value, count):
    return (isinstance(value, list) and len(value) == count and
            all(type(item) in (int, float) and math.isfinite(item) for item in value))


def verify(text, run_id, identity):
    require_normal_identity(identity)
    if not isinstance(run_id, str) or re.fullmatch('[0-9a-f]{32}', run_id) is None:
        raise ValueError('fresh Curve challenge required')
    rows = [json.loads(line) for line in text.splitlines()]
    names = ['members'] + ['generation.' + str(generation) + '.' + name
        for generation in range(2) for name, _, _ in PRESETS] + ['summary']
    keys = {'runId', 'name', 'typed', 'native', 'values', 'reference', 'isolated', 'repeats', 'repeatError', 'error'}
    if len(rows) != len(names) or [row.get('name') for row in rows] != names:
        raise ValueError('all original members and two real preset generations required')
    for row in rows:
        if (set(row) != keys or row['runId'] != run_id or row['error'] != '' or
            type(row['isolated']) is not bool or type(row['repeats']) is not int or
            type(row['repeatError']) not in (int, float) or not math.isfinite(row['repeatError'])):
            raise ValueError('malformed/stale/failed Curve result')
    member = rows[0]
    strings = [row[1] for row in PRESETS]
    if (member['typed'] != strings or not verified_native(member['native'], strings) or
        member['values'] != [] or member['reference'] != [] or member['isolated'] is not False or
        member['repeats'] != 0 or member['repeatError'] != 0):
        raise ValueError('Curve requires every real typed AND native string/own member')
    for index, row in enumerate(rows[1:-1]):
        points = PRESETS[index % len(PRESETS)][2]
        if (row['typed'] != [] or row['native'] is not None or row['isolated'] is not True or
            row['repeats'] != 32 or not 0 <= row['repeatError'] <= 1e-5 or
            not finite_values(row['values'], len(TIMES)) or not finite_values(row['reference'], len(TIMES))):
            raise ValueError('real independent preset factories/repetitions required')
        for values in (row['values'], row['reference']):
            if values[0] != values[1] or values[-1] != values[-2]:
                raise ValueError('actual input clamp must equal actual endpoint interpolation')
            for time, actual in zip(TIMES, values):
                clamped = min(1., max(0., time))
                if points is None:
                    lower = upper = clamped
                else:
                    # Existing native CubicCurve stops at x residual 0.001;
                    # independently bound its y, including degenerate endpoints.
                    # This does NOT claim exact mathematical endpoint values.
                    lower = bezier(points, clamped - .001001)
                    upper = bezier(points, clamped + .001001)
                if not lower - 1e-5 <= actual <= upper + 1e-5:
                    raise ValueError('actual interpolation violates independent Bezier residual bounds')
        if any(abs(actual - reference) > 1e-5 for actual, reference in zip(row['values'], row['reference'])):
            raise ValueError('typed preset differs from the actual corresponding real cubic/linear factory')
    summary = rows[-1]
    if (summary['values'] != [26, 0] or any(type(value) is not int for value in summary['values']) or
        summary['typed'] != [] or summary['native'] is not None or summary['reference'] != [] or
        summary['isolated'] is not False or summary['repeats'] != 0 or summary['repeatError'] != 0):
        raise ValueError('all actual Curve generations must finish without an error')
    return {'member_count': 13, 'preset_generations': 26, 'repeats_per_generation': 32,
            'actual_typed_native_string_contract': True, 'actual_clamp_and_independent_objects': True,
            'independent_native_x_residual_bounds': .001,
            'closed': ['arkts_export:@ohos.curves:Curve'],
            'not_claimed': 'exact_mathematical_Cubic_endpoints_or_animation_frame_scheduling'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'results', 'inputs', 'application-identity', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--arch', choices=('arm64', 'armv7a', 'x86_64'), required=True)
    args = parser.parse_args()
    report = {'status': 'fail', 'scope': SCOPE, 'run_id': args.run_id, 'arch': args.arch,
        'verifier_sha256': digest(Path(__file__)),
        'first_artifact_behavior_gate_passed': False, 'failures': []}
    try:
        report.update(archive_sha256=digest(args.archive), results_sha256=digest(args.results),
            inputs_sha256=digest(args.inputs), application_identity_sha256=digest(args.application_identity))
        verify_inputs(json.loads(args.inputs.read_text()), args.run_id, args.arch)
        report['results'] = verify(args.results.read_text(), args.run_id, args.application_identity.read_text())
        report['status'] = 'pass'
    except (OSError, ValueError, KeyError, TypeError) as error:
        report['failures'].append(str(error))
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    return 0 if report['status'] == 'pass' else 1


def verify_evidence(document, root, archive_sha, boot_id):
    root = Path(root)
    run_id, arch = document.get('run_id'), document.get('arch')
    if (document.get('status') != 'pass' or document.get('persona') != 'curve' or
            document.get('archive_sha256') != archive_sha or document.get('boot_id') != boot_id or
            arch not in ('arm64', 'armv7a', 'x86_64')):
        raise ValueError('actual Curve factories were not executed on this package and kernel boot')
    paths = {'result': root / 'verified-result.json', 'raw_results': root / 'results.log',
        'ordinary_identity': root / 'application-identity.json',
        'compiled_contract_inputs': root / 'project/curve-probe-inputs.json'}
    for key, path in paths.items():
        if (path.is_symlink() or not path.is_file() or digest(path) != document.get(key + '_sha256') or
                key in ('result', 'compiled_contract_inputs') and document.get(key) != str(path)):
            raise ValueError('original Curve caller/results/ordinary identity changed or escaped')
    value = json.loads(paths['result'].read_text())
    if (value.get('status') != 'pass' or value.get('scope') != SCOPE or value.get('run_id') != run_id or
            value.get('arch') != arch or value.get('archive_sha256') != archive_sha or
            value.get('verifier_sha256') != digest(Path(__file__)) or
            value.get('results_sha256') != digest(paths['raw_results']) or
            value.get('application_identity_sha256') != digest(paths['ordinary_identity']) or
            value.get('inputs_sha256') != digest(paths['compiled_contract_inputs'])):
        raise ValueError('Curve verification requires all unchanged original inputs and current verifier')
    inputs = json.loads(paths['compiled_contract_inputs'].read_text())
    if inputs.get('generated_source') != str(root / 'project/entry/src/main/ets/pages/Index.ets'):
        raise ValueError('Curve source escaped the actual fresh compiled caller project')
    verify_inputs(inputs, run_id, arch)
    result = verify(paths['raw_results'].read_text(), run_id, paths['ordinary_identity'].read_text())
    if value.get('results') != result:
        raise ValueError('Curve closure differs from actual native/typed interpolation results')
    return result


if __name__ == '__main__':
    raise SystemExit(main())
