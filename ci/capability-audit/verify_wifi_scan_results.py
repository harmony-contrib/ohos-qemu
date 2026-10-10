#!/usr/bin/env python3
"""Verify ordinary real scan callbacks without claiming full WLAN support."""
import argparse
import json
from pathlib import Path
import re

from run_normal_hap_probe import require_normal_identity
from run_root_probe import digest
from wifi_scan_contract import SCOPE, verify_inputs

NAMES = ('active', 'legacy-location-denial', 'generation0', 'generation1', 'retired', 'summary')


def verify(text, run_id, identity):
    if not isinstance(run_id, str) or re.fullmatch('[0-9a-f]{32}', run_id) is None:
        raise ValueError('fresh Wi-Fi scan nonce required')
    require_normal_identity(identity)
    rows = [json.loads(line) for line in text.splitlines()]
    if len(rows) != len(NAMES):
        raise ValueError('complete scan callback observations required')
    for row, name in zip(rows, NAMES):
        if (not isinstance(row, dict) or set(row) != {'runId', 'name', 'values', 'error'} or
                row['runId'] != run_id or row['name'] != name or row['error'] != '' or
                not isinstance(row['values'], list) or any(type(value) is not int for value in row['values'])):
            raise ValueError('failed, stale, reordered or malformed scan observation: ' + name)
    if rows[0]['values'] != [1] or rows[1]['values'] != [201] or rows[-1]['values'] != [5, 0]:
        raise ValueError('actual active radio, permission denial and completion required')
    for row in rows[2:4]:
        values = row['values']
        if len(values) != 3 or values[0] != 1 or values[1] != 1 or values[2] < 0:
            raise ValueError('real successful one-shot callback and scan result count required')
    if rows[4]['values'] != [1, 1]:
        raise ValueError('retired callback was invoked after unregister')
    return dict(closed=[], scope=SCOPE, observations=len(rows), callback_generations=2,
                visible_result_counts=[row['values'][2] for row in rows[2:4]],
                association_proven=False, controlled_ssid_proven=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'results', 'inputs', 'application-identity', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--arch', choices=('arm64', 'armv7a', 'x86_64'), required=True)
    args = parser.parse_args()
    report = dict(status='fail', scope=SCOPE, run_id=args.run_id, arch=args.arch,
        archive_sha256=digest(args.archive), results_sha256=digest(args.results),
        application_identity_sha256=digest(args.application_identity),
        compiled_inputs_sha256=digest(args.inputs), verifier_sha256=digest(Path(__file__)),
        first_artifact_behavior_gate_passed=False, failures=[])
    try:
        verify_inputs(json.loads(args.inputs.read_text()), args.run_id, args.arch)
        report['result'] = verify(args.results.read_text(), args.run_id, args.application_identity.read_text())
        report['status'] = 'pass'
    except (OSError, ValueError, KeyError, TypeError) as error:
        report['failures'].append(str(error))
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(status=report['status'], failures=report['failures'])))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
