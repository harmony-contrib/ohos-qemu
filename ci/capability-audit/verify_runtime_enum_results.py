#!/usr/bin/env python3
"""Verify complete enum collection, closing only exact typed + native values."""
import argparse
import json
from pathlib import Path
import re

from runtime_enum_contracts import SCOPE, sha256, verify_inputs


def exact_values(actual, wanted):
    return isinstance(actual, list) and len(actual) == len(wanted) and all(
        type(a) is type(b) and a == b for a, b in zip(actual, wanted))


def verified_native(native, wanted):
    count = len(wanted)
    expected_types = [3 if type(value) is int else 4 for value in wanted]
    return (isinstance(native, dict) and set(native) == {'values', 'statuses', 'types', 'own', 'exception'} and
        exact_values(native['values'], wanted) and exact_values(native['statuses'], [0] * (10 + 4 * count)) and
        native['types'] in ([6, 6] + expected_types, [6, 7] + expected_types,
                           [7, 6] + expected_types, [7, 7] + expected_types) and
        all(type(value) is int for value in native['types']) and
        exact_values(native['own'], [True] * (1 + count)) and native['exception'] is False)


def verify(text, contracts, run_id, identity):
    from run_normal_hap_probe import require_normal_identity
    require_normal_identity(identity)
    if not isinstance(run_id, str) or re.fullmatch('[0-9a-f]{32}', run_id) is None or not contracts:
        raise ValueError('fresh complete regular-enum challenge required')
    lines = text.splitlines()
    if len(lines) != len(contracts) + 1:
        raise ValueError('every original compiler-resolved enum and final summary required')
    summary = json.loads(lines[-1])
    if (summary != {'runId': run_id, 'summary': len(contracts)} or type(summary['summary']) is not int):
        raise ValueError('stale or incomplete enum collection summary')
    closed, unresolved = [], []
    for line, contract in zip(lines[:-1], contracts):
        row = json.loads(line)
        if (not isinstance(row, dict) or set(row) != {'runId', 'module', 'name', 'values', 'typedException', 'native'} or
            row['runId'] != run_id or row['module'] != contract['module'] or row['name'] != contract['name'] or
            type(row['typedException']) is not bool or not isinstance(row['values'], list) or
            not isinstance(row['native'], dict) or set(row['native']) != {'values', 'statuses', 'types', 'own', 'exception'}):
            raise ValueError('malformed/reordered/missing/stale actual enum observation')
        native = row['native']
        if (any(not isinstance(native[key], list) for key in ('values', 'statuses', 'types', 'own')) or
                any(type(value) is not int or value < 0 for value in native['statuses']) or
                any(type(value) is not int or not 0 <= value <= 9 for value in native['types']) or
                any(type(value) is not bool for value in native['own']) or type(native['exception']) is not bool):
            raise ValueError('invalid actual NAPI enum observations')
        identifier = 'arkts_export:' + contract['module'] + ':' + contract['name']
        wanted = [member['value'] for member in contract['members']]
        if not row['typedException'] and exact_values(row['values'], wanted) and verified_native(native, wanted):
            closed.append({'contract': identifier, 'member_count': len(wanted)})
        else:
            unresolved.append(identifier)
    return {'closed': closed, 'unresolved': unresolved,
            'collection_complete': True, 'not_claimed': 'associated_hardware_provider_or_service_behavior'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'results', 'inputs', 'application-identity', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--arch', choices=('arm64', 'armv7a', 'x86_64'), required=True)
    args = parser.parse_args()
    report = {'status': 'fail', 'scope': SCOPE, 'archive_sha256': sha256(args.archive), 'run_id': args.run_id,
        'arch': args.arch, 'inputs_sha256': sha256(args.inputs), 'results_sha256': sha256(args.results),
        'application_identity_sha256': sha256(args.application_identity), 'failures': [],
        'first_artifact_behavior_gate_passed': False}
    try:
        contracts = verify_inputs(json.loads(args.inputs.read_text()), args.run_id, args.arch)
        report['results'] = verify(args.results.read_text(), contracts, args.run_id, args.application_identity.read_text())
        report['status'] = 'pass'  # Collection only; each absent/wrong enum remains unresolved.
    except (ValueError, OSError, KeyError, TypeError) as error:
        report['failures'].append(str(error))
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'scope': SCOPE}))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
