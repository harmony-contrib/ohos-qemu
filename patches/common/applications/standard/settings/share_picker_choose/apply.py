#!/usr/bin/env python3
"""Install the complete Settings/native chooser candidate or restore original bytes."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import stat
import subprocess
import tempfile

COMPONENT = Path(__file__).resolve().parent
PROJECTS = {
    'applications/standard/settings': '0aba461c750fda71977c2f5186ca0e756ecfc6ca',
    'foundation/ability/ability_runtime': '6c18fdc9bdef6cfcf5888517cd8ed9448584f6e8',
}
SETTINGS = 'applications/standard/settings/'
NATIVE = 'foundation/ability/ability_runtime/'
TARGETS = {
    SETTINGS + 'product/phone/src/main/module.json5',
    SETTINGS + 'product/phone/src/main/resources/base/profile/main_pages.json',
    SETTINGS + 'product/phone/src/main/ets/Setting/SharePicker/ChoosePickerController.ets',
    SETTINGS + 'product/phone/src/main/ets/Setting/SharePicker/ChoosePickerAbility.ets',
    SETTINGS + 'product/phone/src/main/ets/pages/ChoosePicker.ets',
    NATIVE + 'services/abilitymgr/src/ability_manager_service.cpp',
    NATIVE + 'services/abilitymgr/include/ability_manager_service.h',
    NATIVE + 'services/abilitymgr/src/dialog_session/dialog_session_manager.cpp',
    NATIVE + 'services/abilitymgr/include/dialog_session/dialog_session_manager.h',
}
DEPENDENCIES = {
    SETTINGS + 'product/phone/src/main/ets/Setting/SharePicker/SharePickerController.ets',
    SETTINGS + 'product/phone/src/main/ets/Setting/SharePicker/SharePickerExtension.ets',
    SETTINGS + 'product/phone/src/main/ets/pages/SharePicker.ets',
    SETTINGS + 'feature/theme/src/main/ets/ThemeSettings.ets',
    SETTINGS + 'feature/theme/src/main/ets/WallpaperPicker.ets',
    SETTINGS + 'feature/theme/src/main/ets/utils/WallpaperSelectionController.ets',
    SETTINGS + 'feature/theme/src/main/resources/base/element/string.json',
    SETTINGS + 'feature/theme/src/main/resources/zh_CN/element/string.json',
    NATIVE + 'interfaces/kits/native/appkit/ability_bundle_manager_helper/bundle_mgr_helper.h',
    NATIVE + 'services/abilitymgr/include/ability_record.h',
    NATIVE + 'services/common/include/task_handler_wrap.h',
    NATIVE + 'services/abilitymgr/src/ability_record.cpp',
    NATIVE + 'frameworks/native/appkit/ability_bundle_manager_helper/bundle_mgr_helper.cpp',
    NATIVE + 'services/common/include/in_process_call_wrapper.h',
    NATIVE + 'services/common/src/permission_verification.cpp',
    NATIVE + 'services/common/include/permission_verification.h',
    NATIVE + 'services/common/include/support_system_ability_permission.h',
    NATIVE + 'services/abilitymgr/src/utils/update_caller_info_util.cpp',
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_path(root, relative):
    relative = Path(relative)
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('unsafe component/source path')
    target = root / relative
    cursor = target
    while cursor != root:
        if cursor.is_symlink():
            raise ValueError('source symlink refused: ' + str(relative))
        cursor = cursor.parent
    return target


def source_root(root):
    root = Path(root).absolute()
    if root.is_symlink():
        raise ValueError('source root symlink refused')
    canonical = root.resolve(strict=True)
    if root != canonical:
        raise ValueError('source root must be canonical, without parent aliases')
    root = canonical
    if not root.is_dir():
        raise ValueError('source root must be a directory')
    return root


def manifest():
    value = json.loads((COMPONENT / 'manifest.json').read_text())
    if value.get('schema_version') != 2 or value.get('projects') != PROJECTS or set(value.get('files', {})) != TARGETS:
        raise ValueError('exact two-project/nine-target contract required')
    if set(value.get('patches', {})) != {
        '0001-register-private-settings-picker.patch', '0002-authenticate-native-select-dialog-session.patch',
        '0003-bind-private-start-to-one-native-request.patch',
    }:
        raise ValueError('exact chooser patch stack required')
    if {p.name for p in COMPONENT.glob('*.patch')} != set(value['patches']):
        raise ValueError('unknown extra component patch')
    for name, row in value['patches'].items():
        path = safe_path(COMPONENT, name)
        if digest(path.read_bytes()) != row['sha256']:
            raise ValueError('unknown patch bytes: ' + name)
        # Git silently filters patch paths when invoked from a repository
        # subdirectory. This is a readonly inventory of the entire patch.
        names = subprocess.check_output(['git', 'apply', '--numstat', str(path)],
                                        cwd=Path(path.anchor), text=True)
        actual = {line.split('\t')[2] for line in names.splitlines()}
        if not actual or actual != set(row['targets']) or not actual.issubset(TARGETS):
            raise ValueError('unexpected patch targets')
    for name, row in value['files'].items():
        if row.get('payload') is not None:
            if row['before'] is not None or digest(safe_path(COMPONENT, row['payload']).read_bytes()) != row['after']:
                raise ValueError('unknown new-source payload: ' + name)
    if set(value.get('dependencies', {})) != DEPENDENCIES:
        raise ValueError('complete exact predecessor/header dependencies required')
    return value


def revisions(root, value):
    for relative, expected in value['projects'].items():
        project = safe_path(root, relative)
        # Repo's .git metadata symlink is supported; source symlinks are not.
        if not (project / '.git').exists():
            raise ValueError('fixed project Git metadata required: ' + relative)
        actual = subprocess.check_output(['git', '-C', str(project), 'rev-parse', '--verify', 'HEAD^{commit}'],
                                         text=True, stderr=subprocess.PIPE).strip()
        top = subprocess.check_output(['git', '-C', str(project), 'rev-parse', '--show-toplevel'],
                                      text=True, stderr=subprocess.PIPE).strip()
        if actual != expected or Path(top).resolve() != project:
            raise ValueError('fixed project revision/toplevel required: ' + relative)


def state(root, value, check_revisions=True):
    root = source_root(root)
    if check_revisions:
        revisions(root, value)
    for name, expected in value['dependencies'].items():
        path = safe_path(root, name)
        if not path.is_file() or digest(path.read_bytes()) != expected:
            raise ValueError('incomplete or unknown predecessor dependency: ' + name)
        if path.stat().st_nlink != 1:
            raise ValueError('source alias refused: ' + name)
    states = set()
    for name, row in value['files'].items():
        path = safe_path(root, name)
        if not path.exists():
            if row['before'] is not None:
                raise ValueError('missing fixed source: ' + name)
            states.add('before')
        elif path.is_file():
            if path.stat().st_nlink != 1:
                raise ValueError('source alias refused: ' + name)
            current = digest(path.read_bytes())
            if current == row['after']:
                states.add('after')
            elif row['before'] is not None and current == row['before']:
                states.add('before')
            else:
                raise ValueError('unknown source bytes; preserving edits: ' + name)
        else:
            raise ValueError('nonregular source: ' + name)
    if len(states) != 1:
        raise ValueError('mixed Settings/native component; preserving all files')
    return states.pop()


def capture(root, relative):
    """Retain bytes, mode and actual identity, including still-absent targets."""
    path = safe_path(root, relative)
    parents = []
    cursor = path.parent
    while True:
        info = cursor.lstat()
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError('source parent must be a real directory: ' + relative)
        parents.append((str(cursor), info.st_dev, info.st_ino, stat.S_IMODE(info.st_mode)))
        if cursor == root:
            break
        cursor = cursor.parent
    try:
        info = path.lstat()
    except FileNotFoundError:
        return {'data': None, 'identity': None, 'parents': parents}
    if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
        raise ValueError('source alias or nonregular file refused: ' + relative)
    return {'data': path.read_bytes(), 'identity': identity(info), 'parents': parents}


def identity(info):
    return (info.st_dev, info.st_ino, info.st_nlink, stat.S_IMODE(info.st_mode), info.st_uid, info.st_gid)


def unchanged(root, expected):
    for name, row in expected.items():
        if capture(root, name) != row:
            raise ValueError('source bytes/mode/identity changed during transaction: ' + name)


def patch_environment(directory):
    # Do not let an inherited repository or a TMPDIR inside this checkout make
    # git apply silently filter the component's unrelated upstream paths.
    environment = {key: val for key, val in os.environ.items() if not key.startswith('GIT_')}
    environment['GIT_CEILING_DIRECTORIES'] = str(directory.parent)
    return environment


def atomic_write(target, data, mode):
    temporary = target.with_name('.' + target.name + '.qemu-choose-' + secrets.token_hex(8))
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
            os.fchmod(stream.fileno(), mode)
            published_identity = identity(os.fstat(stream.fileno()))
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    try:
        os.replace(temporary, target)
    except BaseException:
        temporary.unlink(missing_ok=True)
        raise
    # No fallible work after publication: callers can track only actual writes.
    return published_identity


def install(root, value):
    before = state(root, value)
    if before == 'after':
        return {'status': 'already_applied', 'runtime_validated': False}
    expected = {name: capture(root, name) for name in [*value['files'], *value['dependencies']]}
    originals = {name: expected[name] for name in value['files']}
    with tempfile.TemporaryDirectory(prefix='ohos-choose-candidate-') as scratch:
        candidate = Path(scratch).resolve()
        for name in [*value['files'], *value['dependencies']]:
            source = safe_path(root, name)
            if source.exists():
                target = candidate / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
        for name in value['patches']:
            subprocess.run(['git', '-C', str(candidate), 'apply', '--check', str(COMPONENT / name)],
                           env=patch_environment(candidate), check=True)
            subprocess.run(['git', '-C', str(candidate), 'apply', str(COMPONENT / name)],
                           env=patch_environment(candidate), check=True)
        for name, row in value['files'].items():
            if row.get('payload') is not None:
                target = candidate / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(COMPONENT / row['payload'], target)
        if state(candidate, value, check_revisions=False) != 'after' or state(root, value) != before:
            raise ValueError('source changed during candidate preparation')
        unchanged(root, expected)
        recovery = Path(tempfile.mkdtemp(prefix='ohos-choose-recovery-')).resolve()
        for name, row in originals.items():
            data = row['data']
            if data is not None:
                saved = recovery / name
                saved.parent.mkdir(parents=True, exist_ok=True)
                saved.write_bytes(data)
        (recovery / 'original.json').write_text(json.dumps({name: {
            'existed': row['data'] is not None,
            'mode': row['identity'][3] if row['identity'] else 0o644,
            'sha256': digest(row['data']) if row['data'] is not None else None
        } for name, row in originals.items()}, indent=2) + '\n')
        written = []
        try:
            for name, row in originals.items():
                unchanged(root, expected)
                target = safe_path(root, name)
                data = (candidate / name).read_bytes()
                mode = row['identity'][3] if row['identity'] else 0o644
                published_identity = atomic_write(target, data, mode)
                written.append(name)
                expected[name] = {'data': data, 'identity': published_identity, 'parents': row['parents']}
            unchanged(root, expected)
            if state(root, value) != 'after':
                raise ValueError('final source guard failed')
        except BaseException as failure:
            rollback_errors = []
            for name in reversed(written):
                try:
                    target = safe_path(root, name)
                    # A failure on an unwritten file never authorizes restoring
                    # it. An external edit to a written file is also preserved.
                    if capture(root, name) != expected[name]:
                        raise ValueError('external edit preserved during rollback: ' + name)
                    row = originals[name]
                    data = row['data']
                    if data is None:
                        target.unlink(missing_ok=True)
                    else:
                        atomic_write(target, data, row['identity'][3])
                except BaseException as error:
                    rollback_errors.append(name + ': ' + str(error))
            if rollback_errors:
                raise RuntimeError('rollback incomplete; original bytes retained at ' + str(recovery) +
                                   '; ' + '; '.join(rollback_errors)) from failure
            shutil.rmtree(recovery)
            raise
        shutil.rmtree(recovery)
    return {'status': 'applied', 'files': list(value['files']), 'runtime_validated': False}


def apply(root):
    root = source_root(root)
    value = manifest()
    state(root, value)
    # No cross-component files/markers authorize a skip. The whole two-project
    # state is checked again while holding this component's lock.
    marker = root / '.ohos-qemu-patches'
    if marker.is_symlink():
        raise ValueError('component lock directory must not be a symlink')
    marker.mkdir(exist_ok=True)
    fd = os.open(marker / 'settings-share-picker-choose.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'a') as lock:
        info = os.fstat(lock.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise ValueError('component lock alias/nonregular file refused')
        fcntl.flock(lock, fcntl.LOCK_EX)
        return install(root, value)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(apply(args.source_root)))
