#!/usr/bin/env python3
"""Normalize one known ArkDown native staging layout before real HAP signing.

Only archive paths and ZIP64 extras change. Library bytes, module permissions,
application code and resources stay exact. Unknown nesting/collisions/wrong ELF
ABIs fail closed. This does not grant permissions or demonstrate guest loading.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import stat
import struct
import zipfile

ABIS = {'arm64-v8a': (2, 183), 'armeabi-v7a': (1, 40), 'x86_64': (2, 62)}
LIBRARY = re.compile(r'lib[A-Za-z0-9_+.\-]+\.so')


def canonical_library(name, data):
    parts = name.split('/')
    if len(parts) < 3 or parts[1] not in ABIS or not LIBRARY.fullmatch(parts[-1]):
        raise ValueError('unexpected QEMU test HAP native library path: ' + name)
    abi, filename = parts[1], parts[-1]
    canonical = 'libs/' + abi + '/' + filename
    if name != canonical:
        module = parts[2]
        if re.fullmatch('[A-Za-z0-9_.-]+', module) is None:
            raise ValueError('unknown native staging module')
        expected = (f'libs/{abi}/{module}/build/default/intermediates/stripped_native_libs/default/{abi}/'
                    f'{module}/build/default/intermediates/libs/default/{abi}/{module}/libs/{abi}/{filename}')
        if name != expected:
            raise ValueError('unrecognized native staging layout: ' + name)
    cls, machine = ABIS[abi]
    if (len(data) < (64 if cls == 2 else 52) or data[:7] != b'\x7fELF' + bytes((cls, 1, 1)) or
            struct.unpack_from('<HH', data, 16) != (3, machine)):
        raise ValueError('native HAP library ELF differs from its declared ABI: ' + name)
    return canonical


def normalize_archive(unsigned, output):
    unsigned, output = Path(unsigned), Path(output)
    if unsigned.is_symlink() or not unsigned.is_file() or output.exists() or output.is_symlink():
        raise ValueError('regular unsigned input and fresh output required')
    original_sha = hashlib.sha256(unsigned.read_bytes()).hexdigest()
    names, libraries = set(), []
    with zipfile.ZipFile(unsigned) as source, zipfile.ZipFile(output, 'x', allowZip64=False) as target:
        for original in source.infolist():
            name = original.filename
            parts = PurePosixPath(name).parts
            mode = original.external_attr >> 16
            if (not parts or name.startswith('/') or '\\' in name or '..' in parts or
                    any(ord(char) < 32 for char in name) or stat.S_ISLNK(mode)):
                raise ValueError('unsafe test HAP archive entry')
            content = source.read(original)
            canonical = canonical_library(name, content) if name.startswith('libs/') and not original.is_dir() else name
            if canonical in names:
                raise ValueError('duplicate/colliding test HAP archive entry: ' + canonical)
            names.add(canonical)
            member = copy.copy(original)
            member.filename = canonical
            member.extra = b''
            target.writestr(member, content)
            if name.startswith('libs/') and not original.is_dir():
                libraries.append({'original': name, 'canonical': canonical,
                                  'sha256': hashlib.sha256(content).hexdigest(), 'bytes': len(content)})
    if hashlib.sha256(unsigned.read_bytes()).hexdigest() != original_sha:
        raise ValueError('unsigned HAP changed during normalization')
    return {'scope': 'test_HAP_archive_layout_only_NOT_signature_or_guest_loading',
            'unsigned_sha256': original_sha, 'normalized_sha256': hashlib.sha256(output.read_bytes()).hexdigest(),
            'libraries': libraries, 'library_bytes_changed': False, 'permissions_changed': False}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--unsigned', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(normalize_archive(args.unsigned, args.output), indent=2))
