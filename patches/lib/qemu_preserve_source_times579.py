#!/usr/bin/env python3
"""Keep original mtimes only when serialized preparation restores exact bytes.

This is an incremental-build input operation, never source or QEMU acceptance.
Every ordinary component guard and final preparation step must still run.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import time

PATCHES = Path(__file__).resolve().parents[1]
COMPONENTS = (
    ('common/build/sanitizers/qemu_thin_cfi', 2),
    ('common/foundation/ability/ability_runtime/service_idle_startid', 18),
    ('common/applications/standard/settings_data/accessibility_notification_defaults', 2),
    ('common/foundation/multimedia/av_session/qemu_panel_lifecycle', 3),
    ('common/applications/standard/settings/dnd_selection_ids', 3),
    ('common/applications/standard/calendardata/lifecycle579', 18),
    ('common/foundation/multimedia/audio_framework/playback_capture_consent579', 5),
)


def need(value, message):
    if not value:
        raise ValueError(message)


def finite(name):
    path = PurePosixPath(name)
    need(type(name) is str and not path.is_absolute() and '..' not in path.parts and
         path.as_posix() == name and name not in ('', '.'), 'finite fixed source path required')
    return name


def unaliased(path):
    path = Path(path)
    need(path.is_absolute() and path.resolve() == path and
         not any(part.is_symlink() for part in (path, *path.parents)), 'unaliased absolute path required')
    return path


def regular(path, *, missing=False):
    path = unaliased(path)
    try:
        before = path.stat(follow_symlinks=False)
    except FileNotFoundError:
        if missing:
            return None
        raise
    need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1, 'single regular source required')
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as stream:
        opened = os.fstat(stream.fileno())
        body = stream.read()
        after = os.fstat(stream.fileno())
    named = path.stat(follow_symlinks=False)
    def observed(value):
        return (value.st_dev, value.st_ino, value.st_size, value.st_mtime_ns, value.st_ctime_ns,
                stat.S_IMODE(value.st_mode), value.st_uid, value.st_gid)
    need(observed(before) == observed(opened) == observed(after) == observed(named),
         'source changed while observed')
    return body, named


def reference(path):
    body, _ = regular(path)
    return dict(path=str(path), sha256=hashlib.sha256(body).hexdigest())


def write_new(path, value):
    path = unaliased(path)
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600), 'w') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())


def root_identity(root):
    value = unaliased(root).stat(follow_symlinks=False)
    need(stat.S_ISDIR(value.st_mode), 'actual source directory required')
    return dict(path=str(root), device=value.st_dev, inode=value.st_ino)


def catalog():
    result, projects = {}, {}
    for relative, count in COMPONENTS:
        path = PATCHES / relative / 'source_states.json'
        value = json.loads(regular(path)[0])
        need(type(value['files']) is dict and len(value['files']) == count and
             type(value['projects']) is dict and value['projects'], 'complete fixed component vector required')
        for project, head in value['projects'].items():
            finite(project)
            need(re.fullmatch('[a-f0-9]{40}', head) is not None and
                 projects.get(project, head) == head, 'consistent actual project HEAD required')
            projects[project] = head
        for name, pair in value['files'].items():
            finite(name)
            need(any(name.startswith(project + '/') for project in value['projects']) and
                 type(pair) is list and len(pair) == 2 and
                 all(item is None or re.fullmatch('[a-f0-9]{64}', item) is not None for item in pair),
                 'finite exact source pair required')
        if 'legacy_final' in value:
            need(relative == 'common/foundation/ability/ability_runtime/service_idle_startid' and
                 value.get('schema') == 'settings579-conditional-idle-stop-source-vector/v3' and
                 set(value['legacy_final']) == set(value['files']) and
                 set(value.get('previous_napi_final', {})) == set(value['files']) and
                 all(type(item) is str and re.fullmatch('[a-f0-9]{64}', item) is not None
                     for epoch in ('legacy_final', 'previous_napi_final')
                     for item in value[epoch].values()), 'only complete known ServiceExtension whole vectors')
        result[relative] = (value, reference(path))
    return result, projects


def heads(root, projects):
    for relative, expected in projects.items():
        project = unaliased(root / relative)
        value = subprocess.run(['git', '-C', str(project), 'rev-parse', 'HEAD'],
                               check=False, capture_output=True, text=True)
        need(value.returncode == 0 and value.stdout.strip() == expected, 'actual source project HEAD changed')


def capture(root, snapshot):
    values, projects = catalog()
    heads(root, projects)
    captured_ns = time.time_ns()
    result = dict(schema='qemu579-unchanged-source-time-capture/v1', root=root_identity(root),
                  captured_ns=captured_ns, projects=projects, components={}, files={},
                  scope='incremental build input times only; no source/build/runtime acceptance',
                  first_artifact_behavior_gate_passed=False)
    for relative, (value, source) in values.items():
        rows, observed = {}, {}
        for name in value['files']:
            item = regular(root / name, missing=True)
            observed[name] = None if item is None else hashlib.sha256(item[0]).hexdigest()
            rows[name] = item
        final = {name: pair[1] for name, pair in value['files'].items()}
        legacy = value.get('legacy_final')
        previous = value.get('previous_napi_final')
        known = observed == final or (legacy is not None and observed == legacy) or (previous is not None and observed == previous)
        result['components'][relative] = dict(manifest=source, retained=known,
            state='complete_final_or_known_legacy' if known else 'not_retained_NOT_verified')
        if not known:
            continue
        for name, item in rows.items():
            if item is None:
                continue
            body, value_stat = item
            # Future timestamps cannot establish a valid incremental input age.
            if not 0 < value_stat.st_mtime_ns <= captured_ns:
                continue
            row = dict(sha256=hashlib.sha256(body).hexdigest(), bytes=len(body),
                       mode=stat.S_IMODE(value_stat.st_mode), uid=value_stat.st_uid, gid=value_stat.st_gid,
                       original_mtime_ns=value_stat.st_mtime_ns)
            need(result['files'].get(name, row) == row, 'overlapping source capture changed')
            result['files'][name] = row
    heads(root, projects)
    write_new(snapshot, result)
    print(json.dumps(dict(snapshot=reference(snapshot), retained_files=len(result['files']),
                          first_artifact_behavior_gate_passed=False)))


def restore(root, snapshot):
    raw, original_stat = regular(snapshot)
    need(stat.S_IMODE(original_stat.st_mode) == 0o600 and original_stat.st_uid == os.geteuid(),
         'original preparation-owned capture required')
    value = json.loads(raw)
    values, projects = catalog()
    need(value['schema'] == 'qemu579-unchanged-source-time-capture/v1' and
         value['root'] == root_identity(root) and value['projects'] == projects and
         set(value['components']) == set(values) and value['first_artifact_behavior_gate_passed'] is False,
         'same complete source preparation scope required')
    allowed = set()
    for relative, (component, source) in values.items():
        need(value['components'][relative]['manifest'] == source, 'preparation source manifest changed')
        if value['components'][relative]['retained'] is True:
            allowed.update(component['files'])
    need(set(value['files']) <= allowed, 'capture contains an unowned source path')
    heads(root, projects)
    receipt = dict(schema='qemu579-unchanged-source-time-restore/v1', capture=reference(snapshot),
                   root=value['root'], restored=[], skipped_changed=[],
                   source_validated=False, runtime_validated=False, first_artifact_behavior_gate_passed=False)
    for name, before in value['files'].items():
        finite(name)
        path = root / name
        item = regular(path, missing=True)
        if item is None:
            receipt['skipped_changed'].append(name)
            continue
        body, current = item
        if (hashlib.sha256(body).hexdigest(), len(body), stat.S_IMODE(current.st_mode), current.st_uid, current.st_gid) != (
                before['sha256'], before['bytes'], before['mode'], before['uid'], before['gid']):
            receipt['skipped_changed'].append(name)
            continue
        need(type(before['original_mtime_ns']) is int and 0 < before['original_mtime_ns'] <= value['captured_ns'],
             'original source input timestamp required')
        if current.st_mtime_ns == before['original_mtime_ns']:
            receipt['restored'].append(name)
            continue
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), 'rb') as stream:
            opened = os.fstat(stream.fileno())
            fresh = stream.read()
            after = os.fstat(stream.fileno())
            need((opened.st_dev, opened.st_ino, opened.st_mtime_ns, opened.st_ctime_ns, opened.st_size) ==
                 (current.st_dev, current.st_ino, current.st_mtime_ns, current.st_ctime_ns, current.st_size) ==
                 (after.st_dev, after.st_ino, after.st_mtime_ns, after.st_ctime_ns, after.st_size) and
                 fresh == body, 'source changed before input-time restoration')
            os.utime(stream.fileno(), ns=(after.st_atime_ns, before['original_mtime_ns']))
            changed = os.fstat(stream.fileno())
            named = path.stat(follow_symlinks=False)
            need((changed.st_dev, changed.st_ino) == (named.st_dev, named.st_ino) and
                 changed.st_mtime_ns == named.st_mtime_ns == before['original_mtime_ns'],
                 'source path changed during input-time restoration')
        receipt['restored'].append(name)
    heads(root, projects)
    write_new(Path(str(snapshot) + '.restored.json'), receipt)
    print(json.dumps(dict(restored=len(receipt['restored']), skipped_changed=len(receipt['skipped_changed']),
                          source_validated=False, first_artifact_behavior_gate_passed=False)))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--snapshot', type=Path, required=True)
    parser.add_argument('--action', choices=('capture', 'restore'), required=True)
    args = parser.parse_args()
    root, snapshot = unaliased(args.source_root), unaliased(args.snapshot)
    (capture if args.action == 'capture' else restore)(root, snapshot)


if __name__ == '__main__':
    main()
