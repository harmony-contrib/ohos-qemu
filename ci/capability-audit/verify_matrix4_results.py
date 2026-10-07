#!/usr/bin/env python3
"""Verify real typed Matrix4 arithmetic, boundaries and existing object regressions."""
import argparse
import json
import math
from pathlib import Path
import re

from run_normal_hap_probe import require_normal_identity
from run_root_probe import digest

TEMPLATE = Path(__file__).with_name('matrix4_probe.ets')
EXPECTED = {
    'identity.init': [3, -2, 13, -22, 3, -2],
    'root.copy': [7, -7, 14, -21, 7, -7],
    'root.invert': [-1, 3, 3, -2],
    'root.combine': [14, -21],
    'root.translate': [7, -7, 7, -7, 7, -7],
    'root.scale': [6, -6, 5, -10, -3, 2, 3, -2],
    'root.rotate': [0, 1, 2, 4, 3, -2, 0, -1],
    'root.transformPoint': [3, -2, 0, 0, -8, 11],
    'root.boundary.missing': [1, 3, -2],
    'root.boundary.type': [1, 3, -2],
    'root.boundary.point': [1, 3, -2],
    'object.copy': [7, -7, 14, -21, 7, -7],
    'object.invert': [-1, 3, 3, -2],
    'object.combine': [14, -21],
    'object.transforms': [6, -6, 7, -7, 0, 1, 0, 0, 3, -2],
    'repeat.isolation': [64, 0],
    'summary': [16, 0],
}


def verify_inputs(inputs, run_id, arch):
    page = Path(inputs['generated_source'])
    declaration = Path(inputs['sdk_declaration'])
    if (inputs.get('run_id') != run_id or inputs.get('arch') != arch or
            inputs.get('role') != 'ordinary_app' or inputs.get('scope') != 'real_typed_matrix4_helpers_only' or
            inputs.get('request_permissions') != [] or
            declaration.name != '@ohos.matrix4.d.ts' or not declaration.is_file() or
            digest(declaration) != inputs.get('sdk_declaration_sha256') or
            digest(TEMPLATE) != inputs.get('template_sha256') or
            digest(page) != inputs.get('generated_source_sha256') or
            page.read_text() != TEMPLATE.read_text().replace('__MATRIX_RUN_ID__', run_id)):
        raise ValueError('Matrix4 caller must match the current complete typed page and actual SDK')


def verify(text, run_id, identity_text):
    if not isinstance(run_id, str) or re.fullmatch('[0-9a-f]{32}', run_id) is None:
        raise ValueError('fresh Matrix4 challenge required')
    require_normal_identity(identity_text)
    rows = [json.loads(line) for line in text.splitlines()]
    if (len(rows) != len(EXPECTED) or any(not isinstance(row, dict) for row in rows) or
            [row.get('name') for row in rows] != list(EXPECTED)):
        raise ValueError('Matrix4 observations missing, duplicated, reordered or extra')
    for row in rows:
        wanted = EXPECTED[row['name']]
        values = row.get('values')
        if (set(row) != {'name', 'values', 'error', 'runId'} or row['runId'] != run_id or
                row['error'] != '' or not isinstance(values, list) or len(values) != len(wanted) or
                any(type(value) not in (int, float) or not math.isfinite(value) for value in values)):
            raise ValueError('Matrix4 malformed/failed/stale observation: ' + row['name'])
        # Tolerance is only for actual floating-point rotation/roundtrip error.
        # Counts and boundary flags are required exactly, not approximately.
        tolerance = 1e-4
        if (any(abs(actual - expected) > tolerance for actual, expected in zip(values, wanted)) or
                (row['name'] in ('summary', 'repeat.isolation') and values[0] != wanted[0]) or
                (row['name'].startswith('root.boundary.') and values[0] != 1) or
                (row['name'] == 'summary' and values[1] != 0)):
            raise ValueError('Matrix4 actual arithmetic/boundary differs: ' + row['name'])
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'results', 'application-identity', 'inputs', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--arch', choices=('arm64', 'armv7a', 'x86_64'), required=True)
    parser.add_argument('--run-id', required=True)
    args = parser.parse_args()
    report = {'status': 'fail', 'scope': 'actual_typed_matrix4_arithmetic_and_boundaries_only',
              'run_id': args.run_id, 'arch': args.arch, 'failures': [],
              'first_artifact_behavior_gate_passed': False}
    try:
        report.update(archive_sha256=digest(args.archive), results_sha256=digest(args.results),
                      inputs_sha256=digest(args.inputs),
                      application_identity_sha256=digest(args.application_identity))
        verify_inputs(json.loads(args.inputs.read_text()), args.run_id, args.arch)
        report['results'] = verify(args.results.read_text(), args.run_id, args.application_identity.read_text())
        report['status'] = 'pass'
    except (ValueError, OSError, KeyError, TypeError) as error:
        report['failures'].append(str(error))
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ('status', 'scope', 'failures')}))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
