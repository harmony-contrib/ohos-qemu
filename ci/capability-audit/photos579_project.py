"""Fixed true2in1 restart callers; original API26 generation/signing retained."""
from pathlib import Path
import hashlib
import json
import re
import apps_providers579_project as original

HERE = Path(__file__).resolve().parent
ROOT = Path('/Volumes/PSSD/code/ohos-rs/ohos-qemu')
PINS = ROOT / '.tmp/parallel-capability-20261016/root-normal-link579-private-source-successors/photos/SOURCE-PINS.json'
ROLES = {'photos': ('normal', 'foreign', 'janitor')}
ACTIONS = {'photos': original.ACTIONS['photos']}
IDS = {'photos': ('behavior:photo-provider-not-activated-2in1',)}
require = original.require


def sources():
    value = json.loads(PINS.read_text())
    require(value['schema'] == 'photos579-2in1-fixed-source-inputs/v1', 'fixed Photos source vector')
    for row in value['files']:
        path = Path(row['path'])
        require(path.is_absolute() and path.resolve() == path and path.is_file() and
            not any(p.is_symlink() for p in (path, *path.parents)) and
            hashlib.sha256(path.read_bytes()).hexdigest() == row['sha256'], 'Photos actual source changed')
    require(Path(original.__file__).resolve() == ROOT / 'ci/capability-audit/apps_providers579_project.py',
        'original project cannot be shadowed')


def validate(case, run, role=None, parameters=None):
    require(case == 'photos' and re.fullmatch('[a-f0-9]{32}', run or '') and
        (role is None or role in ROLES[case]), 'fixed Photos restart case/nonce/role only')
    if parameters is not None:
        require(set(parameters) == {'profile', 'udid'} and parameters['profile'] == '2in1' and
            re.fullmatch('[a-fA-F0-9]{64}', parameters['udid']), 'actual2in1 SDK/UDID required')


def bundle(case, role):
    require(case == 'photos' and role in ROLES[case], 'fixed independent role')
    return 'org.ohos.qemu.photos579.restart.' + role


def module_fields(case, role, parameters=None):
    require(parameters is not None, 'actual2in1 caller profile mandatory')
    validate(case, '0' * 32, role, parameters)
    return original.module_fields(case, role, parameters)


def source_files(case, run, role, parameters=None):
    sources(); validate(case, run, role, parameters)
    result = original.source_files(case, run, role, parameters)
    key = 'entry/src/main/ets/common/Journal.ets'
    before = "export const BUNDLE: string = '" + original.bundle(case, role) + "';"
    require(result[key].count(before) == 1, 'one actual original bundle literal')
    result[key] = result[key].replace(before, "export const BUNDLE: string = '" + bundle(case, role) + "';", 1)
    if role != 'janitor':
        result['entry/src/main/ets/common/Driver.ets'] = (HERE / 'photos579/PhotosDriver.ets').read_text()
    else:
        text = (HERE / 'photos579/JanitorDriver.ets').read_text()
        for old, new in {'__APPS579_RUN__':run,'__APPS579_CASE__':case,
            '__APPS579_ROLE__':role,'__APPS579_BUNDLE__':bundle(case,role)}.items():
            text = text.replace(old,new)
        result['entry/src/main/ets/common/Driver.ets'] = text
    return result


def configure_profile(case):
    require(case == 'photos', 'fixed Photos signing case')
    def configure(profile, role, udid, compiled):
        require(role in ROLES[case] and re.fullmatch('[a-fA-F0-9]{64}', udid or '') and
            compiled['app']['bundleName'] == bundle(case, role) and
            compiled['module']['deviceTypes'] == ['2in1'] and
            [row['name'] for row in compiled['module'].get('requestPermissions', [])] == original.permissions(case, role),
            'actual compiled2in1 roles and least permissions differ')
        system = role == 'janitor'
        profile['bundle-info'].update({'bundle-name': bundle(case, role),
            'apl': 'system_core' if system else 'normal',
            'app-feature': 'hos_system_app' if system else 'hos_normal_app'})
        profile['debug-info']['device-ids'] = [udid]
        profile['acls']['allowed-acls'] = original.permissions(case, role)
        profile['permissions']['restricted-permissions'] = original.permissions(case, role)
        return profile
    return configure
