#!/usr/bin/env python3
"""Stage one fixed PrivacyCenter HAP and its BMS scan entry; never sign or grant."""
from __future__ import annotations

import argparse
import copy
from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import ssl
import stat
import subprocess
import tempfile
import zipfile

BUNDLE = 'com.ohos.security.privacycenter'
FILENAME = 'SecurityPrivacyCenter.hap'
TARGET = 'applications/standard/hap/sceneboard/' + FILENAME
POLICY_DIR = 'vendor/ohemu/virt/preinstall-config'
ENTRY = {'app_dir': '/system/app/' + BUNDLE, 'removable': False}
ORIGINAL_SHA = 'd150dedbbf732b57ddc376e4a11dc4d873a75281d749bb74873ae0081d35e7e4'
CANONICAL_SHA = 'e955901c2f23c23edb819b92493fb7455873656815e21ac693681fa6af453f6a'
HAP_BYTES = 419639
JAR = 'prebuilts/ohos-sdk/linux/26.0.0/toolchains/lib/hap-sign-tool.jar'
JAR_SHA = 'a434b6747e6c5d0b14e73837a46b39f4816ab25b42d1833d6f767bf867cf616d'
APP_LEAF = '8E93863FC32EE238060BF69A9B37E2608FFFB21F93C862DD511CBAC9F30024B5'
PROFILE_LEAF = 'BF9771B891CF2DF55B50BDC7F1D583D842DC8CC68E99C381680BD6D25E7FFF20'
OLD_PROFILE_APP = 'C47D73E889DF1220F5E7B0A88FFCC7BECA6A80A7C3958580D592191EBAD70EB3'
COMPONENT = Path(__file__).resolve().parents[1] / 'common/applications/standard/hap/privacycenter_provider'
PUBLIC = COMPONENT / 'public'
FIXTURE_SHA = {
    'payload-inventory.json': '29432329dbc84c94814452c5b12b8238f8a90f7993d3a7851f7e69da8029b3ed',
    'original-profile.json': 'afd8c265a7849d23355d2898ff12a382cd7be806757c42bb5452c4a393011719',
    'original-profile.p7b': '443934d3823c4dd1b7694b594da52eeaffc31cfbdb059f57e6c548afb0ef16fc',
    'canonical-profile.json': 'e19b5b8c8b3c6c82b0caad6ca01bfb44f7eb25df886efe595f30ca9818159075',
    'canonical-profile.p7b': 'fae5769fd1b69499ace02473481e83b7f6cdefdf9e867a23e3bb28bf1538671e',
    'profile-release-leaf.pem': '868977cd0c8a3f9c1474dd9facda0dda2ca1b3cad36fb76f22623a78a0e2643c',
    'OpenHarmonyApplication.pem': 'b5c1d6254faa91eab645a32fc3ce136128c94d88a739a0e956e6a49b331387e5',
    'OpenHarmonyProfileRelease.pem': '515f0bd8173fabb8bf8f146cd61207baa0e2d6ab8693ae7623df7ee6f16af70e',
    'canonical-app-chain.cer': '5358faac7e78e3d89755a0b5da6c0ffe847c66f8dec02cce313e1f4b1b867de4',
    'canonical-verify-app.stdout': '9852bb8a09021fc9a270a41f8bc936deaf145d6d738b965fa2b56319de83c716',
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def unique(pairs):
    value = {}
    for key, item in pairs:
        require(key not in value, 'duplicate PrivacyCenter JSON field: ' + key)
        value[key] = item
    return value


def load(data):
    return json.loads(data, object_pairs_hook=unique)


def same(actual, expected):
    if type(actual) is not type(expected):
        return False
    if type(expected) is dict:
        return actual.keys() == expected.keys() and all(same(actual[k], v) for k, v in expected.items())
    if type(expected) is list:
        return len(actual) == len(expected) and all(same(a, b) for a, b in zip(actual, expected))
    return actual == expected


def canonical_root(path):
    path = Path(path).absolute()
    require(path.resolve() == path and path.is_dir(), 'canonical existing directory required: ' + str(path))
    for parent in (path, *path.parents):
        require(not parent.is_symlink(), 'redirected PrivacyCenter directory: ' + str(parent))
    return path


def parents(path):
    result = []
    for parent in path.parents:
        st = parent.lstat()
        require(stat.S_ISDIR(st.st_mode), 'redirected PrivacyCenter parent: ' + str(parent))
        result.append((str(parent), st.st_dev, st.st_ino))
    return tuple(result)


@dataclass(frozen=True)
class Snapshot:
    path: Path
    data: bytes
    mode: int
    owner: tuple
    identity: tuple
    ancestry: tuple

    @classmethod
    def read(cls, path, maximum=32 * 1024 * 1024):
        path = Path(path).absolute()
        ancestry = parents(path)
        first = path.lstat()
        require(stat.S_ISREG(first.st_mode) and first.st_nlink == 1 and first.st_size <= maximum,
                'one bounded regular nonaliased PrivacyCenter input required: ' + str(path))
        descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, 'rb') as stream:
            st = os.fstat(stream.fileno())
            require(stat.S_ISREG(st.st_mode) and st.st_nlink == 1 and st.st_size <= maximum,
                    'one bounded regular nonaliased PrivacyCenter input required: ' + str(path))
            require((st.st_dev, st.st_ino, st.st_mode, st.st_size) ==
                    (first.st_dev, first.st_ino, first.st_mode, first.st_size), 'PrivacyCenter input replaced before open')
            require(path.lstat().st_ino == st.st_ino and not path.is_symlink(), 'redirected PrivacyCenter file')
            data = stream.read(maximum + 1)
            end = os.fstat(stream.fileno())
        identity = (st.st_dev, st.st_ino, st.st_nlink)
        require(len(data) == st.st_size and (end.st_dev, end.st_ino, end.st_nlink, end.st_size,
                end.st_mtime_ns, end.st_ctime_ns, end.st_mode, end.st_uid, end.st_gid) ==
                (st.st_dev, st.st_ino, st.st_nlink, st.st_size, st.st_mtime_ns, st.st_ctime_ns,
                 st.st_mode, st.st_uid, st.st_gid), 'PrivacyCenter input changed while reading')
        result = cls(path, data, stat.S_IMODE(st.st_mode), (st.st_uid, st.st_gid), identity, ancestry)
        require(parents(path) == ancestry and path.lstat().st_dev == st.st_dev and path.lstat().st_ino == st.st_ino,
                'PrivacyCenter input replaced while reading')
        return result

    def check(self):
        require(Snapshot.read(self.path, max(len(self.data), 32 * 1024 * 1024)) == self,
                'PrivacyCenter input bytes/mode/owner/alias changed: ' + str(self.path))


def certificate_fingerprints(data):
    certificates = re.findall(r'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----', data.decode(), re.S)
    require(certificates, 'public certificate absent')
    return [digest(ssl.PEM_cert_to_DER_cert(cert)).upper() for cert in certificates]


def fixtures():
    rows = {name: Snapshot.read(PUBLIC / name) for name in FIXTURE_SHA}
    for name, row in rows.items():
        require(digest(row.data) == FIXTURE_SHA[name], 'fixed PrivacyCenter public fixture changed: ' + name)
    original, expected = (load(rows[name].data) for name in ('original-profile.json', 'canonical-profile.json'))
    info = original['bundle-info']
    require(info['bundle-name'] == BUNDLE and info['apl'] == 'normal' and info['app-feature'] == 'hos_system_app' and
            original['type'] == 'release' and original['validity'] == {'not-before': 1594865258, 'not-after': 1689473258} and
            certificate_fingerprints(info['distribution-certificate'].encode()) == [OLD_PROFILE_APP],
            'fixed authenticated original profile identity changed')
    wanted = copy.deepcopy(original)
    wanted['bundle-info']['distribution-certificate'] = expected['bundle-info']['distribution-certificate']
    require(same(wanted, expected) and certificate_fingerprints(wanted['bundle-info']['distribution-certificate'].encode()) == [APP_LEAF],
            'canonical profile must change only its distribution certificate')
    require(certificate_fingerprints(rows['profile-release-leaf.pem'].data) == [PROFILE_LEAF] and
            certificate_fingerprints(rows['OpenHarmonyApplication.pem'].data)[-1] == APP_LEAF and
            certificate_fingerprints(rows['OpenHarmonyProfileRelease.pem'].data)[-1] == PROFILE_LEAF,
            'fixed public OS application/profile leaves changed')
    return rows


def inspect_payload(data, inventory, *, canonical=True):
    expected_hash = CANONICAL_SHA if canonical else ORIGINAL_SHA
    require(digest(data) == expected_hash and len(data) == (HAP_BYTES if canonical else 417639),
            'PrivacyCenter HAP is not the exact original/canonical artifact')
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        entries = archive.infolist()
        names = [item.filename for item in entries]
        require(len(names) == len(set(names)) == len(inventory) and set(names) == set(inventory),
                'PrivacyCenter ZIP member inventory/duplicates changed')
        for item in entries:
            path = PurePosixPath(item.filename)
            mode = item.external_attr >> 16
            require(path.as_posix() == item.filename and not path.is_absolute() and '..' not in path.parts and
                    '\\' not in item.filename and not item.flag_bits & 1 and not item.is_dir() and
                    stat.S_IFMT(mode) in (0, stat.S_IFREG) and item.file_size <= 16 * 1024 * 1024,
                    'unsafe PrivacyCenter ZIP member')
            payload = archive.read(item)
            require(same({'bytes': len(payload), 'sha256': digest(payload)}, inventory[item.filename]),
                    'PrivacyCenter original payload changed: ' + item.filename)
        module = load(archive.read('module.json'))
        require(module['app']['bundleName'] == BUNDLE and module['module']['name'] == 'entry' and
                module['module']['deviceTypes'] == ['default', '2in1'], 'PrivacyCenter compiled identity changed')
    return {'hap_sha256': digest(data), 'bytes': len(data), 'original_payload_members_verified': len(inventory),
            'original_abc_sha256': inventory['ets/modules.abc']['sha256'],
            'module': module, 'payload_unchanged': True}


def application_leaf(log):
    sections = re.split(r'certificate #0\b', log)
    require(len(sections) == 2, 'one actual PrivacyCenter application leaf required')
    leaf = re.split(r'certificate #1\b', sections[1])[0]
    fingerprints = re.findall(r'SHA256:\s*([0-9A-Fa-f:]+)', leaf)
    require(len(fingerprints) == 1 and fingerprints[0].replace(':', '').upper() == APP_LEAF,
            'PrivacyCenter actual application signer differs')


def command(argv, label, commands):
    argv = list(map(str, argv))
    try:
        result = subprocess.run(argv, capture_output=True, timeout=60)
    except subprocess.TimeoutExpired as error:
        stdout, stderr = error.stdout or b'', error.stderr or b''
        commands.append({'label': label, 'argv': argv, 'exit_code': None, 'timed_out': True,
                         'stdout': stdout.decode(errors='replace'), 'stderr': stderr.decode(errors='replace'),
                         'stdout_sha256': digest(stdout), 'stderr_sha256': digest(stderr)})
        raise
    row = {'label': label, 'argv': list(map(str, argv)), 'exit_code': result.returncode,
           'stdout': result.stdout.decode(errors='replace'), 'stderr': result.stderr.decode(errors='replace'),
           'stdout_sha256': digest(result.stdout), 'stderr_sha256': digest(result.stderr)}
    commands.append(row)
    require(result.returncode == 0, 'PrivacyCenter verification command failed: ' + label)
    return row['stdout'], row['stderr']


def verify_signature(data, jar, public, *, java='java', openssl='openssl', commands=None):
    """Execute verification only. No keystore, signing, grant or date renewal."""
    commands = [] if commands is None else commands
    inspect_payload(data, load(public['payload-inventory.json'].data))
    require(digest(jar.data) == JAR_SHA, 'fixed real hap-sign-tool.jar required')
    expected = load(public['canonical-profile.json'].data)
    original = load(public['original-profile.json'].data)
    with tempfile.TemporaryDirectory(prefix='privacycenter-signature-') as temporary:
        scratch = Path(temporary).resolve()
        copied = {}
        for name in ('original-profile.p7b', 'profile-release-leaf.pem'):
            copied[name] = scratch / name; copied[name].write_bytes(public[name].data)
        tool = scratch / 'hap-sign-tool.jar'; tool.write_bytes(jar.data)
        hap = scratch / FILENAME; hap.write_bytes(data)
        chain, profile = scratch / 'actual-chain.cer', scratch / 'actual-profile.p7b'
        stdout, _ = command([java, '-jar', tool, 'verify-app', '-inFile', hap,
                             '-outCertChain', chain, '-outProfile', profile], 'verify-app', commands)
        require(all(marker in stdout for marker in ('verify codesign success', 'Digest verify result: true',
                'verify permission sign success', 'verify-app success')), 'PrivacyCenter four actual signature checks required')
        application_leaf(stdout)
        chain_data = Snapshot.read(chain).data
        expected_chain = certificate_fingerprints(public['OpenHarmonyApplication.pem'].data)
        actual_chain = certificate_fingerprints(chain_data)
        require(len(actual_chain) == 3 and actual_chain[0] == APP_LEAF and
                len(set(actual_chain)) == 3 and set(actual_chain) == set(expected_chain), 'PrivacyCenter full public OS chain differs')
        require(Snapshot.read(profile).data == public['canonical-profile.p7b'].data, 'embedded canonical profile bytes changed')
        for name, path, desired in (('canonical', profile, expected), ('original', copied['original-profile.p7b'], original)):
            verified, cms = scratch / (name + '-verified.json'), scratch / (name + '-CMS.json')
            stdout, _ = command([java, '-jar', tool, 'verify-profile', '-inFile', path, '-outFile', verified],
                                 name + '-verify-profile', commands)
            report = load(Snapshot.read(verified).data)
            require('verify-profile success' in stdout and report.get('verifiedPassed') is True and
                    report.get('message') == 'OK' and same(report.get('content'), desired), 'verified profile content differs')
            _, stderr = command([openssl, 'cms', '-verify', '-inform', 'DER', '-nointern', '-certfile',
                copied['profile-release-leaf.pem'], '-noverify', '-in', path, '-out', cms], name + '-fixed-release-CMS', commands)
            require('CMS Verification successful' in stderr and same(load(Snapshot.read(cms).data), desired),
                    'fixed release-leaf CMS profile verification differs')
    return {'application_leaf_sha256': APP_LEAF, 'profile_leaf_sha256': PROFILE_LEAF,
            'original_profile_authenticated': True, 'profile_policy_only_change': 'bundle-info.distribution-certificate',
            'legacy_validity_preserved_NOT_runtime_acceptance': expected['validity'], 'commands': commands}


def policy_inventory(directory):
    require(directory.is_dir() and not directory.is_symlink(), 'real preinstall policy directory required')
    return tuple(sorted(item.name for item in directory.iterdir()))


def policy_audit(rows, *, installed=False):
    required = {'install_list.json', 'install_list_capability.json', 'install_list_permissions.json', 'uninstall_list.json'}
    require(required <= rows.keys(), 'complete preinstall installation/permission/capability/uninstall policies required')
    documents = {name: load(data) for name, data in rows.items() if name.endswith('.json')}
    install = documents['install_list.json']
    require(type(install) is dict and type(install.get('install_list')) is list and
            all(type(row) is dict and type(row.get('app_dir')) is str for row in install['install_list']),
            'invalid actual BMS scan installation list')
    matches = [row for row in install['install_list'] if BUNDLE in json.dumps(row)]
    require(not matches or same(matches, [ENTRY]), 'conflicting/aliased/duplicate PrivacyCenter scan entry')
    require(not installed or same(matches, [ENTRY]), 'canonical PrivacyCenter scan entry missing')
    remainder = copy.deepcopy(install)
    remainder['install_list'] = [row for row in remainder['install_list'] if row not in matches]
    require(BUNDLE not in json.dumps(remainder), 'unrecognized PrivacyCenter installation policy reference')
    for row in install['install_list']:
        path = PurePosixPath(row['app_dir'])
        require(path.is_absolute() and path.as_posix() == row['app_dir'] and '..' not in path.parts and
                (str(path) == ENTRY['app_dir'] or not PurePosixPath(ENTRY['app_dir']).is_relative_to(path)),
                'aliased or overlapping PrivacyCenter scan directory')
    capability = documents['install_list_capability.json']
    grants = documents['install_list_permissions.json']
    uninstall = documents['uninstall_list.json']
    require(type(capability) is dict and type(capability.get('install_list')) is list and
            all(type(row) is dict for row in capability['install_list']) and
            type(grants) is list and all(type(row) is dict for row in grants) and
            type(uninstall) is dict and all(type(uninstall.get(key)) is list and
                all(type(item) is str for item in uninstall[key]) for key in ('uninstall_list', 'recover_list')),
            'invalid capability/permission/uninstall audit input')
    for name, data in rows.items():
        if name != 'install_list.json':
            normalized = json.dumps(documents[name], ensure_ascii=False) if name in documents else data.decode()
            require(BUNDLE not in normalized, 'existing PrivacyCenter policy requires review; preserve it: ' + name)
    if matches:
        return rows['install_list.json']
    changed = copy.deepcopy(install)
    changed['install_list'].append(copy.deepcopy(ENTRY))
    return (json.dumps(changed, indent=2, ensure_ascii=False) + '\n').encode()


def metadata(device, revision):
    require(device in ('phone', '2in1') and re.fullmatch('[0-9a-f]{40}', revision or ''), 'explicit device and native source revision required')
    return {'bundle': BUNDLE, 'hap_sha256': CANONICAL_SHA, 'original_hap_sha256': ORIGINAL_SHA,
            'original_payload_inventory_sha256': FIXTURE_SHA['payload-inventory.json'],
            'canonical_profile_sha256': FIXTURE_SHA['canonical-profile.p7b'], 'application_signer_sha256': APP_LEAF,
            'profile_signer_sha256': PROFILE_LEAF, 'profile_validity_preserved': {'not-before': 1594865258, 'not-after': 1689473258},
            'native_source_revision': revision, 'device': device, 'install_entry': ENTRY,
            'provider_runtime_validated': False, 'first_artifact_behavior_gate_passed': False}


def collect(source, assets, device, revision, *, installed=False):
    source = canonical_root(source)
    public = fixtures()
    policy_dir = source / POLICY_DIR
    inventory = policy_inventory(policy_dir)
    policies = {name: Snapshot.read(policy_dir / name, 4 * 1024 * 1024) for name in inventory}
    snapshots = {row.path: row for row in (*public.values(), *policies.values())}
    hap = Snapshot.read(source / TARGET)
    require(digest(hap.data) in ((CANONICAL_SHA,) if installed else (ORIGINAL_SHA, CANONICAL_SHA)),
            'unknown source PrivacyCenter HAP; preserve source')
    inspect_payload(hap.data, load(public['payload-inventory.json'].data), canonical=digest(hap.data) == CANONICAL_SHA)
    install = policy_audit({name: row.data for name, row in policies.items()}, installed=installed)
    meta_path = source / f'vendor/ohemu/virt/virt_{device}_full.meta.json'
    meta = Snapshot.read(meta_path)
    document = load(meta.data)
    require(type(document) is dict, 'actual device metadata must be an object')
    desired = metadata(device, revision)
    if 'privacycenter_provider' in document:
        require(same(document['privacycenter_provider'], desired) and digest(hap.data) == CANONICAL_SHA and
                install == policies['install_list.json'].data, 'unknown or partial PrivacyCenter metadata; preserve it')
    elif installed:
        raise ValueError('PrivacyCenter device metadata missing')
    document['privacycenter_provider'] = desired
    meta_data = meta.data if same(load(meta.data), document) else (json.dumps(document, indent=2, ensure_ascii=False) + '\n').encode()
    jar = Snapshot.read(source / JAR)
    require(digest(jar.data) == JAR_SHA, 'fixed source HAP verification JAR required')
    for row in (hap, meta, jar): snapshots[row.path] = row
    asset = None
    if assets is not None:
        asset = Snapshot.read(canonical_root(assets) / FILENAME)
        require(asset.path not in snapshots, 'PrivacyCenter asset must be separate from source inputs')
        inspect_payload(asset.data, load(public['payload-inventory.json'].data))
        snapshots[asset.path] = asset
    return {'source': source, 'public': public, 'policies': policies, 'snapshots': snapshots, 'hap': hap,
            'asset': asset, 'jar': jar, 'meta': meta, 'meta_data': meta_data, 'install': install,
            'policy_dir': policy_dir, 'policy_inventory': inventory, 'metadata': desired}


def recheck(state, written=None):
    written = {} if written is None else written
    require(policy_inventory(state['policy_dir']) == state['policy_inventory'], 'preinstall policy file inventory changed')
    for path, row in state['snapshots'].items():
        written.get(path, row).check()


def replace(path, data, before, written):
    """Atomic single-file replacement with tracked ownership even on late errors."""
    pending = None
    try:
        with tempfile.NamedTemporaryFile(prefix='.privacycenter-provider-', dir=path.parent, delete=False) as stream:
            pending = Path(stream.name)
            stream.write(data); stream.flush(); os.fsync(stream.fileno())
            os.fchmod(stream.fileno(), before.mode)
            st = os.fstat(stream.fileno())
            if (st.st_uid, st.st_gid) != before.owner: os.fchown(stream.fileno(), *before.owner)
        candidate = Snapshot.read(pending)
        installed = Snapshot(path, candidate.data, candidate.mode, candidate.owner, candidate.identity, before.ancestry)
        before.check()
        try:
            os.replace(pending, path)
        finally:
            if path.exists() and (path.lstat().st_dev, path.lstat().st_ino) == candidate.identity[:2]:
                written[path] = installed
        descriptor = os.open(path.parent, os.O_RDONLY)
        try: os.fsync(descriptor)
        finally: os.close(descriptor)
        installed.check()
    finally:
        if pending is not None: pending.unlink(missing_ok=True)


def transaction(state, updates):
    written = {}
    try:
        for path, data in updates.items():
            recheck(state, written)
            if data != state['snapshots'][path].data:
                replace(path, data, state['snapshots'][path], written)
        recheck(state, written)
    except BaseException as error:
        conflicts = []
        for path, owned in reversed(list(written.items())):
            try:
                owned.check()
                original = state['snapshots'][path]
                replace(path, original.data, owned, {})
            except Exception as rollback_error:
                conflicts.append(str(path) + ': ' + str(rollback_error))
        if conflicts:
            raise ValueError('PrivacyCenter transaction failed; preserve external changes/rollback conflicts: ' +
                             repr(error) + '; ' + '; '.join(conflicts)) from error
        raise
    return [str(path) for path in written]


def apply(source, assets, device, revision, *, java='java', openssl='openssl', commands=None):
    state = collect(source, assets, device, revision)
    proof = verify_signature(state['asset'].data, state['jar'], state['public'], java=java, openssl=openssl, commands=commands)
    recheck(state)
    updates = {state['hap'].path: state['asset'].data,
               state['policies']['install_list.json'].path: state['install'], state['meta'].path: state['meta_data']}
    changed = transaction(state, updates)
    return {'status': 'pass', 'scope': 'exact_PrivacyCenter_HAP_scan_entry_staging_ONLY', 'changed': changed,
            'source_hap': {'path': str(state['hap'].path), 'before_sha256': digest(state['hap'].data),
                           'after_sha256': CANONICAL_SHA, 'preserved_mode': oct(state['hap'].mode)},
            'asset': {'path': str(state['asset'].path), 'sha256': digest(state['asset'].data)},
            'preinstall_policy_audit_before': {name: digest(row.data) for name, row in state['policies'].items()},
            'metadata': state['metadata'], 'signature': proof, 'provider_runtime_validated': False,
            'first_artifact_behavior_gate_passed': False}


def verify_source(source, device, revision, *, java='java', openssl='openssl', commands=None):
    state = collect(source, None, device, revision, installed=True)
    proof = verify_signature(state['hap'].data, state['jar'], state['public'], java=java, openssl=openssl, commands=commands)
    recheck(state)
    return state, {'status': 'pass', 'scope': 'offline_PrivacyCenter_source_HAP_policy_ONLY',
                   'source_hap': {'path': str(state['hap'].path), 'sha256': digest(state['hap'].data)},
                   'metadata': state['metadata'], 'signature': proof,
                   'policies': {name: digest(row.data) for name, row in state['policies'].items()},
                   'provider_runtime_validated': False, 'first_artifact_behavior_gate_passed': False}


def main(device=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--asset-root', type=Path)
    parser.add_argument('--device', choices=('phone', '2in1'), required=device is None, default=device)
    parser.add_argument('--native-source-revision', required=True)
    parser.add_argument('--java', default='java'); parser.add_argument('--openssl', default='openssl')
    parser.add_argument('--verify-only', action='store_true')
    args = parser.parse_args()
    if not args.verify_only and args.asset_root is None: parser.error('--asset-root required for staging')
    commands = []
    try:
        if args.verify_only:
            _, result = verify_source(args.source_root, args.device, args.native_source_revision, java=args.java, openssl=args.openssl, commands=commands)
        else:
            result = apply(args.source_root, args.asset_root, args.device, args.native_source_revision, java=args.java, openssl=args.openssl, commands=commands)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, zipfile.BadZipFile) as error:
        print(json.dumps({'status': 'fail', 'error': str(error), 'commands': commands, 'provider_runtime_validated': False,
                          'first_artifact_behavior_gate_passed': False})); return 1
    print(json.dumps(result, ensure_ascii=False)); return 0


if __name__ == '__main__': raise SystemExit(main())
