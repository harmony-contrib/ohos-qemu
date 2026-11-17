#!/usr/bin/env python3
"""Apply the fixed QEMU-only RIL wiring; parent schedules the source resource."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from verify_source import HERE, state

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from guarded_source_vector579 import apply, heads, identity, load, replace, target


def restore_known_partial(root, value):
    """Repair only the exact partial write retained from source prepare579-05."""
    names = ('vendor/ohemu/virt/hdf_config/uhdf/device_info.hcs',
             'base/telephony/core_service/services/etc/param/telephony.para')
    paths = [target(root, name) for name in names]
    current = [path.read_bytes() for path in paths]
    digests = [hashlib.sha256(data).hexdigest() for data in current]
    expected = [value['files'][names[0]][0], value['files'][names[1]][1]]
    if digests != expected:
        return
    metadata = [identity(path) for path in paths]
    original = (HERE / 'before/telephony.para').read_bytes()
    if hashlib.sha256(original).hexdigest() != value['files'][names[1]][0]:
        raise ValueError('fixed original RIL parameter prefix changed')
    if any(path.read_bytes() != data or identity(path) != info
           for path, data, info in zip(paths, current, metadata)):
        raise ValueError('retained partial RIL source changed before restoration')
    replace(paths[1], original, metadata[1], {}, names[1])
    print(json.dumps({'scope': 'restore exact known failed source-preparation prefix only',
        'prepare579_05_partial_vector': digests, 'restored_parameter_sha256': value['files'][names[1]][0]}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    args = parser.parse_args()
    root = args.source_root.resolve()
    value = load(HERE)
    heads(root, value)
    restore_known_partial(root, value)
    # The ordinary guarded transaction stages both exact whole files first.
    # --binary preserves the original HCS CRLF bytes; a failed patch can no
    # longer leave just the parameter file modified in the live source volume.
    apply(root, HERE, value, patch_name='0001-enable-existing-reference-ril.patch')
    if state(root) != 'final':
        raise ValueError('Complete final QEMU RIL wiring vector required')
    print('QEMU reference RIL wiring source applied; runtime NOT accepted')


if __name__ == '__main__':
    main()
