#!/usr/bin/env python3
"""Root-only normal signing stage for exact local Number roles; never guest/SDK."""
from pathlib import Path, PurePosixPath
import hashlib
import importlib.util
import json
import os
import re
import stat
import sys
import time
import tarfile

R = Path('/Volumes/PSSD/code/ohos-rs/ohos-qemu')
BASE = Path('/Volumes/PSSD/qemu/validation/first-20261005/issue-20-20261006')
PYTHON = '/Volumes/PSSD/qemu/validation/first-20261005/host-regression-venv/bin/python'
NORMAL10 = ('produce580.py', 'owner499.py', 'corpus580.py', 'protocol580.py', 'register580.py',
            'project580.py', 'CONTRACT580.json', 'caller/LegacyNumberCorpus580.js',
            'caller/LegacyNumberCorpus580.d.ts', 'caller/NumberCorpus580.ets')
NORMAL5 = {'produce580.py', 'project580.py', 'caller/LegacyNumberCorpus580.js',
           'caller/LegacyNumberCorpus580.d.ts', 'caller/NumberCorpus580.ets'}
COMPLETED6 = {'owner_report', 'corpus', 'owner_closure', 'config', 'spec', 'observer_proof'}
UUID = r'[a-f0-9]{8}(?:-[a-f0-9]{4}){3}-[a-f0-9]{12}'
GET = 'ohos.permission.GET_TELEPHONY_STATE'
SET = 'ohos.permission.SET_TELEPHONY_STATE'
ROLES = ('system-granted', 'system-readonly', 'ordinary')
PERMISSIONS = {'system-granted': [GET, SET], 'system-readonly': [GET], 'ordinary': [],
              'account': ['ohos.permission.MANAGE_LOCAL_ACCOUNTS', 'ohos.permission.GET_LOCAL_ACCOUNTS',
                          'ohos.permission.INTERACT_ACROSS_LOCAL_ACCOUNTS_EXTENSION']}
BUNDLES = dict(zip(ROLES, ('org.harmonycontrib.numberlocal376.systemgranted',
                         'org.harmonycontrib.numberlocal376.systemreadonly',
                         'org.harmonycontrib.numberlocal376.ordinary')),
               account='org.ohos.qemu.networkwhole579.account')
_LOADED = {}


def need(value, message):
    if not value:
        raise ValueError(message)


def regular(path):
    path = Path(path)
    need(path.is_absolute() and path.resolve() == path and
         not any(p.is_symlink() for p in (path, *path.parents)), 'canonical nonalias path required')
    info = path.stat()
    need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, 'one-link regular file required')
    return path


def record(path):
    path = regular(path); before = path.stat(); digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    after = path.stat()
    fields = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    need(all(getattr(before, k) == getattr(after, k) for k in fields), 'actual file changed while reading')
    return dict(path=str(path), sha256=digest.hexdigest(), bytes=after.st_size)


def checked(row):
    need(type(row) is dict and set(row) == {'path', 'sha256', 'bytes'} and type(row['path']) is str and
         type(row['bytes']) is int and row['bytes'] >= 0 and type(row['sha256']) is str and
         re.fullmatch('[a-f0-9]{64}', row['sha256']), 'exact Ref3 required')
    path = regular(row['path']); need(record(path) == row, 'actual Ref3 bytes differ')
    return path


def decode(raw):
    need(type(raw) is bytes and len(raw) <= 256 * 1024 * 1024, 'bounded ordinary JSON required')
    def unique(pairs):
        result = {}
        for key, value in pairs:
            need(key not in result, 'duplicate JSON key'); result[key] = value
        return result
    return json.loads(raw, object_pairs_hook=unique,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))


def doc(row):
    return decode(checked(row).read_bytes())


def save(path, value):
    with Path(path).open('x', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False); stream.write('\n')
        stream.flush(); os.fsync(stream.fileno())
    return record(path)


def fresh(path):
    path = Path(path)
    need(path.is_absolute() and path.parent.resolve() == path.parent and path.parent.is_dir() and
         path.is_relative_to(BASE) and not path.exists() and not path.is_symlink(), 'fresh Root evidence output required')
    path.mkdir(mode=0o700)
    return path


def ref2(row):
    return {k: row[k] for k in ('path', 'sha256')}


def origin_check(authority):
    for name, module in list(sys.modules.items()):
        source = getattr(module, '__file__', None)
        if type(source) is not str or not source.endswith('.py'):
            continue
        path = Path(source)
        if path.is_absolute() and path.is_relative_to(R):
            actual = record(path)
            need(authority.get(str(path)) == actual['sha256'], 'foreign/unadmitted Python source: ' + name)


def fixed(path, name, authority):
    path = regular(path); need(authority.get(str(path)) == record(path)['sha256'], 'fixed source not in actual authority')
    cached = sys.modules.get(name)
    if name in _LOADED:
        need(cached is _LOADED[name] and Path(cached.__file__) == path, 'owned fixed module object replaced')
        origin_check(authority)
        return cached
    need(cached is None, 'foreign cached module refused before execution: ' + name)
    definition = importlib.util.spec_from_file_location(name, path)
    need(definition is not None and definition.loader is not None, 'fixed source loader required')
    module = importlib.util.module_from_spec(definition); sys.modules[name] = module
    _LOADED[name] = module
    try:
        definition.loader.exec_module(module)
        need(Path(module.__file__) == path and record(path)['sha256'] == authority[str(path)], 'fixed source changed on import')
        origin_check(authority)
        return module
    except BaseException:
        if sys.modules.get(name) is module: del sys.modules[name]
        _LOADED.pop(name, None)
        raise


def admit(inputs):
    need(sys.dont_write_bytecode and sys.executable == PYTHON, 'original host Python -B required')
    source = doc(inputs['normal_source']); final = doc(inputs['final_source_manifest'])
    commit = inputs['source_commit']
    need(type(commit) is str and re.fullmatch('[a-f0-9]{40}', commit) and
         source['schema'] == 'postpackage-source579-output/v1' and source['source_commit'] == commit and
         final['schema'] == 'final579-network-successor-fixed-source-vector/v1' and
         final['source_commit'] == commit and final['pending_dependencies'] == [] and
         final['original_kit'] == ref2(source['source_kit_manifest']), 'actual full normal/Final/Kit source identity')
    checked(source['source_kit_manifest']); snapshot = doc(source['canonical_snapshot'])
    need(snapshot['source_commit'] == commit and snapshot['count'] == len(snapshot['files']) == source['snapshot_count'],
         'complete actual canonical snapshot identity')
    authority = {}; canonical = {}
    need(type(final['files']) is list and final['files'], 'complete Final source authority required')
    for row in final['files']:
        need(type(row) is dict and set(row) == {'path', 'sha256'}, 'Final exact Ref2 source vector')
        path = regular(row['path']); need(str(path) not in authority, 'duplicate Final source path')
        need(record(path)['sha256'] == row['sha256'], 'actual Final source bytes differ')
        authority[str(path)] = row['sha256']
    for row in snapshot['files']:
        relative = PurePosixPath(row['path'])
        need(not relative.is_absolute() and '..' not in relative.parts and str(relative) == row['path'] and
             row['path'] not in canonical, 'canonical snapshot relative path')
        canonical[row['path']] = row
        if row['path'].endswith('.py'):
            path = R / row['path']; need(record(path) == dict(path=str(path), sha256=row['sha256'], bytes=row['bytes']) and
                 stat.S_IMODE(path.stat().st_mode) == row['mode'], 'actual canonical Python bytes/mode changed')
            previous = authority.get(str(path)); need(previous in (None, row['sha256']), 'conflicting canonical/Final source')
            authority[str(path)] = row['sha256']
    # The actual Kit manifest is a separate complete authority for its original
    # source members (e.g. held376.py), not assumed to be duplicated in Final.files.
    kit_manifest = checked(source['source_kit_manifest']); kit_root = kit_manifest.parent
    kit = doc(source['source_kit_manifest']); kit_names = set()
    for row in kit['members']:
        relative = PurePosixPath(row['path'])
        need(not relative.is_absolute() and '..' not in relative.parts and str(relative) == row['path'] and
             row['path'] not in kit_names, 'complete original Kit member path')
        kit_names.add(row['path']); path = kit_root / row['path']
        if row['kind'] == 'file':
            need(record(path) == dict(path=str(path), sha256=row['sha256'], bytes=row['bytes']) and
                 stat.S_IMODE(path.stat().st_mode) == row['mode'], 'actual complete Kit source bytes/mode')
            need(authority.get(str(path)) in (None, row['sha256']), 'conflicting original Kit source authority')
            authority[str(path)] = row['sha256']
        else:
            need(row['kind'] == 'symlink' and row['path'] == 'bin/docker' and row['target'] == '../docker_shim377.py' and
                 path.is_symlink() and os.readlink(path) == row['target'] and path.resolve() == kit_root / 'docker_shim377.py' and
                 stat.S_IMODE(path.lstat().st_mode) == row['mode'], 'only original Kit Docker shim alias')
    actual_kit = {p.relative_to(kit_root).as_posix() for p in kit_root.rglob('*') if p.is_file() or p.is_symlink()}
    need(actual_kit == kit_names | {'manifest.json'}, 'unknown/unlisted complete Kit member')
    need(authority.get(inputs['normal_source']['path']) == inputs['normal_source']['sha256'], 'Final must admit actual normal SOURCE')
    directory = checked(inputs['normal_source']).parent / 'number'
    need(source['number_local']['schema'] == 'number-local580-normal-source-selection/v1' and
         set(source['number_local']['sources']) == NORMAL5, 'normal SOURCE keeps exact five SDK source refs')
    for name in NORMAL10:
        path = directory / name
        need(authority.get(str(path)) == record(path)['sha256'], 'missing/changed one of all ten actual Number sources: ' + name)
    for name, row in source['number_local']['sources'].items():
        need(checked(row) == directory / name, 'normal five-source sibling selection differs')
    need(authority.get(str(Path(__file__))) == record(__file__)['sha256'], 'canonical entry must itself be in actual snapshot')
    # Reject existing canonical leaf imports before any selected business source can run.
    for relative in canonical:
        p = PurePosixPath(relative)
        if p.suffix == '.py' and p.parent.as_posix() in ('ci/capability-audit', 'scripts'):
            need(p.stem not in sys.modules, 'foreign preloaded canonical module: ' + p.stem)
    origin_check(authority)
    sys.path.insert(0, str(R / 'scripts')); sys.path.insert(0, str(R / 'ci/capability-audit'))
    owner = fixed(directory / 'owner499.py', 'number580_entry_original499', authority)
    need(owner.SOURCE_COMMIT == commit and owner.KIT == checked(source['source_kit_manifest']).parent and
         owner.KIT_SHA == source['source_kit_manifest']['sha256'] and owner.NUMBER580_DIRECTORY == directory,
         'owner literals must be actual typed SourceGEN identity, never parent globals')
    owner.verify_frozen_kit(owner.KIT_SHA, owner.KIT, docker_alias=True)
    return dict(source=source, final=final, commit=commit, directory=directory, authority=authority,
                owner=owner, canonical=canonical)


def archive_target(inputs, admitted):
    # Existing normal archive reader; the complete canonical Python closure was checked first.
    target = fixed(R / 'ci/capability-audit/production579_target.py', 'production579_target', admitted['authority'])
    actual = target.archive_manifest(checked(inputs['archive']))
    member = actual['context']['package_root'] + '/build-inputs.json'
    with tarfile.open(checked(inputs['archive']), 'r:gz') as archive:
        rows = [r for r in archive if r.name == member]
        need(len(rows) == 1 and rows[0].isfile() and 0 < rows[0].size <= 16 * 1024 * 1024,
             'single actual package build-input member')
        stream = archive.extractfile(rows[0]); need(stream is not None, 'actual archive source input')
        with stream: build = decode(stream.read())
    need(build['source_git_revision'] == inputs['source_commit'], 'archive must be this actual normal source HEAD')
    checked(inputs['archive']); origin_check(admitted['authority'])
    return actual['context']

import argparse
import subprocess
import zipfile
from types import SimpleNamespace


def configure(profile, role, udid, module):
    need(role in (*ROLES, 'account') and re.fullmatch('[a-fA-F0-9]{64}', udid) and
         udid.lower() not in ('0' * 64, 'f' * 64), 'fixed signed role and actual BM UDID')
    requests = module['module'].get('requestPermissions', [])
    need(module['app']['bundleName'] == BUNDLES[role] and module['module']['type'] == 'entry' and
         module['module']['deviceTypes'] == ['default'] and
         requests == [dict(name=p) for p in PERMISSIONS[role]], 'exact compiled phone role/bundle/permission contract')
    system = role != 'ordinary'
    profile['bundle-info'].update({'bundle-name': BUNDLES[role], 'apl': 'system_core' if system else 'normal',
                                  'app-feature': 'hos_system_app' if system else 'hos_normal_app'})
    profile['debug-info']['device-ids'] = [udid]
    profile['acls']['allowed-acls'] = list(PERMISSIONS[role])
    profile['permissions']['restricted-permissions'] = list(PERMISSIONS[role])
    return profile


def actual_udid(boot_ref, archive, target):
    boot_path = checked(boot_ref); boot = doc(boot_ref); env = boot['test_environment']
    need(boot['archive'] == archive['path'] and boot['archive_sha256'] == archive['sha256'] and
         boot['purpose'] == 'acceptance' and boot['status'] == 'pass' and boot['failures'] == [] and
         (env['product'], env['device_type'], env['guest_arch']) == (target['product'], target['device'], target['arch']) and
         re.fullmatch(UUID, env['boot_id']) and re.fullmatch('[a-fA-F0-9]{64}', env['udid']), 'same actual new archive boot/BM identity')
    wanted = 'param get const.ohos.apiversion; param get const.ohos.fullname; param get bootevent.boot.completed; bm get --udid'
    rows = []
    for row in boot['commands']:
        argv = row['argv']
        if type(argv) is list and len(argv) >= 5 and argv[-2:] == ['shell', wanted] and row['exit_code'] == 0:
            path = regular(row['log'])
            need(path.parent == boot_path.parent and record(path)['sha256'] == row['sha256'] and
                 row.get('timed_out', False) is False, 'actual retained owned BM command log')
            lines = path.read_bytes().decode('ascii').replace('\r', '').splitlines()
            if len(lines) == 5 and lines[0] == '26' and re.fullmatch(r'OpenHarmony-7\.0\.0\.[0-9]+', lines[1]) and                     lines[2:4] == ['true', 'udid of current device is :'] and lines[4] == env['udid']:
                rows.append(dict(command=row, log=record(path)))
    need(rows and env['udid'].lower() not in ('0' * 64, 'f' * 64), 'actual successful original BM/version raw is required')
    checked(boot_ref); checked(archive)
    return env['udid'], dict(boot=boot_ref, boot_id=env['boot_id'], retained_successful_BM_commands=rows)


def run(args):
    input_ref = record(args.inputs); need(input_ref['sha256'] == args.inputs_sha256, 'sign inputs exact SHA')
    inputs = doc(input_ref)
    need(type(inputs) is dict and set(inputs) == {'schema', 'source_commit', 'archive', 'normal_source',
         'final_source_manifest', 'sdk_evidence', 'identity_boot', 'signer'} and
         inputs['schema'] == 'number580-sign-inputs/v1', 'fixed signing DATA, no code selector')
    admitted = admit(inputs); target = archive_target(inputs, admitted); output = fresh(args.output)
    receipt = dict(schema='number580-normal-signing-output/v1', source_commit=inputs['source_commit'], inputs=input_ref,
        normal_source=inputs['normal_source'], final_source_manifest=inputs['final_source_manifest'], archive=inputs['archive'],
        target=target, commands=[], roles={}, account_controller=None, failures=[], runtime_pass=False,
        first_artifact_behavior_gate_passed=False, guest_executed=False, SDK_executed=False)
    try:
        sdk = doc(inputs['sdk_evidence'])
        need(sdk['schema'] == 'number-local580-actual-SDK/v1' and sdk['source_commit'] == admitted['commit'] and
             sdk['target']['device'] == target['device'] and sdk['target']['product'] == target['product'] and
             sdk['target']['arch'] == target['arch'] and sdk['exit_code'] == 0 and sdk['failures'] == [],
             'normal unsigned SDK and actual archive target')
        if target['device'] == '2in1':
            need(sdk['status'] == 'not_applicable' and sdk['roles'] == [] and sdk['account_controller'] is None and
                 sdk['commands'] == [] and inputs['identity_boot'] is None and inputs['signer'] is None,
                 '2in1 Number is explicit N/A without signing/phone data')
            receipt.update(status='not_applicable', applicable=False, exit_code=0)
        else:
            need(target['device'] == 'phone' and sdk['signed'] is False and sdk['guest_executed'] is False and
                 sdk['archive_binding']['archive'] == inputs['archive'] and
                 sdk['archive_binding']['normal_source'] == inputs['normal_source'], 'normal unsigned phone SDK only')
            udid, identity = actual_udid(inputs['identity_boot'], inputs['archive'], target); receipt['BM_identity'] = identity
            owner = admitted['owner']; _, collector = owner.source_modules()
            project = fixed(admitted['directory'] / 'project580.py', 'number580_sign_project', admitted['authority'])
            source_rows = {row['role']: row for row in sdk['roles']}
            need(len(sdk['roles']) == 3 and set(source_rows) == set(ROLES), 'exact three separately compiled Number roles')
            for role in ROLES:
                project.sdk_role_artifacts(dict(unsigned_hap=source_rows[role]['unsigned_hap'], sdk_evidence=inputs['sdk_evidence']),
                    role, admitted['commit'], original_collector=collector)
            controller = sdk['account_controller']
            project.account_sdk_artifacts(dict(run=sdk['run'], unsigned_hap=controller['unsigned_hap'],
                sdk_evidence=controller['sdk_evidence']), admitted['commit'], number_sdk=inputs['sdk_evidence'], original_collector=collector)
            signer = inputs['signer']; wanted = {'jar', 'UnsgnedDebugProfileTemplate.json', 'OpenHarmony.p12',
                                               'OpenHarmonyProfileDebug.pem', 'OpenHarmonyApplication.pem'}
            need(type(signer) is dict and set(signer) == wanted, 'complete actual original signer materials')
            paths = {k: checked(v) for k, v in signer.items()}; dist = paths['OpenHarmony.p12'].parent
            need(all(paths[n] == dist / n for n in wanted - {'jar'}), 'one actual public test signer distribution')
            shared = fixed(R / 'ci/capability-audit/sign_certificate_probe.py', 'sign_certificate_probe', admitted['authority'])
            for role in (*ROLES, 'account'):
                source = controller if role == 'account' else source_rows[role]
                unsigned = checked(source['unsigned_hap']); signed = output / (role + '.hap')
                order = []
                def command(argv, **kwargs):
                    need(list(argv[:3]) == ['java', '-jar', str(paths['jar'])] and
                         argv[3] == ('sign-profile', 'sign-app', 'verify-app', 'verify-profile')[len(order)] and
                         set(kwargs) <= {'check', 'capture_output', 'text'}, 'only original four signing mechanics commands')
                    index = len(receipt['commands']); start = time.monotonic_ns()
                    timeout_error = None
                    try:
                        actual = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                                timeout=300, check=False)
                    except subprocess.TimeoutExpired as error:
                        timeout_error = error
                        actual = subprocess.CompletedProcess(argv, None, error.stdout or b'', error.stderr or b'')
                    stdout = output / ('command-%03d.stdout' % index); stderr = output / ('command-%03d.stderr' % index)
                    stdout.write_bytes(actual.stdout); stderr.write_bytes(actual.stderr)
                    receipt['commands'].append(dict(role=role, argv=list(argv), exit_code=actual.returncode,
                        timed_out=timeout_error is not None, started_monotonic_ns=start, finished_monotonic_ns=time.monotonic_ns(),
                        stdout=record(stdout), stderr=record(stderr)))
                    order.append(argv[3]); save(output / ('command-%03d.json' % index), receipt['commands'][-1])
                    if timeout_error is not None: raise timeout_error
                    if kwargs.get('check') and actual.returncode:
                        raise subprocess.CalledProcessError(actual.returncode, argv, actual.stdout, actual.stderr)
                    if kwargs.get('text'):
                        return subprocess.CompletedProcess(argv, actual.returncode, actual.stdout.decode(), actual.stderr.decode())
                    return actual
                shared.sign(SimpleNamespace(unsigned=unsigned, output=signed, signer_dist=dist, jar=paths['jar'],
                                             role=role, udid=udid), configure=configure, command=command)
                need(order == ['sign-profile', 'sign-app', 'verify-app', 'verify-profile'], 'complete actual original signing/verification')
                with zipfile.ZipFile(unsigned) as old, zipfile.ZipFile(signed) as new:
                    need(old.namelist() == new.namelist() and all(old.read(n) == new.read(n) for n in old.namelist()),
                         'signing must preserve every unsigned member byte')
                sign = record(signed.with_suffix('.signing.json')); value = doc(sign)
                need(value['status'] == 'pass' and value['role'] == role and value['unsigned_sha256'] == source['unsigned_hap']['sha256'] and
                     value['signed_sha256'] == record(signed)['sha256'] and value['verified_profile']['debug-info']['device-ids'] == [udid],
                     'actual original role signature/profile receipt')
                result = dict(unsigned_hap=source['unsigned_hap'], signed_hap=record(signed), signing_receipt=sign,
                              sdk_evidence=controller['sdk_evidence'] if role == 'account' else inputs['sdk_evidence'])
                if role == 'account': receipt['account_controller'] = dict(run=sdk['run'], **result)
                else: receipt['roles'][role] = result
            checked(inputs['sdk_evidence']); checked(input_ref); checked(inputs['archive']); origin_check(admitted['authority'])
            for row in signer.values(): checked(row)
            receipt.update(status='pass', applicable=True, exit_code=0)
    except BaseException as error:
        receipt.update(status='fail', exit_code=1); receipt['failures'].append(type(error).__name__ + ': ' + str(error))
        save(output / 'signing-output.json', receipt)
        raise
    result = save(output / 'signing-output.json', receipt); print(json.dumps(result))
    return receipt['exit_code']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, required=True); parser.add_argument('--inputs-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    return run(parser.parse_args())


if __name__ == '__main__':
    raise SystemExit(main())
