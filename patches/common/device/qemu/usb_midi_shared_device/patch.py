"""Complete fixed normal USB/MIDI/MTP source transaction; no runtime verdict."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import stat
import subprocess
import tempfile

HERE = Path(__file__).resolve().parent
STATES_SHA256 = '838730f5a808a7849f2efb8bcc889c4987d208d427d62f948ab86a0f13ea8b0c'
PREVIOUS_STATES_SHA256 = '4ffd8a1b23eefc3acc55d8a4b952f0e3f0ca0c2c05c75ca436aeaae0934d5a1b'
PREVIOUS_EDITS_SHA256 = '95217549884a3a978bb1d4299fe961f4b840801df8899ddac86a47ee4e0a26ab'
MTP_FUNCTIONFS_SOURCE = 'drivers/peripheral/usb/gadget/function/mtp/src/qemu_mtp_functionfs.cpp'
PREVIOUS_MTP_CPP_SHA256 = 'c9bae4d9325a7149661a23ba6eeb5218397d683fd1ecb19f70935e4f363f30c7'
CURRENT_MTP_CPP_SHA256 = 'f1cca308728780404fe6065a92b19914f84c8e53e49c1c65fa6e331ba97837f4'
MAX_FILE_BYTES = 4 * 1024 * 1024


def need(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def unaliased(path):
    path = Path(path)
    need(path.is_absolute() and path.resolve() == path and
         not any(p.is_symlink() for p in (path, *path.parents)), 'unaliased absolute source path required')
    return path


def target(root, name):
    relative = Path(name)
    need(not relative.is_absolute() and '..' not in relative.parts and str(relative) == name and
         name not in ('', '.') and relative.parts[0] != 'out', 'fixed source path required')
    return unaliased(root / relative)


def identity(info):
    return tuple(getattr(info, key) for key in
        ('st_dev', 'st_ino', 'st_nlink', 'st_mode', 'st_uid', 'st_gid', 'st_size', 'st_mtime_ns', 'st_ctime_ns'))


def capture(path, *, missing=False):
    path = unaliased(path)
    parents = []
    for parent in path.parents:
        info = parent.lstat()
        need(stat.S_ISDIR(info.st_mode), 'real source parent required')
        parents.append((str(parent), info.st_dev, info.st_ino, stat.S_IMODE(info.st_mode), info.st_uid, info.st_gid))
    try:
        info = path.lstat()
    except FileNotFoundError:
        need(missing, 'fixed existing source missing: ' + str(path))
        return dict(data=None, identity=None, parents=parents, mode=None, uid=None, gid=None)
    need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= MAX_FILE_BYTES,
         'bounded one-link regular source required: ' + str(path))
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as stream:
        opened = os.fstat(stream.fileno())
        data = stream.read(MAX_FILE_BYTES + 1)
        closed = os.fstat(stream.fileno())
    need(identity(info) == identity(opened) == identity(closed) == identity(path.lstat()) and
         len(data) == info.st_size, 'source changed during byte read: ' + str(path))
    return dict(data=data, identity=identity(info), parents=parents,
                mode=stat.S_IMODE(info.st_mode), uid=info.st_uid, gid=info.st_gid)


def load():
    path = HERE / 'source_states.json'
    retained = capture(path)
    need(sha(retained['data']) == STATES_SHA256, 'fixed complete source manifest differs')
    spec = json.loads(retained['data'])
    need(spec['schema'] == 'qemu-usb-midi-mtp-complete-source-vectors/v2' and len(spec['paths']) == 24 and
         len(set(spec['paths'])) == 24 and len(spec['new_paths']) == 3 and len(spec['vectors']) == 22 and
         len({v['name'] for v in spec['vectors']}) == 15 and
         len({v['variant'] for v in spec['vectors']}) == 22 and
         len(spec['projects']) == 5, 'complete 24-source/fifteen-profile/22-availability/five-project contract required')
    need(sum(v['armv7_jsvm'] == 'off-unselected' for v in spec['vectors']) == 7 and
         all(v['armv7_jsvm'] in ('on', 'off-unselected') and
             (v['armv7_jsvm'] == 'on' or 'armv7a_virt' not in v['products'])
             for v in spec['vectors']), 'fixed unselected ARMv7 availability variants required')
    support = {str(path): retained}
    edits_path = HERE / 'edits.json'
    edits = capture(edits_path)
    need(sha(edits['data']) == spec['edits_sha256'], 'original USB/MIDI/MTP edit contract differs')
    support[str(edits_path)] = edits
    original = json.loads(edits['data'])
    need({x['path'] for x in original['edits'] + original['new_files']} == set(spec['paths']) and
         {x['path'] for x in original['new_files']} == set(spec['new_paths']), 'exact original full source set required')
    bodies = {}
    for expected, row in spec['assets'].items():
        asset = target(HERE, row['file'])
        saved = capture(asset)
        need(sha(saved['data']) == expected and len(saved['data']) == row['bytes'], 'fixed source asset differs')
        support[str(asset)] = saved
        bodies[expected] = saved['data']
    need({x.name for x in (HERE / 'assets').iterdir()} == {Path(x['file']).name for x in spec['assets'].values()},
         'unknown or missing source asset')
    for name, row in spec['proofs'].items():
        path = target(HERE, name)
        saved = capture(path)
        need(sha(saved['data']) == row['sha256'] and len(saved['data']) == row['bytes'], 'actual source proof differs')
        support[str(path)] = saved
    for row in spec['profile_source_guards'].values():
        path = target(HERE.parents[4], row['path'])
        saved = capture(path)
        need(sha(saved['data']) == row['sha256'], 'fixed normal profile source differs')
        support[str(path)] = saved
    for vector in spec['vectors']:
        for endpoint in ('prefix', 'before', 'after'):
            need(set(vector[endpoint]) == set(spec['paths']), 'partial source endpoint refused')
            for name, expected in vector[endpoint].items():
                need(expected in bodies or (expected is None and endpoint in ('prefix', 'before') and name in spec['new_paths']),
                     'unknown source asset or absent existing source')
    # Only this exact complete previous24 manifest is eligible at the prefix.
    # Retain its full edits as well; no individual source accepts an old hash.
    previous_record = dict(states='PREVIOUS-SOURCE-STATES579.json', states_sha256=PREVIOUS_STATES_SHA256,
                           edits='PREVIOUS-EDITS579.json', edits_sha256=PREVIOUS_EDITS_SHA256)
    need(spec['previous_final'] == previous_record, 'fixed previous full-source contract differs')
    previous_raw = support[str(HERE / previous_record['states'])]['data']
    previous_edits_raw = support[str(HERE / previous_record['edits'])]['data']
    need(sha(previous_raw) == PREVIOUS_STATES_SHA256 and
         sha(previous_edits_raw) == PREVIOUS_EDITS_SHA256, 'complete previous source/edit bytes differ')
    previous = json.loads(previous_raw)
    previous_edits = json.loads(previous_edits_raw)
    for field in ('schema', 'projects', 'paths', 'new_paths', 'modes', 'profile_source_guards', 'source_only', 'runtime_pass'):
        need(previous[field] == spec[field], 'previous/current source identity differs: ' + field)
    need(previous['edits_sha256'] == PREVIOUS_EDITS_SHA256 and
         len(previous['vectors']) == len(spec['vectors']) == 22,
         'complete previous22 variants and original edits required')
    need(CURRENT_MTP_CPP_SHA256 in spec['assets'] and CURRENT_MTP_CPP_SHA256 not in previous['assets'] and
         previous['assets'] == {k: v for k, v in spec['assets'].items() if k != CURRENT_MTP_CPP_SHA256},
         'only one new fixed MTP source asset may be added')
    need(all(spec['proofs'].get(k) == v for k, v in previous['proofs'].items()),
         'all original actual-source proofs must remain exact')
    restored_edits = json.loads(edits['data'])
    selected = [row for row in restored_edits['new_files'] if row['path'] == MTP_FUNCTIONFS_SOURCE]
    need(len(selected) == 1 and selected[0]['sha256'] == CURRENT_MTP_CPP_SHA256,
         'one exact current MTP source declaration required')
    selected[0]['sha256'] = PREVIOUS_MTP_CPP_SHA256
    need(restored_edits == previous_edits, 'source edit contract differs outside the one MTP asset identity')
    for current, old in zip(spec['vectors'], previous['vectors']):
        restored = dict(current)
        restored['after'] = dict(current['after'])
        need(current['after'][MTP_FUNCTIONFS_SOURCE] == CURRENT_MTP_CPP_SHA256 and
             old['after'][MTP_FUNCTIONFS_SOURCE] == PREVIOUS_MTP_CPP_SHA256,
             'exact complete current/previous MTP postimage required')
        restored['after'][MTP_FUNCTIONFS_SOURCE] = PREVIOUS_MTP_CPP_SHA256
        need(restored == old, 'complete previous/current profile endpoints differ outside the MTP source')
    return spec, bodies, support, previous


def revisions(root, spec):
    for name, expected in spec['projects'].items():
        project = target(root, name)
        need(project.is_dir(), 'fixed source project missing: ' + name)
        command = ['git', '-c', 'safe.directory=' + str(project), '-C', str(project), 'rev-parse']
        actual = subprocess.check_output(command + ['--verify', 'HEAD^{commit}'], text=True).strip()
        top = subprocess.check_output(command + ['--show-toplevel'], text=True).strip()
        need(actual == expected and Path(top).resolve() == project, 'actual fixed HEAD/toplevel differs: ' + name)


def snapshot(root, spec):
    revisions(root, spec)
    result = {}
    for name in spec['paths']:
        saved = capture(target(root, name), missing=name in spec['new_paths'])
        need(saved['data'] is None or saved['mode'] == spec['modes'][name], 'unknown actual source mode: ' + name)
        result[name] = saved
    return result


def support_unchanged(support):
    for name, saved in support.items():
        need(capture(Path(name)) == saved, 'fixed source preparation input changed: ' + name)


def marker_probe(root, spec):
    # Read-only prefix probe. A fresh tree may lack the generated ARMv7 product
    # directory; do not create a source directory or lock merely to discover it.
    result = {}
    for name in spec['paths']:
        path = target(root, name)
        parents = []
        for parent in reversed(path.parents):
            try:
                info = parent.lstat()
            except FileNotFoundError:
                result[name] = dict(data=None, absent_at=str(parent), parents=parents)
                break
            need(stat.S_ISDIR(info.st_mode), 'real source probe parent required')
            parents.append((str(parent), info.st_dev, info.st_ino,
                            stat.S_IMODE(info.st_mode), info.st_uid, info.st_gid))
        else:
            saved = capture(path, missing=True)
            result[name] = dict(data=saved['data'], absent_at=str(path) if saved['data'] is None else None,
                                identity=saved['identity'], parents=parents)
    return result


def has_final_marker(spec, sources):
    observed = hashes(sources)
    return any(sources[n]['data'] is not None for n in spec['new_paths']) or any(
        observed[n] is not None and observed[n] == v['after'][n]
        for n in spec['paths'] for v in spec['vectors'])


def unchanged(root, spec, sources, support):
    need(snapshot(root, spec) == sources, 'actual full source vector changed during transaction')
    support_unchanged(support)


@contextmanager
def locked(root, *, readonly=False):
    directory = unaliased(root / '.ohos-qemu-patches')
    if not readonly:
        directory.mkdir(exist_ok=True)
    need(directory.is_dir(), 'existing source preparation lock directory required')
    path = directory / 'usb-midi-shared-device579.lock'
    flags = os.O_RDONLY if readonly else os.O_RDWR | os.O_CREAT
    fd = os.open(path, flags | os.O_NOFOLLOW, 0o600)
    try:
        info = os.fstat(fd)
        need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and stat.S_IMODE(info.st_mode) == 0o600 and
             info.st_uid == os.geteuid(), 'fixed source preparation lock inode/owner/mode required')
        fcntl.flock(fd, fcntl.LOCK_SH if readonly else fcntl.LOCK_EX)
        named = path.lstat()
        need((info.st_dev, info.st_ino) == (named.st_dev, named.st_ino), 'source lock replaced')
        yield
    finally:
        os.close(fd)


def publish(path, data, expected, metadata, installed, name):
    if data is None:
        need(capture(path, missing=True) == expected, 'source changed immediately before removal')
        installed[name] = None
        path.unlink()
        return
    fd, temporary_name = tempfile.mkstemp(prefix='.usb-midi579-', dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            current = os.fstat(stream.fileno())
            if (current.st_uid, current.st_gid) != (metadata['uid'], metadata['gid']):
                os.fchown(stream.fileno(), metadata['uid'], metadata['gid'])
            os.fchmod(stream.fileno(), metadata['mode'])
            stream.flush()
            os.fsync(stream.fileno())
        staged = capture(temporary)
        need(staged['data'] == data and (staged['mode'], staged['uid'], staged['gid']) ==
             (metadata['mode'], metadata['uid'], metadata['gid']), 'staged source bytes/metadata differ')
        need(capture(path, missing=True) == expected, 'source changed immediately before publication')
        installed[name] = staged
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def hashes(sources):
    return {name: sha(row['data']) if row['data'] is not None else None for name, row in sources.items()}


def transition(root, spec, bodies, support, previous, *, rewind=False, require_final=False, selected_profile=None, selected_products=None):
    original = snapshot(root, spec)
    observed = hashes(original)
    before = [v for v in spec['vectors'] if v['before'] == observed]
    after = [v for v in spec['vectors'] if v['after'] == observed]
    previous_after = [v for v in previous['vectors'] if v['after'] == observed]
    source_epoch = 'current'
    final_marker = has_final_marker(spec, original)
    if rewind and not final_marker:
        unchanged(root, spec, original, support)
        return dict(status='before' if len(before) == 1 else 'deferred_to_original_guards', files=24)
    if rewind:
        need(len(after) + len(previous_after) == 1,
             'only one complete current/previous24 final can rewind; mixed/unknown input preserved')
        source_epoch = 'previous' if previous_after else 'current'
        vector, endpoint = (previous_after or after)[0], 'prefix'
    elif after:
        need(len(after) == 1 and after[0]['name'] == selected_profile and
             (after[0]['armv7_jsvm'] == 'on' or 'armv7a_virt' not in selected_products),
             'complete final does not match selected normal target/actual products')
        unchanged(root, spec, original, support)
        return dict(status='already_final', profile=after[0]['name'], files=24)
    else:
        need(not require_final and len(before) == 1 and before[0]['name'] == selected_profile and
             (before[0]['armv7_jsvm'] == 'on' or 'armv7a_virt' not in selected_products),
             'complete known 24-source before/final for selected normal target required; mixed input preserved')
        vector, endpoint = before[0], 'after'
    need(not require_final, 'complete source final required')
    desired = {name: bodies[expected] if expected is not None else None for name, expected in vector[endpoint].items()}
    current, installed, written = dict(original), {}, []
    try:
        for name in spec['paths']:
            unchanged(root, spec, current, support)
            if current[name]['data'] == desired[name]:
                continue
            metadata = original[name] if original[name]['data'] is not None else dict(
                mode=spec['modes'][name], uid=os.geteuid(), gid=os.getegid())
            written.append(name)
            publish(target(root, name), desired[name], current[name], metadata, installed, name)
            current[name] = capture(target(root, name), missing=name in spec['new_paths'])
        unchanged(root, spec, current, support)
        need(hashes(current) == vector[endpoint], 'complete source transition differs')
    except BaseException as failure:
        errors = []
        for name in reversed(written):
            try:
                actual = capture(target(root, name), missing=name in spec['new_paths'])
                if actual == original[name]:
                    continue
                need(actual['parents'] == original[name]['parents'], 'source parent changed; preserve external edit')
                need(name in installed, 'untracked source change; preserve external edit')
                owned = installed[name]
                if owned is None:
                    need(actual['data'] is None, 'removed source replaced externally')
                else:
                    need(actual['data'] == owned['data'] and actual['identity'][:6] == owned['identity'][:6],
                         'published source changed externally')
                publish(target(root, name), original[name]['data'], actual, original[name], {}, name)
            except BaseException as error:
                errors.append(name + ': ' + str(error))
        try:
            for name, saved in original.items():
                actual = capture(target(root, name), missing=name in spec['new_paths'])
                need(actual['data'] == saved['data'] and (actual['mode'], actual['uid'], actual['gid']) ==
                     (saved['mode'], saved['uid'], saved['gid']), 'incomplete full source/metadata rollback: ' + name)
        except BaseException as error:
            errors.append(str(error))
        if errors:
            recovery = root / '.ohos-qemu-patches' / ('usb-midi579-recovery-' + secrets.token_hex(8))
            recovery.mkdir(mode=0o700)
            rows = []
            for name, saved in original.items():
                if saved['data'] is not None:
                    path = recovery / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(saved['data'])
                rows.append(dict(path=name, absent=saved['data'] is None,
                    sha256=sha(saved['data']) if saved['data'] is not None else None,
                    mode=saved['mode'], uid=saved['uid'], gid=saved['gid']))
            (recovery / 'RECOVERY.json').write_text(json.dumps(dict(files=rows, errors=errors, source_only=True), indent=2) + '\n')
            raise RuntimeError('incomplete source rollback; original bytes/absence/metadata at ' + str(recovery)) from failure
        raise
    return dict(status='rewound' if rewind else 'applied', profile=vector['name'], files=24, source_epoch=source_epoch)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--product', nargs='+', choices=('arm64_virt', 'armv7a_virt', 'x86_64_virt'))
    parser.add_argument('--profile', choices=('none', 'phone', '2in1'))
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--rewind', action='store_true')
    mode.add_argument('--require-final', action='store_true')
    args = parser.parse_args()
    root = unaliased(args.source_root)
    need(root.is_dir() and root != Path('/'), 'actual canonical OpenHarmony source root required')
    need(args.rewind or (args.product is not None and args.profile is not None),
         'selected normal products/source profile required for forward/final check')
    need(args.rewind or len(args.product) == len(set(args.product)), 'duplicate normal product refused')
    order = ('arm64_virt', 'armv7a_virt', 'x86_64_virt')
    selected = None
    if not args.rewind:
        selected = 'none' if args.profile == 'none' else args.profile + ':' + ','.join(
            p for p in order if p in args.product)
    spec, bodies, support, previous = load()
    result = None
    if args.rewind:
        probe = marker_probe(root, spec)
        need(marker_probe(root, spec) == probe, 'source presence changed during prefix probe')
        support_unchanged(support)
        if not has_final_marker(spec, probe):
            # Unknown pristine source remains subject to every original guard.
            # No source, directory, or preparation lock has been written here.
            result = dict(status='deferred_to_original_guards', files=24)
    if result is None:
        with locked(root, readonly=args.require_final):
            result = transition(root, spec, bodies, support, previous, rewind=args.rewind,
                                require_final=args.require_final, selected_profile=selected, selected_products=args.product)
    print(json.dumps(dict(schema='usb-midi579-normal-source-transaction/v1', operation=
        'rewind' if args.rewind else 'require-final' if args.require_final else 'apply',
        result=result, source_only=True, runtime_pass=False), sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
