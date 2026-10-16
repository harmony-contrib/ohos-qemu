#!/usr/bin/env python3
"""Install only exact fixed sources and exact new files, with rollback on failure."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import tempfile

COMPONENT = Path(__file__).resolve().parent
BUILD = 'device/qemu/common/virt_full/external_gnss/BUILD.gn'
PREDECESSOR = {BUILD: '436e42030c3e582156b8f9e11a265b4e153890c2c72a4f5d7ed2907245175330'}
ABI_HEADER = 'drivers/peripheral/location/gnss/hdi_service/location_vendor_lib.h'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def safe_path(root, relative):
    relative = Path(relative)
    if relative.is_absolute() or '..' in relative.parts:
        raise ValueError('unsafe source manifest path')
    target = root / relative
    cursor = target
    while cursor != root:
        if cursor.is_symlink():
            raise ValueError('source symlink refused: ' + str(relative))
        cursor = cursor.parent
    return target


def load_manifest():
    manifest = json.loads((COMPONENT / 'manifest.json').read_text())
    patches = list(COMPONENT.glob('*.patch'))
    if len(patches) != 1 or sha(patches[0].read_bytes()) != manifest['patch_sha256']:
        raise ValueError('unknown component patch bytes')
    for row in manifest['files'].values():
        if sha(safe_path(COMPONENT, row['component_file']).read_bytes()) != row['sha256']:
            raise ValueError('unknown component file bytes')
    if manifest.get('installed_predecessor') != PREDECESSOR:
        raise ValueError('only the exact complete predecessor BUILD migration is supported')
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
            overlays[relative] = 'absent'
        elif target.is_file():
            value = sha(target.read_bytes())
            if value == row['sha256']:
                overlays[relative] = 'current'
            elif relative == BUILD and value == PREDECESSOR[BUILD]:
                overlays[relative] = 'predecessor'
            else:
                raise ValueError('unknown existing overlay; preserving edits: ' + relative)
        else:
            raise ValueError('unknown existing overlay; preserving edits: ' + relative)
    if set(originals) == {'before'} and set(overlays.values()) == {'absent'}:
        return 'pristine'
    if set(originals) == {'after'} and set(overlays.values()) == {'current'}:
        return 'patched'
    if (set(originals) == {'after'} and overlays[BUILD] == 'predecessor' and
            all(value == 'current' for relative, value in overlays.items() if relative != BUILD)):
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


def apply(root):
    root = source_root(root)
    manifest, patch = load_manifest()
    state = source_state(root, manifest)
    if state == 'patched':
        return {'status': 'already_applied', 'revision': manifest['revision']}
    original = {}
    for relative in [*manifest['originals'], *manifest['files']]:
        target = safe_path(root, relative)
        original[relative] = (target.read_bytes(), target.stat().st_mode & 0o777) if target.exists() else (None, 0o644)
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
        # A complete predecessor has already patched all three HDI sources.
        # Only BUILD changes in that path; never replay the upstream patch.
        updates = list(original) if state == 'pristine' else [BUILD]
        if source_state(root, manifest) != state:
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
        try:
            for relative in updates:
                _, mode = original[relative]
                target = safe_path(root, relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                written.append(relative)
                atomic_write(target, (candidate / relative).read_bytes(), mode)
            validate(root, manifest, require_patched=True)
        except BaseException as failure:
            rollback_errors = []
            for relative in reversed(written):
                try:
                    target = safe_path(root, relative)
                    data, mode = original[relative]
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
