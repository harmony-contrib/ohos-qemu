#!/usr/bin/env python3
"""Prepare only the absent/complete legacy/complete SDK26 caption project.

The finite legacy migration preserves all other source bytes and metadata.
Verification never migrates. No state here is capability acceptance.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
PATCHES = next(p for p in HERE.parents if p.name == 'patches')
sys.path.insert(0, str(PATCHES / 'lib'))
from guarded_source_vector579 import apply, heads, identity, matches, replace, target

PROJECT = 'applications/standard/hap/vassistant_livecaptions579'
PARENT = 'applications/standard/hap'
PARENT_HEAD = 'f2e956a5dd26102f85c86e91d2bfd7c0998534f8'
MODULE = 'entry/src/main/module.json5'
SESSION = 'entry/src/main/ets/common/CaptionSession.ets'
D4_MODULE = 'faf1e45116735c4029cc78cdf105fef8711f5a2c794d6d0f95d1724750e59e28'
LEGACY_SESSION = 'f69188a57f9fa5e925f520dd870726abad0b1f0dc53365947f1d600779f1f0a7'
LEGACY_MODULE = 'f495f8ad7d7341ffb789ec2ec709dcf458b986a3e09685a30d54cb9676ad4c19'
SERVICE = 'entry/src/main/ets/service/AiCaptionServiceExtAbility.ets'


def digest(data):
    return hashlib.sha256(data).hexdigest()


def manifest():
    source = json.loads((HERE / 'source_states.json').read_text())
    old, previous, final = source['legacy_files'], source['previous_d4_files'], source['files']
    typed = source['previous_b091_files']
    if (source.get('schema') != 'caption579-sdk26-native-context-project/v4' or
            source['project'] != PROJECT or source['parent_project'] != PARENT or
            source['parent_head'] != PARENT_HEAD or len(final) != 23 or
            old.keys() != previous.keys() or old.keys() != typed.keys() or old.keys() != final.keys() or
            old[MODULE] != LEGACY_MODULE or previous[MODULE] != final[MODULE] or
            final[MODULE] != D4_MODULE or old[SESSION] != previous[SESSION] or
            old[SESSION] != LEGACY_SESSION or
            typed[MODULE] != final[MODULE] or typed[SESSION] != final[SESSION] or
            old[SERVICE] != previous[SERVICE] or old[SERVICE] != typed[SERVICE] or
            {name for name in final if old[name] != final[name]} != {MODULE, SESSION, SERVICE} or
            {name for name in final if previous[name] != final[name]} != {SESSION, SERVICE} or
            {name for name in final if typed[name] != final[name]} != {SERVICE} or
            source['device_types'] != ['default', 'tablet', '2in1']):
        raise ValueError('complete legacy72/d4 -> typed SDK26 source contract required')
    return source


def state(root, source):
    actual = {}
    for relative in source['files']:
        path = target(root, PROJECT + '/' + relative)
        actual[relative] = digest(path.read_bytes()) if path.exists() else None
    # Production ETS only: later real model/HAR/profile inputs remain untouched.
    ets = root / PROJECT / 'entry/src/main/ets'
    for path in ets.rglob('*'):
        if path.is_symlink():
            raise ValueError('linked production ETS input preserved')
    names = {p.relative_to(root / PROJECT).as_posix()
             for p in ets.rglob('*.ets') if p.is_file()}
    expected = {p for p in source['files'] if p.startswith('entry/src/main/ets/') and p.endswith('.ets')}
    if all(value is None for value in actual.values()) and not names:
        return 'absent'
    if names != expected:
        raise ValueError('unknown production ETS closure preserved')
    if actual == source['files']:
        return 'final'
    if actual == source['previous_b091_files']:
        return 'b091'
    if actual == source['previous_d4_files']:
        return 'd4'
    if actual == source['legacy_files']:
        return 'legacy72'
    raise ValueError('unknown or mixed complete caption project preserved')


def migrate(root, source, epoch):
    before = source[{'legacy72': 'legacy_files', 'd4': 'previous_d4_files', 'b091': 'previous_b091_files'}[epoch]]
    changed = [name for name in source['files'] if before[name] != source['files'][name]]
    patch = {'legacy72': '0002-sdk26-device-types.patch', 'd4': '0003-d4-to-typed-caption.patch',
        'b091': '0004-b091-to-sdk26-service-context.patch'}[epoch]
    originals = {}
    for relative in source['files']:
        path = target(root, PROJECT + '/' + relative)
        originals[relative] = {'bytes': path.read_bytes(), 'identity': identity(path)}
    if state(root, source) != epoch:
        raise ValueError('complete actual prior project changed before snapshot')
    value = {'projects': {PARENT: PARENT_HEAD}, 'files': {
        PROJECT + '/' + name: [before[name], source['files'][name]] for name in changed}}
    with tempfile.TemporaryDirectory(prefix='caption-sdk26-stage-') as directory:
        staged = Path(directory)
        for relative in changed:
            path = staged / PROJECT / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(originals[relative]['bytes'])
        subprocess.run(['patch', '--binary', '--batch', '--forward', '--fuzz=0', '-p1', '-i',
            str(HERE / patch)], cwd=staged, check=True)
        finals = {name: (staged / PROJECT / name).read_bytes() for name in changed}
        if any(digest(data) != source['files'][name] for name, data in finals.items()) or {
                p.relative_to(staged).as_posix() for p in staged.rglob('*') if p.is_file()} != {
                    PROJECT + '/' + name for name in changed}:
            raise ValueError('exact staged finite migration required')
    heads(root, value)
    for relative, original in originals.items():
        if not matches(target(root, PROJECT + '/' + relative), original):
            raise ValueError('source inode changed before migration: ' + relative)
    installed = {}
    try:
        for relative in changed:
            name = PROJECT + '/' + relative
            path = target(root, name)
            if not matches(path, originals[relative]):
                raise ValueError('source changed during finite migration: ' + relative)
            replace(path, finals[relative], originals[relative]['identity'], installed, name)
        for relative, original in originals.items():
            if relative not in changed and not matches(target(root, PROJECT + '/' + relative), original):
                raise ValueError('unchanged production source raced with migration: ' + relative)
        if state(root, source) != 'final':
            raise ValueError('complete typed SDK26 source vector required')
    except BaseException as error:
        failures = []
        for relative in reversed(changed):
            try:
                name = PROJECT + '/' + relative
                path = target(root, name)
                if matches(path, originals[relative]):
                    continue
                if (name not in installed or not path.exists() or identity(path) != installed[name] or
                        path.read_bytes() != finals[relative]):
                    raise ValueError('unknown concurrent source preserved: ' + relative)
                replace(path, originals[relative]['bytes'], originals[relative]['identity'], {}, name)
            except BaseException as rollback_error:
                failures.append(str(rollback_error))
        if failures:
            raise RuntimeError('owned migration rollback incomplete: ' + '; '.join(failures)) from error
        if state(root, source) != epoch:
            raise RuntimeError('full prior source state changed; foreign bytes preserved') from error
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-final', action='store_true')
    parser.add_argument('--migrate', action='store_true', help='only complete legacy72/d4 -> typed final, or final no-op')
    args = parser.parse_args()
    if args.require_final and args.migrate:
        raise ValueError('verification may not migrate')
    root, source = args.source_root.resolve(), manifest()
    value = {'projects': {PARENT: PARENT_HEAD}, 'files': {
        PROJECT + '/' + p: [None, h] for p, h in source['files'].items()}}
    marker = root / '.ohos-qemu-patches'
    if marker.is_symlink():
        raise ValueError('linked source lock directory refused')
    marker.mkdir(exist_ok=True)
    fd = os.open(marker / (digest(str(HERE).encode()) + '.lock'),
                 os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        heads(root, value)
        current = state(root, source)
        if args.require_final:
            if current != 'final':
                raise ValueError('complete new final required; verification never migrates')
        elif current in ('legacy72', 'd4', 'b091'):
            migrate(root, source, current)
        elif current == 'absent':
            if args.migrate:
                raise ValueError('standalone migration requires complete legacy72/d4 or final')
            apply(root, HERE, value)
        if state(root, source) != 'final':
            raise ValueError('complete new final source vector required')
    print('Complete SDK26 caption source prepared; compilation/QEMU acceptance pending')


if __name__ == '__main__':
    main()
