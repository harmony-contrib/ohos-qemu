#!/usr/bin/env python3
"""Require real typed SDK-caller results, not presence of const enums in NAPI."""
import argparse
import json
from pathlib import Path
import re

from const_enum_contracts import sha256, validate_inputs


def verify(text, inputs, run_id, arch):
    if (re.fullmatch('[0-9a-f]{32}', run_id) is None or inputs.get('run_id') != run_id
            or inputs.get('arch') != arch):
        raise ValueError('wrong fresh compiled-enum challenge or architecture')
    contracts = validate_inputs(inputs)
    expected = [('const_enum:' + row['module'] + ':' + row['name'] + ':' + member['name'], member['value'])
                for row in contracts for member in row['members']]
    expected.append(('summary', len(expected)))
    rows = [json.loads(line) for line in text.splitlines()]
    if len(rows) != len(expected):
        raise ValueError('all SDK enum members and final summary are required')
    for row, (name, value) in zip(rows, expected):
        if (not isinstance(row, dict) or set(row) != {'name', 'value', 'runId'} or row['name'] != name
                or row['runId'] != run_id or type(row['value']) is not type(value) or row['value'] != value):
            raise ValueError('failed/malformed/stale/reordered SDK constant result: ' + name)
    return {'contract_count': len(contracts), 'member_count': len(expected) - 1,
            'contracts': ['const_enum:' + row['module'] + ':' + row['name'] for row in contracts]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--results', type=Path, required=True)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--arch', choices=('arm64', 'armv7a', 'x86_64'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    # Archive streaming uses the same gate helper as the actual app runner.
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
    from verify_first_artifact_gate import checksum
    report = {'scope': 'compiled_const_enum_contracts_only', 'status': 'fail',
              'archive_sha256': checksum(args.archive), 'run_id': args.run_id, 'arch': args.arch,
              'inputs_sha256': sha256(args.inputs), 'results_sha256': sha256(args.results),
              'first_artifact_behavior_gate_passed': False, 'failures': []}
    try:
        report['result'] = verify(args.results.read_text(), json.loads(args.inputs.read_text()), args.run_id, args.arch)
        report['status'] = 'pass'
    except (ValueError, KeyError, TypeError, OSError) as error:
        report['failures'].append(str(error))
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'scope': report['scope']}))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
