#!/usr/bin/env python3
"""Re-enter the original HAP preparation pipeline from its exact known prefix.

The root-composed final graph is restored to its pinned predecessor before the
existing HAP components run again. Unknown source bytes are never rewritten.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from mms_provider import read, replace

ASSETS = Path(__file__).resolve().parents[1] / 'common/applications/standard/hap/qemu_provider_sources'


def prepare(root):
    value = json.loads(read(ASSETS / 'source_states.json'))
    name = 'applications/standard/hap/BUILD.gn'
    pair = value['files'][name]
    before = read(ASSETS / 'before/BUILD.gn')
    if hashlib.sha256(before).hexdigest() != pair[0]:
        raise ValueError('fixed complete original HAP pipeline prefix changed')
    project = 'applications/standard/hap'
    revision = subprocess.check_output(['git', '-C', str(root / project), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != value['projects'][project]:
        raise ValueError('actual fixed HAP source project required')
    path = root / name
    current = read(path)
    digest = hashlib.sha256(current).hexdigest()
    # The preceding composed graph was already applied by a completed normal
    # preparation attempt. Rewind only this exact known graph or the current one.
    previous = 'affe73589b6200a6c8e1a0d96f72d41ca8b5c94fc7d309cfa7ad7c0789e00ba6'
    if digest in (previous, pair[1]):
        if read(path) != current:
            raise ValueError('HAP source changed before exact prefix preparation')
        replace(path, before)
        return {'scope': 'source preparation only', 'restored_exact_prefix': True,
                'before_sha256': digest, 'after_sha256': pair[0]}
    return {'scope': 'source preparation only', 'restored_exact_prefix': False,
            'current_sha256': digest, 'original_component_guards_required': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.source_root.resolve())))
