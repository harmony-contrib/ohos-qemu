#!/usr/bin/env python3
"""Prepare the fixed full CommunicationSetting source with the existing OS signer.

This is production preparation, never a host or guest acceptance result.
The parent serializes the HAP GN block and three shared preinstall documents.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

from calendar_provider import SIGNATURE, certificate_fingerprint
from mms_provider import SIGNING_INPUTS, read, unique, cms, certificates, replace
from preinstall_selection import entry, same_json

PROJECT = 'applications/standard/call'
APP = PROJECT + '/CommunicationSetting'
REVISION = '8383e1930ffb28b512929b913eadf266a4e3a55a'
PROFILE_SHA = '1c0d0273ca25881ed8b8d0423a995b82555f012220b7a6d292c0326382058a17'
PATCH_ROOT = Path(__file__).resolve().parents[1]
BUNDLE = 'com.ohos.communicationsetting'
CAPABILITY = {'bundleName': BUNDLE, 'app_signature': [SIGNATURE],
              'allowAppUsePrivilegeExtension': True}
ACLS = ['ohos.permission.' + name for name in (
    'GET_INSTALLED_BUNDLE_LIST', 'GET_BUNDLE_INFO_PRIVILEGED', 'GET_BUNDLE_RESOURCES',
    'GET_TELEPHONY_STATE', 'MANAGE_NET_STRATEGY', 'GET_NETWORK_STATS',
    'SET_TELEPHONY_STATE', 'MANAGE_SETTINGS', 'ACCESS_SYSTEM_SETTINGS',
    'START_ABILITIES_FROM_BACKGROUND')]
RESTRICTED = ['ohos.permission.' + name for name in ('VIBRATE', 'GET_BUNDLE_INFO', 'GET_NETWORK_INFO')]


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def component(relative):
    path = PATCH_ROOT / 'common' / relative / 'verify_source.py'
    spec = importlib.util.spec_from_file_location('communication_' + relative.replace('/', '_'), path)
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    return guard


def source_ready(root):
    source=component('applications/standard/communicationsetting/source_provider')
    source.prerequisites(root)
    source.validate(root, require_patched=True)
    component('foundation/communication/netmanager_base/net_policy_settings_provider').validate(root, require_patched=True)
    # Parent pins the composed AMS whole-file state with the conditional-stop
    # component. This local anchor is an additional requirement, never a skip.
    ams = read(root / 'foundation/ability/ability_runtime/services/abilitymgr/src/ability_manager_service.cpp').decode()
    stamp = ('    UpdateCallerInfoUtil::GetInstance().UpdateCallerInfoFromToken(abilityRequest.want, callerToken);\n'
             '    sptr<IRemoteObject> parentToken = extensionSessionInfo->parentToken;\n')
    direct='abilityRequest.want.SetParam("ohos.net.policy.callerUid", callerRecord->GetUid());'
    if ams.count(stamp) != 1 or ams.count(direct) != 1:
        raise ValueError('reviewed AMS trusted modal caller stamp is required before export')
    hap = read(root / 'applications/standard/hap/BUILD.gn').decode()
    if hap.count('deps = [ "//applications/standard/call/CommunicationSetting:communicationsetting_hap" ]') != 1:
        raise ValueError('complete real source HAP target is not selected')
    import json5
    for path in (root / APP / 'oh-package.json5', root / APP / 'entry/oh-package.json5'):
        doc = json5.loads(read(path).decode(), allow_duplicate_keys=False)
        for group in ('dependencies', 'devDependencies', 'dynamicDependencies'):
            for name, uri in doc.get(group, {}).items():
                if not isinstance(uri, str) or not uri.startswith('file:'):
                    raise ValueError('nonlocal CommunicationSetting dependency: ' + name)
                target = path.parent / uri[5:]
                if not target.is_dir() or not target.resolve().is_relative_to(root / APP):
                    raise ValueError('missing/escaped CommunicationSetting dependency: ' + name)
    directory = root / 'vendor/ohemu/virt/preinstall-config'
    selected = entry(read(directory / 'install_list.json'), BUNDLE)
    policies = json.loads(read(directory / 'install_list_capability.json'), object_pairs_hook=unique)
    rows = policies['install_list'] if isinstance(policies, dict) else policies
    if not same_json([row for row in rows if row.get('bundleName') == BUNDLE], [CAPABILITY]):
        raise ValueError('exact signer-bound CommunicationSetting privilege-extension policy missing')
    return {'selection': selected, 'capability': CAPABILITY}


def inputs(root):
    if subprocess.check_output(['git', '-C', str(root / PROJECT), 'rev-parse', 'HEAD'], text=True).strip() != REVISION:
        raise ValueError('fixed real CommunicationSetting project required')
    raw = subprocess.check_output(['git', '-C', str(root / PROJECT), 'show',
                                   'HEAD:CommunicationSetting/signature/CommunicationSetting.p7b'])
    if digest(raw) != PROFILE_SHA:
        raise ValueError('fixed original CommunicationSetting profile changed')
    dist = root / 'developtools/hapsigner/dist'
    for name, expected in SIGNING_INPUTS.items():
        if digest(read(dist / name)) != expected:
            raise ValueError('changed existing OS signing input: ' + name)
    app, issuer = (certificates(read(dist / name)) for name in ('OpenHarmonyApplication.pem', 'OpenHarmonyProfileRelease.pem'))
    if len(app) != 3 or len(issuer) != 3 or certificate_fingerprint(app[-1]) != SIGNATURE:
        raise ValueError('fixed OS signer chain changed')
    return dist, raw, app[-1], issuer[-1]


def desired(original, leaf):
    bundle = original.get('bundle-info', {})
    if (bundle.get('bundle-name') != BUNDLE or bundle.get('apl') != 'system_core' or
            bundle.get('app-feature') != 'hos_system_app' or original.get('type') != 'release' or
            original.get('app-distribution-type') != 'os_integration' or
            original.get('acls', {}).get('allowed-acls') != ACLS or
            original.get('permissions', {}).get('restricted-permissions') != RESTRICTED):
        raise ValueError('original identity/APL/ACL/restricted permission contract differs')
    result = copy.deepcopy(original)
    result['bundle-info']['distribution-certificate'] = leaf.decode() + '\n'
    result['validity']['not-after'] = 2208988800
    return result


def verify_profile(path, expected, issuer, scratch):
    signer = scratch / 'issuer.pem'
    actual = cms(path, signer)
    signers = certificates(read(signer))
    if actual != expected or len(signers) != 1 or certificate_fingerprint(signers[0]) != certificate_fingerprint(issuer):
        raise ValueError('CommunicationSetting profile/original OS issuer mismatch')
    return actual



def payload(hap, root, scratch):
    import zipfile
    from pathlib import PurePosixPath
    import json5
    # Reuse the original fixed tool/leaf/profile verification. The original
    # implementation lives beside its script imports, outside patches/lib.
    sys.path.insert(0, str(PATCH_ROOT.parent / 'scripts'))
    from verify_photos_provider_image import verify_signature
    with zipfile.ZipFile(hap) as archive:
        rows=archive.infolist();names=[r.filename for r in rows]
        if len(rows)>10000 or len(set(names))!=len(names) or sum(r.file_size for r in rows)>256*1024*1024:
            raise ValueError('bounded real compiled CommunicationSetting closure required')
        for row in rows:
            path=PurePosixPath(row.filename)
            if (path.is_absolute() or '..' in path.parts or '\\' in row.filename or row.flag_bits&1 or
                (row.external_attr>>16)&0o170000==0o120000):
                raise ValueError('unsafe compiled CommunicationSetting member')
        if not {'module.json','ets/modules.abc','resources.index'}<=set(names):
            raise ValueError('real compiled provider/code/resources missing')
        document=json.loads(archive.read('module.json'),object_pairs_hook=unique)
        app,module=document['app'],document['module']
        if (app.get('bundleName'),app.get('versionCode'),app.get('versionName'),app.get('debug'))!=(BUNDLE,100600338,'6.0.0.338',False):
            raise ValueError('compiled full application identity/version differs')
        source=json5.loads(read(root/APP/'entry/src/main/module.json5').decode(),allow_duplicate_keys=False)['module']
        for key in ('name','type','deviceTypes','mainElement'):
            if not same_json(module.get(key),source.get(key)):
                raise ValueError('compiled provider module boundary differs: '+key)
        if [r['name'] for r in module.get('requestPermissions',[])]!=[r['name'] for r in source['requestPermissions']]:
            raise ValueError('compiled provider acquired/lost a request permission')
        for key in ('abilities','extensionAbilities'):
            actual,expected=module.get(key,[]),source.get(key,[])
            if len(actual)!=len(expected) or [r['name'] for r in actual]!=[r['name'] for r in expected]:
                raise ValueError('compiled extension/ability closure differs')
            for actual_row,source_row in zip(actual,expected):
                for field in ('name','type','permissions','exported','visible'):
                    # Hvigor may emit an explicit false/default for a source
                    # omission. This cannot authorize a new true/export gate.
                    left,right=actual_row.get(field),source_row.get(field)
                    if field in ('exported','visible'):
                        left=False if left is None else left;right=False if right is None else right
                    if not same_json(left,right):
                        raise ValueError('compiled extension admission differs: '+field)
        abc=archive.read('ets/modules.abc')
        if not archive.read('resources.index') or not all(value in abc for value in (
            b'ohos.net.policy.callerUid',b'Network policy caller identity mismatch',
            b'Network policy committed uid:',b'net-policy-dialog-title')):
            raise ValueError('actual compiled trusted provider/await/UI payload absent')
    signature=verify_signature(hap,root,scratch,APP+'/signature/CommunicationSetting.p7b')
    return {'bundle':BUNDLE,'module':'entry','hap_sha256':digest(read(hap)),**signature,
            'scope':'actual compiled-byte/signing admission; QEMU business remains pending'}

def prepare(root, cache):
    policies = source_ready(root)
    dist, raw, leaf, issuer = inputs(root)
    profile = root / APP / 'signature/CommunicationSetting.p7b'
    before = read(profile)
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='communication-profile-', dir=cache) as temporary:
        scratch = Path(temporary)
        original = scratch / 'original.p7b'
        original.write_bytes(raw)
        expected = desired(cms(original), leaf)
        if before == raw:
            template, signed = scratch / 'profile.json', scratch / 'renewed.p7b'
            template.write_text(json.dumps(expected, indent=2) + '\n')
            subprocess.run(['java', '-jar', str(dist / 'hap-sign-tool.jar'), 'sign-profile',
                '-keyAlias', 'openharmony application profile release', '-signAlg', 'SHA256withECDSA',
                '-mode', 'localSign', '-profileCertFile', str(dist / 'OpenHarmonyProfileRelease.pem'),
                '-inFile', str(template), '-keystoreFile', str(dist / 'OpenHarmony.p12'),
                '-outFile', str(signed), '-keyPwd', '123456', '-keystorePwd', '123456'],
                capture_output=True, check=True, timeout=120)
            verify_profile(signed, expected, issuer, scratch)
            if read(profile) != before:
                raise ValueError('source profile changed during preparation')
            replace(profile, read(signed))
        else:
            verify_profile(profile, expected, issuer, scratch)
    return {'scope': 'production source/signing preparation only', 'source_revision': REVISION,
            'profile_sha256': digest(read(profile)), 'signer': SIGNATURE, 'policies': policies,
            'actual_compilation': False, 'runtime_validated': False, 'first_artifact_behavior_gate_passed': False}


def verify(root):
    policies = source_ready(root)
    _, raw, leaf, issuer = inputs(root)
    with tempfile.TemporaryDirectory(prefix='communication-profile-verify-') as temporary:
        scratch = Path(temporary)
        original = scratch / 'original.p7b'
        original.write_bytes(raw)
        actual = verify_profile(root / APP / 'signature/CommunicationSetting.p7b', desired(cms(original), leaf), issuer, scratch)
    return {'profile': actual, 'policies': policies, 'scope': 'read-only production source/signing guard'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--cache-root', type=Path)
    parser.add_argument('--prepare-profile', action='store_true')
    args = parser.parse_args()
    if args.prepare_profile:
        if args.cache_root is None:
            raise ValueError('explicit original Owner cache required')
        result = prepare(args.source_root.resolve(), args.cache_root.resolve())
    else:
        if args.cache_root is not None:
            raise ValueError('read-only source guard does not accept a cache')
        result = verify(args.source_root.resolve())
    print(json.dumps(result, indent=2))
