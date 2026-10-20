#!/usr/bin/env python3
"""Bind eleven actual screen-capture image resources to fixed source bytes."""
import argparse
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile

from ext_image_entries import dump_unique_file
from verify_alsa_config_image import debugfs_path, file_sha256

COMPONENT = Path(__file__).resolve().parents[1] / 'patches/common/foundation/multimedia/player_framework/screen_capture_resources'
NAMES = ('capsule.svg', 'capsule_stop.svg', 'mic.svg', 'mic_off.svg', 'notification.png',
         'stop_dark.png', 'stop.png', 'capsule_stop_live2.svg', 'light.svg', 'pause.svg', 'play.svg')


def require(ok, message):
    if not ok:
        raise ValueError(message)


def regular(path):
    path = Path(path)
    require(path.is_absolute() and path.resolve() == path and path.is_file() and
            all(not item.is_symlink() for item in (path, *path.parents)),
            'canonical actual screen capture source/image required')
    return path


def source_guard(source):
    path = COMPONENT / 'verify_source.py'
    spec = importlib.util.spec_from_file_location('screen_capture_resource_source_guard', path)
    guard = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(guard)
    guard.validate_source(source, require_patched=True)
    expected = {'services/etc/image/' + name for name in NAMES}
    require(len(guard.FILES) == 11 and {row[0] for row in guard.FILES} == expected and
            all(before is None for _, before, _ in guard.FILES), 'exact eleven new source resource identities required')
    rows = {}
    for relative, _, digest in guard.FILES:
        path = regular(Path(source) / guard.PROJECT / relative)
        require(file_sha256(path) == digest and path.stat().st_size > 0,
                'actual screen capture source differs: ' + relative)
        rows[path.name] = {'source': str(path), 'sha256': digest, 'bytes': path.stat().st_size}
    return guard, rows


def verify_image(image, source, scratch):
    guard, expected = source_guard(source)
    executable = debugfs_path()
    observed = {}
    for name in NAMES:
        directory = scratch / name
        directory.mkdir()
        path, identity = dump_unique_file(image, ('/etc/screencapture/' + name,
            '/system/etc/screencapture/' + name), directory, executable)
        require(file_sha256(path) == expected[name]['sha256'] and
                path.stat().st_size == expected[name]['bytes'],
                'packaged screen capture resource differs from exact source: ' + name)
        observed[name] = dict(expected[name], **identity)
    guard.validate_source(source, require_patched=True)
    require(all(file_sha256(Path(row['source'])) == row['sha256'] for row in expected.values()),
            'actual screen capture source changed during image export')
    return observed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system-image', type=Path, required=True)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = {'status': 'fail', 'scope': 'actual_eleven_screen_capture_resources_source_image_bytes_ONLY',
              'runtime_validated': False, 'guest_decode_and_UI_validated': False,
              'first_artifact_behavior_gate_passed': False, 'failures': []}
    try:
        image = regular(args.system_image)
        before = image.stat()
        checksum = file_sha256(image)
        report.update(system_image_sha256=checksum, source_root=str(args.source_root),
                      source_guard_sha256=file_sha256(COMPONENT / 'verify_source.py'))
        with tempfile.TemporaryDirectory(prefix='screen-capture-resources-image-') as directory:
            report['assets'] = verify_image(image, args.source_root, Path(directory))
        after = image.stat()
        require((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns) ==
                (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) and file_sha256(image) == checksum,
                'actual system image changed during screen capture source guard')
        report['status'] = 'pass'
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        report['failures'].append(str(error))
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ('status', 'failures')}))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
