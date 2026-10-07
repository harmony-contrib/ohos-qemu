#!/usr/bin/env python3
"""Record checksums, actual ELF ABI and pinned real-code inputs; no runtime claim."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess


def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact-root', type=Path, required=True)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--ohos-root', type=Path, required=True)
    parser.add_argument('--arch', nargs='+', choices=('arm', 'arm64', 'x86_64'), required=True)
    args = parser.parse_args()
    outputs = {}
    for arch in args.arch:
        path = args.artifact_root / arch / 'libavcenc_ohos.z.so'
        header = path.read_bytes()[:20]
        elf_class, machine = {'arm': (1, 40), 'arm64': (2, 183), 'x86_64': (2, 62)}[arch]
        if (len(header) != 20 or header[:4] != b'\x7fELF' or header[4:6] != bytes((elf_class, 1)) or
                struct.unpack_from('<H', header, 18)[0] != machine):
            raise ValueError('AVC ELF ABI mismatch: ' + str(path))
        outputs[path.relative_to(args.artifact_root).as_posix()] = {
            'sha256': checksum(path), 'size': path.stat().st_size,
            'elf_class': elf_class, 'elf_machine': machine,
            'dynamic_dependencies': subprocess.check_output(['readelf', '-d', str(path)], text=True),
        }
    manifest = {
        'schema_version': 1, 'backend': 'real pinned M144 OpenH264 AVC encoder',
        'status': 'compile_only_not_new_image_runtime_acceptance',
        'chromium_revision': 'a8168622b056f25c2e68d5f12fe2759bad2d9a44',
        'openh264_revision': '652bdb7719f30b52b08e506645a7322ff1b2cc6f',
        'av_codec_revision': 'e5c525670d1f6622d441c9e5bf975ea0579ea177',
        'wrapper_abi_header_sha256': checksum(args.source_root / 'ohos/qemu_avc/AvcEnc_Typedef.h'),
        'inputs': {name: checksum(args.source_root / 'ohos/qemu_avc' / name)
                   for name in ('BUILD.gn', 'qemu_avc_encoder.cc', 'avcenc.map')},
        'licenses': {name: checksum(args.artifact_root / 'licenses' / name)
                     for name in ('openh264-LICENSE', 'libc++-LICENSE.TXT',
                                  'libc++abi-LICENSE.TXT', 'compiler-rt-LICENSE.TXT')},
        'artifacts': outputs,
    }
    (args.artifact_root / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'status': manifest['status'], 'artifacts': outputs}, indent=2))


if __name__ == '__main__':
    main()
