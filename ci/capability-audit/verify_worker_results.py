#!/usr/bin/env python3
"""Require real worker-context ports and two challenge-bearing buffer lifecycles."""
import argparse
import json
from pathlib import Path
import re

from verify_audio_stream_results import application_identity, sha256
from worker_contracts import verify_inputs

MODES = {'legacy': ('Worker', 'parentPort', 0), 'thread': ('ThreadWorker', 'workerPort', 10200004)}


def verify(text, run_id, identity_text, mode):
    if mode not in MODES or re.fullmatch('[0-9a-f]{32}', run_id or '') is None:
        raise ValueError('explicit Worker version and fresh challenge required')
    uid = application_identity(identity_text)
    if uid // 200000 != 100 or uid % 200000 < 10000:
        raise ValueError('Worker must run in an ordinary account-100 app')
    rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    if len(rows) != 20 or any(not isinstance(row, dict) or row.get('run_id') != run_id for row in rows):
        raise ValueError('incomplete/mixed actual Worker lifecycle rows')
    constructor, port, error_code = MODES[mode]
    identity = rows[0]
    if (set(identity) != {'type', 'run_id', 'worker_class', 'port_name', 'main_parent_port_absent',
                          'main_worker_port_absent'} or identity.get('type') != 'identity' or
            identity.get('worker_class') != constructor or identity.get('port_name') != port or
            identity.get('main_parent_port_absent') is not True or identity.get('main_worker_port_absent') is not True):
        raise ValueError('main/worker context boundary or constructor mismatch')
    index = 1
    salt = int(run_id[:8], 16)

    def step(generation, name, actual):
        nonlocal index
        row = rows[index]
        index += 1
        if (set(row) != {'type', 'run_id', 'generation', 'name', 'actual'} or row.get('type') != 'step' or
                type(row.get('generation')) is not int or row['generation'] != generation or row.get('name') != name or
                type(row.get('actual')) is not int or row['actual'] != actual):
            raise ValueError('wrong Worker lifecycle/error boundary: ' + name)

    for generation in (1, 2):
        step(generation, 'created', 1)
        for sequence in (1, 2):
            transfer, data = rows[index:index + 2]
            index += 2
            for row in (transfer, data):
                if (type(row.get('generation')) is not int or row['generation'] != generation or
                        type(row.get('sequence')) is not int or row['sequence'] != sequence):
                    raise ValueError('duplicate/reordered worker transfer')
            if (set(transfer) != {'type', 'run_id', 'generation', 'sequence', 'input_bytes', 'detached_bytes',
                                 'detached_length_error', 'detached_access_error'} or
                    transfer.get('type') != 'transfer' or type(transfer.get('input_bytes')) is not int or
                    transfer['input_bytes'] != 256 or type(transfer.get('detached_bytes')) is not int or
                    transfer['detached_bytes'] != -1 or
                    transfer.get('detached_length_error') != 'TypeError: IsDetachedBuffer' or
                    transfer.get('detached_access_error') != 'TypeError'):
                raise ValueError('no real host-to-worker transferable-buffer detachment')
            words = data.get('words')
            expected = [((((salt + i * 257 + generation * 65537 + sequence * 17) & 0xffffffff) ^
                          0x5a5a5a5a) + generation + sequence) & 0xffffffff for i in range(64)]
            if (set(data) != {'type', 'run_id', 'generation', 'sequence', 'nonce', 'words', 'bytes', 'input_bytes',
                             'port_name', 'port_usable', 'other_port_absent'} or data.get('type') != 'data' or
                    data.get('nonce') != run_id or type(data.get('bytes')) is not int or data['bytes'] != 256 or
                    type(data.get('input_bytes')) is not int or data['input_bytes'] != 256 or
                    data.get('port_name') != port or data.get('port_usable') is not True or
                    data.get('other_port_absent') is not True or not isinstance(words, list) or
                    len(words) != 64 or any(type(word) is not int for word in words) or words != expected):
                raise ValueError('no complete challenge-derived worker transform/return bytes or real port')
        step(generation, 'close_ack', 1)
        step(generation, 'exit', 0)
        step(generation, 'post_after_exit_error', error_code)
        step(generation, 'post_after_exit_quiet', 1)
    summary = rows[index]
    if (index != len(rows) - 1 or set(summary) != {'type', 'run_id', 'cycles', 'passed', 'scope'} or
            summary.get('type') != 'summary' or summary.get('passed') is not True or
            type(summary.get('cycles')) is not int or summary['cycles'] != 2 or summary.get('scope') !=
            'ordinary_worker_context_ports_and_transfer_lifecycle_only'):
        raise ValueError('Worker lifecycle incomplete or falsely expanded capability scope')
    return {'mode': mode, 'worker_class': constructor, 'port_name': port, 'rows': rows,
            'ordinary_uid': uid, 'cycles': 2, 'actual_transformed_words': 256,
            'scope': 'worker-context port, transfer, close/recreate and closed-message boundary only'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'results', 'application-identity', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--mode', choices=tuple(MODES), required=True)
    parser.add_argument('--inputs', type=Path, required=True)
    parser.add_argument('--arch', choices=('arm64', 'armv7a', 'x86_64'), required=True)
    args = parser.parse_args()
    evidence = {'status': 'fail', 'scope': 'ordinary Worker context ports NOT all worker backends',
        'first_artifact_behavior_gate_passed': False, 'run_id': args.run_id, 'mode': args.mode, 'failures': []}
    try:
        verify_inputs(json.loads(args.inputs.read_text()), args.inputs.parent, args.run_id, args.arch, args.mode)
        evidence.update(archive_sha256=sha256(args.archive), results_sha256=sha256(args.results),
                        application_identity_sha256=sha256(args.application_identity),
                        compiled_inputs_sha256=sha256(args.inputs))
        evidence['result'] = verify(args.results.read_text(), args.run_id, args.application_identity.read_text(), args.mode)
        evidence['status'] = 'pass'
    except (OSError, ValueError, KeyError, TypeError) as error:
        evidence['failures'].append(str(error))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps({key: value for key, value in evidence.items() if key != 'result'}))
    return 0 if evidence['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
