#!/usr/bin/env python3
"""Authenticate NumberIdentity and renew its OS leaf, expiry and extension privilege.

Source candidate. Only the coordinating root may execute --prepare with its signing
lease. --verify reads public certificates/profile only; it never reads a keystore.
No preinstall permissions, ACLs or application data are changed.
"""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile

PROJECT = 'base/telephony/number_identity'
REVISION = '50e1330646432ce166e7981c577f25f46c90e7ac'
PROFILE = 'signature/NumberIdentity.hapRelease.p7b'
PROFILE_SHA = '419bead94100bf511b6885e09541a01804d4f2fb58b5cd0e042eaa745dc96595'
BUNDLE = 'com.ohos.numberidentity'
OS_LEAF = '8E93863FC32EE238060BF69A9B37E2608FFFB21F93C862DD511CBAC9F30024B5'
ORIGINAL_NOT_AFTER = 1689473258
RENEWED_NOT_AFTER = 2208988800
PUBLIC_INPUTS = {
    'hap-sign-tool.jar': 'a434b6747e6c5d0b14e73837a46b39f4816ab25b42d1833d6f767bf867cf616d',
    'OpenHarmonyApplication.pem': 'b5c1d6254faa91eab645a32fc3ce136128c94d88a739a0e956e6a49b331387e5',
    'OpenHarmonyProfileRelease.pem': '515f0bd8173fabb8bf8f146cd61207baa0e2d6ab8693ae7623df7ee6f16af70e',
}
# Only --prepare accesses this fixed existing public test signing input. The
# source agent never executes that path or reads the real file.
KEYSTORE_SHA = '7a5efc3ea9245596d157f6ccbbdc5b8ae7cd714e7086c3c1645986c9d495d071'


def need(condition, message):
    if not condition:
        raise ValueError(message)


def regular(path):
    path = Path(path)
    need(path.is_absolute() and path.resolve() == path and
         all(not p.is_symlink() for p in (path, *path.parents)), 'unaliased NumberIdentity input required')
    info = path.stat()
    need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, 'single regular NumberIdentity input required')
    return path


def read(path):
    return regular(path).read_bytes()


def root_path(root):
    root = Path(root)
    need(root.is_absolute() and root.resolve() == root and root.is_dir() and
         all(not p.is_symlink() for p in (root, *root.parents)), 'canonical real source root required')
    return root


def unique(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, 'duplicate NumberIdentity profile key')
        result[key] = value
    return result


def decode(data):
    need(len(data) <= 1048576, 'bounded NumberIdentity profile required')
    result = json.loads(data, object_pairs_hook=unique,
                        parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite profile JSON')))
    need(type(result) is dict, 'NumberIdentity profile object required')
    return result


def same_json(left, right):
    # Preserve JSON type: Python's ordinary equality accepts True == 1 == 1.0.
    return json.dumps(left, sort_keys=True, ensure_ascii=True, allow_nan=False) == json.dumps(
        right, sort_keys=True, ensure_ascii=True, allow_nan=False)


def certificates(data):
    return re.findall(b'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----', data, re.S)


def fingerprint(certificate):
    value = subprocess.run(['openssl', 'x509', '-outform', 'DER'], input=certificate,
                           capture_output=True, check=True, timeout=30).stdout
    return hashlib.sha256(value).hexdigest().upper()


def cms(path, signer=None):
    command = ['openssl', 'cms', '-verify', '-inform', 'DER', '-noverify', '-in', str(regular(path))]
    if signer is not None:
        command.extend(['-signer', str(signer)])
    # -noverify skips time/chain validation, NOT cryptographic signature checking.
    # A renewed profile additionally requires the exact pinned OS issuer below.
    return decode(subprocess.run(command, capture_output=True, check=True, timeout=30).stdout)


def desired_profile(original, leaf):
    bundle = original.get('bundle-info', {})
    validity = original.get('validity', {})
    need(type(bundle) is dict and type(validity) is dict and
         bundle.get('bundle-name') == BUNDLE and bundle.get('apl') == 'system_core' and
         bundle.get('app-feature') == 'hos_system_app' and original.get('type') == 'release' and
         original.get('app-distribution-type') == 'os_integration' and
         type(validity.get('not-after')) is int and validity['not-after'] == ORIGINAL_NOT_AFTER and
         type(bundle.get('distribution-certificate')) is str and
         fingerprint(leaf) == OS_LEAF, 'unexpected original NumberIdentity identity/expiry or fixed OS leaf')
    result = copy.deepcopy(original)
    result['bundle-info']['distribution-certificate'] = leaf.decode('ascii')
    result['validity']['not-after'] = RENEWED_NOT_AFTER
    result['app-privilege-capabilities'] = ['AllowAppUsePrivilegeExtension']
    return result


def source_identity(root, scratch):
    root = root_path(root)
    project = root / PROJECT
    dist = root / 'developtools/hapsigner/dist'
    actual = subprocess.check_output(['git', '-C', str(project), 'rev-parse', 'HEAD'],
                                     text=True, timeout=30).strip()
    need(actual == REVISION, 'fixed NumberIdentity source revision required')
    public = {name: read(dist / name) for name in PUBLIC_INPUTS}
    for name, expected in PUBLIC_INPUTS.items():
        need(hashlib.sha256(public[name]).hexdigest() == expected,
             'changed fixed public OS signing input: ' + name)
    raw = subprocess.check_output(['git', '-C', str(project), 'show', 'HEAD:' + PROFILE], timeout=30)
    need(hashlib.sha256(raw).hexdigest() == PROFILE_SHA, 'changed original public NumberIdentity profile')
    app_chain = certificates(public['OpenHarmonyApplication.pem'])
    issuer_chain = certificates(public['OpenHarmonyProfileRelease.pem'])
    need(len(app_chain) == 3 and len(issuer_chain) == 3, 'unexpected fixed OS certificate chain')
    original = scratch / 'original.p7b'
    original.write_bytes(raw)
    desired = desired_profile(cms(original), app_chain[-1] + b'\n')
    path = regular(project / PROFILE)
    return dict(root=root, project=project, dist=dist, raw=raw, public=public, path=path,
                current=read(path), desired=desired, issuer=fingerprint(issuer_chain[-1]))


def profile_matches(path, expected, issuer, scratch):
    signer = scratch / 'verified-profile-signer.pem'
    signer.unlink(missing_ok=True)
    actual = cms(path, signer)
    signers = certificates(read(signer))
    need(same_json(actual, expected) and len(signers) == 1 and fingerprint(signers[0]) == issuer,
         'NumberIdentity renewed policy or authenticated OS profile issuer differs')


def classify(identity, scratch, require_renewed=False):
    need(read(identity['path']) == identity['current'], 'NumberIdentity profile changed before classification')
    if identity['current'] == identity['raw']:
        need(not require_renewed, 'original public NumberIdentity profile is expired; authenticated renewal required')
        return 'original_expired_not_ready'
    # Never accept merely decoded JSON, a supplied receipt, filename or new SHA.
    state = 'authenticated_renewed'
    try:
        profile_matches(identity['path'], identity['desired'], identity['issuer'], scratch)
    except ValueError:
        if require_renewed:
            raise
        prior = copy.deepcopy(identity['desired'])
        prior.pop('app-privilege-capabilities', None)
        profile_matches(identity['path'], prior, identity['issuer'], scratch)
        state = 'prior_renewed_not_ready'
    need(read(identity['path']) == identity['current'], 'NumberIdentity profile changed during CMS verification')
    return state


def report(identity, state, changed=False):
    return {'status': 'pass', 'scope': 'source_profile_policy_and_fixed_OS_issuer_only',
            'state': state, 'changed': changed, 'bundle': BUNDLE, 'signer': OS_LEAF,
            'profile_sha256': hashlib.sha256(read(identity['path'])).hexdigest(),
            'original_profile_sha256': PROFILE_SHA,
            'original_not_after': ORIGINAL_NOT_AFTER, 'renewed_not_after': RENEWED_NOT_AFTER,
            'first_artifact_behavior_gate_passed': False, 'aggregate_provider_supported': False,
            'final_hap_signature_or_BMS_acceptance_proven': False}


def verify(root):
    """Package preflight. No keystore, signer invocation or source mutation."""
    with tempfile.TemporaryDirectory(prefix='number-profile-check-') as temporary:
        scratch = Path(temporary).resolve()
        identity = source_identity(root, scratch)
        state = classify(identity, scratch, require_renewed=True)
        return report(identity, state)


def inspect(root):
    """Read-only diagnostic; original is observable but explicitly not ready."""
    with tempfile.TemporaryDirectory(prefix='number-profile-inspect-') as temporary:
        scratch = Path(temporary).resolve()
        identity = source_identity(root, scratch)
        state = classify(identity, scratch)
        result = report(identity, state)
        result['ready_for_source_package_preflight'] = state == 'authenticated_renewed'
        return result


def sign_profile(identity, template, signed):
    # Root-only execution under its SDK/signing lease; source tests mock this.
    dist = identity['dist']
    need(hashlib.sha256(read(dist / 'OpenHarmony.p12')).hexdigest() == KEYSTORE_SHA,
         'changed fixed existing public test keystore; preserving source')
    subprocess.run(['java', '-jar', str(dist / 'hap-sign-tool.jar'), 'sign-profile',
                    '-keyAlias', 'openharmony application profile release', '-signAlg', 'SHA256withECDSA',
                    '-mode', 'localSign', '-profileCertFile', str(dist / 'OpenHarmonyProfileRelease.pem'),
                    '-inFile', str(template), '-keystoreFile', str(dist / 'OpenHarmony.p12'),
                    '-outFile', str(signed), '-keyPwd', '123456', '-keystorePwd', '123456'],
                   capture_output=True, check=True, timeout=120)


def replace(path, data):
    mode = stat.S_IMODE(regular(path).stat().st_mode)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix='.number-profile-', dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def publish(identity, pending, scratch):
    """One-file transaction: recheck source and all public inputs before publish."""
    check = source_identity(identity['root'], scratch)
    need(check['current'] == identity['current'] and check['raw'] == identity['raw'] and
         check['public'] == identity['public'] and same_json(check['desired'], identity['desired']) and
         check['issuer'] == identity['issuer'], 'NumberIdentity source changed before profile publication')
    if pending == identity['current']:
        return False
    try:
        replace(identity['path'], pending)
        profile_matches(identity['path'], identity['desired'], identity['issuer'], scratch)
    except BaseException:
        # Preserve a foreign writer. Only undo precisely our own pending bytes.
        if read(identity['path']) == pending:
            replace(identity['path'], identity['current'])
        raise
    return True


def prepare(root):
    """Root-only profile renewal. Existing legitimate renewal is idempotent."""
    with tempfile.TemporaryDirectory(prefix='number-profile-prepare-') as temporary:
        scratch = Path(temporary).resolve()
        identity = source_identity(root, scratch)
        state = classify(identity, scratch)
        if state == 'authenticated_renewed':
            return report(identity, state)
        template = scratch / 'profile.json'
        template.write_text(json.dumps(identity['desired'], ensure_ascii=False, indent=2) + '\n')
        signed = scratch / 'release.p7b'
        sign_profile(identity, template, signed)
        profile_matches(signed, identity['desired'], identity['issuer'], scratch)
        pending = read(signed)
        changed = publish(identity, pending, scratch)
        return report(identity, 'authenticated_renewed', changed)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    operation = parser.add_mutually_exclusive_group(required=True)
    operation.add_argument('--prepare', action='store_true', help='root only: renew exact original policy')
    operation.add_argument('--verify', action='store_true', help='read-only; expired original is rejected')
    operation.add_argument('--inspect', action='store_true', help='read-only; expired original is not ready')
    args = parser.parse_args(argv)
    action = prepare if args.prepare else verify if args.verify else inspect
    print(json.dumps(action(args.source_root), sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
