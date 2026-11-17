#!/usr/bin/env python3
"""Verify pinned AVC dependency provenance/ABI. Never certifies guest behavior."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'scripts'))
from verify_runtime_elf_contract import read_elf, verify_machine

PINS = {
    'chromium_revision': 'a8168622b056f25c2e68d5f12fe2759bad2d9a44',
    'openh264_revision': '652bdb7719f30b52b08e506645a7322ff1b2cc6f',
    'av_codec_revision': 'e5c525670d1f6622d441c9e5bf975ea0579ea177',
    'wrapper_abi_header_sha256': '728c5432611d621c26f426d64835cb7542b34d32c1b0f167aa6af8754a9edcf7',
}
INPUTS = ('BUILD.gn', 'qemu_avc_encoder.cc', 'avcenc.map')
LICENSES = ('openh264-LICENSE', 'libc++-LICENSE.TXT', 'libc++abi-LICENSE.TXT', 'compiler-rt-LICENSE.TXT')
LICENSE_HASHES = {
    'openh264-LICENSE': 'dd5c1c9668512530fa5a96e4c29ac4033d70a7eeb0eed7a42fddb6dd794ebdbb',
    'libc++-LICENSE.TXT': '539dd7aed86e8a4f12cbdd0e6c50c189c7d74847e4fecc64ce2c6ee3a01da38b',
    'libc++abi-LICENSE.TXT': 'e2b35be49f7284a45b7baca8fc7b3ab7440e7902392b2528a457816b5bb2a15c',
    'compiler-rt-LICENSE.TXT': '1a8f1058753f1ba890de984e48f0242a3a5c29a6a8f2ed9fd813f36985387e8d',
}
EXPORTS = frozenset(('InitEncoder', 'EncodeProcess', 'ReleaseEncoder'))
MACHINES = {'arm': (1, 40), 'arm64': (2, 183), 'x86_64': (2, 62)}


def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def unique_keys(pairs):
    document = {}
    for key, value in pairs:
        if key in document: raise ValueError('duplicate AVC provenance key: ' + key)
        document[key] = value
    return document


def dynamic_contract(data):
    if len(data) < 64 or data[:4] != b'\x7fELF' or data[4] not in (1, 2) or data[5] != 1:
        raise ValueError('invalid AVC ELF header')
    elf_class = data[4]
    if elf_class == 2:
        offset, = struct.unpack_from('<Q', data, 40)
        size, count = struct.unpack_from('<HH', data, 58)
        section_format, entry_format = '<IIQQQQIIQQ', '<qQ'
    else:
        offset, = struct.unpack_from('<I', data, 32)
        size, count = struct.unpack_from('<HH', data, 46)
        section_format, entry_format = '<IIIIIIIIII', '<iI'
    if size < struct.calcsize(section_format) or count == 0 or offset + count * size > len(data):
        raise ValueError('invalid AVC ELF sections')
    sections = [struct.unpack_from(section_format, data, offset + index * size) for index in range(count)]
    tables = [section for section in sections if section[1] == 6]
    if len(tables) != 1: raise ValueError('AVC library must have exactly one dynamic table')
    table = tables[0]
    if table[6] >= len(sections): raise ValueError('invalid AVC ELF dynamic string table')
    strings_section = sections[table[6]]
    if strings_section[1] != 3 or strings_section[4] + strings_section[5] > len(data):
        raise ValueError('invalid AVC ELF dynamic string contents')
    strings = data[strings_section[4]:strings_section[4] + strings_section[5]]
    entry_size = struct.calcsize(entry_format)
    if table[4] + table[5] > len(data) or table[5] % entry_size or table[9] != entry_size:
        raise ValueError('invalid AVC ELF dynamic entries')
    needed, sonames, terminated = [], [], False
    for position in range(table[4], table[4] + table[5], entry_size):
        tag, value = struct.unpack_from(entry_format, data, position)
        if tag == 0:
            terminated = True
            break
        if tag not in (1, 14): continue
        end = strings.find(b'\0', value)
        if value >= len(strings) or end < 0: raise ValueError('invalid AVC ELF dependency name')
        name = strings[value:end].decode('ascii')
        (needed if tag == 1 else sonames).append(name)
    if not terminated or needed != ['libc.so'] or sonames != ['libavcenc_ohos.z.so']:
        raise ValueError('AVC has an unexpected runtime dependency/SONAME')
    return needed


def verify_binary(path, arch):
    data = path.read_bytes()
    elf_class, machine = MACHINES[arch]
    if (len(data) < 64 or data[:4] != b'\x7fELF' or data[4:6] != bytes((elf_class, 1)) or
            struct.unpack_from('<H', data, 16)[0] != 3):
        raise ValueError('AVC must be a native-ABI little-endian ELF shared library')
    info = read_elf(path)
    verify_machine(info, machine, path)
    if info.defined != EXPORTS:
        raise ValueError('AVC must export only the three real wrapper entry points')
    return {'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data),
            'elf_class': elf_class, 'elf_machine': machine, 'needed': dynamic_contract(data)}


def validate(root, arches):
    manifest = json.loads((root / 'manifest.json').read_text(), object_pairs_hook=unique_keys)
    if (type(manifest.get('schema_version')) is not int or manifest['schema_version'] != 1 or
            manifest.get('backend') != 'real pinned M144 OpenH264 AVC encoder' or
            manifest.get('status') != 'compile_only_not_new_image_runtime_acceptance' or
            any(manifest.get(key) != value for key, value in PINS.items())):
        raise ValueError('AVC manifest must retain the fixed source/ABI and compile-only scope')
    files = REPO / 'patches/common/web/arkweb/m144_avc_encoder/files'
    if manifest.get('inputs') != {name: checksum(files / name) for name in INPUTS}:
        raise ValueError('AVC artifacts use stale or unknown adapter inputs; rebuild the dependency')
    licenses = manifest.get('licenses')
    if licenses != LICENSE_HASHES:
        raise ValueError('AVC lacks required OpenH264 and statically linked runtime notices')
    for name in LICENSES:
        if checksum(root / 'licenses' / name) != licenses[name]:
            raise ValueError('AVC runtime notice differs from recorded input: ' + name)
    outputs = {}
    for arch in arches:
        if arch not in MACHINES: raise ValueError('unsupported AVC architecture: ' + arch)
        relative = arch + '/libavcenc_ohos.z.so'
        path = root / relative
        observed = verify_binary(path, arch)
        recorded = manifest.get('artifacts', {}).get(relative)
        if not isinstance(recorded, dict): raise ValueError('missing AVC artifact provenance: ' + arch)
        for key in ('sha256', 'size', 'elf_class', 'elf_machine'):
            if type(recorded.get(key)) is not type(observed[key]) or recorded[key] != observed[key]:
                raise ValueError('AVC artifact differs from recorded provenance: ' + arch + '/' + key)
        outputs[arch] = observed
    return outputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact-root', type=Path, required=True)
    parser.add_argument('--arch', nargs='+', choices=tuple(MACHINES), required=True)
    args = parser.parse_args()
    print(json.dumps({'scope': 'dependency_provenance_and_ABI_only',
                      'first_artifact_behavior_gate_passed': False,
                      'artifacts': validate(args.artifact_root, args.arch)}, indent=2))


if __name__ == '__main__':
    main()
