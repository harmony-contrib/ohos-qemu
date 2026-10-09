#!/usr/bin/env python3
"""Reject LFS placeholders and malformed fonts in the actual packaged image."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import tempfile

from ext_image_entries import dump_unique_file
from verify_alsa_config_image import debugfs_path, file_sha256

MAP = Path(__file__).resolve().parents[1] / 'patches/common/build/github_lfs_assets/assets.tsv'
REQUIRED = {'HarmonyOS_Sans_SC.ttf', 'HMOSColorEmojiCompat.ttf'}


def locked_fonts():
    result = {}
    for line in MAP.read_text().splitlines():
        if not line or line.startswith('#'):
            continue
        project, relative, remote, sha, size = line.split('\t')
        if project != 'base/global/system_resources':
            continue
        if (not re.fullmatch(r'fonts/[A-Za-z0-9_.-]+\.ttf', relative) or
                remote != 'https://gitcode.com/openharmony/global_system_resources' or
                not re.fullmatch('[0-9a-f]{64}', sha) or not size.isdigit() or int(size) <= 1024):
            raise ValueError('invalid pinned font asset identity')
        name = Path(relative).name
        if name in result:
            raise ValueError('duplicate locked font')
        result[name] = {'sha256': sha, 'size': int(size)}
    if not REQUIRED <= set(result):
        raise ValueError('missing fixed-release Chinese/emoji font object identities')
    return result


def font_entries(text):
    entries = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        fields = line.split('/')
        if len(fields) != 8 or fields[0] or fields[-1]:
            raise ValueError('malformed actual font directory listing')
        _, inode, mode, uid, gid, name, size, _ = fields
        if name in ('.', '..'):
            continue
        if (not re.fullmatch('[A-Za-z0-9_.-]+', name) or name in entries or
                not inode.isdigit() or not uid.isdigit() or not gid.isdigit() or not re.fullmatch('100[0-7]{3}', mode) or
                not size.isdigit() or not 0 < int(size) <= 128 * 1024 * 1024):
            raise ValueError('unsafe, duplicate, nonregular or oversized font asset')
        entries[name] = int(size)
    return entries


def inspect_sfnt(data):
    if len(data) < 12 or len(data) > 128 * 1024 * 1024:
        raise ValueError('invalid font size')
    faces = [0]
    if data[:4] == b'ttcf':
        count = struct.unpack_from('>I', data, 8)[0]
        if not 1 <= count <= 64 or 12 + count * 4 > len(data):
            raise ValueError('invalid font collection face directory')
        faces = list(struct.unpack_from('>' + 'I' * count, data, 12))
    for offset in faces:
        if offset + 12 > len(data) or data[offset:offset + 4] not in (b'\x00\x01\x00\x00', b'OTTO'):
            raise ValueError('font is a placeholder or lacks a valid SFNT face')
        count = struct.unpack_from('>H', data, offset + 4)[0]
        if not 1 <= count <= 4096 or offset + 12 + count * 16 > len(data):
            raise ValueError('invalid font table directory')
        tags = set()
        for index in range(count):
            tag, _, start, length = struct.unpack_from('>4sIII', data, offset + 12 + index * 16)
            if tag in tags or start > len(data) or length > len(data) - start:
                raise ValueError('duplicate or truncated font table')
            if tag in (b'cmap', b'head', b'maxp') and length < {b'cmap': 4, b'head': 54, b'maxp': 6}[tag]:
                raise ValueError('truncated essential font table')
            if tag == b'head' and data[start + 12:start + 16] != b'\x5f\x0f\x3c\xf5':
                raise ValueError('invalid font head magic')
            tags.add(tag)
        if not {b'cmap', b'head', b'maxp'} <= tags:
            raise ValueError('font lacks essential character/face tables')
    return len(faces)


def inspect_asset(name, data, locked):
    result = {'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data)}
    if name in locked and result != locked[name]:
        raise ValueError('packaged font does not match its exact immutable object: ' + name)
    if name.endswith(('.ttf', '.otf', '.ttc')):
        result['faces'] = inspect_sfnt(data)
    elif name.endswith('.json'):
        if not isinstance(json.loads(data), (dict, list)):
            raise ValueError('font configuration must be a real JSON document')
    else:
        raise ValueError('unknown unvalidated file in the font directory')
    return result


def verify_image(image, scratch):
    locked = locked_fonts()
    executable = debugfs_path()
    listings = []
    for directory in ('/fonts', '/system/fonts'):
        value = subprocess.run([executable, '-R', 'ls -p ' + directory, str(image)],
                               check=True, capture_output=True, text=True)
        entries = font_entries(value.stdout)
        if entries:
            listings.append(entries)
    if not listings or any(value != listings[0] for value in listings[1:]) or not set(locked) <= set(listings[0]):
        raise ValueError('missing or ambiguous actual packaged font directory')
    result = {}
    for name, size in sorted(listings[0].items()):
        destination = scratch / name
        destination.mkdir()
        path, identity = dump_unique_file(image, ('/fonts/' + name, '/system/fonts/' + name), destination, executable)
        if path.stat().st_size != size:
            raise ValueError('extracted font size differs from actual inode')
        result[name] = dict(inspect_asset(name, path.read_bytes(), locked), **identity)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system-image', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = {'status': 'fail', 'scope': 'actual_packaged_font_objects_and_tables_NOT_text_rendering',
              'first_artifact_behavior_gate_passed': False, 'failures': [],
              'system_image_sha256': file_sha256(args.system_image), 'asset_map_sha256': file_sha256(MAP)}
    try:
        with tempfile.TemporaryDirectory(prefix='qemu-font-image-') as directory:
            report['assets'] = verify_image(args.system_image, Path(directory))
        report['status'] = 'pass'
    except (OSError, ValueError, KeyError, struct.error, subprocess.SubprocessError) as error:
        report['failures'].append(str(error))
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'failures': report['failures']}))
    return 0 if report['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
