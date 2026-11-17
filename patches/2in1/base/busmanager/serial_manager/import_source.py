#!/usr/bin/env python3
"""Import exactly the pinned Serial SIG commit; never overwrite a foreign tree.

The caller supplies an already fetched repository. This importer does not alter
the release manifest, fetch a moving branch, or mutate the repository cache.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tarfile
import tempfile

REVISION = 'c05fbbf156230982aa576373da6ee04378b09ca0'
MANIFEST = 'f079c4ad9848f9cc4a9a4b3a3613ad8fbb142549'
ORIGIN = 'https://gitcode.com/openharmony-sig/busmanager_serial_manager.git'
DESTINATION = Path('base/busmanager/serial_manager')
MARKER = '.ohos-qemu-upstream.json'


def git(repository, *arguments):
    return subprocess.check_output(['git', '-c', 'safe.directory=' + str(repository), '-C', str(repository), *arguments])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--source-repo', type=Path, required=True)
    args = parser.parse_args()
    root = args.source_root.resolve()
    manifests = root / '.repo/manifests'
    if git(manifests, 'rev-parse', 'HEAD').decode().strip() != MANIFEST:
        raise ValueError('Serial integration requires the fixed OpenHarmony 7.0 manifest')
    repository = args.source_repo.resolve()
    if git(repository, 'rev-parse', REVISION + '^{commit}').decode().strip() != REVISION:
        raise ValueError('Serial upstream revision is unavailable')
    archive = git(repository, 'archive', '--format=tar', REVISION)
    tree = git(repository, 'rev-parse', REVISION + '^{tree}').decode().strip()
    provenance = {'revision': REVISION, 'tree': tree, 'origin': ORIGIN,
                  'manifest_revision': MANIFEST,
                  'archive_sha256': hashlib.sha256(archive).hexdigest(),
                  'scope': '2in1_dynamic_cpp_arkts11_candidate_not_runtime_acceptance'}
    target = root / DESTINATION
    if target.is_symlink() or not target.resolve().is_relative_to(root):
        raise ValueError('Serial import target must remain inside its owned source root')
    if target.exists():
        marker = target / MARKER
        if not marker.is_file() or json.loads(marker.read_text()) != provenance:
            raise ValueError('existing Serial tree lacks matching provenance; refusing to overwrite')
        print('pinned Serial tree already imported: ' + REVISION)
        return
    with tempfile.TemporaryDirectory(prefix='serial-import-') as directory:
        staged = Path(directory) / 'source'
        staged.mkdir()
        with tarfile.open(fileobj=io.BytesIO(archive)) as compressed:
            for member in compressed.getmembers():
                relative = PurePosixPath(member.name)
                if relative.is_absolute() or '..' in relative.parts or not (member.isfile() or member.isdir()):
                    raise ValueError('unexpected archive member: ' + member.name)
            compressed.extractall(staged, filter='data')
        (staged / MARKER).write_text(json.dumps(provenance, indent=2) + '\n')
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(staged, target, symlinks=False)
    print('imported pinned Serial SIG source: ' + REVISION)


if __name__ == '__main__':
    main()
