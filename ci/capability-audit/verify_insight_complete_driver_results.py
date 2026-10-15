"""Require challenged native dispatch to both decorated entries and static methods.

This parser is not archive/boot/signature provenance or a complete capability gate.
The narrower prior diagnostic parser remains scoped to its captured old records.
"""
import json
from verify_insight_driver_results import verify as verify_entry


def verify(text, caller_nonce, role, uid, compiled_metadata, target_nonce):
    rows = [json.loads(line) for line in text.splitlines()]
    names = (['identity', 'lookup', 'entry.0', 'entry.1', 'function.metadata',
              'function.0', 'function.1', 'summary'] if role == 'system' else
             ['identity', 'denied.0', 'denied.1', 'denied.2', 'summary'])
    if not text.endswith('\n') or len(rows) != len(names):
        raise ValueError('complete entry and decorated static-method observations required')
    for row, name in zip(rows, names):
        if (not isinstance(row, dict) or set(row) != {'runId', 'role', 'name', 'values', 'data', 'error'} or
                row.get('name') != name or row.get('runId') != caller_nonce or row.get('role') != role or
                row.get('error') != '' or type(row.get('data')) is not str or
                type(row.get('values')) is not list or any(type(v) is not int for v in row['values'])):
            raise ValueError('foreign, partial, malformed or failed complete intent observation')
    excluded = {'function.0', 'function.1'} if role == 'system' else {'denied.2'}
    narrowed = '\n'.join(json.dumps(row) for row in rows if row['name'] not in excluded) + '\n'
    verify_entry(narrowed, caller_nonce, role, uid, compiled_metadata, target_nonce)
    if role == 'system':
        for cycle, row in enumerate(rows[5:7]):
            if row['values'] != [0] or json.loads(row['data']) != {
                    'methodResult': json.dumps(caller_nonce + ':' + str(cycle) + ':echo', separators=(',', ':'))}:
                raise ValueError('native decorated static-method dispatch did not return its distinct challenge')
    elif rows[3]['values'] != [1, 202 if role == 'normal' else 201, 1] or rows[3]['data']:
        raise ValueError('decorated static-method execution requires the exact numeric permission denial')
    return rows
