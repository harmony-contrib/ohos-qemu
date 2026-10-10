#!/usr/bin/env python3
"""Read-only thermal callback proof; cannot alone close the HDI/backend gap."""
import argparse
import json
from pathlib import Path
import re

from thermal_contract import SCOPE, verify_inputs
from run_normal_hap_probe import require_normal_identity
from run_root_probe import digest
from verify_thermal_backend import verify_capture

EXPECTED = {'levels': [0, 0, 0, 7], 'generation0': [0, 0, 1, 1],
            'generation1': [0, 0, 1, 1], 'generation2': [0, 0, 1, 1],
            'generation3': [0, 0, 1, 1], 'retired': [1, 1, 1, 1], 'summary': [6, 0]}


def verify(text, run_id, identity):
    if not isinstance(run_id, str) or re.fullmatch('[0-9a-f]{32}', run_id) is None:
        raise ValueError('fresh thermal nonce required')
    require_normal_identity(identity)
    rows = [json.loads(line) for line in text.splitlines()]
    if len(rows) != len(EXPECTED):
        raise ValueError('complete thermal observations required')
    for row, (name, values) in zip(rows, EXPECTED.items()):
        if (not isinstance(row, dict) or set(row) != {'runId', 'name', 'values', 'error'} or
                row['runId'] != run_id or row['name'] != name or row['error'] != '' or
                row['values'] != values or any(type(value) is not int for value in row['values'])):
            raise ValueError('failed, stale, reordered or malformed thermal observation: ' + name)
    return {'closed': [], 'scope': SCOPE, 'observations': len(rows), 'generations': 4,
            'modern_callbacks': 2, 'legacy_callbacks': 2, 'hot_transitions_proven': False}


def verify_evidence(document, archive_sha, boot_id, arch):
    if (document.get('status') != 'pass' or document.get('persona') != 'thermal' or
            document.get('archive_sha256') != archive_sha or document.get('boot_id') != boot_id or
            document.get('arch') != arch or document.get('failures') != [] or
            document.get('first_artifact_behavior_gate_passed') is not False):
        raise ValueError('thermal evidence must belong to this actual package/boot/architecture')
    result_path = Path(document.get('result', ''))
    if not result_path.is_absolute() or result_path.name != 'verified-result.json':
        raise ValueError('explicit thermal result required')
    root = result_path.parent
    files = {'result': result_path, 'raw_results': root / 'results.log',
             'ordinary_identity': root / 'application-identity.json', 'hap': root / 'ordinary-probe-signed.hap',
             'compiled_contract_inputs': root / 'project/thermal-probe-inputs.json',
             'thermal_backend': root / 'thermal-backend.json'}
    for key, path in files.items():
        if path.is_symlink() or not path.is_file() or digest(path) != document.get(key + '_sha256'):
            raise ValueError('actual thermal evidence changed: ' + key)
    value = json.loads(result_path.read_text())
    if (value.get('status') != 'pass' or value.get('scope') != SCOPE or value.get('failures') != [] or
            value.get('archive_sha256') != archive_sha or value.get('boot_id') != boot_id or
            value.get('arch') != arch or value.get('run_id') != document.get('run_id') or
            value.get('first_artifact_behavior_gate_passed') is not False or
            value.get('verifier_sha256') != digest(Path(__file__))):
        raise ValueError('thermal summary is stale or belongs to another run')
    for field, key in (('results_sha256', 'raw_results'), ('application_identity_sha256', 'ordinary_identity'),
                       ('compiled_inputs_sha256', 'compiled_contract_inputs'), ('backend_sha256', 'thermal_backend')):
        if value.get(field) != digest(files[key]):
            raise ValueError('thermal verifier did not consume captured evidence')
    verify_inputs(json.loads(files['compiled_contract_inputs'].read_text()), document['run_id'], arch)
    identity = files['ordinary_identity'].read_text()
    actual = verify(files['raw_results'].read_text(), document['run_id'], identity)
    backend = verify_capture(json.loads(files['thermal_backend'].read_text()), archive_sha, boot_id, document['run_id'])
    if (actual != value.get('result') or backend != value.get('backend') or
            require_normal_identity(identity) != document.get('ordinary_uid')):
        raise ValueError('thermal summary differs from real backend/ordinary-app observations')
    return {'callbacks': actual, 'backend': backend, 'closed': []}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'results', 'inputs', 'application-identity', 'backend', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--boot-id', required=True)
    parser.add_argument('--arch', choices=('arm64', 'armv7a', 'x86_64'), required=True)
    args = parser.parse_args()
    report = {'status': 'fail', 'scope': SCOPE, 'run_id': args.run_id, 'boot_id': args.boot_id, 'arch': args.arch,
        'archive_sha256': digest(args.archive), 'results_sha256': digest(args.results),
        'application_identity_sha256': digest(args.application_identity),
        'compiled_inputs_sha256': digest(args.inputs), 'verifier_sha256': digest(Path(__file__)),
        'backend_sha256': digest(args.backend),
        'first_artifact_behavior_gate_passed': False, 'failures': []}
    try:
        verify_inputs(json.loads(args.inputs.read_text()), args.run_id, args.arch)
        report['result'] = verify(args.results.read_text(), args.run_id, args.application_identity.read_text())
        report['backend'] = verify_capture(json.loads(args.backend.read_text()), report['archive_sha256'],
                                           args.boot_id, args.run_id)
        report['status'] = 'pass'
    except (OSError, ValueError, KeyError, TypeError) as error:
        report['failures'].append(str(error))
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'failures': report['failures']}))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
