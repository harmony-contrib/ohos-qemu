#!/usr/bin/env python3
"""Verify locked boot resources and reject LFS stubs in every staged partition."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import zipfile

from ext_image_entries import dump_unique_file
from verify_alsa_config_image import debugfs_path, file_sha256
from verify_font_assets_image import MAP

REQUIRED = {'bootpic.zip', 'bootvideo.mp4'}
MARKERS = (b'version https://git-lfs.github.com/spec/v1',
           b'# This file was originally tracked by Git LFS')


def scan_staging(root):
    if not root.is_dir() or root.is_symlink():
        raise ValueError('missing or symbolic staging directory')
    checked = 0
    failures = []
    def fail(error):
        raise error
    for directory, _, files in os.walk(root, followlinks=False, onerror=fail):
        for name in files:
            path = Path(directory) / name
            info = path.lstat()
            if not stat.S_ISREG(info.st_mode):
                continue
            checked += 1
            with path.open('rb') as stream:
                prefix = stream.read(256)
            if any(prefix.startswith(marker) for marker in MARKERS):
                failures.append(str(path.relative_to(root)))
    if not checked:
        raise ValueError('empty staged package')
    if failures:
        raise ValueError('unmaterialized staged LFS resources: ' + ', '.join(sorted(failures)))
    return {'regular_files_checked': checked, 'unmaterialized_resources': []}


def locked_assets():
    result = {}
    for line in MAP.read_text().splitlines():
        if not line or line.startswith('#'):
            continue
        project, relative, remote, sha, size = line.split('\t')
        if project != 'foundation/graphic/graphic_2d':
            continue
        name = Path(relative).name
        if (name not in REQUIRED or relative != 'frameworks/bootanimation/data/' + name or
                remote != 'https://gitcode.com/openharmony/graphic_graphic_2d' or name in result):
            raise ValueError('unexpected boot resource identity')
        result[name] = {'sha256': sha, 'size': int(size)}
    if set(result) != REQUIRED:
        raise ValueError('missing pinned boot resources')
    return result


def inspect_asset(name, data, identity):
    actual = {'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data)}
    if actual != identity:
        raise ValueError('boot resource differs from fixed-release object: ' + name)
    if name == 'bootpic.zip':
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if not archive.namelist() or archive.testzip() is not None:
                raise ValueError('corrupt boot picture archive')
    elif name == 'bootvideo.mp4':
        if len(data) < 24 or data[4:8] != b'ftyp':
            raise ValueError('invalid boot video header')
    else:
        raise ValueError('unexpected boot resource')
    return actual


def verify_image(image, scratch):
    result = {}
    for name, identity in locked_assets().items():
        destination = scratch / name
        destination.mkdir()
        path, inode = dump_unique_file(image, ('/etc/graphic/' + name, '/system/etc/graphic/' + name),
                                       destination, debugfs_path())
        result[name] = dict(inspect_asset(name, path.read_bytes(), identity), **inode)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system-image', type=Path, required=True)
    parser.add_argument('--staging-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = {'status': 'fail', 'scope': 'staged_LFS_and_packaged_boot_objects_NOT_playback',
              'first_artifact_behavior_gate_passed': False, 'failures': [],
              'system_image_sha256': file_sha256(args.system_image), 'asset_map_sha256': file_sha256(MAP)}
    try:
        report['staging'] = scan_staging(args.staging_root)
        with tempfile.TemporaryDirectory(prefix='qemu-boot-assets-') as directory:
            report['assets'] = verify_image(args.system_image, Path(directory))
        report['status'] = 'pass'
    except (OSError, ValueError, zipfile.BadZipFile, subprocess.SubprocessError) as error:
        report['failures'].append(str(error))
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'failures': report['failures']}))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
