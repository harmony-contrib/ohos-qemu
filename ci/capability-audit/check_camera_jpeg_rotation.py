#!/usr/bin/env python3
"""Real Camera CPP compilation and libjpeg 3.1 rotation in an owned scratch.

The completed matching Camera GN trees provide read-only command/header inputs.
No source volume, prior scratch evidence, product output or guest is modified.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess

REPO = Path(__file__).resolve().parents[2]
COMPONENT = REPO / 'patches/common/drivers/peripheral/camera/jpeg_rotation'
RELATIVE = 'camera/vdi_base/usb_camera/pipeline_core/src/node/codec_node.cpp'
TARGET = 'obj/drivers/peripheral/camera/vdi_base/usb_camera/pipeline_core/src/node/usb_camera_pipeline_core/codec_node.o'
REVISION = '69094b77aa2200160207b1b06b3c0b586ae2157c'
SEEDS = (
    ('arm64_virt', '/tmp/camera-full-gn-arm64-06', 'aarch64-unknown-linux-ohos'),
    ('armv7a_virt', '/tmp/camera-full-gn-armv7a-07', 'thumbv7-unknown-linux-ohos'),
    ('x86_64_virt', '/tmp/camera-full-gn-x64-07', 'x86_64-unknown-linux-ohos'),
)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def function_body(source):
    text = source.decode()
    start = text.index('static void RotJpegImg(')
    end = text.index('\nRetCode CodecNode::ConfigJpegOrientation', start)
    return text[start:end]


def candidate_command(command, source, output):
    """Change only the source, object and depfile of one actual Ninja command."""
    if any(token in command for token in ('&&', ';', '|', '>', '<')):
        raise ValueError('unexpected shell operation in genuine Camera command')
    command = list(command)
    for flag, value in (('-c', source), ('-o', output), ('-MF', str(output) + '.d')):
        if command.count(flag) != 1:
            raise ValueError('genuine Camera command must have one ' + flag)
        command[command.index(flag) + 1] = str(value)
    return command


def completed_evidence(seed, product):
    records = {}
    for path in sorted(seed.glob('camera-component-*-evidence.json'), reverse=True):
        data = json.loads(path.read_text())
        reference = path
        correction = None
        if data.get('scope') == 'corrected_TLS_validator_for_referenced_actual_build_NOT_new_build_or_guest_acceptance':
            if data.get('validation_exit_code') != 0:
                continue
            correction = data
            reference = Path(data['referenced_build_evidence'])
            if reference.parent != seed or sha(reference) != data['referenced_build_evidence_sha256']:
                raise ValueError('corrected Camera evidence does not match its actual build')
            data = json.loads(reference.read_text())
        if data.get('product') != product or data.get('scratch_source') != str(seed):
            continue
        if any(data.get(key) != 0 for key in ('gn_exit_code', 'link_exit_code',
                                            'installer_repeat_exit_code', 'repeat_link_exit_code')):
            continue
        if data.get('validation_exit_code') != 0 and correction is None:
            continue
        for item in data['artifacts']:
            if sha(Path(item['path'])) != item['sha256']:
                raise ValueError('completed Camera artifact differs from actual build evidence')
        records[str(reference)] = sha(reference)
        if correction is not None:
            records[str(path)] = sha(path)
        return records
    if not records:
        raise ValueError('matching completed actual Camera GN/link evidence required for ' + product)
    return records


def run(command, cwd, log, environment=None):
    with log.open('x') as stream:
        stream.write(json.dumps({'argv': list(map(str, command)), 'cwd': str(cwd)}) + '\n')
        stream.flush()
        result = subprocess.run(list(map(str, command)), cwd=cwd, env=environment,
                                stdout=stream, stderr=subprocess.STDOUT)
    return {'command': list(map(str, command)), 'cwd': str(cwd), 'exit_code': result.returncode,
            'log': str(log), 'log_sha256': sha(log)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--work', type=Path, required=True)
    args = parser.parse_args()
    root = args.source_root.resolve()
    for path in (root, root / 'out', REPO):
        if not os.statvfs(path).f_flag & os.ST_RDONLY:
            raise ValueError('production source, product out and repository must be read-only')
    work = args.work.absolute()
    if work.is_symlink() or work.parent != Path('/tmp') or not work.name.startswith('camera-jpeg-'):
        raise ValueError('exclusive /tmp/camera-jpeg-* work directory required')
    work.mkdir(exist_ok=True)
    if any(work.iterdir()):
        raise ValueError('work must be empty; preserve prior evidence')
    evidence = {'scope': 'actual_three_ABI_Camera_CPP_and_host_libjpeg_rotation_NOT_packaged_guest_acceptance',
                'started_utc': datetime.now(timezone.utc).isoformat(),
                'source_root': str(root), 'work': str(work),
                'production_source_out_and_repo_readonly': True,
                'first_package_behavior_gate_passed': False,
                'build_dependency_changed': False, 'commands': [], 'cross_compilation': []}
    environment = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    try:
        peripheral = root / 'drivers/peripheral'
        revision = subprocess.check_output(['git', '-C', str(peripheral), 'rev-parse', 'HEAD'], text=True).strip()
        if revision != REVISION:
            raise ValueError('requires pinned Camera peripheral ' + REVISION)
        original = subprocess.check_output(['git', '-C', str(peripheral), 'show', 'HEAD:' + RELATIVE])
        if (peripheral / RELATIVE).read_bytes() != original:
            raise ValueError('production Camera JPEG source differs from pinned original')
        staged = work / 'source'
        copied = staged / 'drivers/peripheral'
        source = copied / RELATIVE
        source.parent.mkdir(parents=True)
        source.write_bytes(original)
        gitdir = subprocess.check_output(['git', '-C', str(peripheral), 'rev-parse', '--absolute-git-dir'],
                                         text=True).strip()
        (copied / '.git').write_text('gitdir: ' + gitdir + '\n')
        evidence['peripheral_revision'] = revision
        evidence['original_source_sha256'] = hashlib.sha256(original).hexdigest()
        evidence['component_payload_sha256'] = {
            str(path.relative_to(REPO)): sha(path) for path in sorted(COMPONENT.iterdir()) if path.is_file()}
        for iteration in (1, 2):
            result = run(['bash', COMPONENT / 'apply.sh', '--source-root', staged], work,
                         work / f'apply-{iteration}.log', environment)
            evidence['commands'].append(result)
            if result['exit_code']:
                raise ValueError('component apply or replay failed')
        evidence['candidate_source_sha256'] = sha(source)
        # Rebuild the genuine fixed dependency with upstream host CMake config.
        # Its installer publishes headers, so give it an exclusively owned copy.
        jpeg_source = staged / 'third_party/libjpeg-turbo'
        shutil.copytree(root / 'third_party/libjpeg-turbo', jpeg_source, symlinks=True)
        jpeg_gitdir = subprocess.check_output(['git', '-C', str(root / 'third_party/libjpeg-turbo'),
                                              'rev-parse', '--absolute-git-dir'], text=True).strip()
        if (jpeg_source / '.git').is_symlink():
            (jpeg_source / '.git').unlink()
        (jpeg_source / '.git').write_text('gitdir: ' + jpeg_gitdir + '\n')
        jpeg_component = REPO / 'patches/common/third_party/libjpeg-turbo/release_3_1_0'
        for iteration in (1, 2):
            result = run(['bash', jpeg_component / 'apply.sh', '--source-root', staged], work,
                         work / f'jpeg-apply-{iteration}.log', environment)
            evidence['commands'].append(result)
            if result['exit_code']:
                raise ValueError('fixed real libjpeg component apply failed')
        generated = work / 'jpeg-generated'
        generated.mkdir()
        result = run(['python3', jpeg_source / 'install.py', '--source-dir', jpeg_source,
                      '--gen-dir', generated], work, work / 'jpeg-install.log', environment)
        evidence['commands'].append(result)
        if result['exit_code']:
            raise ValueError('fixed genuine libjpeg installer failed')
        tree = generated / 'libjpeg-turbo-3.1.0'
        retained = work / 'retained-ohos-config'
        retained.mkdir()
        for name in ('jconfig.h', 'jconfigint.h'):
            (tree / 'src' / name).rename(retained / name)
        native = work / 'jpeg-native-build'
        for label, command in (
            ('configure', ['cmake', '-S', tree, '-B', native, '-DWITH_SIMD=OFF',
                           '-DENABLE_SHARED=ON', '-DENABLE_STATIC=OFF', '-DWITH_JAVA=OFF']),
            ('build', ['cmake', '--build', native, '--target', 'jpeg', '--parallel', '2']),
        ):
            result = run(command, work, work / f'jpeg-host-{label}.log', environment)
            evidence['commands'].append(result)
            if result['exit_code']:
                raise ValueError('genuine libjpeg host ' + label + ' failed')
        evidence['jpeg_dependency_evidence'] = {
            'archive_sha256': sha(jpeg_source / 'libjpeg-turbo-3.1.0.tar.gz'),
            'component_payload_sha256': {str(path.relative_to(REPO)): sha(path)
                                       for path in sorted(jpeg_component.iterdir()) if path.is_file()},
            'configuration': 'actual upstream CMake host JPEG target; not OHOS GN or all TurboJPEG tests',
            'library_sha256': sha(native / 'libjpeg.so'),
            'transupp_sha256': sha(tree / 'src/transupp.c')}
        compiler = shutil.which('c++')
        cc = shutil.which('cc')
        if not compiler or not cc:
            raise ValueError('real host C/C++ compilers required')
        instrumentation = ['-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-g']
        transupp = work / 'transupp.o'
        result = run([cc, '-c', tree / 'src/transupp.c', '-I', native, '-I', tree / 'src',
                      *instrumentation, '-o', transupp], work, work / 'host-transupp.log', environment)
        evidence['commands'].append(result)
        if result['exit_code']:
            raise ValueError('real transupp host compilation failed')
        for label, implementation in (('original', original), ('candidate', source.read_bytes())):
            host = work / label
            host.mkdir()
            (host / 'rotation_under_test.inc').write_text(function_body(implementation))
            executable = host / 'rotation-test'
            command = [compiler, '-std=c++17', REPO / 'ci/capability-audit/probes/camera_jpeg_rotation_host.cpp',
                       '-I', host, '-I', native, '-I', tree / 'src', *instrumentation,
                       transupp, native / 'libjpeg.so', '-Wl,-rpath,' + str(native),
                       *['-Wl,--wrap=' + symbol for symbol in ('jpeg_CreateCompress', 'jpeg_CreateDecompress',
                          'jpeg_destroy_compress', 'jpeg_destroy_decompress', 'jpeg_mem_dest')], '-o', executable]
            result = run(command, work, work / f'{label}-host-compile.log', environment)
            evidence['commands'].append(result)
            if result['exit_code']:
                raise ValueError(label + ' host regression compile failed')
            runtime_environment = dict(environment, ASAN_OPTIONS='detect_leaks=1:halt_on_error=1',
                                       UBSAN_OPTIONS='halt_on_error=1')
            result = run([executable, *(['rejection-only'] if label == 'original' else [])], work,
                         work / f'{label}-host-test.log', runtime_environment)
            evidence['commands'].append(result)
            if label == 'original':
                if result['exit_code'] == 0 or 'JPEG objects leaked on transform exit' not in Path(result['log']).read_text():
                    raise ValueError('original source did not reproduce workspace object leak')
                evidence['original_rejection_leak_reproduced'] = True
            elif result['exit_code']:
                raise ValueError('candidate runtime regression failed')
            else:
                evidence['real_host_rotation_marker_boundary_and_cleanup_regression_passed'] = True
        ninja = root / 'prebuilts/build-tools/linux-x86/bin/ninja'
        llvm_dis = root / 'prebuilts/clang/ohos/linux-x86_64/llvm/bin/llvm-dis'
        for product, seed_name, expected_triple in SEEDS:
            seed = Path(seed_name)
            output = seed / 'out' / product
            prior_evidence = completed_evidence(seed, product)
            seed_inputs = {str(path): sha(path) for path in (
                output / 'args.gn', output / 'build.ninja',
                output / 'gen/third_party/libjpeg-turbo/libjpeg-turbo-3.1.0/src/transupp.h',
                seed / 'drivers/peripheral' / RELATIVE)}
            export = [str(ninja), '-w', 'dupbuild=warn', '-C', str(output), '-t', 'commands', '-s', TARGET]
            exported = subprocess.run(export, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            lines = [line for line in exported.stdout.splitlines() if line.strip()]
            if len(lines) != 1:
                raise ValueError('Ninja must export exactly one genuine Camera CPP compile command')
            actual = shlex.split(lines[0])
            if actual[actual.index('-c') + 1] != '../../drivers/peripheral/' + RELATIVE:
                raise ValueError('exported command does not compile actual Camera codec_node.cpp')
            directory = work / product
            directory.mkdir()
            obj = directory / 'codec_node.o'
            command = candidate_command(actual, source, obj)
            result = run(command, output, directory / 'compile.log', environment)
            evidence['commands'].append(result)
            if result['exit_code']:
                raise ValueError(product + ' real Camera CPP compile failed')
            # GN uses split thin-LTO bitcode with multiple modules. llvm-dis
            # cannot emit these to stdout; write all IR only inside this run.
            ir_base = directory / 'codec.ll'
            result = run([llvm_dis, obj, '-o', ir_base], work, directory / 'inspect.log', environment)
            evidence['commands'].append(result)
            if result['exit_code']:
                raise ValueError(product + ' actual LLVM object inspection failed')
            modules = [path for path in sorted(directory.glob('codec.ll*')) if path.is_file()]
            triples = [re.search(r'^target triple = "([^"]+)"$', path.read_text(), re.MULTILINE)
                       for path in modules]
            if not triples or any(not triple or triple.group(1) != expected_triple for triple in triples):
                raise ValueError(product + ' object does not contain the matching target triple')
            if any(sha(Path(path)) != digest for path, digest in {**prior_evidence, **seed_inputs}.items()):
                raise ValueError('prior Camera graph/source/evidence changed during candidate compile')
            evidence['cross_compilation'].append({'product': product, 'seed_source': str(seed),
                'preserved_completed_evidence_sha256': prior_evidence, 'preserved_seed_input_sha256': seed_inputs,
                'ninja_export_command': export, 'genuine_ninja_command': actual,
                'object': str(obj), 'object_sha256': sha(obj), 'object_bytes': obj.stat().st_size,
                'depfile_sha256': sha(Path(str(obj) + '.d')), 'target_triple': expected_triple,
                'split_LTO_module_sha256': {str(path): sha(path) for path in modules},
                'actual_matching_generated_headers_and_flags': True})
        if sha(source) != evidence['candidate_source_sha256']:
            raise ValueError('candidate changed during validation')
        evidence['validation_status'] = 'passed'
    except Exception as failure:
        evidence['validation_status'] = 'failed'
        evidence['error'] = str(failure)
    evidence['finished_utc'] = datetime.now(timezone.utc).isoformat()
    destination = work / 'evidence.json'
    with destination.open('x') as stream:
        json.dump(evidence, stream, indent=2)
        stream.write('\n')
    print(json.dumps({'status': evidence['validation_status'], 'evidence': str(destination),
                      'evidence_sha256': sha(destination), 'error': evidence.get('error'),
                      'compiled_products': [item['product'] for item in evidence['cross_compilation']]}))
    return 0 if evidence['validation_status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
