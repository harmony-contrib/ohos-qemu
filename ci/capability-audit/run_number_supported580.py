#!/usr/bin/env python3
"""Root serial outer wait + fixed original499 inner; no replacement resource Owner."""
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
import ctypes
import errno
import fcntl
import signal
import subprocess


def read_inputs(args):
    source = record(args.inputs); need(source['sha256'] == args.inputs_sha256, 'runtime inputs full SHA')
    value = doc(source)
    need(type(value) is dict and set(value) == {'schema', 'source_commit', 'archive', 'normal_source',
         'final_source_manifest', 'config', 'spec', 'observer_proof'} and value['schema'] == 'number580-run-inputs/v1',
         'fixed original499 input DATA only')
    admitted = admit(value); target = archive_target(value, admitted)
    if target['device'] == '2in1':
        need(value['config'] is None and value['spec'] is None and value['observer_proof'] is None, '2in1 has no phone runtime inputs')
    else:
        need(target['device'] == 'phone', 'finite phone runtime target')
        config = doc(value['config']); spec = doc(value['spec']); doc(value['observer_proof'])
        need(config['archive'] == value['archive'] and spec['source_commit'] == value['source_commit'] and
             spec['archive_sha256'] == value['archive']['sha256'] and spec['vm'] is None and
             spec['number580']['sources']['normal_source'] == value['normal_source'], 'same actual new archive/config/spec/normal identity')
    return source, value, admitted, target


def interrupt(signum, frame):
    raise InterruptedError('actual outer/inner signal ' + str(signum))


def inner(args):
    _, value, admitted, target = read_inputs(args)
    need(target['device'] == 'phone', 'inner is only the actual phone original499 run')
    owner = admitted['owner']
    registration = fixed(admitted['directory'] / 'register580.py', 'number580_entry_complete', admitted['authority'])
    for number in (signal.SIGINT, signal.SIGTERM): signal.signal(number, interrupt)
    # The only resource constructor chain remains wholly inside original owner499.run.
    return owner.run(value['config']['path'], value['config']['sha256'], value['spec']['path'], value['spec']['sha256'],
        args.output, observer_proof=doc(value['observer_proof']),
        number580_account_window=owner.account_window, number580_complete=registration.number580_complete)


def marker_cut(module):
    rows = []
    for path in (module.MARKER, module.BASE / '.representative35-unresolved.json'):
        need(path.parent == BASE and path.is_absolute(), 'fixed original marker location')
        # lstat, including dangling symlinks; never delete or rewrite any marker.
        try:
            info = path.lstat()
        except FileNotFoundError:
            rows.append(dict(path=str(path), absent=True))
        else:
            rows.append(dict(path=str(path), absent=False, mode=stat.S_IMODE(info.st_mode),
                             dev=info.st_dev, inode=info.st_ino, uid=info.st_uid))
    return rows


def lock_cut(module, *, before):
    path = module.LOCK
    need(path == BASE / '.representative10-resource.lock', 'original lease path only')
    # Original owner creates it if cold; the outer never manufactures it to claim release.
    regular(path); fd = os.open(path, os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0))
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        opened, named = os.fstat(fd), path.lstat()
        need((opened.st_dev, opened.st_ino) == (named.st_dev, named.st_ino) and opened.st_uid == os.getuid() and
             opened.st_nlink == 1 and stat.S_ISREG(opened.st_mode), 'original acquired lock inode/owner differs')
        rows = marker_cut(module); need(all(r['absent'] for r in rows), 'unresolved/foreign marker is preserved')
        identity = dict(path=str(path), dev=opened.st_dev, inode=opened.st_ino, uid=opened.st_uid, mode=stat.S_IMODE(opened.st_mode))
        if before is not None: need(identity == before, 'original runtime lease inode changed')
        return dict(identity=identity, exclusive_flock_acquired=True, markers=rows, monotonic_ns=time.monotonic_ns())
    finally:
        os.close(fd)


def group_members(pgid, owner):
    # Native Darwin readonly observation: no ps child and no additional Popen site.
    need(sys.platform == 'darwin' and ctypes.sizeof(owner.ProcBSDInfo) == 136, 'original Darwin proc_bsdinfo ABI')
    lib = ctypes.CDLL('/usr/lib/libproc.dylib', use_errno=True)
    call = lib.proc_listpids; call.argtypes = [ctypes.c_uint32, ctypes.c_uint32, ctypes.c_void_p, ctypes.c_int]; call.restype = ctypes.c_int
    buffer = (ctypes.c_int * 4096)(); ctypes.set_errno(0)
    size = call(2, pgid, buffer, ctypes.sizeof(buffer))  # PROC_PGRP_ONLY=2
    need((size > 0 or ctypes.get_errno() in (0, errno.ESRCH)) and 0 <= size < ctypes.sizeof(buffer) and size % ctypes.sizeof(ctypes.c_int) == 0, 'complete bounded actual process group cut')
    pids = [pid for pid in buffer[:size // ctypes.sizeof(ctypes.c_int)] if pid > 0]
    need(len(pids) == len(set(pids)), 'duplicate actual group PID')
    info = lib.proc_pidinfo; info.argtypes = [ctypes.c_int, ctypes.c_int, ctypes.c_uint64, ctypes.c_void_p, ctypes.c_int]; info.restype = ctypes.c_int
    rows = []
    for pid in pids:
        value = owner.ProcBSDInfo()
        ctypes.set_errno(0); count = info(pid, 3, 0, ctypes.byref(value), ctypes.sizeof(value))
        if count == 0:
            need(ctypes.get_errno() == errno.ESRCH, 'unknown native group-member observation error')
            continue  # It exited between the two native calls; next complete cut reconfirms.
        need(count == ctypes.sizeof(value) and value.pid == pid and value.pgid == pgid and value.uid == os.getuid(),
             'actual owned group member changed identity')
        rows.append(dict(pid=pid, pgid=value.pgid, status=value.status,
                         seconds=value.start_sec, microseconds=value.start_usec))
    return dict(api='proc_listpids.PROC_PGRP_ONLY+proc_pidinfo.PROC_PIDTBSDINFO', pgid=pgid,
                listed_pids=pids, members=rows, monotonic_ns=time.monotonic_ns())


def outer(args):
    input_ref, value, admitted, target = read_inputs(args); output = fresh(args.output)
    if target['device'] == '2in1':
        result = save(output / 'not-applicable.json', dict(schema='number580-original499-not-applicable/v1',
            inputs=input_ref, target=target, number_local=None, runtime_pass=False, first_artifact_behavior_gate_passed=False))
        print(json.dumps(result)); return 0
    owner = admitted['owner']; module, _ = owner.source_modules()
    need(all(hasattr(os, n) for n in ('waitid', 'P_PID', 'WEXITED', 'WNOHANG', 'WNOWAIT', 'CLD_EXITED', 'CLD_KILLED', 'CLD_DUMPED')),
         'actual unreaped WNOWAIT host support required')
    need(type(args.timeout) is int and 1 <= args.timeout <= 86400, 'explicit bounded Root runtime timeout')
    lease_before = lock_cut(module, before=None)
    child_output = output / 'original499'; stdout = output / 'stdout.raw'; stderr = output / 'stderr.raw'
    argv = [PYTHON, '-B', str(regular(__file__)), '--inner', '--inputs', str(checked(input_ref)),
            '--inputs-sha256', input_ref['sha256'], '--output', str(child_output), '--timeout', str(args.timeout)]
    attempt = dict(schema='number580-original499-command-completed/v1', source_commit=value['source_commit'],
        archive_sha256=value['archive']['sha256'], inputs=input_ref, argv=argv, exit_code=None, actual_wait=None,
        stdout=None, stderr=None, completed_input=None, leader_reaped=False, group_closed=False,
        lease_released=False, marker_absent=False, cleanup_verified=False, must_resolve=True, timed_out=False,
        failures=[], lease_before=lease_before, original_owner_close=None, group_cuts=[], signals=[], runtime_pass=False,
        first_artifact_behavior_gate_passed=False)
    process = None; reaped = False; observed = None; lease_after = None
    for number in (signal.SIGINT, signal.SIGTERM): signal.signal(number, interrupt)
    def observe():
        need(process is not None and process.returncode is None and not reaped, 'held unreaped exact Popen only')
        row = os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
        if row is None:
            need(os.getpgid(process.pid) == process.pid and os.getsid(process.pid) == process.pid,
                 'held original child session/group changed')
            if attempt.get('birth') is not None:
                need(owner.darwin_birth(process.pid) == attempt['birth'], 'running child PID incarnation changed')
            return None
        need(row.si_pid == process.pid and row.si_code in (os.CLD_EXITED, os.CLD_KILLED, os.CLD_DUMPED), 'exact WNOWAIT child result')
        return dict(pid=row.si_pid, si_code=row.si_code, si_status=row.si_status,
                    returncode=row.si_status if row.si_code == os.CLD_EXITED else -row.si_status,
                    monotonic_ns=time.monotonic_ns(), reaped=False)
    def signal_owned(number):
        observe()  # Successful WNOWAIT keeps the PID/PGID reserved, even if the leader is now a zombie.
        attempt['signals'].append(dict(pgid=process.pid, signal=number, monotonic_ns=time.monotonic_ns()))
        try: os.killpg(process.pid, number)
        except ProcessLookupError: pass
    def settle():
        nonlocal reaped, observed
        observed = observe(); cut = group_members(process.pid, owner); attempt['group_cuts'].append(cut)
        live = lambda c: [r for r in c['members'] if r['pid'] != process.pid and r['status'] != 5]  # Darwin SZOMB=5
        if observed is None or live(cut):
            signal_owned(signal.SIGTERM)
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                observed = observe(); cut = group_members(process.pid, owner); attempt['group_cuts'].append(cut)
                if observed is not None and not live(cut): break
                time.sleep(.2)
            if observed is None or live(cut):
                signal_owned(signal.SIGKILL); deadline = time.monotonic() + 15
                while time.monotonic() < deadline:
                    observed = observe(); cut = group_members(process.pid, owner); attempt['group_cuts'].append(cut)
                    if observed is not None and not live(cut): break
                    time.sleep(.2)
        need(observed is not None and not live(cut), 'original child/group remains unresolved; retain unreaped authority')
        # Final mutation boundary passed. No PGID signal is ever sent after this actual wait.
        actual = process.wait(timeout=10); reaped = True
        attempt['exit_code'] = actual; attempt['leader_reaped'] = True
        need(actual == observed['returncode'], 'actual Popen.wait differs from held WNOWAIT result')
        attempt['actual_wait'] = save(output / 'actual-wait-observed.json', dict(schema='number580-actual-Popen-wait/v1',
            pid=process.pid, pgid=process.pid, birth=attempt.get('birth'), argv=argv, returncode=actual,
            reaped=True, group_closed=False, wnowait=observed, monotonic_ns=time.monotonic_ns()))
        cuts = [group_members(process.pid, owner), group_members(process.pid, owner)]
        attempt['group_cuts'].extend(cuts)
        need(all(c['listed_pids'] == [] and c['members'] == [] for c in cuts), 'post-wait group is not absent; never signal historical PGID')
        attempt['group_closed'] = True
        attempt['actual_wait'] = save(output / 'actual-wait.json', dict(schema='number580-actual-Popen-wait/v1',
            pid=process.pid, pgid=process.pid, birth=attempt.get('birth'), argv=argv, returncode=actual,
            reaped=True, group_closed=True, wnowait=observed, group_cuts=cuts, monotonic_ns=time.monotonic_ns()))
    try:
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', PYTHONNOUSERSITE='1')
        env.pop('PYTHONPATH', None); env.pop('PYTHONHOME', None)
        with stdout.open('xb') as out, stderr.open('xb') as err:
            # The sole new runtime Popen constructor site; original owner499 owns all guest/resource constructors.
            process = subprocess.Popen(argv, cwd=R, env=env, stdin=subprocess.DEVNULL, stdout=out, stderr=err,
                                       start_new_session=True, close_fds=True)
            attempt['pid'] = process.pid; attempt['birth'] = owner.darwin_birth(process.pid)
            deadline = time.monotonic() + args.timeout
            while observe() is None:
                if time.monotonic() >= deadline:
                    attempt['timed_out'] = True; raise TimeoutError('actual Number original499 command timed out')
                time.sleep(.2)
            settle()
    except BaseException as error:
        attempt['failures'].append(type(error).__name__ + ': ' + str(error))
        if process is not None and not reaped:
            try: settle()
            except BaseException as close_error:
                attempt['failures'].append('settlement: ' + type(close_error).__name__ + ': ' + str(close_error))
    finally:
        for name, path in (('stdout', stdout), ('stderr', stderr)):
            try:
                attempt[name] = record(path)
            except BaseException as error:
                # A still-running unresolved child may still write this original
                # raw file. Keep its path, never invent a complete stable Ref.
                attempt.setdefault('partial_streams', {})[name] = str(path)
                attempt['failures'].append('actual ' + name + ': ' + type(error).__name__ + ': ' + str(error))
        try:
            lease_after = lock_cut(module, before=lease_before['identity'])
            attempt.update(lease_after=lease_after, lease_released=True, marker_absent=True)
        except BaseException as error:
            attempt['failures'].append('actual lease/marker: ' + type(error).__name__ + ': ' + str(error))
        try:
            close_ref = record(child_output / 'resource-close.json'); original_close = doc(close_ref)
            need(original_close['cleanup_verified'] is True and
                 checked(original_close['held_processes']).parent == child_output,
                 'actual original Owner finish/held close receipt required')
            attempt['original_owner_close'] = close_ref
        except BaseException as error:
            attempt['failures'].append('original Owner close: ' + type(error).__name__ + ': ' + str(error))
        try:
            completed_path = child_output / 'number580-completed-input.json'; completed = doc(record(completed_path))
            need(type(completed) is dict and set(completed) == COMPLETED6, 'original post-finish exact six completed inputs')
            for row in completed.values(): checked(row)
            need(completed['config'] == value['config'] and completed['spec'] == value['spec'] and
                 doc(completed['observer_proof']) == doc(value['observer_proof']), 'original six refs must bind actual supplied data')
            closure = doc(completed['owner_closure']); report = doc(completed['owner_report'])
            need(closure['cleanup_verified'] is True and completed['owner_closure'] == attempt['original_owner_close'] and
                 report['actual_resource_close'] == completed['owner_closure'],
                 'original Owner actual resource-close is required independently of parent wait')
            attempt['completed_input'] = completed
        except BaseException as error:
            attempt['failures'].append('actual completed input: ' + type(error).__name__ + ': ' + str(error))
        attempt['cleanup_verified'] = bool(attempt['leader_reaped'] and attempt['group_closed'] and
            attempt['lease_released'] and attempt['marker_absent'] and attempt['original_owner_close'] is not None)
        attempt['must_resolve'] = not attempt['cleanup_verified']
        if attempt['exit_code'] != 0 or attempt['timed_out']:
            attempt['failures'].append('actual unsuccessful/timeout original499 command; not accepted')
        result = save(output / 'command-attempt.json', attempt)
        completed7_ref = None
        if attempt['completed_input'] is not None:
            completed7 = dict(attempt['completed_input'], command_attempt=result)
            completed7_ref = save(output / 'completed7Refs.json', completed7)
        print(json.dumps(dict(schema='number580-runtime-entry-output/v1', command_attempt=result,
                              completed7Refs=completed7_ref)))
    return 0 if attempt['exit_code'] == 0 and not attempt['failures'] and attempt['cleanup_verified'] else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inputs', type=Path, required=True); parser.add_argument('--inputs-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True); parser.add_argument('--timeout', type=int, required=True)
    parser.add_argument('--inner', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    return inner(args) if args.inner else outer(args)


if __name__ == '__main__':
    raise SystemExit(main())
