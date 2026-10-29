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
EDITS_SHA = 'aa619e7a6a2ac20dd5793eeb78e138b6fb8d5b208eded5515c5a54c950660c0a'
PREVIOUS_EDITS_SHA = 'c050aec95959eb8178c247cf76450f12947d28488bce5455860c025cd726e38e'
PREVIOUS_C22_EDITS_SHA = '71a7f202b149d9530c22ebb2815b722237f8a65bcc15cf93220f1683b7659c17'
PREVIOUS_INPUT_SOURCES_SHA = '61b6851f5bc8a50f174a4ec6328df1313e35ac13714edbc97f2f26345d0f8da4'
PREVIOUS_GN_SHA = 'e16ba5fb2a35de048f42027b4c243434b9a79941ee8c62f49a2e2124de293251'
PREVIOUS_GN_INPUT = 'legacy/CPU-BUILD-previous.gn'
CPU_GN_INPUT = 'sources/drivers/peripheral/intelligent_voice/passthrough/cpu/BUILD.gn'
PREVIOUS_C23_INPUT_SOURCES_SHA = '206c5f355b1c8e5cb4d59a2708751213107db9cf7c83afb2ce8d5ab15489698d'
PREVIOUS_C23_GN_SHA = '4fadb8d00e75ab0b66afb94f41241ceeb8e41a96ac0c40e470310987239c8491'
PREVIOUS_C23_GN_INPUT = 'legacy/CPU-BUILD-c23.gn'
PREVIOUS_C24_INPUT_SOURCES_SHA = 'e89983ab042d69cdcf414d02aec2633421f65a6c9d4e7635c8dc74308ae2b001'
PREVIOUS_C24_CPP_SHA = '624ae661f8d2639d9b50d7a55c1a19405343137769b738f3cf4775650d74dba6'
PREVIOUS_C24_CPP_INPUT = 'legacy/CPU-VOICE-c24.cpp'
PREVIOUS_C28_INPUT_SOURCES_SHA = 'd9446437d2aa1caba73e137d35de074b0cf2174634343fe8d7beee1b6a70ec49'
PREVIOUS_C28_SPATIAL_GN_SHA = 'c27190ee7936d5beca5fb2ebdeff546aa610c12a198d336ba4cd296d2144b4e2'
PREVIOUS_C28_SPATIAL_GN_INPUT = 'legacy/SPATIAL-BUILD-c28.gn'
PREVIOUS_C29_INPUT_SOURCES_SHA = '880e2f187602b06263d4fa501d01c95078cc6c2ba2af49b90125befeb67253e8'
PREVIOUS_C29_SPATIAL_GN_SHA = '00622e510ca1d6b6a33654a1f04dbd31946c72a73db7ae159b6ad89b5cbecbff'
PREVIOUS_C29_SPATIAL_GN_INPUT = 'legacy/SPATIAL-BUILD-c29.gn'
PREVIOUS_C29_OPENAL_BUILD_SHA = 'de8b821733113889602392192684d3b9bacc9f08978b40a8eaa0faac296dd2be'
PREVIOUS_C29_OPENAL_BUILD_INPUT = 'legacy/BUILD-OPENAL-c29.py'
PREVIOUS_C30_INPUT_SOURCES_SHA = '3f9edcd7605cdf965561b7d7cfc97fc3dfc40420776b346aa0173c8c995a657b'
PREVIOUS_C30_OPENAL_BUILD_SHA = 'e166505d8d6d3ebce9ff4ab407d44620ceca24efa1b06d220ac44e0371221b81'
PREVIOUS_C30_OPENAL_BUILD_INPUT = 'legacy/BUILD-OPENAL-c30.py'
PREVIOUS_C31_INPUT_SOURCES_SHA = 'a39303c83c21b96e9688a84b02155fdf40b82c7e5f2b8477154b4b3d40d2d02d'
PREVIOUS_C31_OPENAL_BUILD_SHA = 'd574d12b31adf4982d15184155d88f7e89bb4095c321b6b7a522b42539eb6dc1'
PREVIOUS_C31_OPENAL_BUILD_INPUT = 'legacy/BUILD-OPENAL-c31.py'
CPU_CPP = 'drivers/peripheral/intelligent_voice/passthrough/engine/cpu_voice_engine.cpp'
CPU_CPP_INPUT = 'sources/drivers/peripheral/intelligent_voice/passthrough/engine/cpu_voice_engine.cpp'
INPUT_FILES_SHA = '0ba90a98fbb56fb694760f13763d5702e1c0775b9119948ec1868a90ed332c6b'
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


def previous_edits(edits):
    raw = file_raw(HERE / 'PREVIOUS-SOURCE-EDITS.json')
    need(sha(raw) == PREVIOUS_EDITS_SHA, 'fixed previous complete31 source contract changed')
    previous = json.loads(raw)
    need(previous['schema'] == edits['schema'] and len(previous['files']) == 31 and
         [(r['path'], r['before_sha256']) for r in previous['files']] ==
         [(r['path'], r['before_sha256']) for r in edits['files']],
         'previous complete31 must share the exact original before vector')
    return previous


def previous_c22_edits(edits):
    raw = file_raw(HERE / 'PREVIOUS-C22-SOURCE-EDITS.json')
    need(sha(raw) == PREVIOUS_C22_EDITS_SHA, 'fixed retained C22 complete31 source contract changed')
    previous = json.loads(raw)
    need(previous['schema'] == edits['schema'] and len(previous['files']) == 31 and
         [(r['path'], r['before_sha256']) for r in previous['files']] ==
         [(r['path'], r['before_sha256']) for r in edits['files']],
         'retained C22 complete31 must share the exact original before vector')
    return previous


def complete_state(actual, edits):
    if all(actual[r['path']] == r['before_sha256'] for r in edits['files']):
        return 'before'
    if all(actual[r['path']] == r['after_sha256'] for r in edits['files']):
        return 'final'
    previous = previous_edits(edits)
    if all(actual[r['path']] == r['after_sha256'] for r in previous['files']):
        return 'previous_final'
    retained = previous_c22_edits(edits)
    need(all(actual[r['path']] == r['after_sha256'] for r in retained['files']),
         'unknown/mixed M01 vector preserved')
    return 'previous_c22_final'


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
    need(len(result) == 443, 'complete fixed443 product payload map required')
    return result


def legacy_payloads(index, current):
    """Seven exact historical full443 maps; no per-file alternative admission.

    Each complete declaration is authenticated and differs from current only
    at its fixed CPU GN/CPP, spatial GN and OpenAL builder overrides. Unchanged
    binary/model bytes are shared; all six prior declarations stay byte identical.
    The C31 declaration retains the complete previous current443 builder epoch.
    """
    selected = json.loads(file_raw(HERE / 'INPUT-SOURCES.json'))
    gn_name = CPU + 'BUILD.gn'
    spatial_name = SPATIAL + 'BUILD.gn'
    openal_name = SPATIAL + 'build_openal.py'
    need(len(current) == 443 and gn_name in current and CPU_CPP in current and
         spatial_name in current and openal_name in current,
         'complete current443 CPU GN/CPP, spatial GN and OpenAL builder map required')
    need(selected['new_sources'][gn_name]['relative'] == CPU_GN_INPUT and
         selected['new_sources'][CPU_CPP]['relative'] == CPU_CPP_INPUT and
         selected['new_sources'][spatial_name]['relative'] == 'sources/' + spatial_name and
         selected['new_sources'][openal_name]['relative'] == 'sources/' + openal_name,
         'fixed current CPU GN/CPP, spatial GN and OpenAL builder component inputs')
    cpp = (CPU_CPP, CPU_CPP_INPUT, PREVIOUS_C24_CPP_INPUT, PREVIOUS_C24_CPP_SHA)
    spatial = (spatial_name, 'sources/' + spatial_name, PREVIOUS_C28_SPATIAL_GN_INPUT, PREVIOUS_C28_SPATIAL_GN_SHA)
    openal = (openal_name, 'sources/' + openal_name, PREVIOUS_C29_OPENAL_BUILD_INPUT, PREVIOUS_C29_OPENAL_BUILD_SHA)
    spatial_c29 = (spatial_name, 'sources/' + spatial_name, PREVIOUS_C29_SPATIAL_GN_INPUT, PREVIOUS_C29_SPATIAL_GN_SHA)
    openal_c30 = (openal_name, 'sources/' + openal_name, PREVIOUS_C30_OPENAL_BUILD_INPUT, PREVIOUS_C30_OPENAL_BUILD_SHA)
    openal_c31 = (openal_name, 'sources/' + openal_name, PREVIOUS_C31_OPENAL_BUILD_INPUT, PREVIOUS_C31_OPENAL_BUILD_SHA)
    fixed = (
        ('previous', 'PREVIOUS-ASSET-SOURCES.json', PREVIOUS_INPUT_SOURCES_SHA,
         ((gn_name, CPU_GN_INPUT, PREVIOUS_GN_INPUT, PREVIOUS_GN_SHA), cpp, spatial, openal)),
        ('previous_c23', 'PREVIOUS-C23-ASSET-SOURCES.json', PREVIOUS_C23_INPUT_SOURCES_SHA,
         ((gn_name, CPU_GN_INPUT, PREVIOUS_C23_GN_INPUT, PREVIOUS_C23_GN_SHA), cpp, spatial, openal)),
        ('previous_c24', 'PREVIOUS-C24-ASSET-SOURCES.json', PREVIOUS_C24_INPUT_SOURCES_SHA,
         (cpp, spatial, openal)),
        ('previous_c28', 'PREVIOUS-C28-ASSET-SOURCES.json', PREVIOUS_C28_INPUT_SOURCES_SHA,
         (spatial, openal)),
        ('previous_c29', 'PREVIOUS-C29-ASSET-SOURCES.json', PREVIOUS_C29_INPUT_SOURCES_SHA,
         (spatial_c29, openal)),
        ('previous_c30', 'PREVIOUS-C30-ASSET-SOURCES.json', PREVIOUS_C30_INPUT_SOURCES_SHA,
         (openal_c30,)),
        ('previous_c31', 'PREVIOUS-C31-ASSET-SOURCES.json', PREVIOUS_C31_INPUT_SOURCES_SHA,
         (openal_c31,)),
    )
    result = {}
    for epoch, declaration, declaration_sha, overrides in fixed:
        raw = file_raw(HERE / declaration)
        need(sha(raw) == declaration_sha, 'fixed previous complete asset declaration changed: ' + epoch)
        previous = json.loads(raw)
        normalized = dict(selected)
        normalized['new_sources'] = dict(selected['new_sources'])
        mapping = dict(current)
        for logical, relative_input, retained_input, retained_sha in overrides:
            need(logical in previous['new_sources'], 'fixed historical input required: ' + epoch)
            old_row = previous['new_sources'][logical]
            need(old_row['relative'] == relative_input and old_row['sha256'] == retained_sha,
                 'only fixed historical GN/CPP input may differ: ' + epoch)
            normalized['new_sources'][logical] = old_row
            entry = index['files'][retained_input]
            retained_raw = file_raw(source(HERE, retained_input))
            need(entry['sha256'] == retained_sha and len(retained_raw) == entry['bytes'] and
                 sha(retained_raw) == retained_sha, 'complete retained historical bytes required: ' + epoch)
            mapping[logical] = retained_raw
        need(normalized == previous,
             'complete asset declarations differ outside fixed overrides: ' + epoch)
        need(set(mapping) == set(current) and len(mapping) == 443,
             'exact same complete443 payload paths required: ' + epoch)
        result[epoch] = mapping
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


def asset_epoch(root, index, current):
    """Classify one whole443 epoch; never a per-file alternative map."""
    expected = {'current': current, **legacy_payloads(index, current)}
    matches = {epoch: True for epoch in expected}
    seen = 0
    for name in current:
        path = source(root, name)
        if not path.exists():
            matches = {epoch: False for epoch in expected}
            continue
        raw = file_raw(path)
        seen += 1
        for epoch, mapping in expected.items():
            matches[epoch] = matches[epoch] and raw == mapping[name]
    need(seen in (0, 443), 'partial fixed443 asset vector preserved')
    directory = source(root, SPATIAL + 'openal-soft', directory=True)
    if directory.exists():
        actual = {str(p.relative_to(root)) for p in directory.rglob('*') if p.is_file() or p.is_symlink()}
        need(actual == {n for n in current if n.startswith(SPATIAL + 'openal-soft/')},
             'extra/missing original OpenAL source preserved')
    if seen == 0:
        return 'absent'
    selected = [epoch for epoch, matched in matches.items() if matched]
    need(len(selected) == 1, 'unknown/mixed/ambiguous complete443 asset bytes preserved')
    return selected[0]


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


def rewind_plan(root):
    """Prefix-only complete474 transaction plan; no mutation/runtime admission.

    An installed current/previous443 always requires a complete known source31,
    even if no final source marker is seen. A valid interrupted common-before31
    with previous443 migrates here, never through the late forward path.
    """
    root = root_path(root)
    edits, index, projects = metadata()
    component_before = component_identity(index)
    project_heads(root, projects)
    assets = payloads(index)
    epoch = asset_epoch(root, index, assets)
    previous = previous_edits(edits)
    retained = previous_c22_edits(edits)
    actual = vectors(root, edits)
    if epoch == 'absent':
        need(not any(actual[r['path']] == r['after_sha256']
                     for contract in (edits, previous, retained) for r in contract['files']),
             'complete final source31 cannot have absent product assets')
        need(vectors(root, edits) == actual and component_identity(index) == component_before,
             'fresh source/component changed during prefix read')
        project_heads(root, projects)
        return None
    state = complete_state(actual, edits)
    need((state == 'final' and epoch in ('current', 'previous_c28', 'previous_c29', 'previous_c30', 'previous_c31')) or
         (state == 'previous_c22_final' and epoch in ('previous', 'previous_c23', 'previous_c24')) or
         (state == 'previous_final' and epoch == 'previous') or
         (state == 'before' and epoch in ('current', 'previous', 'previous_c23', 'previous_c24', 'previous_c28', 'previous_c29', 'previous_c30', 'previous_c31')),
         'only a fixed complete source31/asset443 prefix endpoint is admitted')
    if state == 'before' and epoch == 'current':
        need(vectors(root, edits) == actual and component_identity(index) == component_before and
             asset_epoch(root, index, assets) == epoch, 'complete prepared prefix changed during read')
        project_heads(root, projects)
        return None
    selected = {'previous_final': previous, 'previous_c22_final': retained}.get(state, edits)
    desired = dict(assets)
    for row in selected['files']:
        name = row['path']
        need(name not in desired, 'fixed source31/payload443 destinations must be disjoint')
        raw = file_raw(source(root, name))
        if state == 'before':
            need(sha(raw) == row['before_sha256'], 'complete common source31 changed during prefix read')
            desired[name] = raw
        else:
            desired[name] = inverse(raw, row)
    need(len(desired) == 474 and vectors(root, edits) == actual and
         component_identity(index) == component_before and asset_epoch(root, index, assets) == epoch,
         'complete source31/asset443 prefix plan changed during read')
    project_heads(root, projects)
    return dict(desired=desired, source_state=state, asset_state=epoch, assets=assets)


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
