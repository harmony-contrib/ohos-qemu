#!/usr/bin/env python3
"""Apply only the fixed ALSA443 source tuple; this is not an onset verifier."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
GN_ARG = 'alsa_lib_pcm_onset_diagnostic_enable'
# Fixed paths and complete byte identities: DATA cannot choose code or payloads.
FILES = {'third_party/alsa-lib/BUILD.gn': {'before': {'sha256': 'd7ba75a9591c70b1e463cd8c9463777a1da6b9f194a4ec0aee4a685edd5e2cbb',
                                              'bytes': 13935},
                                   'after': {'sha256': 'd57190261f98cd3975b0a8173b98b90c9f022f5b13f5b88bbca0c62de8b30c41',
                                             'bytes': 14156},
                                   'payload': 'BUILD.gn',
                                   'guard_only': False},
 'third_party/alsa-lib/src/pcm/pcm_hw.c': {'before': {'sha256': 'c7eceb39266147061ec78a83212b8250010b83a192b3f81ee4b23736cbb1019b',
                                                      'bytes': 57940},
                                           'after': {'sha256': 'd6dfc03c36ec0d78414c39047e43e55d81f3d0497361235aea40c977ea949f71',
                                                     'bytes': 61029},
                                           'payload': 'pcm_hw.c',
                                           'guard_only': False},
 'third_party/alsa-lib/src/pcm/pcm_local.h': {'before': {'sha256': 'f80f07d42cac6eee46d53518917030324a790afebac04c119cc0b9966c0fa2cd',
                                                         'bytes': 52680},
                                              'after': {'sha256': 'f80f07d42cac6eee46d53518917030324a790afebac04c119cc0b9966c0fa2cd',
                                                        'bytes': 52680},
                                              'payload': None,
                                              'guard_only': True},
 'third_party/alsa-lib/src/pcm/media398_onset.h': {'before': None,
                                                   'after': {'sha256': '7dd8cf8102dda20a9211e9d56e79416626fcaf5c8ddc449ace5bd37fcc9438d2',
                                                             'bytes': 33433},
                                                   'payload': 'media398_onset.h',
                                                   'guard_only': False},
 'third_party/alsa-lib/src/pcm/media398_wire.h': {'before': None,
                                                  'after': {'sha256': '89e44af7fcc7f2f40e1fb60bdc9fba26de690049034f9d5e943d6b65b50be1da',
                                                            'bytes': 1034},
                                                  'payload': 'media398_wire.h',
                                                  'guard_only': False}}


def digest(raw):
    return {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def target(root, relative):
    path = root / relative
    for node in (path, *path.parents):
        if node == root:
            break
        if node.is_symlink():
            raise ValueError('linked PCM component path: ' + relative)
    return path


def regular_bytes(path, missing=False):
    try:
        before = path.lstat()
    except FileNotFoundError:
        if missing:
            return None
        raise ValueError('missing regular component file: ' + str(path))
    if not stat.S_ISREG(before.st_mode):
        raise ValueError('nonregular component file: ' + str(path))
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as stream:
        held = os.fstat(stream.fileno())
        if (held.st_dev, held.st_ino) != (before.st_dev, before.st_ino):
            raise ValueError('component file changed during open')
        raw = stream.read()
        after = os.fstat(stream.fileno())
    named = path.lstat()
    if ((held.st_dev, held.st_ino, held.st_size, held.st_mtime_ns) !=
            (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns) or
            (after.st_dev, after.st_ino) != (named.st_dev, named.st_ino)):
        raise ValueError('component file changed during read')
    return raw


def payloads():
    manifest = json.loads(regular_bytes(HERE / 'source_states.json'))
    if manifest['files'] != FILES:
        raise ValueError('PCM manifest differs from fixed source states')
    result = {}
    directory = HERE / 'files'
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError('regular PCM payload directory required')
    expected = {entry['payload'] for entry in FILES.values() if not entry['guard_only']}
    if {entry.name for entry in directory.iterdir()} != expected:
        raise ValueError('unexpected or missing PCM payload file')
    for relative, entry in FILES.items():
        if not entry['guard_only']:
            raw = regular_bytes(directory / entry['payload'])
            if digest(raw) != entry['after']:
                raise ValueError('PCM payload hash/size differs: ' + relative)
            result[relative] = raw
    return result


def validate(root, require_patched=False):
    root = Path(os.path.abspath(root))
    if root.is_symlink() or not root.is_dir():
        raise ValueError('regular source root required')
    observed = {}
    for relative in FILES:
        path = target(root, relative)
        if not path.parent.is_dir():
            raise ValueError('missing PCM parent directory')
        raw = regular_bytes(path, missing=True)
        observed[relative] = digest(raw) if raw is not None else None
    before = all(observed[name] == entry['before'] for name, entry in FILES.items())
    after = all(observed[name] == entry['after'] for name, entry in FILES.items())
    if not before and not after:
        raise ValueError('unknown or mixed PCM source tuple; preserving source')
    if require_patched and not after:
        raise ValueError('complete patched PCM tuple required')
    return 'after' if after else 'before'


def gn_argument(root, enabled):
    if enabled not in ('0', '1'):
        raise ValueError('PCM component toggle must be exactly 0 or 1')
    payloads()
    state = validate(root, require_patched=(enabled == '1'))
    if state == 'before':
        return ''  # No declaration in pristine GN: do not pass an unknown arg.
    return GN_ARG + ('=true' if enabled == '1' else '=false')


def run(root):
    root = Path(os.path.abspath(root))
    outputs = payloads()  # Prove all payloads before changing any source file.
    if validate(root) == 'after':
        return
    directory = root / '.ohos-qemu-patches'
    if directory.is_symlink():
        raise ValueError('linked PCM patch lock directory')
    directory.mkdir(exist_ok=True)
    fd = os.open(directory / 'alsa-pcm-onset.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if validate(root) == 'after':
            return
        staged = []
        try:
            for relative, raw in outputs.items():
                path = target(root, relative)
                mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else 0o644
                fd, temporary = tempfile.mkstemp(prefix='.pcm-onset-', dir=path.parent)
                staged.append((path, temporary))
                with os.fdopen(fd, 'wb') as stream:
                    stream.write(raw)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.chmod(temporary, mode)
            # All stages are complete, and the entire source tuple must remain
            # original before the first replacement. Interrupted mixed states
            # are rejected on re-entry; they are never adopted as patched.
            if validate(root) != 'before':
                raise ValueError('PCM source changed before publication')
            for path, temporary in staged:
                os.replace(temporary, path)
        finally:
            for _, temporary in staged:
                if os.path.lexists(temporary):
                    os.unlink(temporary)
        validate(root, require_patched=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--require-patched', action='store_true')
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--gn-arg', choices=('0', '1'))
    args = parser.parse_args()
    if args.gn_arg is not None:
        argument = gn_argument(args.source_root, args.gn_arg)
        if argument:
            print(argument)
    elif args.check or args.require_patched:
        payloads()
        print(validate(args.source_root, require_patched=args.require_patched))
    else:
        run(args.source_root)
        print('verified complete PCM443 source component; GN/DSO/onset/runtime remain separate')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError, json.JSONDecodeError) as error:
        print('PCM component rejected: ' + str(error), file=sys.stderr)
        sys.exit(1)
