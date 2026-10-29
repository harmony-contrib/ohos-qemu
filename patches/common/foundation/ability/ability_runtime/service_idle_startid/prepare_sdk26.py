#!/usr/bin/env python3
"""Prepare the exact SDK26 declaration of this same-source real native method.

No compiler option, implementation, API checker or runtime result is replaced.
Root runs this only in normal source/SDK production under the original lease.
The SDK path is supplied by trusted Root code, not by a business case or JSON.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
from verify_source import state

HERE = Path(__file__).resolve().parent
SOURCE_STATES_SHA = '69ad372ea53eafb45c8223e45631baddaf06e53420275297dfc31115ef18a48a'
BEFORE = 'a9f2c2e20d4b552b1b3aa6615c67b5131139a0e67026629cfc3010e211d0a9bd'
FINAL = 'a436733ec2dc9c393be14e2ac692032be393bf22a6e345d5b6177f0370bac555'
METADATA = {
    '594fe467b979e6851b36839512234383bea257c6ed937656d9afac313dd726b0': {
        'bytes': 194,
        'json': {'apiVersion': '26', 'displayName': 'Ets', 'meta': {'metaVersion': '3.0.2'}, 'path': 'ets', 'platformVersion': '26.0.0', 'releaseType': 'Release', 'version': '26.0.0.39'},
    },
    '250b53f383be634ada496cfb4a1cbebd1e7ad6f14f44fd136ca55d2d9a35acab': {
        'bytes': 195,
        'json': {'apiVersion': '26', 'displayName': 'Ets', 'meta': {'metaVersion': '3.0.2'}, 'path': 'ets', 'platformVersion': '26.0.0', 'releaseType': 'Release', 'version': '26.0.0.105'},
    },
}
RELATIVE = 'api/application/ServiceExtensionContext.d.ts'


def need(value, message):
    if not value:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def regular(path):
    path = Path(path)
    need(path.is_absolute() and path.resolve() == path and
         not any(p.is_symlink() for p in (path, *path.parents)), 'unaliased actual source/SDK path required')
    observed = path.stat(follow_symlinks=False)
    need(stat.S_ISREG(observed.st_mode) and observed.st_nlink == 1, 'one regular single-link actual file required')
    return observed


def identity(value):
    return (value.st_dev, value.st_ino, stat.S_IMODE(value.st_mode), value.st_uid,
            value.st_gid, value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def read_file(path):
    before = regular(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        need(identity(os.fstat(fd)) == identity(before), 'actual source/SDK changed at open')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            data = stream.read(1024 * 1024 + 1)
        need(len(data) <= 1024 * 1024 and identity(os.fstat(fd)) == identity(before) and
             identity(regular(path)) == identity(before), 'actual file changed or exceeded bound during read')
        return data, before
    finally:
        os.close(fd)


def native_final(root):
    need(digest(read_file(HERE / 'source_states.json')[0]) == SOURCE_STATES_SHA,
         'exact complete source18 component manifest required')
    need(state(root) == 'final', 'complete current native18 final and all three actual project HEADs required')


def metadata(ets):
    data, observed = read_file(ets / 'oh-uni-package.json')
    expected = METADATA.get(digest(data))
    need(expected is not None and len(data) == expected['bytes'],
         'only the two reviewed complete SDK26 metadata byte vectors may be prepared')
    value = json.loads(data)
    need(value == expected['json'],
         'exact reviewed SDK26 metadata JSON/version/release required')
    return data, observed


def replace(path, data, before, journal):
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(prefix='.service579-sdk-', dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            actual = os.fstat(stream.fileno())
            # Set the known nonspecial mode while the creator still owns this
            # temporary inode; CAP_CHOWN need not imply CAP_FOWNER afterwards.
            os.fchmod(stream.fileno(), stat.S_IMODE(before.st_mode))
            if (actual.st_uid, actual.st_gid) != (before.st_uid, before.st_gid):
                os.fchown(stream.fileno(), before.st_uid, before.st_gid)
            os.fsync(stream.fileno())
            journal['installed'] = os.fstat(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def prepare(*, source_root, sdk_ets_root, require_final=False):
    root, ets = Path(source_root), Path(sdk_ets_root)
    need(root.is_absolute() and root.resolve() == root and ets.is_absolute() and ets.resolve() == ets and
         ets.is_dir() and not any(p.is_symlink() for p in (root, *root.parents, ets, *ets.parents)),
         'trusted Root actual native source/selected SDK directories required')
    native_final(root)  # Native source and all three projects are read-only.
    pre_meta, pre_meta_stat = metadata(ets)
    target = ets / RELATIVE
    pre_raw, pre_stat = read_file(target)
    need(stat.S_IMODE(pre_stat.st_mode) == 0o644,
         'only the two reviewed SDK API files with exact nonspecial mode0644 may be prepared')
    need(digest(pre_raw) in (BEFORE, FINAL), 'unknown SDK26 whole-file bytes preserved before lock preparation')
    lock_path = ets / '.service579-sdk26.lock'
    # Normal SDK production already owns the selected SDK's writable tree.
    # Read-only verification requires its existing empty lock; it creates and
    # writes nothing, including in the native source tree.
    flags = os.O_RDONLY if require_final else os.O_CREAT | os.O_RDWR
    fd = os.open(lock_path, flags | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'r' if require_final else 'a') as lock:
        locked = os.fstat(lock.fileno())
        need(stat.S_ISREG(locked.st_mode) and locked.st_nlink == 1 and
             locked.st_size == 0 and stat.S_IMODE(locked.st_mode) == 0o600 and
             identity(regular(lock_path)) == identity(locked), 'fixed empty single-link SDK prepare lock required')
        fcntl.flock(lock, fcntl.LOCK_SH if require_final else fcntl.LOCK_EX)
        need(identity(regular(lock_path)) == identity(os.fstat(lock.fileno())), 'SDK prepare lock changed')
        native_final(root)
        meta, meta_stat = metadata(ets)
        original, before = read_file(target)
        need(meta == pre_meta and identity(meta_stat) == identity(pre_meta_stat) and
             original == pre_raw and identity(before) == identity(pre_stat),
             'actual SDK inputs changed before acquiring its original prepare lock')
        observed = digest(original)
        need(observed in (BEFORE, FINAL), 'unknown SDK26 whole-file bytes preserved; require actual source review')
        final, _ = read_file(HERE / 'SDK26-ServiceExtensionContext.final.d.ts')
        need(digest(final) == FINAL, 'fixed complete real-API declaration payload changed')
        if observed == FINAL:
            native_final(root)
            need(metadata(ets)[0] == meta and identity(regular(target)) == identity(before),
                 'actual final SDK/native source changed during idempotent read')
            return {'scope':'SDK source declaration only; NOT compilation/runtime acceptance',
                'sdk':str(ets), 'target':str(target), 'before_sha256':FINAL, 'after_sha256':FINAL,
                'changed':False, 'mtime_preserved':True, 'native_source':str(root),
                'native_component_sha256':SOURCE_STATES_SHA, 'runtime_pass':False}
        need(not require_final, 'SDK26 real-native declaration must be prepared by original Root producer')
        native_final(root)
        need(read_file(target)[0] == original and identity(regular(target)) == identity(before) and
             metadata(ets)[0] == meta and identity(regular(ets / 'oh-uni-package.json')) == identity(meta_stat),
             'actual SDK/native source changed before finite commit')
        journal = {}
        try:
            replace(target, final, before, journal)
            installed, after = read_file(target)
            need(installed == final and identity(after)[:5] == identity(journal['installed'])[:5] and
                 identity(after)[2:5] == identity(before)[2:5], 'actual SDK declaration commit differs')
            need(metadata(ets)[0] == meta, 'SDK metadata changed during declaration commit')
            native_final(root)
        except BaseException as error:
            current, current_stat = read_file(target)
            if current == original and identity(current_stat)[2:5] == identity(before)[2:5]:
                raise
            need('installed' in journal and current == final and
                 identity(current_stat)[:5] == identity(journal['installed'])[:5],
                 'unknown concurrent SDK change preserved; owned rollback refused')
            replace(target, original, before, {})
            need(read_file(target)[0] == original and identity(regular(target))[2:5] == identity(before)[2:5],
                 'owned SDK declaration rollback incomplete')
            raise error
        return {'scope':'SDK source declaration only; NOT compilation/runtime acceptance',
            'sdk':str(ets), 'target':str(target), 'before_sha256':BEFORE, 'after_sha256':FINAL,
            'changed':True, 'native_source':str(root), 'native_component_sha256':SOURCE_STATES_SHA,
            'mode':stat.S_IMODE(before.st_mode), 'uid':before.st_uid, 'gid':before.st_gid,
            'runtime_pass':False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--sdk-ets-root', type=Path, required=True)
    parser.add_argument('--require-final', action='store_true')
    args = parser.parse_args()
    print(json.dumps(prepare(source_root=args.source_root, sdk_ets_root=args.sdk_ets_root,
        require_final=args.require_final), sort_keys=True))


if __name__ == '__main__':
    main()
