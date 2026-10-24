"""Activate exact packaged UI providers during the ordinary product build.

This prepares signing and preinstall inputs. It does not accept any capability;
the newly packaged QEMU image must exercise the actual UI and service behavior.
"""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import os
import re
import subprocess
import tempfile
import zipfile

from calendar_provider import SIGNATURE, certificate_fingerprint
from locationdialog_provider import prepare as prepare_location
from mms_provider import (CAPABILITY as MMS_CAPABILITY, SIGNING_INPUTS,
                          certificates, cms, read, replace, unique)

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
# Ordinary applications already packaged by the product, but omitted from its
# boot-time selection. These need no extra privilege or permission grant row.
LOCAL_PREINSTALL = ('/system/app/com.ohos.calendar',
                    '/system/app/com.ohos.filemanager',
                    '/system/app/com.ohos.soundrecorder')
# Verified leaf certificates of the actual packaged HAPs. The retained official
# Camera/Clock/CallUI/Spooler inputs use a different key from source-built DLP.
PREBUILT_SIGNER = '0716E4E8C9B8CEEF6A974CD2289D5C4C668A5B41FA5DF8C0542DCB72602371F5'
EXTENSION_SIGNERS = {'com.ohos.camera': PREBUILT_SIGNER,
                     'com.ohos.clock': PREBUILT_SIGNER,
                     'com.ohos.callui': PREBUILT_SIGNER,
                     'com.ohos.dlpmanager': SIGNATURE,
                     'com.ohos.spooler': PREBUILT_SIGNER}
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


def policy_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def mms_extension(capabilities):
    rows = [row for row in capabilities['install_list']
            if row.get('bundleName') == 'com.ohos.mms']
    desired = dict(MMS_CAPABILITY, app_signature=[SIGNATURE])
    legacy = dict(desired)
    del legacy['allowAppUsePrivilegeExtension']
    if len(rows) != 1 or policy_bytes(rows[0]) not in (policy_bytes(legacy), policy_bytes(desired)):
        raise ValueError('fixed MMS policy identity changed before provider activation')
    rows[0].update(desired)


def command(argv, commands):
    completed = subprocess.run(argv, capture_output=True, text=True, timeout=120)
    row = {'argv': argv, 'exit_code': completed.returncode,
           'stdout': completed.stdout, 'stderr': completed.stderr}
    commands.append(row)
    if completed.returncode:
        raise ValueError('provider signing input command failed: ' + argv[3])
    return row


def payload(hap, bundle):
    with zipfile.ZipFile(hap) as archive:
        module = json.loads(archive.read('module.json'), object_pairs_hook=unique)
        if not archive.read('ets/modules.abc') or module['app']['bundleName'] != bundle:
            raise ValueError('selected provider bundle/ABC differs: ' + bundle)
        members = archive.infolist()
        if len({item.filename for item in members}) != len(members):
            raise ValueError('duplicate provider archive member')
        files = {item.filename: hashlib.sha256(archive.read(item)).hexdigest() for item in members}
    delivered = {entry['name'] for kind in ('abilities', 'extensionAbilities')
                 for entry in module['module'].get(kind, [])}
    if not set(PREBUILT[bundle][2]) <= delivered:
        raise ValueError('selected provider lacks its real entrypoint: ' + bundle)
    return module, files


def verify_hap(root, hap, bundle, scratch, commands):
    scratch.mkdir(exist_ok=True)
    module, files = payload(hap, bundle)
    leaf_file, profile = scratch / 'chain.cer', scratch / 'profile.p7b'
    argv = ['java', '-jar', str(root / 'developtools/hapsigner/dist/hap-sign-tool.jar'),
        'verify-app', '-inFile', str(hap), '-outCertChain', str(leaf_file), '-outProfile', str(profile)]
    row = command(argv, commands)
    text = row['stdout'] + row['stderr']
    required = ('verify codesign success', 'Digest verify result: true', 'verify-app success')
    # The pinned official Portal/Media/DND inputs can use the original v2
    # signing block. The real signer verifies that block but emits the v3
    # permission-sign marker only for v3. Authenticate its embedded CMS too.
    profile_verified = ('verify permission sign success' in text or
        re.search(r'version is: 2, number of block is: 1\b', text) is not None and
        'verify: Verify success' in text)
    leaf = re.search(r'certificate\s*#0\b(?:(?!certificate\s*#\d).)*?SHA256:\s*([A-Fa-f0-9:]{64,95})', text, re.S)
    if (not all(s in text for s in required) or not profile_verified or
            not leaf or not leaf_file.is_file()):
        raise ValueError('actual provider cryptographic input verification failed: ' + bundle)
    signature = leaf[1].replace(':', '').upper()
    if not re.fullmatch('[A-F0-9]{64}', signature):
        raise ValueError('actual provider leaf SHA256 missing')
    issuer_file = scratch / 'profile-issuer.pem'
    provision = cms(profile, issuer_file)
    if (provision['bundle-info']['bundle-name'] != bundle or
            provision['bundle-info']['app-feature'] != 'hos_system_app'):
        raise ValueError('selected provider is not its pinned system application: ' + bundle)
    return {'hap': record(hap), 'embedded_profile': record(profile), 'signer': signature,
            'module': module, 'payload_sha256': files, 'profile': provision,
            'profile_issuer': record(issuer_file), 'verification': row}


def prepare_prebuilt(root, bundle, scratch, commands):
    name, expected, _ = PREBUILT[bundle]
    original = root / 'applications/standard/hap/sceneboard' / name
    if record(original)['sha256'] != expected:
        raise ValueError('selected official provider HAP changed: ' + bundle)
    source = verify_hap(root, original, bundle, scratch / 'original', commands)
    dist = root / 'developtools/hapsigner/dist'
    app_chain = certificates(read(dist / 'OpenHarmonyApplication.pem'))
    issuer_chain = certificates(read(dist / 'OpenHarmonyProfileRelease.pem'))
    if (len(app_chain) != 3 or len(issuer_chain) != 3 or
            certificate_fingerprint(app_chain[-1]) != SIGNATURE):
        raise ValueError('existing OS signing certificate chain differs')
    # These exact legacy inputs have an authenticated profile for a different
    # distribution certificate. Keep every payload byte and the original APL,
    # ACL, permissions, app identifier and validity; change only that certificate.
    desired = copy.deepcopy(source['profile'])
    desired['bundle-info']['distribution-certificate'] = (app_chain[-1] + b'\n').decode()
    directory = root / 'applications/standard/hap/qemu_ui_provider_inputs'
    directory.mkdir(exist_ok=True)
    if any(p.is_symlink() for p in (directory, *directory.parents)) or not directory.is_dir():
        raise ValueError('regular build-owned provider input directory required')
    destination = directory / name

    def verify_prepared(path):
        actual = verify_hap(root, path, bundle, scratch / 'prepared', commands)
        signers = certificates(read(Path(actual['profile_issuer']['path'])))
        if (actual['signer'] != SIGNATURE or actual['profile'] != desired or
                actual['payload_sha256'] != source['payload_sha256'] or len(signers) != 1 or
                certificate_fingerprint(signers[0]) != certificate_fingerprint(issuer_chain[-1])):
            raise ValueError('prepared provider payload/profile/OS signer differs: ' + bundle)
        return actual

    if destination.exists() or destination.is_symlink():
        read(destination)  # Never replace an unknown previously staged artifact.
        prepared = verify_prepared(destination)
    else:
        with tempfile.TemporaryDirectory(prefix='.qemu-ui-provider-', dir=directory) as temporary:
            work = Path(temporary)
            template, signed_profile, unsigned, signed = (work / value for value in
                ('profile.json', 'profile.p7b', 'unsigned.hap', 'signed.hap'))
            template.write_text(json.dumps(desired, indent=2) + '\n')
            command(['java', '-jar', str(dist / 'hap-sign-tool.jar'), 'sign-profile',
                '-keyAlias', 'openharmony application profile release', '-signAlg', 'SHA256withECDSA',
                '-mode', 'localSign', '-profileCertFile', str(dist / 'OpenHarmonyProfileRelease.pem'),
                '-inFile', str(template), '-keystoreFile', str(dist / 'OpenHarmony.p12'),
                '-outFile', str(signed_profile), '-keyPwd', '123456', '-keystorePwd', '123456'], commands)
            # Rewriting the ordinary ZIP removes its old outer signing block.
            # Copy ZipInfo and all entries; no module/ABC/resource edits occur.
            with zipfile.ZipFile(original) as old, zipfile.ZipFile(unsigned, 'w', allowZip64=False) as new:
                for member in old.infolist():
                    new.writestr(member, old.read(member))
                new.comment = old.comment
            command(['java', '-jar', str(dist / 'hap-sign-tool.jar'), 'sign-app',
                '-keyAlias', 'openharmony application release', '-signAlg', 'SHA256withECDSA',
                '-mode', 'localSign', '-appCertFile', str(dist / 'OpenHarmonyApplication.pem'),
                '-profileFile', str(signed_profile), '-inFile', str(unsigned),
                '-keystoreFile', str(dist / 'OpenHarmony.p12'), '-outFile', str(signed),
                '-keyPwd', '123456', '-keystorePwd', '123456', '-signCode', '1'], commands)
            verify_prepared(signed)
            # Exclusive publication cannot overwrite another producer's file.
            with signed.open('rb') as stream:
                os.fsync(stream.fileno())
            os.link(signed, destination)
        prepared = verify_prepared(destination)
    if record(original)['sha256'] != expected:
        raise ValueError('original provider input changed during preparation')
    prepared['original_input'] = source
    prepared['scope'] = 'normal OS signing input preparation; QEMU install and behavior pending'
    return prepared


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
            report['providers'][bundle] = prepare_prebuilt(root, bundle, scratch, report['commands'])
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
        # Keep the complete C42 output as an exact migration predecessor. MMS
        # runs before this transaction and can already have upgraded its row.
        names = ('install_list.json', 'install_list_capability.json')
        legacy = (policy_bytes(install), policy_bytes(capabilities))
        original = tuple(read(ASSETS / 'before' / name) for name in names)
        base_mms = json.loads(original[1], object_pairs_hook=unique)
        mms_extension(base_mms)
        legacy_mms = copy.deepcopy(capabilities)
        mms_extension(legacy_mms)
        allowed = {original, (original[0], policy_bytes(base_mms)),
                   legacy, (legacy[0], policy_bytes(legacy_mms))}

        if set(LOCAL_PREINSTALL) & {row['app_dir'] for row in install['install_list']}:
            raise ValueError('ordinary application selection predecessor changed')
        install['install_list'].extend({'app_dir': directory, 'removable': False}
                                      for directory in LOCAL_PREINSTALL)
        mms_extension(capabilities)
        for bundle, signature in EXTENSION_SIGNERS.items():
            rows = [row for row in cap_rows if row.get('bundleName') == bundle]
            if len(rows) > 1:
                raise ValueError('duplicate fixed extension policy: ' + bundle)
            if rows:
                capability = rows[0]
                capability['app_signature'] = [signature]
            else:
                capability = {'bundleName': bundle, 'app_signature': [signature]}
                cap_rows.append(capability)
            capability['allowAppUsePrivilegeExtension'] = True
        caption = [row for row in cap_rows if row.get('bundleName') == 'com.ohos.vassistant']
        if len(caption) != 1:
            raise ValueError('fixed caption policy identity changed')
        caption[0]['allowAppUsePrivilegeExtension'] = True
        pending = dict(zip(names, (policy_bytes(install), policy_bytes(capabilities))))
        allowed.add(tuple(pending[name] for name in names))
        # No broad privilege wildcard or new user-grant row is introduced.
        if hashlib.sha256(before['install_list_permissions.json']).hexdigest() != POLICIES['install_list_permissions.json']:
            raise ValueError('unrelated product user-grant policy changed')
        if tuple(before[name] for name in names) not in allowed:
            raise ValueError('unknown complete product policy pair; preserve it')
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
