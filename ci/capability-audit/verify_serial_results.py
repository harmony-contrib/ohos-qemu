#!/usr/bin/env python3
"""Require fresh normal-HAP API records and matching real host byte transcript.

Even a consistent transcript cannot establish that the package was newly built
and booted; the repository's first-artifact validation evidence owns that gate.
"""
import argparse
import hashlib
import json
from pathlib import Path
from serial_host_echo import expected_frame, FRAME_SIZES

EXPECTED_CASE_ORDER = (
    'begin', 'enumerate', 'raw_node_denied_before_grant', 'ordinary_authorization_denied', 'deny_open',
    'allow_open', 'raw_node_denied_after_grant', 'write_empty', 'write_oversize',
    'write_negative_timeout', 'write_oversize_timeout', 'exchange_1', 'exchange_2',
    'last_listener_removed', 'exchange_4', 'control_api', 'close', 'write_closed', 'completed',
)
EXPECTED_CASES = set(EXPECTED_CASE_ORDER)
EXPECTED_CODES = {'ordinary_authorization_denied': 202, 'deny_open': 35700007,
                  'write_empty': 35700002, 'write_oversize': 35700002,
                  'write_negative_timeout': 35700002, 'write_oversize_timeout': 35700002,
                  'write_closed': 35700005}


def verify(guest, host, run_id, bundle, port_name='ttyUSB0'):
    errors = []
    cases = {}
    for row in guest:
        name = row.get('case')
        if row.get('kind') != 'serial_case' or row.get('run_id') != run_id or row.get('bundle') != bundle:
            errors.append('wrong/stale guest identity')
        if name in cases or name not in EXPECTED_CASES:
            errors.append('duplicate/unexpected guest case: ' + str(name))
        cases[name] = row
        code = row.get('code')
        if row.get('passed') is not True or row.get('code_type') != 'number' or type(code) is not int:
            errors.append('failed or non-numeric guest result: ' + str(name))
        if code != EXPECTED_CODES.get(name, 0):
            errors.append('wrong public numeric error code: ' + str(name))
    if set(cases) != EXPECTED_CASES:
        errors.append('missing public API/auth/lifecycle cases')
    if [row.get('case') for row in guest] != list(EXPECTED_CASE_ORDER):
        errors.append('guest authorization/data/lifecycle order changed')
    for name in ('raw_node_denied_before_grant', 'raw_node_denied_after_grant'):
        try:
            raw = json.loads(cases[name]['details'])
            if (raw.get('passed') is not True or raw.get('stat_errno') != 0 or raw.get('open_errno') != 13 or
                    raw.get('port_name') != port_name or raw.get('mode') != 0o660 or
                    raw.get('node_uid') != 1025 or raw.get('node_gid') != 1025 or
                    type(raw.get('app_uid')) is not int or raw['app_uid'] < 10000):
                errors.append('ordinary app raw-node isolation not established: ' + name)
        except (KeyError, TypeError, ValueError):
            errors.append('invalid raw-node syscall record: ' + name)
    try:
        devices = json.loads(cases['enumerate']['details'])
        matched = [device for device in devices if device.get('portName') == port_name]
        if (len(matched) != 1 or type(matched[0].get('vendorId')) is not int or matched[0]['vendorId'] <= 0 or
                type(matched[0].get('productId')) is not int or matched[0]['productId'] <= 0):
            errors.append('dedicated USB-serial device identity not established')
    except (KeyError, TypeError, ValueError, AttributeError):
        errors.append('invalid serial enumeration record')
    phases = {}
    for row in host:
        phase = row.get('phase')
        if (row.get('kind') != 'serial_host_frame' or row.get('run_id') != run_id or type(phase) is not int
                or phase in phases or phase not in FRAME_SIZES):
            errors.append('unexpected/duplicate/stale host frame')
            continue
        phases[phase] = row
        frame = expected_frame(run_id, phase)
        digest = hashlib.sha256(frame).hexdigest()
        if (row.get('challenge_matched') is not True or row.get('frame_sha256') != digest or
                row.get('expected_sha256') != digest or type(row.get('frame_size')) is not int
                or row.get('frame_size') != len(frame) or type(row.get('echo_bytes')) is not int
                or row.get('echo_bytes') != len(frame) or row.get('echo_completed') is not True):
            errors.append('host byte-count/challenge mismatch')
    if set(phases) != set(FRAME_SIZES):
        errors.append('missing host serial exchange frame')
    if [row.get('phase') for row in host] != list(FRAME_SIZES):
        errors.append('host serial exchange order changed')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--guest', type=Path, required=True)
    parser.add_argument('--host', type=Path, required=True)
    parser.add_argument('--inputs', type=Path, required=True)
    args = parser.parse_args()
    inputs = json.loads(args.inputs.read_text())
    guest = [json.loads(line) for line in args.guest.read_text().splitlines() if line.strip()]
    host = [json.loads(line) for line in args.host.read_text().splitlines() if line.strip()]
    errors = verify(guest, host, inputs['run_id'], inputs['bundle_name'], inputs['port_name'])
    print(json.dumps({'serial_transcript_consistent': not errors, 'errors': errors,
                      'first_package_gate_passed': False,
                      'scope': 'transcript_only_requires_separate_new_package_boot_evidence'}, indent=2))
    return 1 if errors else 0


if __name__ == '__main__':
    raise SystemExit(main())
