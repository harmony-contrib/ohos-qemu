#!/usr/bin/env python3
"""Read a freshly extracted package's system image and its real boot trace."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess

from run_root_probe import digest
from verify_boot_profile_results import MODULE_PATH, USAGE_PATHS, verify


def image_stat(image: Path, entry: str, docker_image: str) -> str:
    result = subprocess.run(['docker', 'run', '--rm', '-v', str(image.parent) + ':/pkg:ro',
        '--entrypoint', 'debugfs', docker_image, '-R', 'stat ' + entry, '/pkg/system.img'],
        check=False, capture_output=True, text=True, timeout=120)
    if result.returncode:
        raise ValueError('debugfs could not inspect the packaged system image: ' + entry)
    return result.stdout + result.stderr


def run(archive: Path, boot_path: Path, output: Path, docker_image: str) -> dict:
    boot = json.loads(boot_path.read_text())
    environment = boot.get('test_environment', {})
    archive_sha = digest(archive)
    directory = boot_path.parent / 'extract' / archive.name.removesuffix('.tar.gz')
    image = directory / 'images/system.img'
    serial = boot_path.parent / 'qemu.log'
    image_sha = digest(image) if image.is_file() and not image.is_symlink() else None
    if (boot.get('status') != 'pass' or boot.get('purpose') != 'acceptance' or
            boot.get('archive_sha256') != archive_sha or not environment.get('boot_id') or
            environment.get('external_keepalive') is not False or
            environment.get('freshly_extracted_directory') != str(directory) or
            image.is_symlink() or not image.is_file() or serial.is_symlink() or not serial.is_file() or
            image_sha != boot.get('initial_package_file_sha256', {}).get('images/system.img')):
        raise ValueError('boot profile requires the unchanged fresh package image and serial trace')
    output.mkdir(parents=True, exist_ok=False)
    captured = output / 'serial.log'
    shutil.copyfile(serial, captured)
    entries = (MODULE_PATH,) + USAGE_PATHS
    names = ('module-stat.txt', 'usage-system-stat.txt', 'usage-root-stat.txt')
    observations = []
    for entry, name in zip(entries, names):
        value = image_stat(image, entry, docker_image)
        (output / name).write_text(value)
        observations.append(value)
    result = verify(observations[0], observations[1:], captured.read_text(errors='replace'))
    evidence = {'schema_version': 1, 'status': 'pass', 'persona': 'boot-profile',
        'scope': 'module_update_initializer_and_unused_usage_init_only',
        'archive_sha256': archive_sha, 'boot_id': environment['boot_id'],
        'system_image': str(image), 'system_image_sha256': image_sha,
        'serial_sha256': digest(captured),
        'stat_sha256': {name: digest(output / name) for name in names}, 'result': result}
    (output / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--boot', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--docker-image', required=True)
    args = parser.parse_args()
    run(args.archive, args.boot, args.output, args.docker_image)


if __name__ == '__main__':
    main()
