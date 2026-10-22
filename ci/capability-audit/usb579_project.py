"""Two ordinary callers through the original normal SDK and signer."""
from pathlib import Path
import json
import re

HERE = Path(__file__).resolve().parent
ROLES = ('a', 'b')


def require(ok, text):
    if not ok: raise ValueError(text)


def bundle(case, role):
    require(case == 'shared-device' and role in ROLES, 'fixed real USB case and ordinary role')
    return 'org.harmonycontrib.usb579.' + role


def module_fields(case, role, parameters=None):
    bundle(case, role); require(parameters in (None, {}), 'no caller action/permission from DATA')
    return dict(requestPermissions=[], extensionAbilities=[], abilities=[dict(name='EntryAbility',
        srcEntry='./ets/entryability/EntryAbility.ets', exported=True, launchType='singleton')])


def source_files(case, run, role, parameters=None):
    bundle(case, role); require(re.fullmatch('[a-f0-9]{32}', run) and parameters in (None, {}), 'one fresh actual source nonce')
    result = {}
    for name, destination in {'UsbAudit.ets':'entry/src/main/ets/entryability/UsbAudit.ets',
        'EntryAbility.ets':'entry/src/main/ets/entryability/EntryAbility.ets','Index.ets':'entry/src/main/ets/pages/Index.ets'}.items():
        text = (HERE / 'usb579' / name).read_text()
        if name == 'UsbAudit.ets':
            require(text.count('__USB579_RUN__') == text.count('__USB579_ROLE__') == 1, 'fixed normal source markers')
            text = text.replace('__USB579_RUN__', run).replace('__USB579_ROLE__', role)
        result[destination] = text
    result['entry/src/main/resources/base/profile/main_pages.json'] = '{"src":["pages/Index"]}\n'
    return result


def configure_profile(case):
    require(case == 'shared-device', 'fixed supplemental SDK family')
    def configure(profile, role, udid, compiled):
        require(re.fullmatch('[a-fA-F0-9]{64}', udid or '') and compiled['app']['bundleName'] == bundle(case, role),
            'actual ordinary source bundle and original guest UDID')
        require(compiled['module'].get('requestPermissions', []) == [] and
            compiled['module'].get('extensionAbilities', []) == [] and len(compiled['module']['abilities']) == 1 and
            compiled['module']['abilities'][0]['name'] == 'EntryAbility' and
            compiled['module']['abilities'][0]['launchType'] == 'singleton', 'ordinary compiled native USB right boundary')
        profile['bundle-info'].update({'bundle-name':bundle(case, role), 'apl':'normal', 'app-feature':'hos_normal_app'})
        profile['debug-info']['device-ids'] = [udid]; profile['acls']['allowed-acls'] = []
        profile['permissions']['restricted-permissions'] = []
        return profile
    return configure
