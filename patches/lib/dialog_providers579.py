#!/usr/bin/env python3
"""Production preparation for two fixed real dialog providers, never a test.

The parent owns source selection, shared BMS policies, actual build/sign/package
and held guest validation. The finite provider enum cannot choose arbitrary
source, an executable or a different signing identity.
"""
import argparse
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
import zipfile

from calendar_provider import SIGNATURE, certificate_fingerprint
from mms_provider import SIGNING_INPUTS, read, unique, cms, certificates, replace
from preinstall_selection import same_json

PATCH_ROOT = Path(__file__).resolve().parents[1]
LOTTIE_SHA256 = 'c05579c5378e6ac696a4c36e7ae0a1fde09f611bc47ec198fc91100c8db2cbc5'
LOTTIE_BYTES = 193331
LOTTIE_RELATIVE = 'applications/standard/call/CallSetting/product/default/libs/lottie-2.0.23.har'


def lottie_ready(root):
    path = root / LOTTIE_RELATIVE
    value = read(path)
    if len(value) != LOTTIE_BYTES or digest(value) != LOTTIE_SHA256:
        raise ValueError('actual original Lottie 2.0.23 production HAR differs')
    return {'path': str(path), 'sha256': LOTTIE_SHA256, 'bytes': LOTTIE_BYTES}


def create_input(path, value):
    # Producer inputs are new ordinary files. Never overwrite a concurrent or
    # unknown file, and do not reuse replace(), whose profile target must exist.
    with tempfile.NamedTemporaryFile(prefix='.dialog579-input-', dir=path.parent, delete=False) as stream:
        pending = Path(stream.name)
        try:
            stream.write(value); stream.flush(); os.fsync(stream.fileno())
            os.chmod(pending, 0o644)
            os.link(pending, path)
        finally:
            pending.unlink(missing_ok=True)


def stage_lottie(root, cache, reference):
    if reference is None:
        raise ValueError('root actual production Lottie HAR Ref is required; no registry fallback')
    from livecaptions579_inputs import _resolve_artifact_path
    row = json.loads(read(reference), object_pairs_hook=unique)
    if (set(row) not in ({'path', 'sha256'}, {'path', 'sha256', 'bytes'}) or
        row.get('sha256') != LOTTIE_SHA256 or row.get('bytes', LOTTIE_BYTES) != LOTTIE_BYTES or
        not isinstance(row.get('path'), str)):
        raise ValueError('fixed original Lottie HAR Ref required')
    resolved_lottie = _resolve_artifact_path(row['path'])
    if not resolved_lottie.is_file():
        candidate = Path(reference).resolve().parent / 'lottie/lottie-2.0.23.har'
        if candidate.is_file():
            resolved_lottie = candidate
    value = read(resolved_lottie)
    if len(value) != LOTTIE_BYTES or digest(value) != LOTTIE_SHA256:
        raise ValueError('root actual Lottie HAR bytes differ from its fixed production source')
    cached = cache / 'lottie-2.0.23.har'
    if cached.exists():
        if read(cached) != value: raise ValueError('owned Lottie cache contains different bytes')
    else:
        create_input(cached, value)
    destination = root / LOTTIE_RELATIVE
    if any(path.is_symlink() for path in (destination, *destination.parents)):
        raise ValueError('Lottie production input path must not be a symlink')
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if read(destination) != value: raise ValueError('existing source Lottie input differs')
    else:
        create_input(destination, value)
    return lottie_ready(root)

CONFIG = {
    'callsetting': {
        'project': 'applications/standard/call',
        'revision': '8383e1930ffb28b512929b913eadf266a4e3a55a',
        'app': 'applications/standard/call/CallSetting',
        'module': 'product/default', 'bundle': 'com.ohos.callsetting',
        'profile': 'CallSetting/signature/callsetting.p7b',
        'profile_sha256': 'd399c88bf25c38e3711c1a5a96afdb7fc77b6bd631fd5c76d00e440fcc663f23',
        'install': '/system/app/com.ohos.callsetting', 'removable': False,
        'component': 'applications/standard/callsetting/source_provider',
        'native': 'base/telephony/cellular_data/apn_settings_provider',
        'capability': {'bundleName': 'com.ohos.callsetting', 'app_signature': [SIGNATURE],
                       'allowAppUsePrivilegeExtension': True},
        'markers': [b'SYSTEM_APN_SETTINGS', b'GeneralCallSettingDialogAbility', b'system-apn-settings-navigation'],
    },
    'certmanager': {
        'project': 'applications/standard/user_certificate_manager',
        'revision': '0acf067c28bc3957759d288835762ee0209e9fbe',
        'app': 'applications/standard/user_certificate_manager',
        'module': 'certmanager', 'bundle': 'com.ohos.certmanager',
        'profile': 'signature/privacyCenter.p7b',
        'profile_sha256': 'b634bfec72b32ab4073ce79e190a01e08764ad473d330df4ccc26259264ff0c9',
        # This actual installed directory deliberately differs from the bundle.
        'install': '/system/app/com.ohos.certificatemanager', 'removable': True,
        'component': 'applications/standard/user_certificate_manager/ca_uninstall',
        'native': 'base/security/certificate_manager/ca_uninstall_dialog',
        'capability': {'bundleName': 'com.ohos.certmanager', 'app_signature': [SIGNATURE]},
        'markers': [b'CertificateUninstallPage', b'cert-uninstall-confirm', b'CA uninstall committed uri:'],
    },
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def component(relative):
    path = PATCH_ROOT / 'common' / relative / 'verify_source.py'
    spec = importlib.util.spec_from_file_location('dialog579_' + relative.replace('/', '_'), path)
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    return guard


def source_ready(root, provider, require_lottie=True):
    config = CONFIG[provider]
    guard = component(config['component'])
    guard.prerequisites(root)
    guard.validate(root, require_patched=True)
    native = component(config['native'])
    native.prerequisites(root)
    native.validate(root, require_patched=True)
    directory = root / 'vendor/ohemu/virt/preinstall-config'
    selected = json.loads(read(directory / 'install_list.json'), object_pairs_hook=unique)
    matches = [row for row in selected['install_list'] if row.get('app_dir') == config['install']]
    if not same_json(matches, [{'app_dir': config['install'], 'removable': config['removable']}]):
        raise ValueError('exact real installed directory/removability missing: ' + provider)
    policy = json.loads(read(directory / 'install_list_capability.json'), object_pairs_hook=unique)
    rows = policy['install_list'] if isinstance(policy, dict) else policy
    if not same_json([row for row in rows if row.get('bundleName') == config['bundle']], [config['capability']]):
        raise ValueError('exact OS signer-bound provider capability missing: ' + provider)
    if provider == 'callsetting':
        hap = read(root / 'applications/standard/hap/BUILD.gn').decode()
        if hap.count('deps = [ "//applications/standard/call/CallSetting:callsetting_hap" ]') != 1:
            raise ValueError('actual selected CallSetting target is still a prebuilt')
    result = {'selection': matches[0], 'capability': config['capability']}
    if provider == 'callsetting' and require_lottie:
        result['lottie'] = lottie_ready(root)
    return result


def inputs(root, provider):
    config = CONFIG[provider]
    if subprocess.check_output(['git', '-C', str(root / config['project']), 'rev-parse', 'HEAD'], text=True).strip() != config['revision']:
        raise ValueError('fixed real dialog provider project required')
    original = subprocess.check_output(['git', '-C', str(root / config['project']), 'show', 'HEAD:' + config['profile']])
    if digest(original) != config['profile_sha256']:
        raise ValueError('fixed original provider profile differs')
    dist = root / 'developtools/hapsigner/dist'
    for name, expected in SIGNING_INPUTS.items():
        if digest(read(dist / name)) != expected:
            raise ValueError('changed original OS signer input: ' + name)
    application = certificates(read(dist / 'OpenHarmonyApplication.pem'))
    issuers = certificates(read(dist / 'OpenHarmonyProfileRelease.pem'))
    if len(application) != 3 or len(issuers) != 3 or certificate_fingerprint(application[-1]) != SIGNATURE:
        raise ValueError('existing OS signer chain differs')
    return dist, original, application[-1], issuers[-1]


def desired(original, leaf, provider):
    config = CONFIG[provider]
    bundle = original['bundle-info']
    if (bundle.get('bundle-name') != config['bundle'] or original.get('type') != 'release' or
        original.get('app-distribution-type') != 'os_integration' or
        not isinstance(bundle.get('apl'), str) or not original.get('acls', {}).get('allowed-acls')):
        raise ValueError('fixed original profile identity/type/privilege data invalid')
    # The complete original signed profile was pinned above. Retain its APL,
    # ACLs, restricted permissions, features, debug/privilege and all other keys.
    result = copy.deepcopy(original)
    result['bundle-info']['distribution-certificate'] = leaf.decode() + '\n'
    result['validity']['not-after'] = 2208988800
    return result


def verify_profile(path, expected, issuer, scratch):
    signer = scratch / 'profile-issuer.pem'
    actual = cms(path, signer)
    chain = certificates(read(signer))
    if actual != expected or len(chain) != 1 or certificate_fingerprint(chain[0]) != certificate_fingerprint(issuer):
        raise ValueError('actual profile fields or original OS issuer mismatch')
    return actual


def prepare(root, cache, provider, lottie_input=None):
    policies = source_ready(root, provider, require_lottie=False)
    dist, original, leaf, issuer = inputs(root, provider)
    config = CONFIG[provider]
    path = root / config['project'] / config['profile']
    before = read(path)
    cache.mkdir(parents=True, exist_ok=True)
    if provider == 'callsetting':
        policies['lottie'] = stage_lottie(root, cache, lottie_input)
    elif lottie_input is not None:
        raise ValueError('CertManager does not consume a Lottie input')
    with tempfile.TemporaryDirectory(prefix=provider + '-profile-', dir=cache) as temporary:
        scratch = Path(temporary)
        pinned = scratch / 'original.p7b'; pinned.write_bytes(original)
        expected = desired(cms(pinned), leaf, provider)
        if before == original:
            body = scratch / 'profile.json'; signed = scratch / 'signed.p7b'
            body.write_text(json.dumps(expected, indent=2) + '\n')
            subprocess.run(['java', '-jar', str(dist / 'hap-sign-tool.jar'), 'sign-profile',
                '-keyAlias', 'openharmony application profile release', '-signAlg', 'SHA256withECDSA',
                '-mode', 'localSign', '-profileCertFile', str(dist / 'OpenHarmonyProfileRelease.pem'),
                '-inFile', str(body), '-keystoreFile', str(dist / 'OpenHarmony.p12'),
                '-outFile', str(signed), '-keyPwd', '123456', '-keystorePwd', '123456'],
                check=True, capture_output=True, timeout=120)
            verify_profile(signed, expected, issuer, scratch)
            if read(path) != before:
                raise ValueError('provider profile changed during original preparation')
            replace(path, read(signed))
        else:
            verify_profile(path, expected, issuer, scratch)
    return {'provider': provider, 'signer': SIGNATURE, 'profile_sha256': digest(read(path)),
            'policies': policies, 'actual_compilation': False, 'runtime_pass': False,
            'first_artifact_behavior_gate_passed': False}


def verify(root, provider):
    policies = source_ready(root, provider)
    _, original, leaf, issuer = inputs(root, provider)
    config = CONFIG[provider]
    with tempfile.TemporaryDirectory(prefix=provider + '-profile-') as temporary:
        scratch = Path(temporary); pinned = scratch / 'original.p7b'; pinned.write_bytes(original)
        profile = verify_profile(root / config['project'] / config['profile'],
            desired(cms(pinned), leaf, provider), issuer, scratch)
    return {'provider': provider, 'profile': profile, 'policies': policies,
            'scope': 'production source/signature admission; actual QEMU remains mandatory'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--provider', choices=tuple(CONFIG), required=True)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--prepare-profile', action='store_true')
    parser.add_argument('--cache-root', type=Path)
    parser.add_argument('--lottie-input', type=Path)
    args = parser.parse_args()
    if args.prepare_profile:
        if args.cache_root is None: raise ValueError('original owned producer cache required')
        result = prepare(args.source_root.resolve(), args.cache_root.resolve(), args.provider, args.lottie_input)
    else:
        if args.cache_root is not None or args.lottie_input is not None:
            raise ValueError('read-only guard does not accept preparation inputs')
        result = verify(args.source_root.resolve(), args.provider)
    print(json.dumps(result, indent=2))
