"""Exact all-route ordinary observations and recorded profile boundaries."""
import json
import re

ROUTES = ('input', 'detail', 'network', 'display', 'mobile', 'refresh', 'sound',
          'biometrics', 'about', 'nfc', 'app-detail', 'double-click')
PARAMETERS = ('const.product.devicetype', 'const.SystemCapability.Communication.NFC.Core',
              'const.nfc.not_support')


def supported_routes(device, parameters):
    if device not in ('phone', '2in1') or set(parameters) != set(PARAMETERS):
        raise ValueError('exact actual Settings profile parameters required')
    if parameters[PARAMETERS[0]] != device:
        raise ValueError('actual Settings device profile differs')
    def boolean(name):
        value = parameters[name]
        if value in ('true', '1'): return True
        if value in ('false', '0'): return False
        if value == 'Get parameter "' + name + '" fail! errNum is:106!':
            return False  # Exact absent parameter; pinned GetBoolParameter default is false.
        raise ValueError('unexpected actual Settings capability parameter result')
    core, disabled = boolean(PARAMETERS[1]), boolean(PARAMETERS[2])
    nfc = core and not disabled
    return {route: (False if route == 'double-click' else
        device == 'phone' and nfc if route == 'nfc' else
        device == 'phone' if route in ('mobile', 'sound') else True) for route in ROUTES}


def verify_rows(text, run_id, uid, pid, *, startup=False):
    if re.fullmatch('[0-9a-f]{32}', run_id or '') is None:
        raise ValueError('fresh ordinary Settings nonce required')
    if type(uid) is not int or uid // 200000 != 100 or type(pid) is not int or pid <= 0:
        raise ValueError('actual ordinary Settings caller UID and PID required')
    expected = ['identity', 'installed-input-methods', 'empty-identity.0', 'empty-identity.1',
                'invalid-app.0', 'invalid-app.1', 'ready']
    if not startup:
        expected += [('network.result' if route == 'network' else route + '.request-returned')
                     for _ in (1, 2) for route in ROUTES]
    if not text.endswith('\n'): raise ValueError('complete append-only Settings journal required')
    rows = [json.loads(line) for line in text.splitlines()]
    if len(rows) != len(expected): raise ValueError('complete two-round all-route Settings sequence required')
    for sequence, (row, name) in enumerate(zip(rows, expected), 1):
        if (set(row) != {'runId', 'sequence', 'name', 'pass', 'value'} or
                row['runId'] != run_id or type(row['sequence']) is not int or
                row['sequence'] != sequence or row['name'] != name or row['pass'] is not True or
                type(row['value']) is not str):
            raise ValueError('foreign, failed or reordered Settings observation')
    who = json.loads(rows[0]['value'])
    if who != [uid, uid, pid] or any(type(value) is not int for value in who):
        raise ValueError('Settings native identity differs from installed/running caller')
    methods = json.loads(rows[1]['value'])
    if (not isinstance(methods, list) or not methods or
            any(not isinstance(item, dict) or any(type(item.get(key)) is not str or not item[key]
                for key in ('name', 'id')) for item in methods)):
        raise ValueError('actual installed input method identity required')
    for row in rows[2:6]:
        error = json.loads(row['value'])
        if type(error.get('code')) is not int or error['code'] != 16900010:
            raise ValueError('documented numeric Settings invalid parameter error required')
    if not startup:
        for row, route in zip(rows[7:], ROUTES * 2):
            if route == 'network':
                if json.loads(row['value']) is not True: raise ValueError('actual network request failed')
            elif route == 'detail':
                if json.loads(row['value']) != methods[0]: raise ValueError('foreign input method detail request')
            elif row['value'] != 'void-return-only-not-render-proof':
                raise ValueError('unexpected public Settings route result')
    return {'methods': methods, 'pid': pid, 'uid': uid, 'observations': len(rows)}
