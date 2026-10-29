#!/usr/bin/env python3
"""Install only exact fixed sources and exact new files, with rollback on failure."""
import argparse
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
BUILD = 'device/qemu/common/virt_full/external_gnss/BUILD.gn'
PREDECESSOR = {BUILD: '436e42030c3e582156b8f9e11a265b4e153890c2c72a4f5d7ed2907245175330'}
QGN1_FILES = {
    BUILD: 'a33e9ad3ab6652be5e57eb1b310f31652f1b1491b1221dad79d6684a68ad4f16',
    'device/qemu/common/virt_full/external_gnss/qemu_gnss_input.cpp':
        '2435f10d6243974508ffec8188fa9794d67dc96068a09cac612e71cb3bb88c94',
    'device/qemu/common/virt_full/external_gnss/qemu_gnss_input.h':
        'f879d0083750680101cf43428a6181eeee3268bb070ba14a7df12f8cda51bae6',
    'device/qemu/common/virt_full/external_gnss/qemu_gnss_protocol.h':
        'c8a2bffd726a3cc9f6b1f53637ec0bf5b3832277988e1afbd99f51286b8909cc',
    'device/qemu/common/virt_full/external_gnss/qemu_gnss_vendor.cpp':
        'd2e65a9e9032a251a04bfef72d69bf8837ccfb4bfc23402af92eb95d77660b02',
}
ABI_HEADER = 'drivers/peripheral/location/gnss/hdi_service/location_vendor_lib.h'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def safe_path(root, relative):
    if not isinstance(relative, str) or relative in ('', '.') or str(Path(relative)) != relative:
        raise ValueError('noncanonical source manifest path')
    relative = Path(relative)
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('unsafe source manifest path')
    target = root / relative
    cursor = target
    while cursor != root:
        if cursor.is_symlink():
            raise ValueError('source symlink refused: ' + str(relative))
        cursor = cursor.parent
    if target.is_file() and target.stat().st_nlink != 1:
        raise ValueError('source hardlink alias refused: ' + str(relative))
    return target


def load_manifest():
    manifest = json.loads(safe_path(COMPONENT, 'manifest.json').read_text())
    patches = list(COMPONENT.glob('*.patch'))
    if (len(patches) != 1 or
            sha(safe_path(COMPONENT, patches[0].name).read_bytes()) != manifest['patch_sha256']):
        raise ValueError('unknown component patch bytes')
    for row in manifest['files'].values():
        if sha(safe_path(COMPONENT, row['component_file']).read_bytes()) != row['sha256']:
            raise ValueError('unknown component file bytes')
    if manifest.get('installed_predecessor') != PREDECESSOR:
        raise ValueError('only the exact complete predecessor BUILD migration is supported')
    if (manifest.get('installed_qgn1') != QGN1_FILES or
            set(manifest['files']) != set(QGN1_FILES)):
        raise ValueError('only the exact complete historical QGN1 overlay is supported')
    # This update is exactly removal of the rejected assignment; no arbitrary
    # prior overlay/version is admitted, even if another hash is added to JSON.
    current = safe_path(COMPONENT, manifest['files'][BUILD]['component_file']).read_bytes()
    marker = b'  output_prefix_override = true\n'
    if (current.count(marker) != 1 or b'  output_prefix = ""\n' in current or
            sha(current.replace(marker, b'  output_prefix = ""\n' + marker)) != PREDECESSOR[BUILD]):
        raise ValueError('new BUILD must be the exact one-line predecessor correction')
    if (manifest.get('project') != 'drivers/peripheral' or
            set(manifest.get('projects', {})) != {'drivers/peripheral', 'device/qemu'} or
            manifest['projects'][manifest['project']] != manifest['revision'] or
            manifest.get('dependencies', {}).get(ABI_HEADER) != manifest.get('abi_header_sha256')):
        raise ValueError('complete project/revision/ABI manifest contract required')
    return manifest, patches[0]


def source_root(root):
    root = Path(root).absolute()
    if root.is_symlink():
        raise ValueError('source symlink refused: root')
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError('source root must be a directory')
    return root


def revisions(root, manifest):
    for relative, expected in manifest['projects'].items():
        directory = safe_path(root, relative)
        reason = ('fixed upstream revision required' if relative == manifest['project'] else
                  'fixed source project revision required: ' + relative)
        # repo-managed .git metadata may itself be a symlink. Source files and
        # project directories may not. Require a real commit in each project,
        # rather than silently accepting a missing .git or the parent repo HEAD.
        if not (directory / '.git').exists():
            raise ValueError(reason + ' (missing Git metadata)')
        try:
            actual = subprocess.check_output(['git', '-C', str(directory), 'rev-parse', '--verify', 'HEAD^{commit}'],
                                             text=True, stderr=subprocess.PIPE).strip()
            top = subprocess.check_output(['git', '-C', str(directory), 'rev-parse', '--show-toplevel'],
                                          text=True, stderr=subprocess.PIPE).strip()
        except subprocess.CalledProcessError as error:
            raise ValueError(reason + ' (invalid Git project)') from error
        if actual != expected or Path(top).resolve() != directory:
            raise ValueError(reason)


def source_state(root, manifest, revision=True):
    root = source_root(root)
    if revision:
        revisions(root, manifest)
    for relative, expected in manifest.get('dependencies', {}).items():
        if sha(safe_path(root, relative).read_bytes()) != expected:
            raise ValueError('fixed actual ABI dependency required')
    originals, overlays = [], {}
    for relative, row in manifest['originals'].items():
        value = sha(safe_path(root, relative).read_bytes())
        if value == row['before']:
            originals.append('before')
        elif value == row['after']:
            originals.append('after')
        else:
            raise ValueError('unknown source bytes; preserving edits: ' + relative)
    for relative, row in manifest['files'].items():
        target = safe_path(root, relative)
        if not target.exists():
            overlays[relative] = None
        elif target.is_file():
            value = sha(target.read_bytes())
            if value not in (row['sha256'], QGN1_FILES[relative], PREDECESSOR.get(relative)):
                raise ValueError('unknown existing overlay; preserving edits: ' + relative)
            overlays[relative] = value
        else:
            raise ValueError('unknown existing overlay; preserving edits: ' + relative)
    if set(originals) == {'before'} and set(overlays.values()) == {None}:
        return 'pristine'
    if (set(originals) == {'after'} and
            overlays == {relative: row['sha256'] for relative, row in manifest['files'].items()}):
        return 'patched'
    if set(originals) == {'after'} and overlays == QGN1_FILES:
        return 'qgn1'
    # The old BUILD belongs to the complete QGN1 overlay, never QGN2 or a mix.
    if set(originals) == {'after'} and overlays == {**QGN1_FILES, **PREDECESSOR}:
        return 'predecessor'
    raise ValueError('mixed patch state; preserving edits')


def validate(root, manifest, require_patched=False, revision=True):
    repaired = source_state(root, manifest, revision) == 'patched'
    if require_patched and not repaired:
        raise ValueError('complete patch is required')
    return repaired


def atomic_write(target, data, mode):
    temporary = target.with_name('.' + target.name + '.qemu-' + secrets.token_hex(8))
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
        os.chmod(temporary, mode)
        os.replace(temporary, target)
    finally:
        if temporary.exists():
            temporary.unlink()


def snapshot(root, relative):
    target = safe_path(root, relative)
    return (target.read_bytes(), stat.S_IMODE(target.stat().st_mode)) if target.exists() else (None, 0o644)


def apply(root):
    root = source_root(root)
    manifest, patch = load_manifest()
    state = source_state(root, manifest)
    if state == 'patched':
        return {'status': 'already_applied', 'revision': manifest['revision']}
    original = {relative: snapshot(root, relative) for relative in [*manifest['originals'], *manifest['files']]}
    dependencies = {relative: snapshot(root, relative) for relative in manifest['dependencies']}
    with tempfile.TemporaryDirectory(prefix='qemu-gnss-candidate-') as temporary:
        candidate = Path(temporary)
        for relative in [*manifest['originals'], *manifest['files']]:
            if original[relative][0] is None:
                continue
            target = candidate / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(original[relative][0])
        for relative in manifest.get('dependencies', {}):
            target = candidate / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(safe_path(root, relative), target)
        if state == 'pristine':
            subprocess.run(['git', '-C', str(candidate), 'apply', str(patch)], check=True)
        for relative, row in manifest['files'].items():
            target = candidate / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(COMPONENT / row['component_file'], target)
        validate(candidate, manifest, require_patched=True, revision=False)
        # Historical states already contain the three exact patched HDI files.
        # Replace only differing overlay bytes; never replay the HDI patch.
        updates = [relative for relative, (data, _) in original.items()
                   if data != (candidate / relative).read_bytes()]
        if (source_state(root, manifest) != state or
                any(snapshot(root, name) != value for name, value in {**original, **dependencies}.items())):
            raise ValueError('source state changed while preparing; preserving edits')
        recovery = Path(tempfile.mkdtemp(prefix='qemu-gnss-recovery-'))
        for relative in updates:
            data, _ = original[relative]
            if data is not None:
                target = recovery / relative; target.parent.mkdir(parents=True, exist_ok=True); target.write_bytes(data)
        (recovery / 'original.json').write_text(json.dumps({name: {'existed': original[name][0] is not None,
            'mode': original[name][1], 'sha256': sha(original[name][0]) if original[name][0] is not None else None}
            for name in updates}, indent=2) + '\n')
        written = []
        attempted = None
        try:
            for relative in updates:
                _, mode = original[relative]
                for name, before in {**original, **dependencies}.items():
                    if name not in written and snapshot(root, name) != before:
                        raise ValueError('source changed before replacement; preserving edits: ' + name)
                target = safe_path(root, relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                attempted = relative
                atomic_write(target, (candidate / relative).read_bytes(), mode)
                written.append(relative)
                attempted = None
            validate(root, manifest, require_patched=True)
            for name, before in {**original, **dependencies}.items():
                expected = ((candidate / name).read_bytes(), original[name][1]) if name in written else before
                if snapshot(root, name) != expected:
                    raise ValueError('source changed during installation; preserving edits: ' + name)
        except BaseException as failure:
            rollback_errors = []
            # A failed atomic_write can fail before OR after its rename. Do not
            # treat a never-replaced external value as one of our own writes.
            if attempted is not None:
                try:
                    current = snapshot(root, attempted)
                    expected = ((candidate / attempted).read_bytes(), original[attempted][1])
                    if current == expected:
                        written.append(attempted)
                    elif current != original[attempted]:
                        raise ValueError('unrecognized failed replacement; preserving external edits')
                except BaseException as error:
                    rollback_errors.append(attempted + ': ' + str(error))
            for relative in reversed(written):
                try:
                    target = safe_path(root, relative)
                    data, mode = original[relative]
                    current = snapshot(root, relative)
                    if current == original[relative]:
                        continue
                    if current != ((candidate / relative).read_bytes(), mode):
                        raise ValueError('changed after replacement; preserving external edits')
                    if data is None:
                        target.unlink(missing_ok=True)
                    else:
                        atomic_write(target, data, mode)
                except BaseException as error:
                    rollback_errors.append(relative + ': ' + str(error))
            if rollback_errors:
                raise RuntimeError('rollback incomplete; original bytes retained at ' + str(recovery) +
                                   '; ' + '; '.join(rollback_errors)) from failure
            shutil.rmtree(recovery)
            raise
        shutil.rmtree(recovery)
    return {'status': 'applied' if state == 'pristine' else 'migrated', 'revision': manifest['revision'],
            'patch_sha256': manifest['patch_sha256'], 'files': updates}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(apply(args.source_root)))
