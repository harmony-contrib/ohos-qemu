#!/usr/bin/env python3
"""Snapshot a new package's serial trace of backup SA init and exec."""
import argparse
import json
from pathlib import Path
import shutil

from run_root_probe import digest
from verify_backup_init_results import verify


def run(archive: Path, boot_path: Path, output: Path) -> dict:
    boot = json.loads(boot_path.read_text())
    environment = boot.get('test_environment', {})
    archive_sha = digest(archive)
    if (boot.get('status') != 'pass' or boot.get('purpose') != 'acceptance' or
            boot.get('archive_sha256') != archive_sha or
            environment.get('external_keepalive') is not False or
            not environment.get('boot_id')):
        raise ValueError('backup init requires the exact fresh unassisted package boot')
    original = boot_path.parent / 'qemu.log'
    if original.is_symlink() or not original.is_file():
        raise ValueError('missing real QEMU serial trace')
    output.mkdir(parents=True, exist_ok=False)
    snapshot = output / 'serial.log'
    shutil.copyfile(original, snapshot)
    result = verify(snapshot.read_text(errors='replace'))
    evidence = {'schema_version': 1, 'status': 'pass', 'persona': 'backup-init',
        'scope': 'actual_init_accepts_and_execs_backup_sa_NOT_Backup_API_data_behavior',
        'archive_sha256': archive_sha, 'boot_id': environment['boot_id'],
        'serial': str(snapshot), 'serial_sha256': digest(snapshot), 'result': result}
    (output / 'evidence.json').write_text(json.dumps(evidence, indent=2) + '\n')
    return evidence


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--boot', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    run(args.archive, args.boot, args.output)


if __name__ == '__main__':
    main()
