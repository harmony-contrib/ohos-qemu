"""Require real HTTP bytes and corresponding own-UID public statistics deltas."""
import argparse
import hashlib
import json
from pathlib import Path
import re

from network_accounting_contract import SCOPE, verify_inputs
from network_accounting_endpoint import payload
from run_normal_hap_probe import require_normal_identity
from run_root_probe import digest


def verify(text, run_id, identity, peer, endpoint):
    uid = require_normal_identity(identity)
    if re.fullmatch('[0-9a-f]{32}', run_id or '') is None:
        raise ValueError('fresh network-accounting run required')
    expected_requests = [dict(generation=index, length=len(payload(run_id, index)),
                             sha256=hashlib.sha256(payload(run_id, index)).hexdigest()) for index in range(3)]
    requests = peer.get('requests')
    if (not isinstance(requests, list) or len(requests) != 3 or
            any(not isinstance(row, dict) or set(row) != {'generation', 'length', 'sha256'} or
                type(row['generation']) is not int or type(row['length']) is not int for row in requests)):
        raise ValueError('actual HTTP observations require exact numeric generation/length records')
    if (peer.get('scope') != 'owned_loopback_HTTP_peer_NOT_guest_or_statistics_acceptance' or
            peer.get('run_id') != run_id or peer.get('endpoint') != endpoint or
            peer.get('bind_address') != '127.0.0.1' or peer.get('listener_closed') is not True or
            peer.get('errors') != [] or requests != expected_requests or
            peer.get('implementation_sha256') != digest(Path(__file__).with_name('network_accounting_endpoint.py'))):
        raise ValueError('actual owned HTTP peer did not observe the exact three payload exchanges')
    names = ['identity', 'warmup'] + [name + '.' + str(index) for index in (1, 2)
                                     for name in ('before', 'payload', 'after')] + ['other-uid-denial', 'summary']
    rows = [json.loads(line) for line in text.splitlines()]
    if len(rows) != len(names):
        raise ValueError('incomplete actual network-accounting observations')
    for row, name in zip(rows, names):
        if (not isinstance(row, dict) or set(row) != {'runId', 'name', 'values', 'error'} or
                row['runId'] != run_id or row['name'] != name or row['error'] != '' or
                not isinstance(row['values'], list) or
                any(type(value) is not int or not 0 <= value <= 2**53 - 1 for value in row['values'])):
            raise ValueError('stale, malformed, reordered or failed traffic/statistics observation')
    if rows[0]['values'] != [uid, uid] or rows[1]['values'] != [32]:
        raise ValueError('actual ordinary UID and warmup bytes required')
    last = None
    for index in (1, 2):
        before, actual_payload, after = [row['values'] for row in rows[2 + (index - 1) * 3:5 + (index - 1) * 3]]
        byte_count = len(payload(run_id, index))
        if actual_payload != [byte_count] or len(before) != 2 or len(after) != 2 or min(before) < 32:
            raise ValueError('real initialized own-UID counters and validated HTTP bytes required')
        if last is not None and any(value < previous for value, previous in zip(before, last)):
            raise ValueError('UID counters regressed between generations')
        if any(not byte_count <= end - start <= byte_count + 65536 for start, end in zip(before, after)):
            raise ValueError('public statistics did not account for controlled send/receive payloads')
        last = after
    if rows[-2]['values'] != [201, 201] or rows[-1]['values'] != [1]:
        raise ValueError('other-UID isolation and successful caller completion required')
    return dict(closed=[], uid=uid, generations=2, promise_and_callback=True,
                rx_tx_payload_bytes=[131072, 262144], other_uid_denial=201,
                not_claimed='access_policy_changes_privileged_other_UID_statistics_or_complete_network_gap')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('archive', 'results', 'inputs', 'application-identity', 'http-peer', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--run-id', required=True)
    parser.add_argument('--arch', choices=('arm64', 'armv7a', 'x86_64'), required=True)
    args = parser.parse_args()
    report = dict(status='fail', scope=SCOPE, run_id=args.run_id, arch=args.arch,
        archive_sha256=digest(args.archive), results_sha256=digest(args.results),
        application_identity_sha256=digest(args.application_identity), compiled_inputs_sha256=digest(args.inputs),
        http_peer_sha256=digest(args.http_peer), verifier_sha256=digest(Path(__file__)),
        first_artifact_behavior_gate_passed=False, failures=[])
    try:
        inputs = json.loads(args.inputs.read_text())
        verify_inputs(inputs, args.run_id, args.arch)
        report['result'] = verify(args.results.read_text(), args.run_id, args.application_identity.read_text(),
                                  json.loads(args.http_peer.read_text()), inputs['endpoint'])
        report['status'] = 'pass'
    except Exception as error:
        report['failures'].append(type(error).__name__ + ': ' + str(error))
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(dict(status=report['status'], failures=report['failures'])))
    raise SystemExit(0 if report['status'] == 'pass' else 1)
