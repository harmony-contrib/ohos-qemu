"""Match Settings controls to actual service modes, not guessed coordinates."""
import json

from guest_ui import bounds, select_node

BUNDLE = 'com.ohos.settings'
PREFIX = 'qemu-refresh-rate-'


def verify_caller(text, nonce):
    from verify_settings_navigation_results import verify_rows
    lines = text.splitlines()
    if len(lines) != 10:
        raise ValueError('complete input navigation, refresh request and permission observations required')
    verify_rows('\n'.join(lines[:8]), nonce)
    extra = [json.loads(line) for line in lines[8:]]
    for sequence, (row, name) in enumerate(zip(extra, ('refresh.request-returned', 'screen.ordinary-denial')), 9):
        if (not isinstance(row, dict) or set(row) != {'runId', 'sequence', 'name', 'pass', 'value'} or row['runId'] != nonce or
                type(row['sequence']) is not int or row['sequence'] != sequence or row['name'] != name or
                row['pass'] is not True or not isinstance(row['value'], str)):
            raise ValueError('actual fresh ordinary caller sequence failed')
    error = json.loads(extra[1]['value'])
    if not isinstance(error, dict) or type(error.get('code')) is not int or error['code'] != 202:
        raise ValueError('ordinary system-API rejection must be real BusinessError 202')
    return extra


def controls(layout, readback):
    expected = {mode['id']: mode for mode in readback['refresh_choices']}
    active = readback['active_mode']['id']
    if not expected or active not in expected:
        raise ValueError('actual current-resolution modes required')
    pending = [(root, '', None, 0) for root in (layout if isinstance(layout, list) else [layout])]
    rows = {}
    count = 0
    while pending:
        node, inherited, parent, depth = pending.pop()
        count += 1
        if count > 100000 or depth > 256 or not isinstance(node, dict):
            raise ValueError('invalid Settings hierarchy')
        attrs, children = node.get('attributes'), node.get('children', [])
        if not isinstance(attrs, dict) or not isinstance(children, list):
            raise ValueError('invalid Settings node')
        bundle = attrs.get('bundleName') or inherited
        identifier = attrs.get('id', '')
        if bundle == BUNDLE and identifier == PREFIX + 'error':
            raise ValueError('Settings reports an actual display-service failure')
        if bundle == BUNDLE and isinstance(identifier, str) and identifier.startswith(PREFIX):
            suffix = identifier.removeprefix(PREFIX)
            if not suffix.isascii() or not suffix.isdecimal() or str(int(suffix)) != suffix:
                raise ValueError('invalid Settings mode identifier')
            mode_id = int(suffix)
            if mode_id not in expected or mode_id in rows:
                raise ValueError('Settings modes differ from actual service modes')
            label = select_node(layout, BUNDLE, identifier=identifier)
            if attrs.get('type') != 'Text' or attrs.get('text') != str(expected[mode_id]['refreshRate']) + ' Hz':
                raise ValueError('Settings refresh label differs from actual service rate')
            if parent is None or parent.get('attributes', {}).get('type') != 'Row':
                raise ValueError('actual mode label row required')
            radios = [child for child in parent.get('children', [])
                      if child.get('attributes', {}).get('type') == 'Radio']
            if len(radios) != 1:
                raise ValueError('exactly one real radio beside the actual mode label required')
            radio = radios[0]['attributes']
            if ((radio.get('bundleName') or BUNDLE) != BUNDLE or radio.get('visible') != 'true' or
                    radio.get('enabled') != 'true' or radio.get('clickable') != 'true' or
                    radio.get('checked') != str(mode_id == active).lower()):
                raise ValueError('Settings mode selection is not ready or differs from actual readback')
            rows[mode_id] = {'mode': expected[mode_id], 'label': label,
                             'radio': {'attributes': radio, 'bundle': BUNDLE,
                                       'rect': list(bounds(radio.get('bounds')))}}
        pending.extend((child, bundle, node, depth + 1) for child in children)
    if set(rows) != set(expected):
        raise ValueError('Settings must present every actual current-resolution choice')
    return rows
