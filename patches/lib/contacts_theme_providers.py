#!/usr/bin/env python3
"""Preserve real Contacts/Wallpaper identities while using the fixed OS signer."""
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile

from calendar_provider import SIGNATURE, certificate_fingerprint
from mms_provider import SIGNING_INPUTS, OLD_SIGNER, read, unique, cms, certificates, replace
from preinstall_selection import entry, same_json, uninstall_policy

PROFILES = {
    'contacts': {'project': 'applications/standard/contacts',
        'revision': '65de33df8d6d7aaa5797a5625ed0e5938e5cb050', 'profile': 'signature/contacts.p7b',
        'sha256': '11538e37a86ad0d3d3fc30caa4073bbaa2c72c7c74d9d3919080a8e83d5091cc',
        'bundle': 'com.ohos.contacts', 'apl': 'normal', 'removable': False,
        'original_signer': 'D5F3BA069A565A38F7BFDE297FD80B62ACA5BDA726B34693B39BA24F835400E4'},
    'theme': {'project': 'applications/standard/theme',
        'revision': 'a436a43f1c0948fa12df6d520ec695ae4388a057', 'profile': 'signature/wallpaper.p7b',
        'sha256': '16176f3cc1eb9a3147d77a7209c698366f7ac31b7766498d373ba49f22314278',
        'bundle': 'com.ohos.wallpaper', 'apl': 'system_basic', 'removable': True,
        'original_signer': SIGNATURE},
}
CAPABILITY = {'bundleName': 'com.ohos.contacts', 'app_signature': [OLD_SIGNER], 'singleton': True,
    'keepAlive': False, 'allowCommonEvent': ['usual.event.INCOMING_CALL_MISSED', 'contact.event.CANCEL_MISSED']}
GRANTS = {'bundleName': 'com.ohos.contacts', 'app_signature': [OLD_SIGNER], 'permissions': [
    {'name': 'ohos.permission.' + name, 'userCancellable': False} for name in
    ('READ_CONTACTS', 'WRITE_CONTACTS', 'READ_CALL_LOG', 'WRITE_CALL_LOG', 'MANAGE_VOICEMAIL')]}
POLICIES = {'install_list_capability.json': CAPABILITY, 'install_list_permissions.json': GRANTS}


def policy(data, expected, require_current=False):
    value = json.loads(data, object_pairs_hook=unique)
    rows = value.get('install_list') if isinstance(value, dict) else value
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        raise ValueError('invalid Contacts preinstall policy')
    matches = [row for row in rows if row.get('bundleName') == 'com.ohos.contacts']
    current = dict(expected, app_signature=[SIGNATURE])
    allowed = ([current],) if require_current else ([expected], [current])
    if not any(same_json(matches, row) for row in allowed):
        raise ValueError('unknown Contacts signer/grants; preserving all source')
    matches[0]['app_signature'] = [SIGNATURE]
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def desired_profile(original, leaf, config):
    bundle = original.get('bundle-info', {})
    if (bundle.get('bundle-name') != config['bundle'] or bundle.get('apl') != config['apl'] or
            bundle.get('app-feature') != 'hos_system_app' or original.get('type') != 'release' or
            original.get('app-distribution-type') != 'os_integration' or
            certificate_fingerprint(bundle['distribution-certificate'].encode()) != config['original_signer'] or
            certificate_fingerprint(leaf) != SIGNATURE):
        raise ValueError('unexpected original Contacts/Wallpaper OS identity')
    desired = copy.deepcopy(original)
    desired['bundle-info']['distribution-certificate'] = leaf.decode()
    desired['validity']['not-after'] = 2208988800
    return desired


def profile_matches(path, expected, issuer, scratch):
    signer = scratch / 'issuer.pem'
    actual = cms(path, signer)
    chain = certificates(signer.read_bytes())
    if (not same_json(actual, expected) or len(chain) != 1 or
            certificate_fingerprint(chain[0]) != issuer):
        raise ValueError('Contacts/Wallpaper profile policy or OS issuer differs')


def inputs(root, scratch):
    dist = root / 'developtools/hapsigner/dist'
    for name, expected in SIGNING_INPUTS.items():
        if hashlib.sha256(read(dist / name)).hexdigest() != expected:
            raise ValueError('changed fixed public OS signing input: ' + name)
    application = certificates(read(dist / 'OpenHarmonyApplication.pem'))
    issuers = certificates(read(dist / 'OpenHarmonyProfileRelease.pem'))
    if len(application) != 3 or len(issuers) != 3: raise ValueError('unexpected existing OS certificate chains')
    issuer = certificate_fingerprint(issuers[-1])
    profiles = {}
    for name, config in PROFILES.items():
        project = root / config['project']
        actual = subprocess.check_output(['git', '-C', str(project), 'rev-parse', 'HEAD'], text=True, timeout=30).strip()
        if actual != config['revision']: raise ValueError('fixed source revision required: ' + name)
        raw = subprocess.check_output(['git', '-C', str(project), 'show', 'HEAD:' + config['profile']], timeout=30)
        if hashlib.sha256(raw).hexdigest() != config['sha256']: raise ValueError('changed original profile: ' + name)
        original = scratch / (name + '-original.p7b');original.write_bytes(raw)
        desired = desired_profile(cms(original), application[-1] + b'\n', config)
        path = project / config['profile'];current = read(path)
        if current != raw:profile_matches(path, desired, issuer, scratch)
        profiles[name] = {'path': path, 'raw': raw, 'current': current, 'desired': desired}
    directory = root / 'vendor/ohemu/virt/preinstall-config'
    for config in PROFILES.values():
        entry(read(directory / 'install_list.json'), config['bundle'], config['removable'])
        uninstall_policy(read(directory / 'uninstall_list.json'), config['bundle'])
    return dist, issuer, profiles


def prepare(root):
    with tempfile.TemporaryDirectory(prefix='contacts-theme-profiles-') as temporary:
        scratch = Path(temporary);dist, issuer, profiles = inputs(root, scratch)
        directory = root / 'vendor/ohemu/virt/preinstall-config'
        before = {p['path']: p['current'] for p in profiles.values()}
        before.update({directory / name: read(directory / name) for name in POLICIES})
        pending = {directory / name: policy(before[directory / name], expected) for name, expected in POLICIES.items()}
        for name, profile in profiles.items():
            data = profile['current']
            if data == profile['raw']:
                template, signed = scratch / (name + '.json'), scratch / (name + '.p7b')
                template.write_text(json.dumps(profile['desired'], indent=2) + '\n')
                subprocess.run(['java', '-jar', str(dist / 'hap-sign-tool.jar'), 'sign-profile',
                    '-keyAlias', 'openharmony application profile release', '-signAlg', 'SHA256withECDSA',
                    '-mode', 'localSign', '-profileCertFile', str(dist / 'OpenHarmonyProfileRelease.pem'),
                    '-inFile', str(template), '-keystoreFile', str(dist / 'OpenHarmony.p12'),
                    '-outFile', str(signed), '-keyPwd', '123456', '-keystorePwd', '123456'],
                    capture_output=True, check=True, timeout=120)
                profile_matches(signed, profile['desired'], issuer, scratch);data = signed.read_bytes()
            pending[profile['path']] = data
        written = []
        try:
            for path, data in before.items():
                if read(path) != data: raise ValueError('Contacts/Theme source changed before signer transaction')
            for path, data in pending.items():
                if before[path] != data:replace(path, data);written.append(path)
        except BaseException:
            for path in reversed(written):
                if read(path) == pending[path]:replace(path, before[path])
            raise
    return {'status': 'pass', 'scope': 'real Contacts/Wallpaper fixed OS profiles and original Contacts grants ONLY',
        'profiles': {name: hashlib.sha256(read(p['path'])).hexdigest() for name, p in profiles.items()},
        'signer': SIGNATURE, 'first_artifact_behavior_gate_passed': False}


def verify(root):
    components = Path(__file__).resolve().parents[1] / 'common/applications/standard'
    for name in ('contacts/source_provider', 'contacts/production_manifest', 'contacts/picker_session_lifecycle',
                 'theme/source_provider', 'theme/sdk_schema', 'theme/module_names', 'theme/api26_compat',
                 'theme/renderer_lifecycle', 'hap/contacts_theme_provider'):
        spec = importlib.util.spec_from_file_location('contacts_theme_guard_' + name.replace('/', '_'), components / name / 'verify_source.py')
        guard = importlib.util.module_from_spec(spec);spec.loader.exec_module(guard);guard.validate(root, require_patched=True)
    with tempfile.TemporaryDirectory(prefix='contacts-theme-profile-check-') as temporary:
        scratch = Path(temporary);_, issuer, profiles = inputs(root, scratch)
        for profile in profiles.values():profile_matches(profile['path'], profile['desired'], issuer, scratch)
        directory = root / 'vendor/ohemu/virt/preinstall-config'
        for name, expected in POLICIES.items():policy(read(directory / name), expected, True)
    return {name: profile['desired'] for name, profile in profiles.items()}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__);parser.add_argument('--source-root', type=Path, required=True)
    args = parser.parse_args();print(json.dumps(prepare(args.source_root.resolve())))
