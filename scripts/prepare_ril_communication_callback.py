#!/usr/bin/env python3
"""Append the genuine modem communication-state event to the fixed RIL IDL.

The full inherited HDI transaction map must be regenerated and compared in
private before packaging. This source preparation alone proves no modem state.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile

PROJECT = 'drivers/interface'
REVISION = '42289d3f8e46f5a112bd7ea6d36e4baaeac0718d'
TARGET = PROJECT + '/ril/v1_5/IRilCallback.idl'
BEFORE_SHA = 'ee3749d490bf2239ec0d7d99a36aa859bc450997b9df66e337f711709a62a292'
ANCHOR = '    [oneway] SetPrimarySlotResponse([in] struct RilRadioResponseInfo responseInfo);\n'
APPEND = '''
    /**
     * Reports the actual modem-provided 5A communication state for this slot.
     * NR registration or signal strength alone does not determine this state.
     * Appended after the existing v1_5 callbacks to preserve all old commands.
     */
    [oneway] CommunicationStateUpdated([in] struct RilRadioResponseInfo responseInfo, [in] boolean is5A);
'''


def transform(data):
    separator = b'\r\n' if b'\r\n' in data else b'\n'
    anchor = ANCHOR.encode().replace(b'\n', separator)
    append = APPEND.encode().replace(b'\n', separator)
    original = data
    if data.count(append) == 1:
        original = data.replace(append, b'')
    if hashlib.sha256(original).hexdigest() != BEFORE_SHA or original.count(anchor) != 1:
        raise ValueError('unknown or partial RIL callback IDL; preserving source')
    final = original.replace(anchor, anchor + append)
    if data not in (original, final):
        raise ValueError('noncanonical RIL callback extension; preserving source')
    return final


def apply(root):
    root = Path(root).absolute()
    if root.is_symlink() or not root.is_dir():
        raise ValueError('materialized source root required')
    target = root / TARGET
    cursor = target
    while cursor != root:
        if cursor.is_symlink():
            raise ValueError('linked RIL callback source rejected')
        cursor = cursor.parent
    project = root / PROJECT
    if (project / '.git').exists() and subprocess.check_output(
            ['git', '-C', str(project), 'rev-parse', 'HEAD'], text=True).strip() != REVISION:
        raise ValueError('fixed RIL interface project revision required')
    original = target.read_bytes()
    final = transform(original)
    if original != final:
        descriptor, temporary = tempfile.mkstemp(prefix='.qemu-ril-callback-', dir=target.parent)
        try:
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(final)
                stream.flush()
                os.fsync(stream.fileno())
            os.chmod(temporary, target.stat().st_mode & 0o777)
            if target.read_bytes() != original:
                raise ValueError('RIL callback source changed after preflight')
            os.replace(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)
    return {'status': 'source_extension_ONLY_NOT_HDI_compile_or_modem_runtime', 'project': PROJECT,
            'revision': REVISION, 'target': TARGET, 'sha256': hashlib.sha256(final).hexdigest(),
            'first_artifact_behavior_gate_passed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(apply(args.source_root), indent=2))
