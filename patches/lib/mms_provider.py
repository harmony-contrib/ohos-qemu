#!/usr/bin/env python3
"""Bind the pinned source MMS app to the existing public OS signer."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

from calendar_provider import SIGNATURE, certificate_fingerprint

PROJECT = 'applications/standard/mms'
REVISION = '26df98e3738f4219aa45efe6a3e7f6b1be55c051'
PROFILE_SHA = 'b18d4d1106a00e7b45aa87ecee15c5dcbd2b4f87f03e0a3b9afa4229f7efbf3a'
OLD_SIGNER = '04AC9C3F045EAB7DB992B7C4E38B59468CA3EABB7D654AE47641471B9785EA04'
SIGNING_INPUTS = {
    'hap-sign-tool.jar': 'a434b6747e6c5d0b14e73837a46b39f4816ab25b42d1833d6f767bf867cf616d',
    'OpenHarmony.p12': '7a5efc3ea9245596d157f6ccbbdc5b8ae7cd714e7086c3c1645986c9d495d071',
    'OpenHarmonyApplication.pem': 'b5c1d6254faa91eab645a32fc3ce136128c94d88a739a0e956e6a49b331387e5',
    'OpenHarmonyProfileRelease.pem': '515f0bd8173fabb8bf8f146cd61207baa0e2d6ab8693ae7623df7ee6f16af70e',
}
CAPABILITY = {'bundleName': 'com.ohos.mms', 'app_signature': [OLD_SIGNER], 'singleton': True,
              'keepAlive': False, 'allowCommonEvent': ['usual.event.SMS_RECEIVE_COMPLETED']}
GRANTS = {'bundleName': 'com.ohos.mms', 'app_signature': [OLD_SIGNER], 'permissions': [
    {'name': 'ohos.permission.READ_CONTACTS', 'userCancellable': True},
    *[{'name': 'ohos.permission.' + name, 'userCancellable': False}
      for name in ('READ_MESSAGES', 'SEND_MESSAGES', 'RECEIVE_SMS')]]}


def read(path):
    if any(p.is_symlink() for p in (path, *path.parents)) or not path.is_file():
        raise ValueError('regular MMS source/signing input required: ' + str(path))
    return path.read_bytes()


def unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result: raise ValueError('duplicate MMS profile/policy key')
        result[key] = value
    return result


def cms(path, signer=None):
    command = ['openssl', 'cms', '-verify', '-inform', 'DER', '-noverify', '-in', str(path)]
    if signer is not None: command += ['-signer', str(signer)]
    return json.loads(subprocess.run(command, capture_output=True, check=True).stdout, object_pairs_hook=unique)


def desired_profile(original, leaf):
    bundle = original['bundle-info']
    if (bundle.get('bundle-name') != 'com.ohos.mms' or bundle.get('apl') != 'normal' or
            bundle.get('app-feature') != 'hos_system_app' or original.get('type') != 'release' or
            original.get('app-distribution-type') != 'os_integration' or
            certificate_fingerprint(bundle['distribution-certificate'].encode()) != OLD_SIGNER or
            certificate_fingerprint(leaf) != SIGNATURE):
        raise ValueError('unexpected pinned MMS identity or existing OS signer')
    result = copy.deepcopy(original)
    result['bundle-info']['distribution-certificate'] = leaf.decode()
    result['validity']['not-after'] = 2208988800
    return result


def policy(data, expected):
    value = json.loads(data, object_pairs_hook=unique)
    rows = value['install_list'] if isinstance(value, dict) else value
    matches = [r for r in rows if r.get('bundleName') == 'com.ohos.mms']
    desired = dict(expected, app_signature=[SIGNATURE])
    if matches not in ([expected], [desired]):
        raise ValueError('unknown MMS preinstall capability/grants; preserving source')
    matches[0]['app_signature'] = [SIGNATURE]
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def replace(path, data):
    with tempfile.NamedTemporaryFile(prefix='.mms-provider-', dir=path.parent, delete=False) as stream:
        pending = Path(stream.name)
        try:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
            os.chmod(pending, path.stat().st_mode & 0o777)
            os.replace(pending, path)
        finally:
            pending.unlink(missing_ok=True)


def prepare(root):
    project, dist = root / PROJECT, root / 'developtools/hapsigner/dist'
    if subprocess.check_output(['git', '-C', str(project), 'rev-parse', 'HEAD'], text=True).strip() != REVISION:
        raise ValueError('MMS requires the fixed release checkout')
    for name, expected in SIGNING_INPUTS.items():
        if hashlib.sha256(read(dist / name)).hexdigest() != expected:
            raise ValueError('changed existing public OS signing input: ' + name)
    original = subprocess.check_output(['git', '-C', str(project), 'show', 'HEAD:signature/mms.p7b'])
    if hashlib.sha256(original).hexdigest() != PROFILE_SHA: raise ValueError('changed original MMS profile')
    certificates = lambda data: re.findall(b'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----', data, re.S)
    app_chain = certificates(read(dist / 'OpenHarmonyApplication.pem'))
    issuer_chain = certificates(read(dist / 'OpenHarmonyProfileRelease.pem'))
    if len(app_chain) != 3 or len(issuer_chain) != 3: raise ValueError('unexpected existing OS certificate chain')
    profile = project / 'signature/mms.p7b'
    directory = root / 'vendor/ohemu/virt/preinstall-config'
    paths = {directory / 'install_list_capability.json': CAPABILITY,
             directory / 'install_list_permissions.json': GRANTS}
    before = {p: read(p) for p in (*paths, profile)}
    pending = {p: policy(before[p], expected) for p, expected in paths.items()}
    with tempfile.TemporaryDirectory(prefix='mms-source-profile-') as temporary:
        scratch = Path(temporary)
        original_file, signer, signed = (scratch / n for n in ('original.p7b', 'issuer.pem', 'release.p7b'))
        original_file.write_bytes(original)
        desired = desired_profile(cms(original_file), app_chain[-1] + b'\n')
        issuer = certificate_fingerprint(issuer_chain[-1])
        def verify(path):
            actual = cms(path, signer)
            signers = certificates(signer.read_bytes())
            if actual != desired or len(signers) != 1 or certificate_fingerprint(signers[0]) != issuer:
                raise ValueError('source MMS signed policy/issuer differs')
        if before[profile] != original:
            verify(profile)
            pending[profile] = before[profile]
        else:
            template = scratch / 'profile.json';template.write_text(json.dumps(desired, indent=2) + '\n')
            subprocess.run(['java', '-jar', str(dist / 'hap-sign-tool.jar'), 'sign-profile',
                '-keyAlias', 'openharmony application profile release', '-signAlg', 'SHA256withECDSA',
                '-mode', 'localSign', '-profileCertFile', str(dist / 'OpenHarmonyProfileRelease.pem'),
                '-inFile', str(template), '-keystoreFile', str(dist / 'OpenHarmony.p12'),
                '-outFile', str(signed), '-keyPwd', '123456', '-keystorePwd', '123456'],
                capture_output=True, check=True)
            verify(signed);pending[profile] = signed.read_bytes()
        # Commit only the exact profile and existing two signer-bound rows.
        written = []
        try:
            for path in pending:
                if read(path) != before[path]: raise ValueError('MMS source changed before signer transaction')
            for path, data in pending.items():
                if before[path] != data:
                    replace(path, data);written.append(path)
        except BaseException:
            for path in reversed(written):
                if read(path) == pending[path]: replace(path, before[path])
            raise
    return {'status': 'pass', 'scope': 'pinned_MMS_OS_signer_and_existing_grants_ONLY_NOT_install_or_runtime',
            'profile_sha256': hashlib.sha256(read(profile)).hexdigest(), 'signer': SIGNATURE,
            'first_artifact_behavior_gate_passed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source_root.resolve())))
