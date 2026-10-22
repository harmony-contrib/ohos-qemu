#!/usr/bin/env python3
"""Prepare the exact five existing product fixes with an atomic reverse prefix.

No Owner, SDK, image or runtime switch. Source-only normal build preparation.
"""
from pathlib import Path
from contextlib import contextmanager
import argparse
import fcntl
import hashlib
import json
import os
import secrets
import stat
import subprocess
import tempfile

PAIRS = [('applications/standard/admin_provisioning/entry/src/main/ets/MainAbility/ByodAdminProvisionAbility.ts', '448901d9fd4b081a4949d2d06906b404a45504bd57730bc2ce3454d18e89514f', '9a16f377696e60d73cc9dc8d08a8f97d4a01238d2cac4cc01de3f158acc09fbd'), ('applications/standard/admin_provisioning/entry/src/main/ets/pages/byod/byodActivationPage.ets', 'c87ad0d795d4073e9ee553e24c183378f7ea7ca78134696f13e419ab363fc83e', 'd7ddfb7d63c59fec041799d494169cbb3ca7380ce842930d9c2d38e486fa5e44'), ('applications/standard/mms/entry/src/main/ets/pages/transmitmsg/transmitMsgPage.ets', '516e94fcada17b5c6e16c2c19d6121b0c0e709a675c540ad13699634303a596f', 'b53cf189c1e91f61c9b3de58bb48971ef97134003b056bbc73ed834d4f1beec9'), ('foundation/ability/ability_runtime/services/abilitymgr/etc/appfwk.para', 'fb05d3b87cfa9def879abec2b45f7e97d8d42b8069b2932cfde370a71d45a884', '50d25cbc171bd151b3016fd9b7a8911b24080b36a7acf031296b3fef02ed3a94'), ('foundation/ability/ability_runtime/services/abilitymgr/src/dialog_session/dialog_session_manager.cpp', '65d04f5cf9dfaf1f0aaa267ff8b0dfa06296a0ea600e25ceac2ac0438a60f11a', 'b3dec3bcc065de6c80814fd3c0cca599f80da43f25f00c5e56406732f57aef63')]
PROJECTS = {'applications/standard/admin_provisioning': '352a226f5c969a14be6f711fb41c8d02fddce2d7', 'applications/standard/mms': '26df98e3738f4219aa45efe6a3e7f6b1be55c051', 'foundation/ability/ability_runtime': '6c18fdc9bdef6cfcf5888517cd8ed9448584f6e8'}
ASSETS = Path(__file__).resolve().parent / 'additional579-product'
BEFORE_ASSETS = Path(__file__).resolve().parent / 'additional579-product-before'


def need(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def source_root(root):
    root = Path(root)
    need(root.is_absolute() and root.resolve() == root and root.is_dir() and root != Path('/'),
         'actual canonical normal source root required')
    need(not any(p.is_symlink() for p in (root, *root.parents)), 'linked source root refused')
    return root


def target(root, relative):
    name = Path(relative)
    need(not name.is_absolute() and '..' not in name.parts and str(name) == relative,
         'fixed canonical source path required')
    path = root / name
    need(not any(p.is_symlink() for p in (path, *path.parents)), 'linked source or asset refused: ' + relative)
    return path


def identity(info):
    return tuple(getattr(info, k) for k in
        ('st_dev', 'st_ino', 'st_nlink', 'st_mode', 'st_uid', 'st_gid', 'st_size', 'st_mtime_ns', 'st_ctime_ns'))


def capture(path):
    info = path.lstat()
    need(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_size <= 4 * 1024 * 1024,
         'complete bounded one-link regular source required: ' + str(path))
    with path.open('rb') as stream:
        opened = os.fstat(stream.fileno())
        data = stream.read(4 * 1024 * 1024 + 1)
        closed = os.fstat(stream.fileno())
    need(identity(info) == identity(opened) == identity(closed) == identity(path.lstat()) and len(data) == info.st_size,
         'source changed during byte read: ' + str(path))
    return dict(data=data, identity=identity(info), mode=stat.S_IMODE(info.st_mode), uid=info.st_uid, gid=info.st_gid)


def revisions(root):
    for relative, expected in PROJECTS.items():
        project = target(root, relative)
        need(project.is_dir(), 'actual normal project missing: ' + relative)
        command = ['git', '-c', 'safe.directory=' + str(project), '-C', str(project)]
        actual = subprocess.check_output(command + ['rev-parse', '--verify', 'HEAD^{commit}'], text=True).strip()
        top = subprocess.check_output(command + ['rev-parse', '--show-toplevel'], text=True).strip()
        need(actual == expected and Path(top).resolve() == project, 'actual fixed project HEAD/toplevel differs: ' + relative)


def snapshot(root):
    revisions(root)
    sources, assets = {}, {}
    for relative, before, after in PAIRS:
        for folder, expected in ((BEFORE_ASSETS, before), (ASSETS, after)):
            path = target(folder, relative)
            actual = capture(path)
            need(sha(actual['data']) == expected, 'complete fixed before/final asset differs: ' + relative)
            assets[str(path)] = actual
        sources[relative] = capture(target(root, relative))
    return sources, assets


def unchanged(root, sources, assets):
    revisions(root)
    for relative, saved in sources.items():
        need(capture(target(root, relative)) == saved, 'actual source changed during transaction: ' + relative)
    for path, saved in assets.items():
        need(capture(Path(path)) == saved, 'fixed source asset changed during transaction: ' + path)


@contextmanager
def locked(root, readonly=False):
    directory = root / '.ohos-qemu-patches'
    need(not directory.is_symlink(), 'linked normal source lock directory')
    if not readonly:
        directory.mkdir(exist_ok=True)
    need(directory.is_dir(), 'normal source preparation lock missing')
    path = directory / 'additional579-product.lock'
    flags = os.O_RDONLY if readonly else os.O_RDWR | os.O_CREAT
    fd = os.open(path, flags | os.O_NOFOLLOW, 0o600)
    try:
        opened = os.fstat(fd)
        need(stat.S_ISREG(opened.st_mode) and opened.st_nlink == 1 and
             stat.S_IMODE(opened.st_mode) == 0o600 and opened.st_uid == os.geteuid(),
             'fixed normal lock inode/owner/mode required')
        fcntl.flock(fd, fcntl.LOCK_SH if readonly else fcntl.LOCK_EX)
        named = path.lstat()
        need((opened.st_dev, opened.st_ino) == (named.st_dev, named.st_ino), 'source lock replaced')
        yield
    finally:
        os.close(fd)


def replace(path, data, original, installed, relative, expected):
    fd, name = tempfile.mkstemp(prefix='.additional579-', dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            owner = os.fstat(stream.fileno())
            if (owner.st_uid, owner.st_gid) != (original['uid'], original['gid']):
                os.fchown(stream.fileno(), original['uid'], original['gid'])
            os.fchmod(stream.fileno(), original['mode'])
            stream.flush()
            os.fsync(stream.fileno())
        staged = capture(temporary)
        need(staged['data'] == data and (staged['mode'], staged['uid'], staged['gid']) ==
             (original['mode'], original['uid'], original['gid']), 'complete staged source/ownership differs')
        # Register the unique staged inode before the only publishing syscall.
        # No fallible observation is needed to remember an already-live write.
        need(capture(path) == expected, 'source changed immediately before publication')
        installed[relative] = staged
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def transition(root, *, rewind=False, require_final=False):
    sources, assets = snapshot(root)
    observed = {name: sha(row['data']) for name, row in sources.items()}
    before = {name: a for name, a, b in PAIRS}
    after = {name: b for name, a, b in PAIRS}
    if rewind and not any(observed[name] == after[name] for name in after):
        # Scheduling only: pristine/older bytes are still checked by every
        # original source guard and the strict late forward operation.
        unchanged(root, sources, assets)
        return dict(status='before' if observed == before else 'deferred_to_original_source_guards', files=[])
    if rewind:
        need(observed == after, 'only the complete fixed five-source final can rewind; mixed/unknown preserved')
    else:
        need(all(observed[name] in (before[name], after[name]) for name in observed),
             'unknown five-source input preserved; no write')
    if require_final:
        need(observed == after, 'complete final five-source vector required')
        unchanged(root, sources, assets)
        return dict(status='final', files=[])
    wanted = before if rewind else after
    folder = BEFORE_ASSETS if rewind else ASSETS
    desired = {name: assets[str(folder / name)]['data'] for name in wanted}
    recovery = None
    written = []
    installed = {}
    current = dict(sources)
    try:
        for relative, a, b in PAIRS:
            unchanged(root, current, assets)
            if current[relative]['data'] == desired[relative]:
                continue
            written.append(relative)
            replace(target(root, relative), desired[relative], sources[relative], installed, relative, current[relative])
            current[relative] = capture(target(root, relative))
        unchanged(root, current, assets)
        need({name: sha(row['data']) for name, row in current.items()} == wanted, 'complete final transition differs')
    except BaseException as failure:
        errors = []
        for relative in reversed(written):
            try:
                actual = capture(target(root, relative))
                if actual == sources[relative]:
                    continue
                owned = installed.get(relative)
                need(owned is not None and actual['identity'][:6] == owned['identity'][:6] and
                     actual['data'] == owned['data'], 'external edit preserved during rollback')
                replace(target(root, relative), sources[relative]['data'], sources[relative], {}, relative, actual)
                current[relative] = capture(target(root, relative))
            except BaseException as error:
                errors.append(relative + ': ' + str(error))
        try:
            for relative, original in sources.items():
                actual = capture(target(root, relative))
                need(actual['data'] == original['data'] and (actual['mode'], actual['uid'], actual['gid']) ==
                     (original['mode'], original['uid'], original['gid']), 'incomplete original vector rollback')
        except BaseException as error:
            errors.append(str(error))
        if errors:
            recovery = root / '.ohos-qemu-patches' / ('additional579-recovery-' + secrets.token_hex(8))
            recovery.mkdir(mode=0o700)
            for relative, original in sources.items():
                path = recovery / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(original['data'])
            (recovery / 'RECOVERY.json').write_text(json.dumps(dict(
                schema='additional579-source-rollback-recovery/v1',
                files=[dict(path=name, sha256=sha(row['data']), mode=row['mode'],
                            uid=row['uid'], gid=row['gid']) for name, row in sources.items()],
                errors=errors, source_only=True, runtime_pass=False), indent=2) + '\n')
            raise RuntimeError('source rollback incomplete; original five bytes retained at ' + str(recovery) + '; ' + '; '.join(errors)) from failure
        raise
    rows = [dict(path=name, before=a, after=b, was_already_applied=observed[name] == b) for name, a, b in PAIRS]
    return dict(status='rewound' if rewind else 'applied', files=rows)


@contextmanager
def preceding_view(root):
    """Read-only exact old bytes, only after the complete real five-final proof."""
    root = source_root(root)
    with locked(root, readonly=True):
        sources, assets = snapshot(root)
        need(all(sha(sources[name]['data']) == after for name, before, after in PAIRS),
             'complete actual five-source final required for readonly ancestor view')
        before = {name: assets[str(BEFORE_ASSETS / name)]['data'] for name, a, b in PAIRS}
        try:
            yield before
        finally:
            unchanged(root, sources, assets)


def apply(root, output, *, rewind=False, require_final=False):
    root = source_root(root)
    with locked(root, readonly=require_final):
        result = transition(root, rewind=rewind, require_final=require_final)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(dict(schema='additional579-normal-product-source-apply/v1',
        files=result['files'], operation='rewind' if rewind else 'require-final' if require_final else 'apply',
        status=result['status'], source_only=True, runtime_param_mutation=False), indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--receipt', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--rewind', action='store_true')
    mode.add_argument('--require-final', action='store_true')
    args = parser.parse_args()
    apply(args.source_root, args.receipt, rewind=args.rewind, require_final=args.require_final)
