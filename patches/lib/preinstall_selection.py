"""Exact BMS preinstall selection; JSON booleans must retain their type."""
import json


def unique(pairs):
    value = {}
    for key, item in pairs:
        if key in value: raise ValueError('duplicate preinstall selection key')
        value[key] = item
    return value


def same_json(actual, expected):
    if type(actual) is not type(expected): return False
    if isinstance(expected, dict):
        return actual.keys() == expected.keys() and all(same_json(actual[k], v) for k, v in expected.items())
    if isinstance(expected, list):
        return len(actual) == len(expected) and all(same_json(a, b) for a, b in zip(actual, expected))
    return actual == expected


def entry(data, bundle):
    value = json.loads(data, object_pairs_hook=unique)
    rows = value.get('install_list') if isinstance(value, dict) else None
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError('invalid BMS preinstall selection list')
    expected = {'app_dir': '/system/app/' + bundle, 'removable': False}
    if not same_json([row for row in rows if row.get('app_dir') == expected['app_dir']], [expected]):
        raise ValueError('unique original nonremovable preinstall directory required: ' + bundle)
    return expected


def uninstall_policy(data, bundle):
    value = json.loads(data, object_pairs_hook=unique)
    if not isinstance(value, dict): raise ValueError('invalid preinstall uninstall policy')
    for key in ('uninstall_list', 'recover_list'):
        if not isinstance(value.get(key), list) or any(type(item) is not str for item in value[key]):
            raise ValueError('invalid preinstall uninstall/recover directories')
    if '/system/app/' + bundle in set(value['uninstall_list']) - set(value['recover_list']):
        raise ValueError('preinstall entry vetoed by uninstall policy: ' + bundle)
    return value
