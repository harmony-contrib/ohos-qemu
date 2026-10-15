"""Require actual BMS decorator registration and two challenged entry executions.

This parser alone does not bind HAP signatures, a new archive, or a guest boot.
The enclosing evidence verifier must supply those before registering closure.
"""
import json
import re
from build_insight_driver_probe import ROLES
from verify_insight_decorator_build import NAMES, verify_metadata


def expected_info(row):
    value = {key: row[key] for key in (
        'bundleName', 'moduleName', 'intentName', 'domain', 'intentVersion', 'displayName')}
    value.update(intentType=row['decoratorType'], developType='decorator')
    if 'parameters' in row:
        value['parameters'] = row['parameters']
    entities = []
    for entity in row.get('entities', []):
        item = {key: entity[key] for key in (
            'className', 'entityId', 'entityCategory', 'parameters', 'parentClassName',
            'supportedQueryProperties')}
        item['isQueryable'] = False
        entities.append(item)
    value['entities'] = entities
    kind = row['decoratorType']
    if kind == '@InsightIntentEntry':
        value['subIntentInfo'] = {'abilityName': 'EntryAbility', 'executeMode': [1]}
    elif kind == '@InsightIntentForm':
        value['subIntentInfo'] = {'abilityName': row['abilityName'], 'formName': row['formName']}
    elif kind == '@InsightIntentLink':
        value['subIntentInfo'] = {'uri': row['uri']}
    elif kind == '@InsightIntentPage':
        value['subIntentInfo'] = {'uiAbility': row['uiAbility'], 'pagePath': row['pagePath'],
                                'navigationId': '', 'navDestinationName': ''}
    else:
        value['subIntentInfo'] = {}
    return value


def verify_info(actual, expected):
    if not isinstance(actual, dict):
        raise ValueError('actual BMS intent info is not an object')
    for key, value in expected.items():
        if actual.get(key) != value:
            raise ValueError('actual registered intent differs: ' + key)
    for key in ('displayDescription', 'schema', 'icon', 'llmDescription'):
        if actual.get(key) != '':
            raise ValueError('unexpected registered intent display/schema default: ' + key)
    if actual.get('keywords') != []:
        raise ValueError('unexpected registered intent keywords')
    return actual


def verify(text, caller_nonce, role, uid, compiled_metadata, target_nonce):
    if (role not in ROLES or type(uid) is not int or uid < 10000 or
            re.fullmatch('[a-f0-9]{32}', caller_nonce or '') is None):
        raise ValueError('explicit actual non-root caller role/UID/nonce required')
    target_rows = verify_metadata(compiled_metadata, target_nonce)
    rows = [json.loads(line) for line in text.splitlines()]
    names = (['identity', 'lookup', 'entry.0', 'entry.1', 'function.metadata', 'summary']
             if role == 'system' else ['identity', 'denied.0', 'denied.1', 'summary'])
    if not text.endswith('\n') or len(rows) != len(names):
        raise ValueError('complete ordered intent caller observations required')
    for row, name in zip(rows, names):
        if (not isinstance(row, dict) or set(row) != {'runId', 'role', 'name', 'values', 'data', 'error'} or
                row['runId'] != caller_nonce or row['role'] != role or row['name'] != name or
                row['error'] != '' or type(row['data']) is not str or type(row['values']) is not list or
                any(type(value) is not int for value in row['values'])):
            raise ValueError('foreign, reordered, failed or malformed intent observation: ' + name)
    if len(rows[0]['values']) != 3 or rows[0]['values'][:2] != [uid, uid] or rows[0]['values'][2] <= 1:
        raise ValueError('actual caller UID/eUID/PID differs')
    if rows[0]['data'] or rows[-1]['values'] != [1] or rows[-1]['data']:
        raise ValueError('invalid intent caller identity/summary payload')
    if role != 'system':
        for row in rows[1:-1]:
            if row['values'] != [1, 202 if role == 'normal' else 201, 1] or row['data']:
                raise ValueError('real numeric system/permission denial required')
        return rows
    if rows[1]['values'] != [5]:
        raise ValueError('all five registered decorated intent records required')
    infos = json.loads(rows[1]['data'])
    if not isinstance(infos, list) or len(infos) != len(NAMES):
        raise ValueError('missing/extra actual BMS intent info')
    mapping = {}
    for info in infos:
        if not isinstance(info, dict) or info.get('intentName') in mapping:
            raise ValueError('duplicate/malformed registered intent')
        mapping[info.get('intentName')] = info
    if set(mapping) != set(NAMES):
        raise ValueError('wrong registered intent names')
    for source in target_rows:
        verify_info(mapping[source['intentName']], expected_info(source))
    for cycle, row in enumerate(rows[2:4]):
        if row['values'] != [0] or json.loads(row['data']) != {
                'entityId': 'audit', 'value': caller_nonce + ':' + str(cycle) + ':entry'}:
            raise ValueError('actual decorated entry did not execute the distinct challenge')
    if rows[4]['values'] or json.loads(rows[4]['data']) != mapping['AuditFunction']:
        raise ValueError('named function lookup differs from the registered real target')
    return rows
