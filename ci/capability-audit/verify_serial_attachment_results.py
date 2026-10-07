#!/usr/bin/env python3
"""Check ordinary-HAP attachment transcript consistency, not hardware/UI proof.

Actual devnode/sysfs lifetime snapshots, late trusted-UI replies, other users,
devices, and the new packaged guest remain separate required acceptance inputs.
"""
import argparse
import json
from pathlib import Path

ORDER = ('begin', 'enumerate_original', 'unplug_pending_open', 'enumerate_replacement',
         'deny_replacement', 'allow_replacement', 'raw_node_denied_after_grant',
         'on_off_disconnect', 'enumerate_absent', 'write_stale_object',
         'enumerate_replug', 'deny_replug', 'allow_replug', 'close_replug', 'completed')
CODES = {'unplug_pending_open': 35700003, 'write_stale_object': 35700003,
         'deny_replacement': 35700007, 'deny_replug': 35700007}


def verify(rows, run_id, bundle, port_name):
    errors = []
    cases = {}
    if [row.get('case') for row in rows] != list(ORDER):
        errors.append('missing, duplicate or reordered attachment lifecycle cases')
    for row in rows:
        name = row.get('case')
        if (row.get('kind') != 'serial_attachment_case' or row.get('run_id') != run_id
                or row.get('bundle') != bundle):
            errors.append('wrong/stale ordinary-HAP identity')
        if (name not in ORDER or name in cases or row.get('passed') is not True
                or row.get('code_type') != 'number' or type(row.get('code')) is not int
                or row.get('code') != CODES.get(name, 0)):
            errors.append('failed or invalid numeric attachment case: ' + str(name))
        cases[name] = row
    try:
        original = None
        for name in ('enumerate_original', 'enumerate_replacement', 'enumerate_replug'):
            devices = json.loads(cases[name]['details'])
            matched = [device for device in devices if device.get('portName') == port_name]
            if len(matched) != 1:
                raise ValueError('missing dedicated USB attachment')
            info = matched[0]
            if (type(info.get('vendorId')) is not int or info['vendorId'] <= 0
                    or type(info.get('productId')) is not int or info['productId'] <= 0
                    or type(info.get('manufacturer')) is not str):
                raise ValueError('malformed USB enumeration')
            identity = tuple(info.get(field) for field in ('portName', 'vendorId', 'productId', 'manufacturer'))
            if original is None:
                original = identity
            elif original != identity:
                raise ValueError('replacement did not exercise identical public device tuple')
        absent = json.loads(cases['enumerate_absent']['details'])
        if any(device.get('portName') == port_name for device in absent):
            raise ValueError('device still enumerated during offline stage')
        counts = json.loads(cases['on_off_disconnect']['details'])
        if (type(counts.get('removed')) is not int or counts['removed'] != 0
                or type(counts.get('retained')) is not int or counts['retained'] != 1):
            raise ValueError('selective disconnect callback removal not established')
        raw = json.loads(cases['raw_node_denied_after_grant']['details'])
        expected = {'stat_errno': 0, 'open_errno': 13, 'mode': 0o660, 'node_uid': 1025, 'node_gid': 1025}
        if (raw.get('passed') is not True or raw.get('port_name') != port_name
                or type(raw.get('app_uid')) is not int or raw['app_uid'] < 10000
                or any(type(raw.get(key)) is not int or raw[key] != value for key, value in expected.items())):
            raise ValueError('ordinary raw-node isolation not established')
    except (KeyError, TypeError, ValueError, AttributeError) as error:
        errors.append('invalid attachment details: ' + str(error))
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--guest', type=Path, required=True)
    parser.add_argument('--inputs', type=Path, required=True)
    args = parser.parse_args()
    inputs = json.loads(args.inputs.read_text())
    if inputs.get('scenario') != 'attachment' or inputs.get('request_permissions') != []:
        raise ValueError('requires the ordinary attachment HAP input manifest')
    rows = [json.loads(line) for line in args.guest.read_text().splitlines() if line.strip()]
    errors = verify(rows, inputs['run_id'], inputs['bundle_name'], inputs['port_name'])
    print(json.dumps({'scope': 'attachment_transcript_consistency_NOT_device_UI_or_package_acceptance',
                      'attachment_transcript_consistent': not errors, 'errors': errors,
                      'first_package_gate_passed': False, 'hardware_UI_acceptance_established': False}, indent=2))
    raise SystemExit(1 if errors else 0)


if __name__ == '__main__':
    main()
