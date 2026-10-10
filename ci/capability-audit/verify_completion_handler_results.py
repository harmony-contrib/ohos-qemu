#!/usr/bin/env python3
"""Validate real constructor/field observations, never component-start success."""
import argparse
import json
from pathlib import Path
import re

from completion_handler_contract import SCOPE, verify_inputs
from run_normal_hap_probe import require_normal_identity
from run_root_probe import digest

EXPECTED = {'constructor': [1, 1, 1], 'optional': [1, 1], 'callbacks': [1, 1, 2],
            'isolation': [1, 1], 'mutation': [1, 1], 'subclass': [1, 1, 7],
            'repeated': [64, 0, 1], 'summary': [7, 0]}


def verify(text, run_id, identity):
    if not isinstance(run_id, str) or re.fullmatch('[0-9a-f]{32}', run_id) is None:
        raise ValueError('fresh constructor nonce required')
    require_normal_identity(identity)
    rows = [json.loads(line) for line in text.splitlines()]
    if len(rows) != len(EXPECTED):
        raise ValueError('complete constructor observations required')
    for row, (name, values) in zip(rows, EXPECTED.items()):
        if (not isinstance(row, dict) or set(row) != {'runId', 'name', 'values', 'error'} or
                row['runId'] != run_id or row['name'] != name or row['error'] != '' or
                row['values'] != values or any(type(value) is not int for value in row['values'])):
            raise ValueError('failed, stale, reordered or malformed constructor observation: ' + name)
    return {'closed': [], 'scope': SCOPE, 'observations': len(rows), 'instances': 67}


def verify_evidence(document, archive_sha, boot_id, arch):
    if (document.get('status') != 'pass' or document.get('persona') != 'completion-handler' or
            document.get('archive_sha256') != archive_sha or document.get('boot_id') != boot_id or
            document.get('arch') != arch or document.get('failures') != [] or
            document.get('first_artifact_behavior_gate_passed') is not False):
        raise ValueError('constructor evidence must belong to this actual package/boot/architecture')
    result_path = Path(document.get('result', ''))
    if not result_path.is_absolute() or result_path.name != 'verified-result.json':
        raise ValueError('explicit constructor result required')
    root = result_path.parent
    files = {'result': result_path, 'raw_results': root / 'results.log',
             'ordinary_identity': root / 'application-identity.json', 'hap': root / 'ordinary-probe-signed.hap',
             'compiled_contract_inputs': root / 'project/completion-handler-probe-inputs.json'}
    for key, path in files.items():
        if path.is_symlink() or not path.is_file() or digest(path) != document.get(key + '_sha256'):
            raise ValueError('actual constructor evidence changed: ' + key)
    value = json.loads(result_path.read_text())
    if (value.get('status') != 'pass' or value.get('scope') != SCOPE or value.get('failures') != [] or
            value.get('archive_sha256') != archive_sha or value.get('arch') != arch or
            value.get('run_id') != document.get('run_id') or
            value.get('first_artifact_behavior_gate_passed') is not False or
            value.get('verifier_sha256') != digest(Path(__file__))):
        raise ValueError('constructor summary is stale or belongs to another run')
    for field, key in (('results_sha256', 'raw_results'), ('application_identity_sha256', 'ordinary_identity'),
                       ('compiled_inputs_sha256', 'compiled_contract_inputs')):
        if value.get(field) != digest(files[key]):
            raise ValueError('constructor verifier did not consume captured evidence')
    verify_inputs(json.loads(files['compiled_contract_inputs'].read_text()), document['run_id'], arch)
    identity = files['ordinary_identity'].read_text()
    actual = verify(files['raw_results'].read_text(), document['run_id'], identity)
    if actual != value.get('result') or require_normal_identity(identity) != document.get('ordinary_uid'):
        raise ValueError('constructor summary differs from raw ordinary-app observations')
    return actual


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'results', 'inputs', 'application-identity', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--arch', choices=('arm64', 'armv7a', 'x86_64'), required=True)
    args = parser.parse_args()
    report = {'status': 'fail', 'scope': SCOPE, 'run_id': args.run_id, 'arch': args.arch,
        'archive_sha256': digest(args.archive), 'results_sha256': digest(args.results),
        'application_identity_sha256': digest(args.application_identity),
        'compiled_inputs_sha256': digest(args.inputs), 'verifier_sha256': digest(Path(__file__)),
        'first_artifact_behavior_gate_passed': False, 'failures': []}
    try:
        verify_inputs(json.loads(args.inputs.read_text()), args.run_id, args.arch)
        report['result'] = verify(args.results.read_text(), args.run_id, args.application_identity.read_text())
        report['status'] = 'pass'
    except (OSError, ValueError, KeyError, TypeError) as error:
        report['failures'].append(str(error))
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'failures': report['failures']}))
    raise SystemExit(0 if report['status'] == 'pass' else 1)
