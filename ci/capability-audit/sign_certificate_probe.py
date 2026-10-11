#!/usr/bin/env python3
"""Sign only the dedicated two-role CertificateManager QEMU regression HAP.

Normal role has no ACLs. System role uses exactly the two documented certificate
permissions, public QEMU test keys and a concrete guest UDID. This does not
change the image permission table, install policy or ordinary signer defaults.
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import tempfile
import time
import uuid
import zipfile

from sign_web_probe import verify_signed_hap
from check_m144_core_package import verified_profile_content
from run_root_probe import digest

BUNDLE = 'org.harmonycontrib.capabilityaudit'
PERMISSIONS = ('ohos.permission.ACCESS_CERT_MANAGER', 'ohos.permission.ACCESS_CERT_MANAGER_INTERNAL')


def configure_profile(profile, role, udid, module):
    if role not in ('normal', 'system') or re.fullmatch('[0-9a-fA-F]{64}', udid) is None:
        raise ValueError('explicit certificate role and actual guest UDID required')
    expected = set(PERMISSIONS) if role == 'system' else set()
    requests = module['module']['requestPermissions']
    if (module['app'].get('bundleName') != BUNDLE or not isinstance(requests, list) or
            any(not isinstance(row, dict) or set(row) != {'name'} for row in requests) or
            {row['name'] for row in requests} != expected or len(requests) != len(expected)):
        raise ValueError('certificate probe bundle and exact role permission contract differ')
    profile['bundle-info']['bundle-name'] = BUNDLE
    profile['bundle-info']['apl'] = 'system_core' if role == 'system' else 'normal'
    profile['bundle-info']['app-feature'] = 'hos_system_app' if role == 'system' else 'hos_normal_app'
    profile['debug-info']['device-ids'] = [udid]
    profile['acls']['allowed-acls'] = sorted(expected)
    profile['permissions']['restricted-permissions'] = sorted(expected)
    return profile


def sign(args, configure=configure_profile):
    """Shared signing mechanics; each caller supplies an exact role contract."""
    receipt = args.output.with_suffix('.signing.json')
    if (args.output.exists() or args.output.is_symlink() or args.unsigned.is_symlink() or
            not args.unsigned.is_file() or receipt.exists() or receipt.is_symlink()):
        raise ValueError('new signed output and regular unsigned input required')
    original_sha256 = digest(args.unsigned)
    dist = args.signer_dist.resolve()
    with zipfile.ZipFile(args.unsigned) as archive:
        module = json.loads(archive.read('module.json'))
    profile = configure(json.loads((dist / 'UnsgnedDebugProfileTemplate.json').read_text()),
                                args.role, args.udid, module)
    now = int(time.time())
    profile['uuid'] = str(uuid.uuid4())
    profile['validity'] = {'not-before': now - 86400, 'not-after': now + 86400 * 30}
    jar = str(args.jar.resolve()); keystore = str(dist / 'OpenHarmony.p12')
    with tempfile.TemporaryDirectory(prefix='ohos-certificate-probe-sign-') as directory:
        work = Path(directory)
        profile_json, profile_signed, normalized = (work / name for name in
            ('profile.json', 'profile.p7b', 'normalized.hap'))
        profile_json.write_text(json.dumps(profile, indent=2) + '\n')
        with zipfile.ZipFile(args.unsigned) as original, zipfile.ZipFile(normalized, 'w', allowZip64=False) as output:
            for member in original.infolist():
                data = original.read(member); member.extra = b''; output.writestr(member, data)
        subprocess.run(['java', '-jar', jar, 'sign-profile', '-keyAlias', 'openharmony application profile debug',
            '-signAlg', 'SHA256withECDSA', '-mode', 'localSign', '-profileCertFile', str(dist / 'OpenHarmonyProfileDebug.pem'),
            '-inFile', str(profile_json), '-keystoreFile', keystore, '-outFile', str(profile_signed),
            '-keyPwd', '123456', '-keystorePwd', '123456'], check=True)
        subprocess.run(['java', '-jar', jar, 'sign-app', '-keyAlias', 'openharmony application release',
            '-signAlg', 'SHA256withECDSA', '-mode', 'localSign', '-appCertFile', str(dist / 'OpenHarmonyApplication.pem'),
            '-profileFile', str(profile_signed), '-inFile', str(normalized), '-keystoreFile', keystore,
            '-outFile', str(args.output.resolve()), '-keyPwd', '123456', '-keystorePwd', '123456', '-signCode', '1'],
            check=True)
        verify_signed_hap(jar, args.output.resolve(), work)
        extracted = work / 'verified-profile.json'
        completed = subprocess.run(['java', '-jar', jar, 'verify-profile',
            '-inFile', str(work / 'verified-profile.p7b'), '-outFile', str(extracted)],
            capture_output=True, text=True, check=True)
        if ('verify-profile success' not in completed.stdout + completed.stderr or
                verified_profile_content(json.loads(extracted.read_text())) != profile or
                digest(args.unsigned) != original_sha256):
            raise ValueError('actual signed profile differs from the exact role contract or unsigned input changed')
        receipt.write_text(json.dumps({'status': 'pass', 'scope': 'actual_signature_profile_and_codesign_NOT_guest',
            'role': args.role, 'unsigned_sha256': original_sha256, 'signed_sha256': digest(args.output),
            'verified_profile': profile}, indent=2) + '\n')
    print(args.output.resolve())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('signer-dist', 'jar', 'unsigned', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--role', choices=('normal', 'system'), required=True)
    parser.add_argument('--udid', required=True)
    sign(parser.parse_args())


if __name__ == '__main__':
    main()
