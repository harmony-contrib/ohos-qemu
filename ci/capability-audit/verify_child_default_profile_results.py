"""Exact disabled-profile observations; never supported child lifecycle proof."""
import json
import re

PARAMETERS = ('persist.sys.abilityms.multi_process_model',
              'const.max_native_child_process', 'const.product.devicetype')
SCOPE = 'actual_disabled_child_profile_C_ArkTS_boundaries_NOT_supported_lifecycle'
C_ROWS = [('parent.args.present', 0), ('destroy.null', 401), ('config.created', 1),
          ('isolation.uid.null', 401), ('isolation.uid', 0), ('process.name', 0),
          ('start', 16010004), ('start.configured', 16010004), ('start.null', 401),
          ('start.configured.null', 401), ('config.destroy', 0)]
COMPLETE_C_ROWS = [('parent.args.present', 0), ('native.supported', 0), ('destroy.null', 0),
    ('config.created', 1), ('isolation.mode.null', 401), ('isolation.mode.normal', 0),
    ('isolation.mode.isolated', 0), ('isolation.mode.invalid', 401), ('isolation.mode.restored', 0),
    ('isolation.uid.null', 401), ('isolation.uid', 0), ('process.name', 0),
    ('process.name.null-config', 401), ('process.name.null', 401), ('process.name.empty', 401),
    ('process.name.invalid', 401), ('process.name.64', 0), ('process.name.65', 401),
    ('process.name.restored', 0), ('create', 16010004), ('create.configured', 16010004),
    ('create.null-library', 401), ('create.null-callback', 401), ('create.configured.null', 401),
    ('start', 16010004), ('start.configured', 16010004), ('start.null', 401),
    ('start.configured.null', 401), ('config.destroy', 0), ('callback.count', 0)]


def verify(text, nonce, uid, pid, parameters, device, *, original_diagnostic=False):
    if (re.fullmatch('[a-f0-9]{32}', nonce or '') is None or type(uid) is not int or
            uid // 200000 != 100 or type(pid) is not int or pid <= 1 or
            device not in ('phone', '2in1') or
            parameters != dict(zip(PARAMETERS, ('false', '0', device)))):
        raise ValueError('exact actual disabled child profile and ordinary identity required')
    rows = [json.loads(line) for line in text.splitlines()]
    c_expected = C_ROWS if original_diagnostic else COMPLETE_C_ROWS
    expected = [('identity', [uid, uid, pid]), ('typed.const.enum', [0, 1]),
                ('supported', [0, 0]), ('C_API', [])]
    expected += [('legacy.'+kind+'.reject.'+str(mode), [16000061])
                 for mode in (0, 1) for kind in ('promise', 'callback')]
    expected += [('ark.reject', [801]), ('native.reject', [801]),
                 ('invalid.entry.reject', [401]), ('summary', [1])]
    if len(rows) != len(expected):
        raise ValueError('missing or extra actual child boundary observations')
    for row, (name, values) in zip(rows, expected):
        if (type(row) is not dict or set(row) != {'runId', 'name', 'values', 'data'} or
                row['runId'] != nonce or row['name'] != name or
                type(row['values']) is not list or any(type(v) is not int for v in row['values']) or
                row['values'] != values or type(row['data']) is not str):
            raise ValueError('failed, foreign or reordered child boundary observation: '+name)
        if name == 'C_API':
            native = json.loads(row['data'])
            if type(native) is not list or len(native) != len(c_expected):
                raise ValueError('complete actual C child boundary observations required')
            for actual, (operation, code) in zip(native, c_expected):
                if (type(actual) is not dict or set(actual) != {'name', 'code', 'pid'} or
                        actual['name'] != operation or type(actual['code']) is not int or
                        actual['code'] != code or type(actual['pid']) is not int or actual['pid'] != -1):
                    raise ValueError('C child parameter/profile boundary differs: '+operation)
        elif name.endswith('.reject') or '.reject.' in name:
            if not row['data'].startswith('number:') or len(row['data']) <= len('number:'):
                raise ValueError('actual typed child BusinessError and message required')
        elif row['data'] != '':
            raise ValueError('unexpected child boundary native data: '+name)
    return dict(scope=SCOPE, observations=len(rows), native_observations=len(c_expected),
                actual_uid=uid, actual_pid=pid, support_flags=[0, 0],
                started_children=0, original_diagnostic_only=original_diagnostic,
                supported_lifecycle_verified=False)
