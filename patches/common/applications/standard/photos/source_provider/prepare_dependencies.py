#!/usr/bin/env python3
"""Prepare pinned Photos assets and its unchanged-policy OS release profile.

Run in local Docker before any product traversal. This neither accepts the
HAP nor supplies a cloud/userPropertySettings provider.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tarfile
import tempfile

from verify_source import REVISION, validate

PROFILE_SHA = '8fe41b76d646c90e3cb60c1aeade3cd9dd62f6fb0ad0efb35e8490a125e71eb3'
SIGNATURE = '8E93863FC32EE238060BF69A9B37E2608FFFB21F93C862DD511CBAC9F30024B5'
ORIGINAL_SIGNATURE = '38DD4F043FB164BB5402D7FA48FF7D6FEF1A46BD705F491CE039E2B7D626A3F6'
JSONCPP_COMMIT = '5defb4ed1a4293b8e2bf641e16b156fb9de498cc'
ASSETS = {
    'lottie-2.0.19.har': (
        'https://ohpm.openharmony.cn/ohpm/@ohos/lottie/-/lottie-2.0.19.har',
        'c2c144849af2ac19f087c832dff4980ce579bf1fe59206da29bd26cbb670bd9f'),
    'jsoncpp-' + JSONCPP_COMMIT + '.tar.gz': (
        'https://codeload.github.com/open-source-parsers/jsoncpp/tar.gz/' + JSONCPP_COMMIT,
        '331381ca5adf86dc7df0b467ace058f35f15942769bc8045d10cee5de808b04b'),
}
SIGNING_INPUTS = {
    'hap-sign-tool.jar': 'a434b6747e6c5d0b14e73837a46b39f4816ab25b42d1833d6f767bf867cf616d',
    'OpenHarmony.p12': '7a5efc3ea9245596d157f6ccbbdc5b8ae7cd714e7086c3c1645986c9d495d071',
    'OpenHarmonyApplication.pem': 'b5c1d6254faa91eab645a32fc3ce136128c94d88a739a0e956e6a49b331387e5',
    'OpenHarmonyProfileRelease.pem': '515f0bd8173fabb8bf8f146cd61207baa0e2d6ab8693ae7623df7ee6f16af70e',
}


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def owned(path):
    path = Path(path)
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError('refuse redirected Photos asset/signing path')
    return path


def unique_object(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError('duplicate profile key: ' + name)
        result[name] = value
    return result


def document(raw):
    return json.loads(raw, object_pairs_hook=unique_object)


def fingerprint(certificate):
    der = subprocess.check_output(['openssl', 'x509', '-outform', 'DER'], input=certificate)
    return hashlib.sha256(der).hexdigest().upper()


def release_profile(original, leaf):
    """Only align the expired profile's certificate and finite expiry."""
    if (original.get('bundle-info', {}).get('bundle-name') != 'com.ohos.photos' or
            original['bundle-info'].get('apl') != 'system_core' or
            original['bundle-info'].get('app-feature') != 'hos_system_app' or
            original.get('type') != 'release' or original.get('app-distribution-type') != 'os_integration' or
            original.get('permissions') != {'restricted-permissions': []} or
            original.get('acls') != {'allowed-acls': ['']} or
            original.get('validity') != {'not-before': 1594865258, 'not-after': 1689473258} or
            fingerprint(original['bundle-info']['distribution-certificate'].encode()) != ORIGINAL_SIGNATURE or
            fingerprint(leaf) != SIGNATURE):
        raise ValueError('unexpected fixed Photos profile or OS application signer')
    desired = document(json.dumps(original))
    desired['bundle-info']['distribution-certificate'] = leaf.decode()
    desired['validity']['not-after'] = 2208988800
    return desired


def cms(path, signer_output=None):
    argv = ['openssl', 'cms', '-verify', '-inform', 'DER', '-noverify', '-in', str(path)]
    if signer_output is not None:
        argv += ['-signer', str(signer_output)]
    result = subprocess.run(argv,
                            capture_output=True, check=True)
    return document(result.stdout)


def release_cms(path, scratch, expected_signer):
    signer_output = scratch / 'actual-profile-signer.pem'
    content = cms(path, signer_output)
    signers = re.findall(b'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----',
                         signer_output.read_bytes(), re.S)
    if len(signers) != 1 or fingerprint(signers[0]) != expected_signer:
        raise ValueError('Photos CMS was not signed by the exact fixed OS profile issuer')
    return content


def fetch(cache, name, url, checksum):
    target = owned(cache / name)
    if target.exists():
        if not target.is_file() or sha(target) != checksum:
            raise ValueError('unknown cached Photos dependency; preserve it: ' + name)
        return target
    with tempfile.TemporaryDirectory(prefix='photos-dependency-', dir=cache) as scratch:
        downloaded = Path(scratch) / name
        subprocess.run(['curl', '-fL', '--proto', '=https', '--proto-redir', '=https',
                        '--retry', '2', '--retry-all-errors', '--connect-timeout', '30', '--max-time', '300',
                        '--output', str(downloaded), url], check=True)
        if sha(downloaded) != checksum:
            raise ValueError('pinned Photos dependency checksum mismatch: ' + name)
        if target.exists() or target.is_symlink():
            raise ValueError('Photos dependency cache changed during preparation')
        downloaded.rename(target)
    return target


def tree(path):
    result = {}
    for entry in sorted(path.rglob('*')):
        owned(entry)
        if entry.is_file():
            result[entry.relative_to(path).as_posix()] = sha(entry)
        elif not entry.is_dir():
            raise ValueError('unexpected JsonCpp source node')
    return result


def unpack_jsoncpp(archive, destination):
    prefix = 'jsoncpp-' + JSONCPP_COMMIT
    with tarfile.open(archive, 'r:gz') as source:
        seen, members = set(), []
        for entry in source.getmembers():
            name = PurePosixPath(entry.name)
            if (name.is_absolute() or '..' in name.parts or '\\' in entry.name or not name.parts or
                    name.parts[0] != prefix or entry.name.rstrip('/') != name.as_posix() or
                    name.as_posix() in seen or
                    not (entry.isfile() or entry.isdir()) or entry.size > 8 * 1024 * 1024):
                raise ValueError('unsafe, duplicate or non-regular pinned JsonCpp archive member')
            seen.add(name.as_posix())
            members.append(entry)
        if not members:
            raise ValueError('empty JsonCpp source archive')
        source.extractall(destination, members=members, filter='data')
    path = destination / prefix
    for name in ('json_reader.cpp', 'json_value.cpp', 'json_writer.cpp'):
        if not (path / 'src/lib_json' / name).is_file():
            raise ValueError('pinned JsonCpp implementation absent')
    return path


def prepare(root, cache):
    root, cache = owned(root), owned(cache)
    validate(root, require_patched=True)
    photos = root / 'applications/standard/photos'
    if subprocess.check_output(['git', '-C', str(photos), 'rev-parse', 'HEAD'], text=True).strip() != REVISION:
        raise ValueError('actual fixed Photos checkout is required')
    dist = root / 'developtools/hapsigner/dist'
    for name, expected in SIGNING_INPUTS.items():
        if sha(owned(dist / name)) != expected:
            raise ValueError('fixed public release signing input changed: ' + name)
    # Retain the vendored JsonCpp renamed-namespace headers for ABI consistency.
    headers = photos / 'imageEditor/common/src/main/cpp/sdk/libs/JsonCpp/include'
    if not headers.is_dir() or not (headers / 'json/config.h').is_file():
        raise ValueError('original Photos JsonCpp namespace/header tree is absent')
    for path in headers.rglob('*'):
        owned(path)
        if path.is_file() and path.read_bytes() != subprocess.check_output(
                ['git', '-C', str(photos), 'show', 'HEAD:' + path.relative_to(photos).as_posix()]):
            raise ValueError('original Photos JsonCpp header was edited')
    original_cms = subprocess.check_output(['git', '-C', str(photos), 'show', 'HEAD:signature/photos.p7b'])
    if hashlib.sha256(original_cms).hexdigest() != PROFILE_SHA:
        raise ValueError('fixed Photos source profile changed')
    chain = (dist / 'OpenHarmonyApplication.pem').read_bytes()
    certificates = re.findall(b'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----', chain, re.S)
    if len(certificates) != 3:
        raise ValueError('unknown OS application certificate chain')
    leaf = certificates[-1] + b'\n'
    issuers = re.findall(b'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----',
                        (dist / 'OpenHarmonyProfileRelease.pem').read_bytes(), re.S)
    if len(issuers) != 3:
        raise ValueError('unexpected fixed OS profile issuer certificate chain')
    expected_issuer = fingerprint(issuers[-1])
    profile_path = owned(photos / 'signature/photos.p7b')
    cache.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='photos-source-preparation-', dir=cache) as temporary:
        scratch = Path(temporary)
        original_path = scratch / 'original.p7b'
        original_path.write_bytes(original_cms)
        desired = release_profile(cms(original_path), leaf)
        pristine = sha(profile_path) == PROFILE_SHA
        if not pristine and release_cms(profile_path, scratch, expected_issuer) != desired:
            raise ValueError('unknown Photos profile edits; preserve all grants and identities')
        lottie = owned(photos / 'lottie-2.0.19.har')
        if lottie.exists() and (not lottie.is_file() or sha(lottie) != ASSETS[lottie.name][1]):
            raise ValueError('unknown source Photos Lottie dependency')
        archives = {name: fetch(cache, name, *values) for name, values in ASSETS.items()}
        source = unpack_jsoncpp(archives['jsoncpp-' + JSONCPP_COMMIT + '.tar.gz'], scratch)
        native_source = owned(photos / 'imageEditor/common/src/main/cpp/sdk/libs/JsonCpp/source')
        expected_tree = tree(source)
        if native_source.exists() and (not native_source.is_dir() or tree(native_source) != expected_tree):
            raise ValueError('unknown existing Photos JsonCpp source; preserve it')
        template, signed, verified = (scratch / name for name in ('profile.json', 'profile.p7b', 'verified.json'))
        if pristine:
            template.write_text(json.dumps(desired, indent=2) + '\n')
            subprocess.run(['java', '-jar', str(dist / 'hap-sign-tool.jar'), 'sign-profile',
                '-keyAlias', 'openharmony application profile release', '-signAlg', 'SHA256withECDSA',
                '-mode', 'localSign', '-profileCertFile', str(dist / 'OpenHarmonyProfileRelease.pem'),
                '-inFile', str(template), '-keystoreFile', str(dist / 'OpenHarmony.p12'),
                '-outFile', str(signed), '-keyPwd', '123456', '-keystorePwd', '123456'],
                capture_output=True, check=True)
            subprocess.run(['java', '-jar', str(dist / 'hap-sign-tool.jar'), 'verify-profile',
                            '-inFile', str(signed), '-outFile', str(verified)], capture_output=True, check=True)
            record = document(verified.read_bytes())
            content = record.get('content')
            if (record.get('verifiedPassed') is not True or
                    (document(content) if isinstance(content, str) else content) != desired or
                    release_cms(signed, scratch, expected_issuer) != desired):
                raise ValueError('actual signed Photos profile verification failed')
        # All source/cache/profile checks precede these owned installations.
        if not lottie.exists():
            shutil.copy2(archives[lottie.name], lottie)
        if not native_source.exists():
            source.rename(native_source)
        if pristine:
            signed.replace(profile_path)
    return {'status': 'pass', 'scope': 'fixed_Photos_source_dependencies_and_OS_profile_NOT_HAP_or_guest_acceptance',
            'first_artifact_behavior_gate_passed': False, 'source_revision': REVISION,
            'assets_sha256': {name: values[1] for name, values in ASSETS.items()},
            'jsoncpp_commit': JSONCPP_COMMIT, 'jsoncpp_tree_sha256': hashlib.sha256(
                json.dumps(expected_tree, sort_keys=True).encode()).hexdigest(),
            'profile_sha256': sha(profile_path), 'signer_fingerprint': SIGNATURE,
            'profile_issuer_fingerprint': expected_issuer,
            'bundle_APL_ACL_permissions_unchanged': True,
            'runtime_and_full_audit_validation_required': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--cache-root', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    result = prepare(args.source_root, args.cache_root)
    owned(args.evidence).write_text(json.dumps(result, indent=2) + '\n')
    print('Photos source dependencies/profile prepared; real HAP and guest acceptance still required')
