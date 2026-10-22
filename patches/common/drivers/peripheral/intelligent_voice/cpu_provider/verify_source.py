#!/usr/bin/env python3
"""Exact M01 source/asset verifier and read-only preceding-vector projection.

No SDK/compiler/resource operation. A projection is returned only for the
complete 31-file final vector, exact actual project HEADs and complete assets.
"""
from pathlib import Path, PurePosixPath
import argparse
import hashlib
import io
import json
import os
import re
import stat
import sys
import tarfile

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
EDITS_SHA = 'c050aec95959eb8178c247cf76450f12947d28488bce5455860c025cd726e38e'
INPUT_FILES_SHA = 'f7e7c770c62ffcfa8883bb7cd8e6aa2a18eba148b5a61afded1f384e8e4eed71'
PROJECTS_SHA = 'ea9b404805887ae248a1eda69333465d0ce426c342d5f82e14e5b6e7c62a0b41'
CPU = 'drivers/peripheral/intelligent_voice/passthrough/cpu/'
SPATIAL = 'foundation/multimedia/audio_framework/frameworks/native/audioeffect/qemu_spatial/'


def need(value, message):
    if not value:
        raise ValueError(message)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def file_raw(path, limit=64 * 1024 * 1024):
    path = Path(path)
    before = path.lstat()
    need(stat.S_ISREG(before.st_mode) and before.st_size <= limit, 'bounded regular source: ' + str(path))
    raw = path.read_bytes()
    after = path.lstat()
    fields = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
    need(tuple(getattr(before, k) for k in fields) == tuple(getattr(after, k) for k in fields) and
         len(raw) == before.st_size, 'source changed during read: ' + str(path))
    return raw


def relative(name):
    value = PurePosixPath(name)
    need(name and not value.is_absolute() and '..' not in value.parts and str(value) == name, 'fixed relative source path')
    return value


def source(root, name, *, directory=False):
    relative(name)
    path = root / name
    need(not any(p.is_symlink() for p in (path, *path.parents)), 'source path is linked: ' + name)
    need(not path.exists() or (path.is_dir() if directory else path.is_file()), 'regular source destination: ' + name)
    return path


def root_path(root):
    root = Path(root)
    need(root.is_absolute() and root.resolve() == root and root.is_dir() and root != Path('/'), 'actual source root')
    return root


def metadata():
    edits_raw = file_raw(HERE / 'SOURCE-EDITS.json')
    index_raw = file_raw(HERE / 'INPUT-FILES.json')
    projects_raw = file_raw(HERE / 'PROJECTS.json')
    need((sha(edits_raw), sha(index_raw), sha(projects_raw)) ==
         (EDITS_SHA, INPUT_FILES_SHA, PROJECTS_SHA), 'fixed full component manifests changed')
    edits = json.loads(edits_raw)
    index = json.loads(index_raw)
    projects = json.loads(projects_raw)
    need(edits['schema'] == 'fixed-normal-product-whole-guarded-source-edits/v1' and len(edits['files']) == 31 and
         len({r['path'] for r in edits['files']}) == 31 and
         all(not r['path'].startswith('vendor/') for r in edits['files']), 'exact 31 source edits, no board configurations')
    need(projects['schema'] == 'media579-actual-project-head-vector/v1' and len(projects['projects']) == 4 and
         all(re.fullmatch('[a-f0-9]{40}', v) for v in projects['projects'].values()), 'four actual fixed project HEADs required')
    for row in edits['files']:
        relative(row['path'])
        need(row['before_sha256'] != row['after_sha256'] and row['cuts'] and
             any(row['path'].startswith(p + '/') for p in projects['projects']), 'full changed-file source pair')
    need(index['schema'] == 'media579-original-fixed-component-inputs/v1' and index['files'], 'complete fixed normal input index')
    return edits, index, projects


def component_identity(index):
    result = {}
    for name, row in index['files'].items():
        path = source(HERE, name)
        raw = file_raw(path)
        need(len(raw) == row['bytes'] and sha(raw) == row['sha256'], 'fixed component input changed: ' + name)
        result[name] = sha(raw)
    # These exact two nodes cannot hash themselves/the verifier in this index.
    # Both are bound by Root's actual canonical source vector; Onset pins this
    # verifier explicitly. All other code/data/assets have fixed index rows.
    fixed = {'verify_source.py', 'INPUT-FILES.json'}
    actual = {str(p.relative_to(HERE)) for p in HERE.rglob('*') if p.is_file() or p.is_symlink()}
    need(actual == set(index['files']) | fixed, 'unknown or missing component input/code preserved')
    for name in fixed:
        result[name] = sha(file_raw(source(HERE, name)))
    return result


def actual_head(root, project):
    """Read Git metadata only; do not spawn git or silently use upstream HEAD."""
    directory = source(root, project, directory=True)
    need(directory.is_dir(), 'actual project directory required: ' + project)
    marker = directory / '.git'
    if marker.is_symlink() or marker.is_dir():
        gitdir = marker.resolve(strict=True)
    else:
        text = file_raw(marker, 4096).decode().strip()
        need(text.startswith('gitdir: '), 'actual worktree Git marker')
        gitdir = (directory / text[8:]).resolve(strict=True)
    need(gitdir.is_dir() and gitdir.is_relative_to(root), 'actual source-volume Git directory')
    common = gitdir
    if (gitdir / 'commondir').exists():
        common = (gitdir / file_raw(gitdir / 'commondir', 4096).decode().strip()).resolve(strict=True)
        need(common.is_dir() and common.is_relative_to(root), 'actual source-volume common Git directory')
    text = file_raw(gitdir / 'HEAD', 4096).decode().strip()
    for unused in range(8):
        if re.fullmatch('[a-f0-9]{40}', text):
            return text
        need(text.startswith('ref: '), 'unknown Git HEAD grammar')
        name = text[5:]
        relative(name)
        need(name.startswith('refs/') and not any(c.isspace() for c in name), 'fixed named Git ref')
        loose = [p for p in (gitdir / name, common / name) if p.exists()]
        if loose:
            values = {file_raw(p, 4096).decode().strip() for p in loose}
            need(len(values) == 1, 'ambiguous actual Git ref')
            text = next(iter(values))
            continue
        found = []
        for path in dict.fromkeys((gitdir / 'packed-refs', common / 'packed-refs')):
            if not path.exists():
                continue
            for line in file_raw(path, 1024 * 1024).decode().splitlines():
                if line.startswith(('#', '^')) or not line:
                    continue
                words = line.split()
                need(len(words) == 2 and re.fullmatch('[a-f0-9]{40}', words[0]), 'complete actual packed-ref grammar')
                if words[1] == name:
                    found.append(words[0])
        need(found and len(set(found)) == 1, 'actual selected HEAD ref missing/ambiguous')
        return found[0]
    raise ValueError('Git ref cycle/depth exceeded')


def project_heads(root, projects):
    need({p: actual_head(root, p) for p in projects['projects']} == projects['projects'], 'actual project HEAD vector changed')


def vectors(root, edits):
    actual = {}
    for row in edits['files']:
        path = source(root, row['path'])
        actual[row['path']] = sha(file_raw(path)) if path.exists() else None
    return actual


def complete_state(actual, edits):
    if all(actual[r['path']] == r['before_sha256'] for r in edits['files']):
        return 'before'
    need(all(actual[r['path']] == r['after_sha256'] for r in edits['files']), 'unknown/mixed M01 vector preserved')
    return 'final'


def inverse(raw, row):
    need(sha(raw) == row['after_sha256'], 'only the complete final source can be inversely projected')
    text = raw.decode()
    for cut in reversed(row['cuts']):
        need(text.count(cut['after']) == 1, 'unique reviewed inverse source cut')
        text = text.replace(cut['after'], cut['before'], 1)
    before = text.encode()
    need(sha(before) == row['before_sha256'], 'whole inverse does not equal actual reviewed before')
    return before


def payloads(index):
    spec = json.loads(file_raw(HERE / 'INPUT-SOURCES.json'))
    dependencies_raw = file_raw(HERE / 'DEPENDENCIES.json')
    dependencies = json.loads(dependencies_raw)
    result = {}
    def add(name, raw):
        relative(name)
        need(name not in result, 'one fixed product input per logical path')
        result[name] = raw
    def input_raw(row):
        relative(row['relative'])
        need(row['relative'] in index['files'] and index['files'][row['relative']]['sha256'] == row['sha256'], 'fixed normal input declaration')
        raw = file_raw(source(HERE, row['relative']))
        need(sha(raw) == row['sha256'], 'actual licensed input bytes changed')
        return raw
    for name, row in spec['new_sources'].items():
        add(name, input_raw(row))
    for name, row in spec['models'].items():
        add(CPU + 'assets/' + name, input_raw(row))
    library_metadata = []
    for row in dependencies['libraries']:
        name = Path(row['file']['path']).name
        relative_name = 'assets/native/' + row['abi'] + '/' + name
        add(CPU + 'prebuilt/' + row['abi'] + '/' + name,
            input_raw({'relative': relative_name, 'sha256': row['file']['sha256']}))
        library_metadata.append(dict(abi=row['abi'], original_har=row['original_har'], member=row['member'], sha256=row['file']['sha256'], elf=row['elf']))
    for name, row in spec['original_archives'].items():
        add(CPU + 'original/' + name, input_raw(row))
    for name, row in spec['challenge'].items():
        add(CPU + 'challenge/' + name, input_raw(row))
    add(CPU + 'DEPENDENCIES.json', dependencies_raw)
    original = spec['openal']
    archive = input_raw(original)
    with tarfile.open(fileobj=io.BytesIO(archive)) as tree:
        seen = set()
        for member in tree.getmembers():
            logical = '/'.join(member.name.split('/')[1:])
            if not member.isfile():
                need(member.isdir(), 'unknown original OpenAL member type')
                continue
            relative(logical)
            need(logical in original['files'] and logical not in seen, 'exact complete original OpenAL tree')
            raw = tree.extractfile(member).read()
            need(sha(raw) == original['files'][logical]['sha256'], 'original OpenAL source bytes changed')
            seen.add(logical)
            add(SPATIAL + 'openal-soft/' + logical, raw)
        need(seen == set(original['files']), 'complete original OpenAL tree required')
    add(SPATIAL + 'OPENAL-INPUTS.json', (json.dumps(original, indent=2) + '\n').encode())
    actual = dict(schema='normal-qemu-cpu-voice-inputs/v1', models=spec['models'], libraries=library_metadata, arm32_sources=spec['arm32_sources'],
        normal_prebuilt_dependency_not_compile_proof=True, original_upstream_source_archive=dependencies['source_archive'], runtime_pass=False)
    add(CPU + 'assets/INPUTS.json', (json.dumps(actual, indent=2) + '\n').encode())
    return result


def assets_state(root, expected):
    seen = 0
    for name, raw in expected.items():
        path = source(root, name)
        if path.exists():
            need(file_raw(path) == raw, 'different existing product asset preserved: ' + name)
            seen += 1
    need(seen in (0, len(expected)), 'partial fixed new-source/model/prebuilt/OpenAL vector preserved')
    # CMake's source discovery must not admit an extra unpinned OpenAL file.
    directory = source(root, SPATIAL + 'openal-soft', directory=True)
    if directory.exists():
        actual = {str(p.relative_to(root)) for p in directory.rglob('*') if p.is_file() or p.is_symlink()}
        need(actual == {name for name in expected if name.startswith(SPATIAL + 'openal-soft/')}, 'extra/missing original OpenAL source preserved')
    return 'absent' if seen == 0 else 'final'


def require_final(root):
    root = root_path(root)
    edits, index, projects = metadata()
    identity = component_identity(index)
    project_heads(root, projects)
    need(complete_state(vectors(root, edits), edits) == 'final', 'complete final 31-vector required')
    need(assets_state(root, payloads(index)) == 'final', 'complete fixed normal product inputs required')
    need(component_identity(index) == identity, 'component sources changed during verification')
    project_heads(root, projects)
    return edits


def preceding_files(root):
    """No mutation/subprocess. Empty means defer to the ORIGINAL old guards.

    Seeing any exact new-final member requires the entire new final vector,
    actual HEADs and fixed assets. Return all31 actual inverse bytes, including
    config.gni; never a per-file SHA exception or an incomplete projected tuple.
    """
    root = root_path(root)
    edits, index, projects = metadata()
    actual = vectors(root, edits)
    if not any(actual[r['path']] == r['after_sha256'] for r in edits['files']):
        return {}
    require_final(root)
    result = {row['path']: inverse(file_raw(source(root, row['path'])), row) for row in edits['files']}
    need(vectors(root, edits) == actual, 'final source vector changed during read-only projection')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-final', action='store_true')
    args = parser.parse_args()
    require_final(args.source_root)
    print('Complete M01 normal source/actual HEAD/assets verified; runtime remains pending')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
