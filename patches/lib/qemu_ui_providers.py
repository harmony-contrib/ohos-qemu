"""Activate exact packaged UI providers during the ordinary product build.

This prepares signing and preinstall inputs. It does not accept any capability;
the newly packaged QEMU image must exercise the actual UI and service behavior.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess
import zipfile

from calendar_provider import SIGNATURE, certificate_fingerprint
from locationdialog_provider import prepare as prepare_location
from mms_provider import SIGNING_INPUTS, cms, read, replace, unique

ASSETS = Path(__file__).resolve().parents[1] / 'common/vendor/ohemu/virt/ui_provider_activation'
BASE = 'vendor/ohemu/virt/preinstall-config/'
PROVIDERS = {
    'com.ohos.locationdialog': '/system/app/LocationDialog',
    'com.wifiservice.portallogin': '/system/app/com.wifiservice.portallogin',
    'com.hmos.mediacontroller': '/system/app/com.hmos.mediacontroller',
    'com.ohos.intelligentscene': '/system/app/com.ohos.intelligentscene',
    'com.ohos.callsetting': '/system/app/com.ohos.callsetting',
    'com.ohos.communicationsetting': '/system/app/com.ohos.communicationsetting',
    'com.ohos.vassistant': '/system/app/com.ohos.vassistant'}
PREBUILT = {
    'com.wifiservice.portallogin': ('PortalLogin.hap',
        'd650d0a1bbd744d1bdf8cfcc4ca16ca51cecdc2b96c09d8f358897a54da00185', ('EntryAbility',)),
    'com.hmos.mediacontroller': ('mediacontroller.hap',
        '1118c178e106bfd49bcff5de099daa8f24166595acac24941077e4cde60cd2d3', ('UIExtAbility', 'AVVolumeExtension')),
    'com.ohos.intelligentscene': ('Intelligent_Scene.hap',
        'b328caf535c073768f50d52fcea8d1ced786f13479706e8085fb0553d163b420', ('IntelligentSceneUIExtSettingAbility',))}
POLICIES = {
    'install_list.json': 'c373f96100e8b7263bd51d057f17b695d1a48890c3c48bc84f458a026b6c9ea5',
    'install_list_capability.json': '2ce081c3d8b929070f4ced1a46298c7d019afcba0e83a6c1e6973cd1df653701',
    'install_list_permissions.json': 'fb3e91e110c26d882f2dd4653c908836c6cac8b22ba17c783429e63b304abc87'}


def record(path):
    data = read(path)
    return {'path': str(path), 'sha256': hashlib.sha256(data).hexdigest(), 'bytes': len(data)}


def verify_prebuilt(root, bundle, scratch, commands):
    name, expected, extensions = PREBUILT[bundle]
    hap = root / 'applications/standard/hap/sceneboard' / name
    if record(hap)['sha256'] != expected:
        raise ValueError('selected official provider HAP changed: ' + bundle)
    with zipfile.ZipFile(hap) as archive:
        module = json.loads(archive.read('module.json'), object_pairs_hook=unique)
        if not archive.read('ets/modules.abc') or module['app']['bundleName'] != bundle:
            raise ValueError('selected provider bundle/ABC differs: ' + bundle)
    delivered = {entry['name'] for kind in ('abilities', 'extensionAbilities')
                 for entry in module['module'].get(kind, [])}
    if not set(extensions) <= delivered:
        raise ValueError('selected provider lacks its real entrypoint: ' + bundle)
    leaf_file, profile = scratch / 'chain.cer', scratch / 'profile.p7b'
    argv = ['java', '-jar', str(root / 'developtools/hapsigner/dist/hap-sign-tool.jar'),
        'verify-app', '-inFile', str(hap), '-outCertChain', str(leaf_file), '-outProfile', str(profile)]
    completed = subprocess.run(argv, capture_output=True, text=True, timeout=120)
    row = {'argv': argv, 'exit_code': completed.returncode,
           'stdout': completed.stdout, 'stderr': completed.stderr}
    commands.append(row)
    text = completed.stdout + completed.stderr
    required = ('verify codesign success', 'Digest verify result: true',
                'verify permission sign success', 'verify-app success')
    leaf = re.search(r'certificate\s*#0\b(?:(?!certificate\s*#\d).)*?SHA256:\s*([A-Fa-f0-9:]{64,95})', text, re.S)
    if completed.returncode or not all(s in text for s in required) or not leaf or not leaf_file.is_file():
        raise ValueError('actual provider cryptographic input verification failed: ' + bundle)
    signature = leaf[1].replace(':', '').upper()
    if not re.fullmatch('[A-F0-9]{64}', signature):
        raise ValueError('actual provider leaf SHA256 missing')
    provision = cms(profile)
    if (provision['bundle-info']['bundle-name'] != bundle or
            provision['bundle-info']['app-feature'] != 'hos_system_app' or
            certificate_fingerprint(provision['bundle-info']['distribution-certificate'].encode()) != signature):
        raise ValueError('selected provider is not its actual system application: ' + bundle)
    return {'hap': record(hap), 'embedded_profile': record(profile), 'signer': signature,
            'module': module, 'verification': row}


def prepare(root, cache):
    cache.mkdir(parents=True, exist_ok=True)
    if cache.is_symlink() or not cache.is_dir():
        raise ValueError('original build-owned cache directory required')
    dist = root / 'developtools/hapsigner/dist'
    for name, expected in SIGNING_INPUTS.items():
        if record(dist / name)['sha256'] != expected:
            raise ValueError('existing OS signing input changed: ' + name)
    report = {'scope': 'exact product provider/preinstall input preparation; NOT QEMU acceptance',
              'commands': [], 'providers': {}, 'first_artifact_behavior_gate_passed': False}
    report_path = cache / 'provider-inputs.json'
    try:
        for bundle in PREBUILT:
            scratch = cache / bundle
            scratch.mkdir(exist_ok=True)
            report['providers'][bundle] = verify_prebuilt(root, bundle, scratch, report['commands'])
        # These two complete source HAPs are subsequently built and signed by
        # the original product GN pipeline with the existing public OS key.
        location = prepare_location(root)
        report['providers']['com.ohos.locationdialog'] = location
        report['providers']['com.ohos.communicationsetting'] = {
            'signer': SIGNATURE, 'source_profile_preparation': 'communicationsetting_provider follows this transaction',
            'compiled_HAP_and_actual_guest_binding': 'pending'}
        for bundle, helper in (
                ('com.ohos.callsetting', 'dialog_providers579/callsetting'),
                ('com.ohos.certmanager', 'dialog_providers579/certmanager'),
                ('com.ohos.vassistant', 'livecaptions_provider')):
            report['providers'][bundle] = {'signer': SIGNATURE,
                'source_profile_preparation': helper + ' follows this transaction',
                'compiled_HAP_and_actual_guest_binding': 'pending'}
        signatures = {bundle: value['signer'] for bundle, value in report['providers'].items()}
        before = {}
        originals = {}
        for name, expected in POLICIES.items():
            original = read(ASSETS / 'before' / name)
            if hashlib.sha256(original).hexdigest() != expected:
                raise ValueError('fixed complete product policy predecessor changed: ' + name)
            originals[name] = json.loads(original, object_pairs_hook=unique)
            before[name] = read(root / BASE / name)
        install = originals['install_list.json']
        capabilities = originals['install_list_capability.json']
        paths = {row['app_dir'] for row in install['install_list']}
        cap_rows = capabilities['install_list']
        if (set(PROVIDERS.values()) & paths or
                any(row.get('bundleName') in set(PROVIDERS) | {'com.ohos.certmanager'} for row in cap_rows)):
            raise ValueError('original provider activation predecessor is not empty')
        for bundle, directory in PROVIDERS.items():
            install['install_list'].append({'app_dir': directory, 'removable': False})
            capability = {'bundleName': bundle, 'app_signature': [signatures[bundle]]}
            if bundle == 'com.ohos.vassistant':
                capability.update(keepAlive=False, allowAppDesktopIconHide=True)
            else:
                capability['allowAppUsePrivilegeExtension'] = True
            cap_rows.append(capability)
        # The original CertificateManager directory and removability already
        # select this source app; its actual bundle has a different spelling.
        if [r for r in install['install_list'] if r.get('app_dir') ==
                '/system/app/com.ohos.certificatemanager'] != [
                    {'app_dir': '/system/app/com.ohos.certificatemanager', 'removable': True}]:
            raise ValueError('original CertificateManager install selection changed')
        cap_rows.append({'bundleName': 'com.ohos.certmanager',
                         'app_signature': [signatures['com.ohos.certmanager']]})
        pending = {'install_list.json': (json.dumps(install, indent=2) + '\n').encode(),
                   'install_list_capability.json': (json.dumps(capabilities, indent=2) + '\n').encode()}
        # No broad privilege wildcard or new user-grant row is introduced.
        if hashlib.sha256(before['install_list_permissions.json']).hexdigest() != POLICIES['install_list_permissions.json']:
            raise ValueError('unrelated product user-grant policy changed')
        for name, after in pending.items():
            if before[name] not in (read(ASSETS / 'before' / name), after):
                raise ValueError('unknown complete product policy; preserve it: ' + name)
        written = []
        try:
            for name in pending:
                if read(root / BASE / name) != before[name]:
                    raise ValueError('product policy changed before activation transaction')
            for name, after in pending.items():
                if before[name] != after:
                    replace(root / BASE / name, after)
                    written.append(name)
        except BaseException:
            for name in reversed(written):
                if read(root / BASE / name) == pending[name]:
                    replace(root / BASE / name, before[name])
            raise
        report['policy_inputs'] = {name: record(root / BASE / name) for name in POLICIES}
        return report
    finally:
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--cache-root', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source_root.resolve(), args.cache_root.resolve()), ensure_ascii=False, indent=2))
