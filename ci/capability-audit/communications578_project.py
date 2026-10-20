"""Exact overlays for the root's existing real API26 builder/signer; no tools."""
from pathlib import Path
import re
from communications578_contract import PERMISSIONS
from communications578_raw import require

ASSETS = Path(__file__).with_name('communications578')
ROLES = ('system', 'denied', 'ordinary', 'system_peer', 'system_replacement')
CASES = ('public', 'lifecycle')


def bundle(case, role):
    require(case in CASES and role in ROLES, 'Fixed communications case/role required')
    return 'org.harmonycontrib.communications578.' + case + '.' + role.replace('_', '')


def permissions(case, role):
    bundle(case, role)
    return [] if role == 'denied' else list(PERMISSIONS)


def module_fields(case, role, parameters=None):
    bundle(case, role)
    return {'requestPermissions': [{'name': p, 'reason': '$string:communications578_permission',
                'usedScene': {'abilities': ['EntryAbility'], 'when': 'inuse'}} for p in permissions(case, role)],
            'abilities': [{'name': 'EntryAbility', 'srcEntry': './ets/entryability/EntryAbility.ets',
                'exported': True, 'launchType': 'singleton'}], 'extensionAbilities': []}


def source_files(case, run, role, parameters=None):
    bundle(case, role); require(re.fullmatch('[a-f0-9]{32}', run or ''), 'Actual original Owner run required')
    mapping = {'EntryAbility.ets': 'entry/src/main/ets/entryability/EntryAbility.ets',
               'CommunicationsAudit.js': 'entry/src/main/ets/entryability/CommunicationsAudit.js',
               'Index.ets': 'entry/src/main/ets/pages/Index.ets'}
    out = {}
    for source, dest in mapping.items():
        text = (ASSETS / source).read_text()
        if source == 'CommunicationsAudit.js':
            require(text.count('__COMMUNICATIONS578_RUN__') == 1, 'Exactly one source run marker required')
            text = text.replace('__COMMUNICATIONS578_RUN__', run)
        out[dest] = text
    out['entry/src/main/resources/base/profile/main_pages.json'] = '{"src":["pages/Index"]}\n'
    out['entry/src/main/resources/base/element/communications578.json'] = '{"string":[{"name":"communications578_permission","value":"Validate communication APIs on this QEMU image"}]}\n'
    return out


def configure_profile(case):
    require(case in CASES, 'Fixed communications case required')
    def configure(profile, role, udid, compiled):
        require(role in ROLES and re.fullmatch('[a-fA-F0-9]{64}', udid or ''), 'Actual same-boot UDID and fixed role required')
        require(compiled['app']['bundleName'] == bundle(case, role), 'Actual compiled bundle differs')
        wanted = module_fields(case, role)
        actual_permissions = compiled['module'].get('requestPermissions', [])
        require([p['name'] for p in actual_permissions] == permissions(case, role) and
                compiled['module'].get('extensionAbilities', []) == [] and
                len(compiled['module'].get('abilities', [])) == 1 and
                compiled['module']['abilities'][0].get('launchType') == 'singleton', 'Actual compiled singleton/permission contract differs')
        profile['bundle-info']['bundle-name'] = bundle(case, role)
        profile['bundle-info']['apl'] = 'normal' if role == 'ordinary' else 'system_core'
        profile['bundle-info']['app-feature'] = 'hos_normal_app' if role == 'ordinary' else 'hos_system_app'
        profile['debug-info']['device-ids'] = [udid]
        profile['acls']['allowed-acls'] = permissions(case, role)
        profile['permissions']['restricted-permissions'] = permissions(case, role)
        return profile
    return configure


def native_sources():
    """Fixed native helper inputs; root queries actual GN compile/link commands."""
    from communications578_native import gn_contract, helper_recipes
    return {'gn': str(ASSETS / 'BUILD.gn'), 'recipes': helper_recipes(), 'targets': gn_contract()}
