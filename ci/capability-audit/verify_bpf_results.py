"""Strict root BPF map/filter proof; NetManager/NetFirewall not validated."""
import json
import re

CASES = [('map_create', 0), ('map_update', 0), ('map_lookup', 0), ('map_challenge_readback', 0),
         ('map_lookup_out_of_range', -2), ('map_update_out_of_range', -7), ('map_bad_fd', -9),
         ('map_info', 0), ('map_info_fields', 0), ('load_drop_filter', 0), ('load_allow_filter', 0),
         ('receiver_socket', 0), ('sender_socket', 0), ('bind_loopback', 0), ('query_ephemeral_port', 0),
         ('bounded_receive', 0), ('attach_drop', 0), ('send_drop_challenge', 32), ('drop_no_payload', -11),
         ('replace_with_allow', 0), ('send_allow_challenge', 32), ('allow_payload_length', 32),
         ('allow_challenge_bytes', 0)]


def verify(text, arch, run_id, code):
    if type(code) is not int or code != 0 or re.fullmatch('[0-9a-f]{32}', run_id or '') is None:
        raise ValueError('BPF requires actual successful process exit and explicit fresh challenge')
    rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    if len(rows) != len(CASES) + 2 or any(not isinstance(row, dict) or row.get('run_id') != run_id for row in rows):
        raise ValueError('incomplete or stale BPF cases')
    identity, summary = rows[0], rows[-1]
    bits = {'armv7a': 32, 'arm64': 64, 'x86_64': 64}.get(arch)
    if (set(identity) != {'type', 'run_id', 'uid', 'pointer_bits'} or bits is None or
            identity.get('type') != 'identity' or type(identity.get('uid')) is not int or
            identity['uid'] != 0 or type(identity.get('pointer_bits')) is not int or identity['pointer_bits'] != bits):
        raise ValueError('BPF root/architecture identity mismatch')
    for row, (name, expected) in zip(rows[1:-1], CASES):
        if (set(row) != {'type', 'run_id', 'name', 'actual', 'expected', 'passed'} or
                row.get('type') != 'case' or row.get('name') != name or row.get('passed') is not True or
                type(row.get('actual')) is not int or row['actual'] != expected or
                type(row.get('expected')) is not int or row['expected'] != expected):
            raise ValueError('failed or reordered actual BPF data/boundary case: ' + name)
    if (set(summary) != {'type', 'run_id', 'cases', 'passed'} or
            summary.get('type') != 'summary' or summary.get('passed') is not True or
            type(summary.get('cases')) is not int or summary['cases'] != len(CASES)):
        raise ValueError('BPF summary is incomplete or failed')
    return {'cases': len(CASES), 'scope': 'root map readback and loopback UDP drop/allow filter replacement',
            'netmanager_service_validated': False, 'netfirewall_policy_validated': False, 'results': rows}
