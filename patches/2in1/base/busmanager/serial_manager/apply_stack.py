#!/usr/bin/env python3
"""Apply the pinned Serial stack without trusting stale applied markers.

Overlapping numbered diffs cannot be checked independently in reverse after
the final patch. Compare the complete affected-file set against each canonical
prefix, generated from the actual fixed upstream archive, before any write.
Foreign changes are preserved by refusing a mixed or unknown source state.
"""
import argparse
import fcntl
import hashlib
import io
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import tempfile

from import_source import DESTINATION, REVISION, git


def patch_paths(patches):
    paths = set()
    for patch in patches:
        headers = re.findall(r'^diff --git a/(\S+) b/(\S+)$', patch.read_text(), re.MULTILINE)
        if not headers:
            raise ValueError('numbered Serial patch has no Git file headers')
        for old, new in headers:
            path = PurePosixPath(new)
            if old != new or '..' in path.parts or path.is_absolute() or not path.is_relative_to(DESTINATION):
                raise ValueError('Serial patch must remain inside its fixed component')
            paths.add(Path(path))
    return sorted(paths)


def file_state(root, paths):
    root = root.resolve()
    records = {}
    for path in paths:
        target = root / path
        if target.is_symlink() or not target.resolve().is_relative_to(root):
            raise ValueError('Serial affected file must not escape its owned source root')
        if not target.exists():
            records[str(path)] = None
        elif target.is_file():
            records[str(path)] = hashlib.sha256(target.read_bytes()).hexdigest()
        else:
            raise ValueError('Serial affected file is not a regular file')
    return records


def canonical_states(repository, patches, paths, temporary):
    archive = git(repository, 'archive', '--format=tar', REVISION)
    target = temporary / DESTINATION
    target.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(archive)) as source:
        for member in source.getmembers():
            relative = PurePosixPath(member.name)
            if relative.is_absolute() or '..' in relative.parts or not (member.isfile() or member.isdir()):
                raise ValueError('unexpected fixed Serial archive member')
        source.extractall(target, filter='data')
    states = [file_state(temporary, paths)]
    for patch in patches:
        subprocess.run(['git', '-C', str(temporary), 'apply', '--check', str(patch)], check=True)
        subprocess.run(['git', '-C', str(temporary), 'apply', '--whitespace=nowarn', str(patch)], check=True)
        states.append(file_state(temporary, paths))
    return states


def apply_stack(root, repository, component):
    root, repository, component = root.resolve(), repository.resolve(), component.resolve()
    patches = sorted(component.glob('[0-9][0-9][0-9][0-9]-*.patch'))
    if not patches:
        raise ValueError('Serial component has no numbered patches')
    paths = patch_paths(patches)
    target = root / DESTINATION
    if target.is_symlink() or not target.resolve().is_relative_to(root):
        raise ValueError('Serial stack target must remain inside its owned source root')
    lock_path = target / '.ohos-qemu-stack.lock'
    if lock_path.is_symlink() or not lock_path.resolve().is_relative_to(target.resolve()):
        raise ValueError('Serial stack lock must not escape its owned component')
    lock_descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(lock_descriptor, 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with tempfile.TemporaryDirectory(prefix='serial-canonical-stack-') as temporary:
            states = canonical_states(repository, patches, paths, Path(temporary))
        current = file_state(root, paths)
        matches = [index for index, state in enumerate(states) if state == current]
        if len(matches) != 1:
            raise ValueError('Serial files differ from every complete pinned patch prefix; refusing all writes')
        prefix = matches[0]
        for index, patch in enumerate(patches[prefix:], prefix):
            if file_state(root, paths) != states[index]:
                raise ValueError('Serial source changed during validated stack application')
            subprocess.run(['git', '-C', str(root), 'apply', '--check', str(patch)], check=True)
            subprocess.run(['git', '-C', str(root), 'apply', '--whitespace=nowarn', str(patch)], check=True)
        if file_state(root, paths) != states[-1]:
            raise ValueError('Serial source differs from the canonical completed patch stack')
    print('verified pinned Serial stack: {} of {} patches already applied; complete'.format(prefix, len(patches)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--source-repo', type=Path, required=True)
    args = parser.parse_args()
    apply_stack(args.source_root, args.source_repo, Path(__file__).resolve().parent)


if __name__ == '__main__':
    main()
