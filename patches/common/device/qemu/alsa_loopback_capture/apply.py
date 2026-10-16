#!/usr/bin/env python3
"""Select a real ALSA loopback capture card without moving ES1370 playback."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

REVISIONS = {
    'device/qemu': 'b017aee8e2dfc97e45aeb508facc1527c3d06f4b',
    'vendor/ohemu': 'b56c5a95ec590543691278b85afe9fe228744163',
}
CONFIGS = tuple('device/qemu/common/virt_full/kernel/' + name + '_virt_defconfig'
                for name in ('arm64', 'arm', 'x86_64'))
JSON_PATH = 'vendor/ohemu/virt/hals/audio/alsa_adapter.json'
ORIGINAL_JSON = (b'{\n    "adapters": [\n        {\n            "name": "primary",\n'
                 b'            "cardId": 0,\n            "cardName": "AudioPCI"\n'
                 b'        }\n    ]\n}\n')
FINAL_JSON = ORIGINAL_JSON.replace(
    b'"cardName": "AudioPCI"',
    b'"cardName": "AudioPCI",\n            "captureCardId": 1,\n'
    b'            "captureCardName": "QemuCapture",\n            "captureDevice": 0')
BOOT_PARAMETERS = ('snd-ens1370.index=0', 'snd-aloop.index=1',
                   'snd-aloop.id=QemuCapture', 'snd-aloop.pcm_substreams=1')


def regular_path(root, relative):
    path = root / relative
    cursor = path
    while cursor != root:
        if cursor.is_symlink():
            raise ValueError('symlink input rejected: ' + relative)
        cursor = cursor.parent
    if not path.is_file():
        raise ValueError('regular input required: ' + relative)
    return path


def config_bytes(data, relative):
    text = data.decode('utf-8')
    values = {}
    for line in text.splitlines():
        match = re.fullmatch(r'(CONFIG_[A-Z0-9_]+)=(.+)', line)
        disabled = re.fullmatch(r'# (CONFIG_[A-Z0-9_]+) is not set', line)
        if match or disabled:
            name, value = (match[1], match[2]) if match else (disabled[1], 'n')
            if name in values:
                raise ValueError('duplicate selection ' + name + ': ' + relative)
            values[name] = value
    for name in ('CONFIG_SOUND', 'CONFIG_SND', 'CONFIG_SND_PCM', 'CONFIG_SND_DRIVERS',
                 'CONFIG_SND_PCI', 'CONFIG_SND_ENS1370'):
        if values.get(name) != 'y':
            raise ValueError('required real ALSA dependency missing: ' + name)
    if values.get('CONFIG_SND_ALOOP') not in ('n', 'y'):
        raise ValueError('unknown or absent ALSA loopback selection: ' + relative)
    if values['CONFIG_SND_ALOOP'] == 'y':
        return data
    old = b'# CONFIG_SND_ALOOP is not set'
    if data.splitlines().count(old) != 1:
        raise ValueError('noncanonical ALSA loopback selection: ' + relative)
    return data.replace(old, b'CONFIG_SND_ALOOP=y')


def prepare(root):
    """Validate every input before preparing any source mutation."""
    for relative, revision in REVISIONS.items():
        git = root / relative / '.git'
        cursor = git
        while cursor != root:
            if cursor.is_symlink():
                raise ValueError('symlink source metadata rejected: ' + relative)
            cursor = cursor.parent
        head = subprocess.check_output(['git', '-C', str(root / relative),
                                        'rev-parse', 'HEAD'], text=True).strip()
        if head != revision:
            raise ValueError('pinned source revision required: ' + relative)
    changes = []
    for relative in CONFIGS + (JSON_PATH,):
        path = regular_path(root, relative)
        before = path.read_bytes()
        if relative == JSON_PATH:
            if before not in (ORIGINAL_JSON, FINAL_JSON):
                raise ValueError('unknown ALSA adapter bytes; preserving source')
            after = FINAL_JSON
        else:
            after = config_bytes(before, relative)
        changes.append((path, before, after))
    return changes


def atomic_write(path, data):
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '.', dir=path.parent)
    try:
        os.fchmod(fd, path.stat().st_mode & 0o777)
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def apply(root):
    changes = prepare(root)
    written = []
    try:
        for path, before, after in changes:
            if path.read_bytes() != before:
                raise ValueError('source changed after preflight: ' + str(path))
            if before != after:
                atomic_write(path, after)
                written.append((path, before))
    except BaseException:
        for path, before in reversed(written):
            atomic_write(path, before)
        raise
    return {'status': 'source_selection_only_NOT_kernel_build_or_guest_capture',
            'boot_parameters_required': list(BOOT_PARAMETERS),
            'files': {str(path.relative_to(root)): {
                'before_sha256': hashlib.sha256(before).hexdigest(),
                'after_sha256': hashlib.sha256(after).hexdigest()}
                for path, before, after in changes}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--product', action='append', default=[])
    args = parser.parse_args()
    root = args.source_root.resolve(strict=True)
    print(json.dumps(apply(root), indent=2))


if __name__ == '__main__':
    main()
