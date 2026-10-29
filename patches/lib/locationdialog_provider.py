"""Bind the real LocationDialog source profile to the existing OS signer.

This is product input preparation for the ordinary package build. Capability
acceptance requires the resulting new QEMU image and actual public UI flows.
"""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import subprocess
import tempfile

from calendar_provider import SIGNATURE, certificate_fingerprint
from mms_provider import SIGNING_INPUTS, certificates, cms, read, replace

PROJECT = 'base/location/location'
REVISION = '5a0c49c2adb0623fdac73f76e4f98f2e57674c00'
PROFILE = 'services/location_ui/signature/locationdialog.p7b'
PROFILE_SHA = '99a9a8f7d749d12bf1929f12c19e4356e92c33bfb212140bb0c06d4d44eb2f29'
C42_PREPARED_SHA = '8ad762394aa4bec76a0d21e3dedcd18bbf37ed797eaa794a04f26b5bce75b85e'
C42_PREPARED_BYTES = 3731
OLD_SIGNER = '8FD346D9BF992BE6CD80BFB4F1E60EF0D50BC9E04593AF1D47714E339B44268D'
ORIGINAL_ACLS = (
    'ohos.permission.MANAGE_BLUETOOTH',
    'ohos.permission.ACCESS_SYSTEM_SETTINGS',
    'ohos.permission.WRITE_IMAGEVIDEO',
    'ohos.permission.SET_WIFI_CONFIG',
    'ohos.permission.PUBLISH_LOCATION_EVENT',
)
CROSS_ACCOUNT_ACL = 'ohos.permission.INTERACT_ACROSS_LOCAL_ACCOUNTS'


def prepare(root):
    project, dist = root / PROJECT, root / 'developtools/hapsigner/dist'
    if subprocess.check_output(['git', '-C', str(project), 'rev-parse', 'HEAD'],
                               text=True, timeout=30).strip() != REVISION:
        raise ValueError('LocationDialog requires the fixed actual location checkout')
    for name, expected in SIGNING_INPUTS.items():
        if hashlib.sha256(read(dist / name)).hexdigest() != expected:
            raise ValueError('existing public OS signing input changed: ' + name)
    original = subprocess.check_output(['git', '-C', str(project), 'show', 'HEAD:' + PROFILE], timeout=30)
    if hashlib.sha256(original).hexdigest() != PROFILE_SHA:
        raise ValueError('original LocationDialog profile changed')
    application = certificates(read(dist / 'OpenHarmonyApplication.pem'))
    issuer = certificates(read(dist / 'OpenHarmonyProfileRelease.pem'))
    if len(application) != 3 or len(issuer) != 3 or certificate_fingerprint(application[-1]) != SIGNATURE:
        raise ValueError('unexpected existing OS certificate chain')
    target = project / PROFILE
    before = read(target)
    with tempfile.TemporaryDirectory(prefix='locationdialog-source-profile-') as directory:
        scratch = Path(directory)
        original_file, signer, signed = (scratch / n for n in ('original.p7b', 'issuer.pem', 'release.p7b'))
        original_file.write_bytes(original)
        value = cms(original_file, signer)
        original_issuer = certificate_fingerprint(signer.read_bytes())
        if (value.get('type') != 'release' or value.get('app-distribution-type') != 'os_integration' or
                value['bundle-info']['bundle-name'] != 'com.ohos.locationdialog' or
                value['bundle-info']['apl'] != 'normal' or
                value['bundle-info']['app-feature'] != 'hos_system_app' or
                value.get('acls') != {'allowed-acls': list(ORIGINAL_ACLS)} or
                certificate_fingerprint(value['bundle-info']['distribution-certificate'].encode()) != OLD_SIGNER):
            raise ValueError('actual LocationDialog original identity or profile issuer changed')
        legacy_desired = copy.deepcopy(value)
        legacy_desired['bundle-info']['distribution-certificate'] = (application[-1] + b'\n').decode()
        legacy_desired['validity']['not-after'] = 2208988800
        desired = copy.deepcopy(legacy_desired)
        # Build24 requests this permission at normal APL; its signed ACL must authorize it.
        desired['acls']['allowed-acls'].append(CROSS_ACCOUNT_ACL)

        def check(path, expected):
            observed = cms(path, signer)
            signers = certificates(signer.read_bytes())
            if (json.dumps(observed, sort_keys=True) != json.dumps(expected, sort_keys=True) or len(signers) != 1 or
                    certificate_fingerprint(signers[0]) != certificate_fingerprint(issuer[-1])):
                raise ValueError('LocationDialog replacement profile or issuer differs')

        legacy = (len(before) == C42_PREPARED_BYTES and
                  hashlib.sha256(before).hexdigest() == C42_PREPARED_SHA)
        if before != original:
            # Verify the captured input, not a second, potentially changed live read.
            current = scratch / 'current.p7b'
            current.write_bytes(before)
            check(current, legacy_desired if legacy else desired)
        if read(target) != before:
            raise ValueError('LocationDialog profile changed during input validation')
        if before == original or legacy:
            template = scratch / 'profile.json'
            template.write_text(json.dumps(desired, indent=2) + '\n')
            if read(target) != before:
                raise ValueError('LocationDialog profile changed before signing')
            subprocess.run(['java', '-jar', str(dist / 'hap-sign-tool.jar'), 'sign-profile',
                '-keyAlias', 'openharmony application profile release', '-signAlg', 'SHA256withECDSA',
                '-mode', 'localSign', '-profileCertFile', str(dist / 'OpenHarmonyProfileRelease.pem'),
                '-inFile', str(template), '-keystoreFile', str(dist / 'OpenHarmony.p12'),
                '-outFile', str(signed), '-keyPwd', '123456', '-keystorePwd', '123456'],
                capture_output=True, check=True, timeout=120)
            check(signed, desired)
            if read(target) != before:
                raise ValueError('LocationDialog profile changed before replacement')
            replace(target, signed.read_bytes())
    return {'scope': 'LocationDialog product signing input preparation only',
        'signer': SIGNATURE, 'profile_sha256': hashlib.sha256(read(target)).hexdigest(),
        'original_pinned_profile_issuer': original_issuer,
        'first_artifact_behavior_gate_passed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source_root.resolve())))
