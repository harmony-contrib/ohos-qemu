#!/usr/bin/env python3
"""Replay complete current observer Rust dylib compile/link in private output.

Reuse only source-bound successful CXX objects, regenerate the actual bridge,
rebuild its archive, preserve genuine Rust flags/extern/native inputs. This is
not fresh GN, packaging or runtime. The caller schedules all heavy resources;
this script never starts Docker/VM and never writes source/product out.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
MAP = 'docs/capability-audit/parallel/location/round7-communication-build-map.json'
MAP_SHA = '93eb588863e26645b0e3f870e053c4db81bb21d268af138eca4dfe5ae7929860'
API_MAP = 'docs/capability-audit/parallel/location/round8-registry-api-link-map.json'
API_MAP_SHA = '486604443c997e9e1b273ecfc97d531ef34ba05214993327238e223f0321dcf9'
COMPONENT = 'patches/common/base/telephony/state_registry/communication_state'
RUST_DIR = 'base/telephony/state_registry/frameworks/ets/ani/observer/src'
CONSUMER = RUST_DIR + '/cxx/observer_ani.cpp'
API_DIR = 'base/telephony/state_registry/frameworks/native/observer/src'
NATIVE_ROLES = {'registry_observer': (API_DIR + '/telephony_observer.cpp', 'telephony_observer__tel_state_registry_api'),
                'registry_proxy': (API_DIR + '/telephony_observer_proxy.cpp', 'telephony_observer_proxy__tel_state_registry_api')}
GN_FILES = ('base/telephony/state_registry/frameworks/js/napi/BUILD.gn',
            'base/telephony/state_registry/frameworks/ets/ani/observer/BUILD.gn')
SDK_GN = 'base/security/access_token/interfaces/innerkits/accesstoken/BUILD.gn'
SDK_GN_SHA = '860a2beecac0bf10dc41fd793d4b3fdf5665171e1a48d006e9fdbb80cad1f440'
SDK_NINJA = 'out/arm64_virt/obj/base/security/access_token/interfaces/innerkits/accesstoken/libaccesstoken_sdk.ninja'
SDK_NINJA_SHA = '9c602b094efbcc80bb901153c72458af56d7d375d231b172bb5a068328b76a90'
SDK_LIB = 'security/access_token/libaccesstoken_sdk.z.so'
SCOPE = 'complete_current_Rust_dylib_compile_link_source_bound_CXX_private_registry_API_existing_other_dependencies_NOT_fresh_GN_package_runtime'


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def regular(path, root=None):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), 'owned regular input required: ' + str(path))
    if root is not None:
        require(path.resolve().is_relative_to(Path(root).resolve()), 'input escapes checkpoint: ' + str(path))
        relative = path.absolute().relative_to(Path(root).absolute())
        require(not any((Path(root) / Path(*relative.parts[:n])).is_symlink()
                        for n in range(1, len(relative.parts) + 1)), 'symlink in checkpoint input path')
    return path


def checked(path, checksum):
    require(sha(path) == checksum, 'input SHA256 differs: ' + str(path))
    return Path(path)


def read_json(path):
    return json.loads(regular(path).read_text())


def expected_argv(data, role):
    if role != 'wrapper':
        source = CONSUMER if role == 'consumer' else NATIVE_ROLES[role][0]
        row = next(x for x in data['translation_units'] if x['source_project_relative_path'] == source)
        return row['variants'][0]['compile_command']['argv'][1:]
    return data['rust_and_cxxbridge']['wrapper_compilation']['command']['argv'][1:]


def passed_object(report, unit):
    rows = [row for row in report.get('objects', []) if row.get('product') == 'arm64_virt' and row.get('unit') == unit]
    require(len(rows) == 1 and rows[0].get('status') == 'pass' and rows[0].get('exit_code') == 0,
            'selected current object did not pass: ' + unit)
    return rows[0]


def validate_object(path, row, checkpoint):
    checked(regular(path, checkpoint), row['object_sha256'])
    with path.open('rb') as stream:
        head = stream.read(64)
    if head.startswith(b'BC\xc0\xde'):
        require(row.get('llvm_modules'), 'bitcode lacks full-module verification')
        for module in row['llvm_modules']:
            require(module['target_triple'] in ('target triple = "aarch64-linux-ohos"',
                    'target triple = "aarch64-unknown-linux-ohos"'), 'non-product LLVM module')
            require(Path(module['file']).name == module['file'], 'unexpected module path')
            checked(regular(checkpoint / module['file'], checkpoint), module['sha256'])
    else:
        require(head[:6] == b'\x7fELF\x02\x01' and int.from_bytes(head[18:20], 'little') == 183,
                'actual AArch64 ELF/LLVM object required')


def public_exports(root, manifest, checkpoint):
    for name in GN_FILES:
        path = checked(regular(checkpoint / 'candidate' / name, checkpoint), manifest['states']['final'][name])
        require('"access_token:libaccesstoken_sdk"' in path.read_text(), 'current SDK GN dependency missing')
    text = checked(root / SDK_GN, SDK_GN_SHA).read_text()
    block = re.search(r'config\("accesstoken"\)\s*\{([^}]+)\}', text)
    require(block and 'include_dirs = [ "include" ]' in block.group(1), 'fixed SDK public config changed')
    require('":accesstoken"' in text[text.index('ohos_shared_library("libaccesstoken_sdk")'):], 'SDK config not public')
    return ['-I', str(root / Path(SDK_GN).parent / 'include')]


def validate_checkpoint(evidence_path, role, root, data, manifest):
    """A failed surrounding batch may supply a separately passed bound object.

    Preserve that batch result. Consumer needs current GN; an old wrapper-only
    checkpoint may predate just the two GN additions, with identical code bytes.
    """
    evidence_path = regular(evidence_path)
    checkpoint = evidence_path.parent.resolve()
    report = read_json(evidence_path)
    require(role in ('consumer', 'wrapper', *NATIVE_ROLES), 'unknown CXX input role')
    require(report.get('group') == 'communication_state', 'communication checkpoint required')
    require(report.get('first_artifact_behavior_gate_passed') is False, 'checkpoint must retain runtime non-proof')
    require(all(report.get(key) is True for key in ('source_inputs_unchanged', 'recipe_inputs_unchanged',
            'candidate_inputs_unchanged', 'generated_inputs_unchanged')), 'checkpoint input checks did not finish')
    require(report.get('source_revisions') == data['fixed_project_HEADs'], 'checkpoint project HEADs differ')
    require(report.get('source_revision') == manifest['projects']['base/telephony/state_registry'], 'registry HEAD differs')
    candidates = report.get('candidate_sha256', {})
    required = set(manifest['files']) - (set(GN_FILES) if role != 'consumer' else set())
    require(required <= set(candidates) <= set(manifest['files']), 'candidate coverage differs')
    matched = [state for state, values in manifest['states'].items()
               if candidates == {name: values[name] for name in candidates}]
    require(matched, 'unknown/mixed whole-component checkpoint state')
    for name, checksum in candidates.items():
        checked(regular(checkpoint / 'candidate' / name, checkpoint), checksum)
    maps = [value for name, value in report.get('recipe_sha256', {}).items() if name.endswith('/' + MAP)]
    require(maps == [MAP_SHA], 'checkpoint complete-TU map differs')
    unit = ('observer_ani__observer_ani_cxx' if role == 'consumer' else 'generated_wrapper') if role not in NATIVE_ROLES else NATIVE_ROLES[role][1]
    row = passed_object(report, unit)
    require(row.get('original_argv') == expected_argv(data, role), 'original product command differs')
    argv = row['executed_argv']
    require(all(argv.count(flag) == 1 for flag in ('-c', '-o', '-MF', '-iquote', '-ivfsoverlay')), 'ambiguous CXX command binding')
    old_obj = PurePosixPath(argv[argv.index('-o') + 1])
    require(old_obj.is_absolute() and old_obj.name == 'arm64_virt-' + unit + '.o', 'CXX output identity differs')
    old_root = old_obj.parent
    original_source = CONSUMER if role == 'consumer' else NATIVE_ROLES.get(role, ('', ''))[0]
    bound_source = RUST_DIR + '/wrapper.rs' if role == 'wrapper' else original_source
    require(candidates[bound_source] == manifest['states']['final'][bound_source], 'stale complete selected source')
    source = '/ohos/' + original_source if role != 'wrapper' else '/ohos/out/arm64_virt/gen/' + RUST_DIR + '/wrapper.rs.cc'
    suffix = 'candidate/' + original_source if role != 'wrapper' else 'generated-communication/wrapper.rs.cc'
    require(argv[argv.index('-c') + 1] == str(old_root / suffix), 'object not bound to complete current source')
    require(argv[argv.index('-MF') + 1] == str(old_root / ('arm64_virt-' + unit + '.d')), 'depfile output differs')
    require(argv[argv.index('-ivfsoverlay') + 1] == str(old_root / 'headers.json'), 'unexpected VFS overlay')
    require(argv[argv.index('-iquote') + 1] == str(PurePosixPath(source).parent), 'original quote include differs')
    expected = expected_argv(data, role)[:]
    for flag in ('-c', '-o', '-MF'):
        expected[expected.index(flag) + 1] = argv[argv.index(flag) + 1]
    additions = public_exports(root, manifest, checkpoint) if role == 'consumer' else []
    expected += additions + ['-iquote', str(PurePosixPath(source).parent), '-ivfsoverlay', str(old_root / 'headers.json')]
    require(argv == expected, 'CXX flags changed beyond declared SDK/source/output/overlay')
    if additions:
        proof = row.get('diagnostic_public_export');proofs = proof if isinstance(proof, list) else [proof]
        require(any(p and p.get('build_file') == SDK_GN and p.get('build_file_sha256') == SDK_GN_SHA and
                    p.get('public_config') == 'accesstoken' for p in proofs), 'actual SDK public export proof missing')
    dep = checked(regular(checkpoint / ('arm64_virt-' + unit + '.d'), checkpoint), row['dependency_sha256'])
    dep_text = dep.read_text()
    require(str(old_root / suffix) in dep_text, 'depfile does not consume current complete source')
    obsolete = [name for name, checksum in candidates.items()
                if checksum != manifest['states']['final'][name] and name in dep_text]
    require(not obsolete, 'selected object consumed obsolete owned input: ' + ', '.join(obsolete))
    validate_object(checkpoint / old_obj.name, row, checkpoint)
    aux = report.get('actual_auxiliary_generation', {})
    for key, name in [('generator_sha256', 'out/arm64_virt/clang_x64/thirdparty/rust_cxx/cxxbridge'),
                      ('driver_sha256', 'build/templates/rust/rust_cxxbridge.py')]:
        require(aux.get(key) == data['frozen_other_inputs'][name]['sha256'], 'CXX generator proof differs')
        checked(root / name, aux[key])
    require(aux.get('input_sha256') == manifest['states']['final'][RUST_DIR + '/wrapper.rs'], 'stale bridge source')
    require(aux.get('command') == ['/usr/bin/env', str(root / 'build/templates/rust/rust_cxxbridge.py'),
            '--cxxbridge', str(root / 'out/arm64_virt/clang_x64/thirdparty/rust_cxx/cxxbridge'),
            '--cc', str(old_root / 'generated-communication/wrapper.rs.cc'),
            '--header', str(old_root / 'generated-communication/wrapper.rs.h'), '--',
            str(old_root / 'candidate' / RUST_DIR / 'wrapper.rs')], 'generator command not bound to current source')
    outputs = aux.get('outputs_sha256', {})
    require(set(outputs) == {str(old_root / ('generated-communication/wrapper.rs.' + ext)) for ext in ('h', 'cc')}, 'complete generated pair required')
    for name, checksum in outputs.items():
        checked(regular(checkpoint / 'generated-communication' / PurePosixPath(name).name, checkpoint), checksum)
    overlay = read_json(checkpoint / 'headers.json')
    hpp = '/ohos/out/arm64_virt/gen/' + RUST_DIR + '/wrapper.rs.h'
    entries = [entry for entry in overlay.get('roots', []) if entry.get('name') == hpp]
    require(len(entries) == 1 and entries[0].get('external-contents') == str(old_root / 'generated-communication/wrapper.rs.h'), 'actual generated header overlay missing')
    return {'role': role, 'checkpoint': checkpoint, 'evidence': evidence_path, 'evidence_sha256': sha(evidence_path),
            'parent_batch_status': report.get('status'), 'full_batch_pass_claimed': False, 'unit': unit,
            'parent_coverage': report.get('coverage'),
            'known_component_states': matched, 'obsolete_consumed_owned_files': obsolete,
            'object': checkpoint / old_obj.name, 'object_sha256': row['object_sha256'],
            'CXX_outputs': {PurePosixPath(n).name: h for n, h in outputs.items()}, 'candidate_checksums': candidates}


def replace_option(argv, flag, value):
    require(argv.count(flag) == 1, 'one option required: ' + flag)
    argv[argv.index(flag) + 1] = str(value)


def dependency_inputs(cwd, argv, rsp):
    tokens = argv + rsp.split();files, directories = set(), set()
    for index, token in enumerate(tokens):
        if token == '--extern': files.add(tokens[index + 1].split('=', 1)[1])
        elif token.startswith('-Clink-arg='):
            value = token.split('=', 1)[1]
            if not value.startswith('-') and value.endswith(('.a', '.so', '.rlib')): files.add(value)
        elif token.startswith('-Ldependency='): directories.add(token.split('=', 1)[1])
    inventory, missing, searches = {}, [], {}
    for name in sorted(files):
        path = Path(name) if Path(name).is_absolute() else cwd / name
        if not path.is_file(): missing.append(str(path));continue
        inventory[str(path)] = {'sha256': sha(path), 'kind': 'explicit_extern_or_native'}
    for name in sorted(directories):
        directory = Path(name) if Path(name).is_absolute() else cwd / name
        searches[str(directory)] = {'exists': directory.is_dir(), 'artifact_files': []}
        if directory.is_dir():
            for path in sorted(directory.iterdir()):
                if path.is_file() and path.name.endswith(('.so', '.a', '.rlib', '.rmeta')):
                    checksum = sha(path);inventory.setdefault(str(path), {'sha256': checksum, 'kind': 'Rust_dependency_search_input'})
                    searches[str(directory)]['artifact_files'].append({'file': path.name, 'sha256': checksum})
    return inventory, searches, missing


def sysroot_inputs(root):
    """Record the real target Rust standard library and implicit linker inputs."""
    directories = [root / 'prebuilts/rustc/linux-x86_64/current/lib/rustlib/aarch64-unknown-linux-ohos/lib',
                   root / 'out/arm64_virt/obj/third_party/musl/usr/lib/aarch64-linux-ohos',
                   root / 'prebuilts/clang/ohos/linux-x86_64/libcxx-ndk/lib/aarch64-linux-ohos/c++']
    result = {}
    for directory in directories:
        require(directory.is_dir(), 'real implicit link search directory missing: ' + str(directory))
        rows = [path for path in sorted(directory.iterdir())
                if path.is_file() and path.name.endswith(('.rlib', '.rmeta', '.so', '.a', '.o'))]
        require(rows, 'empty real implicit link search directory: ' + str(directory))
        for path in rows: result[str(path)] = {'sha256': sha(path), 'kind': 'target_std_or_implicit_link_input'}
    return result


def resource_flags(argv, output, jobs):
    changes = []
    for index, value in enumerate(argv):
        if value.startswith('-Wl,--thinlto-jobs='):
            target = '-Wl,--thinlto-jobs=' + str(jobs)
            changes.append({'from': value, 'to': target, 'reason': 'bounded resource parallelism'});argv[index] = target
        if value.startswith('-Wl,--thinlto-cache-dir='):
            target = '-Wl,--thinlto-cache-dir=' + str(output / 'thinlto-cache')
            changes.append({'from': value, 'to': target, 'reason': 'private cache'});argv[index] = target
    return changes


def registry_plan(root, output, inputs, jobs):
    data = read_json(checked(REPO / API_MAP, API_MAP_SHA))
    checked(root / data['ninja'], data['ninja_sha256'])
    # Stream to the known rule and stop at its end, never load the 96.8 MB graph.
    rule, actual = None, {}
    with (root / 'out/arm64_virt/toolchain.ninja').open() as stream:
        for line in stream:
            if line.startswith('rule '):
                if rule == 'solink': break
                rule = line[5:].strip()
            elif rule == 'solink' and line.startswith('  ') and '=' in line:
                key, value = line.strip().split('=', 1);actual[key.strip()] = value.strip()
    require(actual == data['rule'], 'actual full solink rule changed')
    for name, checksum in data['tool_inputs_sha256'].items(): checked(root / name, checksum)
    argv = data['original_argv'][:];argv[1] = str(root / 'build/toolchain/gcc_solink_wrapper.py')
    paths = {'output': output / 'registry-api/libtel_state_registry_api.z.so',
             'unstripped': output / 'registry-api/unstripped/libtel_state_registry_api.z.so',
             'rsp': output / 'registry-api/api.rsp'}
    for index, value in enumerate(argv):
        if value.startswith('--sofile='): argv[index] = '--sofile=' + str(paths['unstripped'])
        if value.startswith('--output='): argv[index] = '--output=' + str(paths['output'])
        if value.startswith('--clang-base-dir='): argv[index] = '--clang-base-dir=' + str(root / 'prebuilts/clang/ohos')
        if value.startswith('@'): argv[index] = '@' + str(paths['rsp'])
    replace_option(argv, '-o', paths['unstripped']);changes = resource_flags(argv, output / 'registry-api', jobs)
    rsp = data['original_rsp'];replacements = {}
    for row in inputs:
        role = row['role'];source = NATIVE_ROLES[role][0]
        variant = next(x for x in read_json(REPO / MAP)['translation_units'] if x['source_project_relative_path'] == source)['variants'][0]
        old = variant['object_target'];require(rsp.split().count(old) == 1, 'one exact native API object required')
        target = output / 'objects' / (role + '.o');rsp = rsp.replace(old, str(target));replacements[old] = target
    inventory = {}
    for name, frozen in data['explicit_inputs'].items():
        if name not in replacements:
            path = root / 'out/arm64_virt' / name;checked(path, frozen['sha256'])
            inventory[str(path)] = {'sha256': sha(path), 'kind': 'unchanged_full_API_product_input'}
    for token in argv + rsp.split():
        name = None
        if token.endswith(('.o', '.a', '.so')) and not token.startswith('-'): name = token
        elif token.startswith('-Wl,--version-script='): name = token.split('=', 1)[1]
        if name and name not in {str(p) for p in paths.values()} and name not in {str(p) for p in replacements.values()}:
            path = Path(name) if Path(name).is_absolute() else root / 'out/arm64_virt' / name
            inventory[str(path)] = {'sha256': sha(path), 'kind': 'actual_API_link_input'}
    return {'map_sha256': API_MAP_SHA, 'original_argv': data['original_argv'], 'executed_argv': argv,
            'original_rsp': data['original_rsp'], 'rsp': rsp, 'paths': paths, 'resource_overrides': changes,
            'replaced_objects': replacements, 'unchanged_link_inputs': inventory,
            'tool_inputs_sha256': data['tool_inputs_sha256'],
            'scope': 'full_original_solink_two_current_source_bound_observer_objects_two_existing_product_objects'}


def rust_plan(root, output, data, archive, registry_library, jobs):
    original = data['rust_and_cxxbridge']['product_Rust']['command'];argv = original['argv'][:]
    driver = root / 'build/toolchain/rustc_wrapper.py'
    checked(driver, data['frozen_other_inputs']['build/toolchain/rustc_wrapper.py']['sha256']);argv[1] = str(driver)
    paths = {'depfile': output / 'observer.so.d', 'rsp': output / 'observer.rsp',
             'output': output / 'libtelephony_observer_ani.so', 'unstripped-file': output / 'unstripped/libtelephony_observer_ani.so'}
    changes = resource_flags(argv, output, jobs)
    for index, value in enumerate(argv):
        for key, target in paths.items():
            if value.startswith('--' + key + '='): argv[index] = '--' + key + '=' + str(target)
        if value.startswith('--clang-base-dir='): argv[index] = '--clang-base-dir=' + str(root / 'prebuilts/clang/ohos')
        if value.startswith('--emit=dep-info='): argv[index] = '--emit=dep-info=' + str(paths['depfile']) + ',link'
        if value.startswith('OUT_DIR='): argv[index] = 'OUT_DIR=' + str(output / 'rust-out')
    entry = '../../' + RUST_DIR + '/lib.rs';require(argv.count(entry) == 1, 'one complete Rust lib.rs entry required')
    argv[argv.index(entry)] = str(output / 'rust-source/lib.rs');replace_option(argv, '-o', paths['unstripped-file'])
    require(argv[argv.index('--crate-type') + 1] == 'dylib' and '--target=aarch64-unknown-linux-ohos' in argv, 'real product Rust dylib target required')
    rsp = original['rspfile_content'];old_archive = data['rust_and_cxxbridge']['cxx_static_archive']['outputs'][0]
    needle = '-Clink-arg=' + old_archive;require(rsp.count(needle) == 1, 'one exact old CXX archive required')
    rsp = rsp.replace(needle, '-Clink-arg=' + str(archive))
    old_api = '-Clink-arg=telephony/state_registry/libtel_state_registry_api.z.so'
    require(rsp.split().count(old_api) == 1, 'one exact native registry API input required')
    rsp = rsp.replace(old_api, '-Clink-arg=' + str(registry_library))
    # Follow the real newly declared GN SDK target, not an invented -l name.
    outputs = []
    with checked(root / SDK_NINJA, SDK_NINJA_SHA).open() as stream:
        for line in stream:
            if line.startswith('build ') and ': solink ' in line: outputs += line[6:].split(': ', 1)[0].split()
    require(SDK_LIB in outputs, 'actual SDK product solink target differs')
    sdk = root / 'out/arm64_virt' / SDK_LIB;rsp += ' -Clink-arg=' + str(sdk)
    return {'original_argv': original['argv'], 'executed_argv': argv, 'rsp_before': original['rspfile_content'],
            'rsp_before_wrapper': rsp, 'paths': paths, 'resource_overrides': changes,
            'declared_new_native_dependency': {'GN_targets': list(GN_FILES), 'external_dep': 'access_token:libaccesstoken_sdk',
                'provider_GN_sha256': SDK_GN_SHA, 'actual_ninja': SDK_NINJA, 'actual_ninja_sha256': SDK_NINJA_SHA,
                'library': str(sdk), 'fresh_GN_dependency_selection_tested': False}}


def serializable(value):
    if isinstance(value, Path): return str(value)
    if isinstance(value, dict): return {k: serializable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)): return [serializable(v) for v in value]
    return value


def execute(argv, cwd, output, name, report, timeout=900):
    row = {'name': name, 'argv': [str(x) for x in argv], 'cwd': str(cwd), 'log': str(output / (name + '.log'))}
    report['commands'].append(row)
    (output / 'evidence.json').write_text(json.dumps(serializable(report), indent=2) + '\n')
    with (output / (name + '.log')).open('xb') as log:
        result = subprocess.run(row['argv'], cwd=cwd, env={**os.environ, 'LC_ALL': 'C', 'LC_CTYPE': 'C', 'LANG': 'C',
            'PYTHONDONTWRITEBYTECODE': '1'}, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
    row['exit_code'] = result.returncode;row['log_sha256'] = sha(output / (name + '.log'))
    require(result.returncode == 0, 'real command failed: ' + name + '; complete log retained')


def run(args):
    root, output = args.source_root.resolve(), args.output.resolve()
    require(not output.exists() and not output.is_relative_to(root), 'fresh independent output required')
    require(all(os.statvfs(p).f_flag & os.ST_RDONLY for p in [root, root / 'out']), 'source/out must be read-only')
    require(str(root) == '/ohos', 'checkpoint source binding requires canonical /ohos mount')
    data = read_json(checked(REPO / MAP, MAP_SHA));manifest = read_json(REPO / COMPONENT / 'source_states.json')
    for project, revision in data['fixed_project_HEADs'].items():
        actual = subprocess.check_output(['git', '-C', str(root / project), 'rev-parse', 'HEAD'], text=True).strip()
        require(actual == revision, 'fixed project HEAD differs: ' + project)
    for path in (args.consumer_evidence, args.wrapper_evidence or args.consumer_evidence, args.registry_api_evidence,
                 args.registry_observer_evidence or args.registry_api_evidence):
        checkpoint = path.resolve().parent
        require(not output.is_relative_to(checkpoint) and not checkpoint.is_relative_to(output), 'output/checkpoint overlap')
    output.mkdir(parents=True)
    report = {'status': 'fail', 'scope': SCOPE, 'fresh_GN_tested': False, 'runtime_tested': False,
              'first_artifact_behavior_gate_passed': False, 'closed_requirements': 0, 'commands': [],
              'script_sha256': sha(Path(__file__)), 'build_map_sha256': MAP_SHA,
              'communication_manifest_sha256': sha(REPO / COMPONENT / 'source_states.json')}
    try:
        consumer = validate_checkpoint(args.consumer_evidence.resolve(), 'consumer', root, data, manifest)
        wrapper = validate_checkpoint((args.wrapper_evidence or args.consumer_evidence).resolve(), 'wrapper', root, data, manifest)
        native = [validate_checkpoint((args.registry_observer_evidence or args.registry_api_evidence).resolve(),
                                      'registry_observer', root, data, manifest),
                  validate_checkpoint(args.registry_api_evidence.resolve(), 'registry_proxy', root, data, manifest)]
        require(consumer['CXX_outputs'] == wrapper['CXX_outputs'], 'objects consumed different generated bridges')
        report['selected_CXX_inputs'] = [consumer, wrapper]
        report['selected_native_API_inputs'] = native
        for name in ('rust-source', 'generated', 'objects', 'unstripped', 'rust-out'): (output / name).mkdir()
        inputs = {}
        for item in data['rust_and_cxxbridge']['product_Rust']['complete_module_inputs']:
            name = item['path'];origin = consumer['checkpoint'] / 'candidate' / name if item['modified_by_component'] else root / name
            checked(regular(origin), item['logical_patched_sha256']);target = output / 'rust-source' / Path(name).name
            shutil.copyfile(origin, target);inputs[name] = {'origin': origin, 'private_input': target, 'sha256': sha(target)}
        report['complete_current_Rust_inputs'] = inputs
        api = registry_plan(root, output, native, args.lto_jobs)
        archive = output / 'libobserver_ani_cxx.a';plan = rust_plan(root, output, data, archive, api['paths']['output'], args.lto_jobs)
        inventory, searches, missing = dependency_inputs(root / 'out/arm64_virt', plan['executed_argv'], plan['rsp_before_wrapper'])
        inventory.update(sysroot_inputs(root))
        inventory.update(api['unchanged_link_inputs'])
        missing = [path for path in missing if path not in (str(archive), str(api['paths']['output']))]
        report.update(Rust_plan=plan, dependency_inputs=inventory, dependency_search_directories=searches, missing_dependencies=missing)
        report['native_API_plan'] = api
        require(not missing, 'real Rust/native dependencies missing; no substitute: ' + ', '.join(missing))
        tools = ['prebuilts/clang/ohos/linux-x86_64/llvm/bin/' + x for x in ('llvm-ar', 'llvm-nm', 'clang++', 'llvm-strip')]
        tools += ['prebuilts/rustc/linux-x86_64/current/bin/' + x for x in ('rustc', 'clippy-driver')]
        tools += ['build/toolchain/rustc_wrapper.py', 'build/toolchain/rust_strip.py', 'build/templates/rust/rust_cxxbridge.py',
                  'out/arm64_virt/clang_x64/thirdparty/rust_cxx/cxxbridge']
        report['tool_inputs_sha256'] = {name: sha(root / name) for name in tools}
        report['tool_inputs_sha256'].update(api['tool_inputs_sha256'])
        if args.plan_only:
            report.update(status='preflight_pass', Rust_compile_link_executed=False);return True
        execute(['/usr/bin/env', str(root / 'build/templates/rust/rust_cxxbridge.py'), '--cxxbridge',
            str(root / 'out/arm64_virt/clang_x64/thirdparty/rust_cxx/cxxbridge'), '--cc', str(output / 'generated/wrapper.rs.cc'),
            '--header', str(output / 'generated/wrapper.rs.h'), '--', str(output / 'rust-source/wrapper.rs')],
            root / 'out/arm64_virt', output, 'cxxbridge-regenerate', report, 120)
        generated = {name: sha(output / 'generated' / name) for name in ('wrapper.rs.h', 'wrapper.rs.cc')}
        require(generated == consumer['CXX_outputs'], 'new bridge differs from actual compiled object inputs')
        report['regenerated_current_CXX_sha256'] = generated
        objects = []
        for row in (consumer, wrapper):
            target = output / 'objects' / (row['role'] + '.o');shutil.copyfile(row['object'], target)
            checked(target, row['object_sha256']);objects.append(target)
        execute([str(root / 'prebuilts/clang/ohos/linux-x86_64/llvm/bin/llvm-ar'), '-r', '-c', '-s', '-D', str(archive),
            *map(str, objects)], root / 'out/arm64_virt', output, 'current-CXX-archive', report)
        report['private_CXX_archive'] = {'path': archive, 'sha256': sha(archive), 'source_bound_members': objects}
        for row in native:
            target = output / 'objects' / (row['role'] + '.o');shutil.copyfile(row['object'], target);checked(target, row['object_sha256'])
        api['paths']['unstripped'].parent.mkdir(parents=True)
        api['paths']['rsp'].write_text(api['rsp'])
        execute(api['executed_argv'], root / 'out/arm64_virt', output, 'complete-native-registry-API', report, 900)
        report['private_native_API_artifacts'] = {key: {'path': path, 'sha256': sha(path), 'size_bytes': path.stat().st_size}
                                                for key, path in api['paths'].items()}
        plan['paths']['rsp'].write_text(plan['rsp_before_wrapper'])
        execute(plan['executed_argv'], root / 'out/arm64_virt', output, 'complete-Rust-dylib', report, 1800)
        dep = plan['paths']['depfile'].read_text()
        require(all(str(row['private_input']) in dep or str(row['private_input']).replace(' ', '\\ ') in dep
                    for row in inputs.values()), 'depfile does not consume all six full current Rust modules')
        for key in ('output', 'unstripped-file'):
            with plan['paths'][key].open('rb') as stream: head = stream.read(64)
            require(head[:6] == b'\x7fELF\x02\x01' and int.from_bytes(head[16:18], 'little') == 3 and
                    int.from_bytes(head[18:20], 'little') == 183, 'linked AArch64 shared ELF required')
        execute([str(root / 'prebuilts/clang/ohos/linux-x86_64/llvm/bin/llvm-nm'), '--defined-only',
            str(plan['paths']['unstripped-file'])], root / 'out/arm64_virt', output, 'Rust-defined-symbols', report, 120)
        with (output / 'Rust-defined-symbols.log').open() as stream:
            require(any('on_communication_state_updated' in line for line in stream), 'linked current callback absent')
        require(all(sha(Path(path)) == row['sha256'] for path, row in inventory.items()), 'existing Rust/native inputs changed')
        require(all(sha(row['private_input']) == row['sha256'] and sha(row['origin']) == row['sha256'] for row in inputs.values()), 'Rust source changed')
        require(all(sha(row['evidence']) == row['evidence_sha256'] and sha(row['object']) == row['object_sha256'] for row in (consumer, wrapper, *native)), 'reused checkpoint changed')
        require(all(sha(root / name) == checksum for name, checksum in report['tool_inputs_sha256'].items()), 'compiler/generator input changed')
        require(sha(archive) == report['private_CXX_archive']['sha256'], 'private CXX archive changed')
        require(all(sha(output / 'generated' / name) == checksum for name, checksum in generated.items()), 'generated bridge changed')
        report['artifacts'] = {key: {'path': path, 'sha256': sha(path), 'size_bytes': path.stat().st_size} for key, path in plan['paths'].items()}
        report.update(status='pass', Rust_compile_link_executed=True, all_six_sources_consumed=True);return True
    except Exception as error:
        report['error'] = type(error).__name__ + ': ' + str(error);return False
    finally:
        if 'plan' in locals() and plan['paths']['depfile'].is_file() and 'inputs' in locals():
            dep = plan['paths']['depfile'].read_text()
            report['all_six_sources_consumed'] = all(str(row['private_input']) in dep or
                str(row['private_input']).replace(' ', '\\ ') in dep for row in inputs.values())
        if 'inventory' in locals():
            report['recorded_dependency_inputs_unchanged'] = all(sha(Path(path)) == row['sha256'] for path, row in inventory.items())
        (output / 'evidence.json').write_text(json.dumps(serializable(report), indent=2) + '\n')
        print(json.dumps({'status': report['status'], 'scope': SCOPE, 'evidence': str(output / 'evidence.json')}))


class ReplayTests(unittest.TestCase):
    """Metadata rejection tests only; these never stand in for a Rust build."""

    def test_failed_wrong_product_or_duplicate_object_rejected(self):
        passed = {'product': 'arm64_virt', 'unit': 'u', 'status': 'pass', 'exit_code': 0}
        self.assertIs(passed_object({'objects': [passed]}, 'u'), passed)
        for rows in ([{**passed, 'status': 'fail'}], [{**passed, 'exit_code': 1}],
                     [{**passed, 'product': 'x86_64_virt'}], [passed, passed]):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                passed_object({'objects': rows}, 'u')

    def test_checkpoint_source_generation_flags_and_consumption(self):
        # Deliberately tiny byte fixtures exercise evidence binding, not any API.
        with tempfile.TemporaryDirectory() as temporary:
            base = Path(temporary);root = base / 'source';checkpoint = base / 'checkpoint';checkpoint.mkdir()
            def write(path, content):
                path.parent.mkdir(parents=True, exist_ok=True);path.write_bytes(content);return sha(path)
            generator = 'out/arm64_virt/clang_x64/thirdparty/rust_cxx/cxxbridge'
            driver = 'build/templates/rust/rust_cxxbridge.py'
            frozen = {name: {'sha256': write(root / name, name.encode())} for name in (generator, driver)}
            name = RUST_DIR + '/wrapper.rs';source_sha = write(checkpoint / 'candidate' / name, b'fixture bridge input')
            manifest = {'projects': {'base/telephony/state_registry': 'fixed'}, 'files': [name],
                        'states': {'final': {name: source_sha}}}
            old = PurePosixPath('/old/private');unit = 'generated_wrapper';basename = 'arm64_virt-' + unit
            original = ['clang++', '-MF', 'obj/wrapper.d', '-flto=thin', '-c', '../../generated/wrapper.rs.cc', '-o', 'obj/wrapper.o']
            argv = original[:]
            for flag, value in [('-MF', old / (basename + '.d')), ('-c', old / 'generated-communication/wrapper.rs.cc'),
                                ('-o', old / (basename + '.o'))]: replace_option(argv, flag, value)
            argv += ['-iquote', '/ohos/out/arm64_virt/gen/' + RUST_DIR, '-ivfsoverlay', str(old / 'headers.json')]
            elf = bytearray(64);elf[:6] = b'\x7fELF\x02\x01';elf[18:20] = (183).to_bytes(2, 'little')
            object_sha = write(checkpoint / (basename + '.o'), elf)
            dep_sha = write(checkpoint / (basename + '.d'), (str(old / 'generated-communication/wrapper.rs.cc') + '\n').encode())
            outputs = {str(old / ('generated-communication/wrapper.rs.' + ext)):
                       write(checkpoint / ('generated-communication/wrapper.rs.' + ext), ext.encode()) for ext in ('h', 'cc')}
            overlay = {'roots': [{'name': '/ohos/out/arm64_virt/gen/' + RUST_DIR + '/wrapper.rs.h',
                                 'external-contents': str(old / 'generated-communication/wrapper.rs.h')}]}
            (checkpoint / 'headers.json').write_text(json.dumps(overlay))
            report = {'group': 'communication_state', 'status': 'fail', 'first_artifact_behavior_gate_passed': False,
                      'source_revisions': {'project': 'fixed'}, 'source_revision': 'fixed', 'candidate_sha256': {name: source_sha},
                      'recipe_sha256': {'/repo/' + MAP: MAP_SHA}, 'objects': [{'product': 'arm64_virt', 'unit': unit,
                      'status': 'pass', 'exit_code': 0, 'original_argv': original, 'executed_argv': argv,
                      'object_sha256': object_sha, 'dependency_sha256': dep_sha}],
                      'actual_auxiliary_generation': {'generator_sha256': frozen[generator]['sha256'],
                      'driver_sha256': frozen[driver]['sha256'], 'input_sha256': source_sha, 'outputs_sha256': outputs,
                      'command': ['/usr/bin/env', str(root / driver), '--cxxbridge', str(root / generator), '--cc',
                      str(old / 'generated-communication/wrapper.rs.cc'), '--header',
                      str(old / 'generated-communication/wrapper.rs.h'), '--', str(old / 'candidate' / name)]}}
            for key in ('source_inputs_unchanged', 'recipe_inputs_unchanged', 'candidate_inputs_unchanged', 'generated_inputs_unchanged'):
                report[key] = True
            data = {'fixed_project_HEADs': report['source_revisions'], 'frozen_other_inputs': frozen,
                    'rust_and_cxxbridge': {'wrapper_compilation': {'command': {'argv': ['ccache', *original]}}}}
            evidence = checkpoint / 'evidence.json'
            def check(value):
                evidence.write_text(json.dumps(value));return validate_checkpoint(evidence, 'wrapper', root, data, manifest)
            result = check(report)
            self.assertEqual(result['parent_batch_status'], 'fail')
            self.assertFalse(result['full_batch_pass_claimed'])
            unused = 'base/telephony/state_registry/services/src/unconsumed.cpp'
            old_unused = write(checkpoint / 'candidate' / unused, b'old unused bytes')
            manifest['files'].append(unused)
            manifest['states']['prefix_2'] = {name: source_sha, unused: old_unused}
            manifest['states']['final'][unused] = hashlib.sha256(b'new unused bytes').hexdigest()
            report['candidate_sha256'][unused] = old_unused
            self.assertEqual(check(report)['known_component_states'], ['prefix_2'])
            depfile = checkpoint / (basename + '.d');original_dep = depfile.read_bytes()
            depfile.write_bytes(original_dep + (str(old / 'candidate' / unused) + '\n').encode())
            report['objects'][0]['dependency_sha256'] = sha(depfile)
            with self.assertRaisesRegex(ValueError, 'obsolete owned input'): check(report)
            depfile.write_bytes(original_dep);report['objects'][0]['dependency_sha256'] = sha(depfile)
            for mutate in ('failed', 'different_source', 'extra_flag', 'wrong_generator_input', 'stale_source', 'unchecked_inputs'):
                broken = json.loads(json.dumps(report))
                if mutate == 'failed': broken['objects'][0]['status'] = 'fail'
                if mutate == 'different_source': broken['objects'][0]['executed_argv'][argv.index('-c') + 1] = '/old/private/stub.cpp'
                if mutate == 'extra_flag': broken['objects'][0]['executed_argv'].append('-DFAKE')
                if mutate == 'wrong_generator_input': broken['actual_auxiliary_generation']['input_sha256'] = '0' * 64
                if mutate == 'stale_source': broken['candidate_sha256'][name] = '0' * 64
                if mutate == 'unchecked_inputs': broken['generated_inputs_unchanged'] = False
                with self.subTest(mutate=mutate), self.assertRaises(ValueError): check(broken)
            (checkpoint / (basename + '.d')).write_text('unrelated source\n')
            with self.assertRaises(ValueError): check(report)

    def test_bitcode_all_modules_and_object_architecture(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary);path = directory / 'object.o';path.write_bytes(b'BC\xc0\xde')
            row = {'object_sha256': sha(path), 'llvm_modules': []}
            with self.assertRaises(ValueError): validate_object(path, row, directory)
            module = directory / 'module.ll';module.write_text('target triple = "aarch64-unknown-linux-ohos"')
            row['llvm_modules'] = [{'file': module.name, 'sha256': sha(module), 'target_triple': module.read_text()}]
            validate_object(path, row, directory)
            module.write_text('tampered second module')
            with self.assertRaises(ValueError): validate_object(path, row, directory)
            path.write_bytes(b'\x7fELF\x02\x01' + bytes(58));row['object_sha256'] = sha(path)
            with self.assertRaises(ValueError): validate_object(path, row, directory)

    def test_symlink_and_escape_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary);real = root / 'real';real.mkdir();(real / 'file').write_text('bytes')
            (root / 'alias').symlink_to(real, target_is_directory=True)
            for name in ('alias/file', '../absent'):
                with self.assertRaises(ValueError): regular(root / name, root)

    def test_dependency_inventory_preserves_and_rejects_missing(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary);(root / 'dep').mkdir()
            for name in ('a.rlib', 'native.so', 'dep/macro.so'): (root / name).write_text(name)
            files, searches, missing = dependency_inputs(root, ['--extern', 'a=a.rlib'],
                '-Ldependency=dep -Clink-arg=native.so -Clink-arg=missing.a')
            self.assertEqual(missing, [str(root / 'missing.a')])
            self.assertEqual(len(files), 3)
            self.assertEqual(len(searches[str(root / 'dep')]['artifact_files']), 1)
            self.assertEqual(files[str(root / 'a.rlib')]['sha256'], sha(root / 'a.rlib'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=Path('/ohos'))
    parser.add_argument('--consumer-evidence', type=Path, help='complete-TU evidence.json with successful current CXX consumer')
    parser.add_argument('--wrapper-evidence', type=Path, help='optional separate successful generated_wrapper evidence.json')
    parser.add_argument('--registry-api-evidence', type=Path, help='complete-TU evidence with successful current native observer and proxy objects')
    parser.add_argument('--registry-observer-evidence', type=Path, help='optional separate successful native TelephonyObserver checkpoint')
    parser.add_argument('--output', type=Path, help='new private output directory, never a source/checkpoint directory')
    parser.add_argument('--lto-jobs', type=int, choices=(1, 2), default=2)
    parser.add_argument('--plan-only', action='store_true', help='validate bindings/dependencies without compilation; never claims Rust pass')
    parser.add_argument('--self-test', action='store_true', help='light metadata rejection tests; no Docker/compiler')
    args = parser.parse_args()
    if args.self_test:
        result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ReplayTests))
        return 0 if result.wasSuccessful() else 1
    if not args.consumer_evidence or not args.registry_api_evidence or not args.output:
        parser.error('--consumer-evidence, --registry-api-evidence and --output are required')
    try: return 0 if run(args) else 1
    except (OSError, ValueError, KeyError) as error:
        print(type(error).__name__ + ': ' + str(error), file=sys.stderr);return 1


if __name__ == '__main__':
    sys.exit(main())
