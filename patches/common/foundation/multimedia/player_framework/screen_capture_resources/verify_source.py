#!/usr/bin/env python3
"""Pin eleven new resources as one exact state; source/packaging guard only."""
import argparse
import hashlib
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / 'lib'))
from exact_source_states import validate_component

PROJECT = 'foundation/multimedia/player_framework'
REVISION = '3d3b1231db27561e8978652d7ae867c12f488d9a'
BUILD_RELATIVE = 'services/etc/BUILD.gn'
BUILD_SHA256 = '611723ea3f2d7217980eeefa76718399740399dbacd2e902e4ac95b4858c3cd7'
BUILD_BYTES = 3918
FILES = (('services/etc/image/capsule.svg', None, '74a720bf8e59f118a93ce62b455bb55e2596bceb2c4fb308e5e798cadd7153a6'),
 ('services/etc/image/capsule_stop.svg',
  None,
  '84442cf7f6519282820983306ad74ed7f3a03bceb70be97f735120d7f4e3bb76'),
 ('services/etc/image/mic.svg', None, '68ba68db5fa4add018bf98de1a93101a5b565d6e7e2a8be2f0666352e9653d11'),
 ('services/etc/image/mic_off.svg', None, '0ca1b2edbde81755a124dc41d7207a82cfb320374b43cd81ac8d4245cbc56092'),
 ('services/etc/image/notification.png',
  None,
  '54287281f24db1144a494c39328bd13ac0eaf8d3dc07e388d07a960bfb67d2a7'),
 ('services/etc/image/stop_dark.png',
  None,
  '6a5cf6983b2603f37ce95cd0fe5f39d0ec1f61e04d39f984290de0f447c978d3'),
 ('services/etc/image/stop.png', None, '6a5cf6983b2603f37ce95cd0fe5f39d0ec1f61e04d39f984290de0f447c978d3'),
 ('services/etc/image/capsule_stop_live2.svg',
  None,
  '84442cf7f6519282820983306ad74ed7f3a03bceb70be97f735120d7f4e3bb76'),
 ('services/etc/image/light.svg', None, '84442cf7f6519282820983306ad74ed7f3a03bceb70be97f735120d7f4e3bb76'),
 ('services/etc/image/pause.svg', None, '0247d52d26968d954d4ce68920f73697655adbdab1e07a471134f0fb3ab80b92'),
 ('services/etc/image/play.svg', None, 'ae755a3e3a3674538cdfe8b895a6d82e1a9f26ad2de44b6a7cbd6beecef32a1d'))


def prerequisites(root):
    """Readonly GN prerequisite, deliberately outside the eleven FILES."""
    root = Path(root).resolve()
    path = root / PROJECT / BUILD_RELATIVE
    cursor = path
    while cursor != root:
        if cursor.is_symlink():
            raise ValueError('screen capture GN prerequisite contains a symlink')
        cursor = cursor.parent
    if not path.is_file() or path.stat().st_size != BUILD_BYTES or hashlib.sha256(path.read_bytes()).hexdigest() != BUILD_SHA256:
        raise ValueError('fixed player screen capture resource GN prerequisite differs')
    return {'path': str(path), 'sha256': BUILD_SHA256, 'bytes': BUILD_BYTES}


def validate(root, require_patched=False):
    # The unchanged exact applier stages only FILES. Keeping this state function
    # about the eleven additions permits its empty scratch preimage. The
    # default apply wrapper and image guard ALWAYS use prerequisites as well.
    return validate_component(root, PROJECT, REVISION, FILES, require_patched)


def validate_source(root, require_patched=False):
    prerequisites(root)
    return validate(root, require_patched)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    parser.add_argument('--prerequisites-only', action='store_true')
    args = parser.parse_args()
    if args.prerequisites_only:
        if args.require_patched:
            raise ValueError('prerequisite-only does not establish an asset state')
        prerequisites(args.source_root)
    else:
        validate_source(args.source_root, args.require_patched)


if __name__ == '__main__':
    main()
