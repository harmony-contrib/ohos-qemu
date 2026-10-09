#!/usr/bin/env python3
"""Pin Settings HAR inputs and renew only its existing OS release signer/expiry."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from verify_source import PROJECT, REVISION, validate

PROFILE_SHA = '5c78cf766c6c3b72104c31a1faea54cee7d119c1b841be31f59297dfec880da6'
SIGNATURE = '8E93863FC32EE238060BF69A9B37E2608FFFB21F93C862DD511CBAC9F30024B5'
ASSETS = {
    'hypium-1.0.16.har': '4eb8e3f3e8b3a5d8e8033abe0681257f0349709e95258c32ed983d0592e44f4d',
    'lottie-2.0.23.har': 'c05579c5378e6ac696a4c36e7ae0a1fde09f611bc47ec198fc91100c8db2cbc5',
    'mpchart-3.0.15.har': 'af410c2382df4504014f4e93bd5d44072061d7e5f3c1ce82d723e3d6da8b885e',
}
SIGNING_INPUTS = {
    'hap-sign-tool.jar': 'a434b6747e6c5d0b14e73837a46b39f4816ab25b42d1833d6f767bf867cf616d',
    'OpenHarmony.p12': '7a5efc3ea9245596d157f6ccbbdc5b8ae7cd714e7086c3c1645986c9d495d071',
    'OpenHarmonyApplication.pem': 'b5c1d6254faa91eab645a32fc3ce136128c94d88a739a0e956e6a49b331387e5',
    'OpenHarmonyProfileRelease.pem': '515f0bd8173fabb8bf8f146cd61207baa0e2d6ab8693ae7623df7ee6f16af70e',
}


def owned(path):
    path = Path(path).absolute()
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError('redirected Settings source/cache/signing path')
    return path


def sha(path):
    return hashlib.sha256(owned(path).read_bytes()).hexdigest()


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate signed Settings profile key')
        result[key] = value
    return result


def document(raw):
    return json.loads(raw, object_pairs_hook=unique)


def fingerprint(certificate):
    der = subprocess.check_output(['openssl', 'x509', '-outform', 'DER'], input=certificate)
    return hashlib.sha256(der).hexdigest().upper()


def certificates(path):
    return re.findall(b'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----', owned(path).read_bytes(), re.S)


def cms(path, signer=None):
    command = ['openssl', 'cms', '-verify', '-inform', 'DER', '-noverify', '-in', str(path)]
    if signer is not None:
        command += ['-signer', str(signer)]
    return document(subprocess.run(command, capture_output=True, check=True).stdout)


def release_profile(original, leaf):
    bundle = original.get('bundle-info', {})
    if (bundle.get('bundle-name') != 'com.ohos.settings' or bundle.get('apl') != 'system_basic' or
            bundle.get('app-feature') != 'hos_system_app' or original.get('type') != 'release' or
            original.get('app-distribution-type') != 'os_integration' or fingerprint(leaf) != SIGNATURE):
        raise ValueError('unexpected fixed Settings identity or OS certificate')
    desired = document(json.dumps(original))
    desired['bundle-info']['distribution-certificate'] = leaf.decode()
    desired['validity']['not-after'] = 2208988800
    return desired


def fetch(cache, name):
    target = owned(cache / name)
    if target.exists():
        if not target.is_file() or sha(target) != ASSETS[name]:
            raise ValueError('unknown Settings dependency cache; preserving it: ' + name)
        return target
    package = name.split('-', 1)[0]
    with tempfile.TemporaryDirectory(prefix='settings-download-', dir=cache) as temporary:
        pending = Path(temporary) / name
        subprocess.run(['curl', '-fL', '--proto', '=https', '--proto-redir', '=https', '--retry', '2',
                        '--connect-timeout', '30', '--max-time', '300', '-o', str(pending),
                        'https://ohpm.openharmony.cn/ohpm/@ohos/' + package + '/-/' + name], check=True)
        if sha(pending) != ASSETS[name] or target.exists() or target.is_symlink():
            raise ValueError('changed Settings download or destination')
        pending.rename(target)
    return target


def prepare(root, cache, signing_root=None):
    root, cache = owned(root), owned(cache)
    validate(root, require_patched=True)
    project = owned(root / PROJECT)
    if subprocess.check_output(['git', '-C', str(project), 'rev-parse', 'HEAD'], text=True).strip() != REVISION:
        raise ValueError('Settings must use the fixed release checkout')
    dist = owned((owned(signing_root) if signing_root else root) / 'developtools/hapsigner/dist')
    for name, expected in SIGNING_INPUTS.items():
        if sha(dist / name) != expected:
            raise ValueError('changed fixed public OS signing input: ' + name)
    original = subprocess.check_output(['git', '-C', str(project), 'show', 'HEAD:signature/settings.p7b'])
    if hashlib.sha256(original).hexdigest() != PROFILE_SHA:
        raise ValueError('changed original Settings release profile')
    application, issuer = certificates(dist / 'OpenHarmonyApplication.pem'), certificates(dist / 'OpenHarmonyProfileRelease.pem')
    if len(application) != 3 or len(issuer) != 3:
        raise ValueError('unexpected OS signing chain')
    leaf = application[-1] + b'\n'
    issuer_sha = fingerprint(issuer[-1])
    profile = owned(project / 'signature/settings.p7b')
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='settings-profile-', dir=cache) as temporary:
        scratch = Path(temporary)
        original_file, signed, signer = (scratch / name for name in ('original.p7b', 'release.p7b', 'issuer.pem'))
        original_file.write_bytes(original)
        desired = release_profile(cms(original_file), leaf)
        pristine = sha(profile) == PROFILE_SHA
        if not pristine:
            actual = cms(profile, signer)
            signers = certificates(signer)
            if actual != desired or len(signers) != 1 or fingerprint(signers[0]) != issuer_sha:
                raise ValueError('unknown Settings profile edits; preserving policy')
        for name, expected in ASSETS.items():
            target = owned(project / name)
            if target.exists() and (not target.is_file() or sha(target) != expected):
                raise ValueError('unknown source Settings dependency; preserving it: ' + name)
        assets = {name: fetch(cache, name) for name in ASSETS}
        if pristine:
            template, verified = scratch / 'profile.json', scratch / 'verified.json'
            template.write_text(json.dumps(desired, indent=2) + '\n')
            subprocess.run(['java', '-jar', str(dist / 'hap-sign-tool.jar'), 'sign-profile',
                '-keyAlias', 'openharmony application profile release', '-signAlg', 'SHA256withECDSA',
                '-mode', 'localSign', '-profileCertFile', str(dist / 'OpenHarmonyProfileRelease.pem'),
                '-inFile', str(template), '-keystoreFile', str(dist / 'OpenHarmony.p12'),
                '-outFile', str(signed), '-keyPwd', '123456', '-keystorePwd', '123456'], capture_output=True, check=True)
            subprocess.run(['java', '-jar', str(dist / 'hap-sign-tool.jar'), 'verify-profile',
                '-inFile', str(signed), '-outFile', str(verified)], capture_output=True, check=True)
            record = document(verified.read_bytes())
            content = record.get('content')
            actual = cms(signed, signer)
            signers = certificates(signer)
            if (record.get('verifiedPassed') is not True or
                    (document(content) if isinstance(content, str) else content) != desired or actual != desired or
                    len(signers) != 1 or fingerprint(signers[0]) != issuer_sha):
                raise ValueError('Settings signed release profile did not verify')
        # No app identity, APL, ACL, permission, extension privilege or policy bypass is added.
        for name, asset in assets.items():
            target = owned(project / name)
            if not target.exists():
                shutil.copy2(asset, target)
            if sha(target) != ASSETS[name]:
                raise ValueError('Settings asset changed during installation')
        if pristine:
            with tempfile.TemporaryDirectory(prefix='.qemu-settings-', dir=profile.parent) as temporary:
                staged = Path(temporary) / 'settings.p7b'
                shutil.copy2(signed, staged)
                if sha(staged) != sha(signed) or sha(profile) != PROFILE_SHA:
                    raise ValueError('Settings profile changed during installation')
                shutil.copymode(profile, staged)
                staged.replace(profile)
    return {'status': 'pass', 'scope': 'fixed_Settings_dependencies_and_OS_profile_NOT_guest',
            'first_artifact_behavior_gate_passed': False, 'source_revision': REVISION,
            'assets_sha256': ASSETS, 'profile_sha256': sha(profile), 'signer_fingerprint': SIGNATURE,
            'profile_issuer_fingerprint': issuer_sha, 'bundle_APL_ACL_permissions_unchanged': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source-root', 'cache-root', 'evidence'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--signing-root', type=Path, help='read-only fixed OS tools for isolated preparation checks')
    args = parser.parse_args()
    result = prepare(args.source_root, args.cache_root, args.signing_root)
    owned(args.evidence).write_text(json.dumps(result, indent=2) + '\n')
    print('Settings source dependencies/profile prepared; HAP and guest acceptance still required')
