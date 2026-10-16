#!/usr/bin/env python3
"""Preserve the original no-build false-accept challenge; new guard must reject.

Run with --scripts pointing at the reviewed checkout's scripts directory.
The initial checker accepted check_inventory with this payload. The corrected
checker rejects it; neither result asserts native behavior or image boot.
"""
import argparse
import json
from pathlib import Path
import struct
import sys
import tempfile

parser = argparse.ArgumentParser()
parser.add_argument('--scripts', type=Path, required=True)
args = parser.parse_args()
sys.path.insert(0, str(args.scripts.resolve()))
import verify_qemu_msdp_image as M
with tempfile.TemporaryDirectory(prefix='msdp-readonly-counterexample-') as temporary:
    directory = Path(temporary).resolve()
    header = bytearray(64)
    header[:7] = b'\x7fELF\x02\x01\x01'
    struct.pack_into('<HH', header, 16, 3, 183)
    for filename in M.LIBRARIES.values(): (directory / filename).write_bytes(header)
    value = {'schema_version': 1, 'product': 'arm64_virt', 'source_sha256': M.source_hashes(),
             'recipe': M.recipe(), 'features': dict(M.EXPECTED), 'first_artifact_behavior_gate_passed': False,
             'graphs': {name: {'sha256': 'a'*64, 'objects_sha256': {u: 'b'*64 for u in units},
                              'compile_commands': {u: 'not-a-compiler -c nonexistent -o nowhere' for u in units},
                              'cross_dso_cfi': False} for name, units in M.UNITS.items()},
             'files_sha256': {name: M.file_sha256(directory / name) for name in M.LIBRARIES.values()}}
    report = {'scope': 'host checker challenge only, no native/image/runtime proof', 'compiled': False}
    try:
        M.check_inventory(value, 'arm64_virt', directory)
        report['original_counterexample'] = 'ACCEPTED'
    except (ValueError, KeyError, OSError) as error:
        report.update(original_counterexample='REJECTED', reason=str(error))
    report['direct_elf_checks'] = []
    for cfi in (False, True):
        try:
            M.elf(directory / M.LIBRARIES['algo'], 'arm64_virt', cfi)
            report['direct_elf_checks'].append({'cfi': cfi, 'accepted': True})
        except ValueError as error:
            report['direct_elf_checks'].append({'cfi': cfi, 'accepted': False, 'reason': str(error)})
    print(json.dumps(report, indent=2))
