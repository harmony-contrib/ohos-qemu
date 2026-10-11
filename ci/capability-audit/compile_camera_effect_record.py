#!/usr/bin/env python3
"""Compile the actual camera module initializer for three ABIs via a VFS overlay.

Read-only source/output mounts; no linking, guest execution or closure claim.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile

from compile_taskpool_thread_info import PRODUCTS, digest

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/multimedia/camera_framework/effect_suggestion_record'
RELATIVE = Path('foundation/multimedia/camera_framework/frameworks/js/camera_napi/src/native_module_ohos_camera.cpp')
TARGET = 'obj/foundation/multimedia/camera_framework/frameworks/js/camera_napi/src/camera_napi/native_module_ohos_camera.o'
IDL_RULES = (
    ('camera_service', 'istream_metadata.h', 10),
    ('deferred_processing_service', 'ideferred_photo_processing_session.h', 4),
)


def generate_hdi(source, cwd, output):
    inputs, destination = output / 'inputs', output / 'generated'
    inputs.mkdir()
    destination.mkdir()
    hashes = {}
    for path in sorted((source / 'drivers/interface/camera').rglob('*.idl')):
        relative = path.relative_to(source / 'drivers/interface')
        target = inputs / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        hashes[str(relative)] = digest(path)
        if digest(target) != hashes[str(relative)]:
            raise ValueError('HDI input copy differs')
    commands = []
    for version in ('v1_0', 'v1_1', 'v1_2', 'v1_3', 'v1_4'):
        query = subprocess.run([str(source / 'prebuilts/build-tools/linux-x86/bin/ninja'),
            '-w', 'dupbuild=warn', '-C', str(cwd), '-t', 'commands', '-s',
            'gen/drivers/interface/camera/' + version + '/types.h'], capture_output=True, text=True, check=True)
        (output / (version + '-query.log')).write_text(query.stdout + query.stderr)
        original = shlex.split(query.stdout.splitlines()[-1])
        command = [str(source / token.removeprefix('/openharmony/'))
                   if token.startswith('/openharmony/') else token for token in original]
        if (command[:2] != ['/usr/bin/env', '/usr/bin/env'] or
                Path(command[2]) != cwd / 'clang_x64/ability/idl_tool/idl' or
                command.count('-d') != 1 or command.count('-r') != 1 or
                any(token in command for token in ('&&', ';', '|'))):
            raise ValueError('unexpected HDI generator command')
        if Path(command[command.index('-d') + 1]) != cwd / 'gen/drivers/interface':
            raise ValueError('unexpected HDI output root')
        command[command.index('-d') + 1] = str(destination)
        mapping = command[command.index('-r') + 1]
        if mapping not in ('ohos.hdi:/openharmony/drivers/interface', 'ohos.hdi:' + str(source / 'drivers/interface')):
            raise ValueError('unexpected HDI source mapping')
        command[command.index('-r') + 1] = 'ohos.hdi:' + str(inputs)
        for index, token in enumerate(command):
            if token == '-c':
                path = Path(command[index + 1])
                relative = path.relative_to(source / 'drivers/interface')
                if str(relative) not in hashes:
                    raise ValueError('unrecorded HDI source')
                command[index + 1] = str(inputs / relative)
        with (output / (version + '-generate.log')).open('x') as stream:
            subprocess.run(command, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT, check=True)
        if not (destination / 'camera' / version / 'types.h').is_file():
            raise ValueError('HDI types were not generated')
        commands.append(dict(original_argv=original, argv=command))
    headers = sorted(destination.rglob('*.h'))
    return dict(commands=commands, input_sha256=hashes,
        headers={str(path.relative_to(destination)): digest(path) for path in headers}), [
        {'type': 'file', 'name': str(cwd / 'gen/drivers/interface' / path.relative_to(destination)),
         'external-contents': str(path)} for path in headers]


def generate_headers(source, cwd, output, service, required_header, minimum):
    """Run the product's actual IDL rule with all outputs redirected to scratch."""
    relative = Path('foundation/multimedia/camera_framework/services') / service / 'idls'
    idl_dir = Path('gen') / relative
    query = subprocess.run([str(source / 'prebuilts/build-tools/linux-x86/bin/ninja'),
        '-w', 'dupbuild=warn', '-C', str(cwd), '-t', 'commands', '-s',
        str(idl_dir / required_header)], capture_output=True, text=True, check=True)
    (output / 'idl-query.log').write_text(query.stdout + query.stderr)
    original = shlex.split(query.stdout.splitlines()[-1])
    if (original[:2] != ['/usr/bin/env', '../../build/config/components/idl_tool/idl.py'] or
            any(original.count(flag) != 1 for flag in ('--src-idl', '--dst-path', '--dst-file', '--idl-tool-path')) or
            any(token in original for token in ('&&', ';', '|'))):
        raise ValueError('unexpected product Camera IDL rule')
    command = [','.join(str(source / path.removeprefix('/openharmony/'))
                       if path.startswith('/openharmony/') else path
                       for path in token.split(',')) for token in original]
    destination = output / 'generated'
    source_destination = Path(command[command.index('--dst-path') + 1])
    if source_destination != cwd / idl_dir:
        raise ValueError('unexpected Camera IDL destination')
    files = command[command.index('--dst-file') + 1].split(',')
    if any(Path(path).parent != source_destination for path in files):
        raise ValueError('IDL outputs escape expected camera directory')
    command[command.index('--dst-file') + 1] = ','.join(str(destination / Path(path).name) for path in files)
    command[command.index('--dst-path') + 1] = str(destination)
    # The pinned IDL reader checks W_OK even for input files. Copy original IDL
    # bytes locally, never relax its checks or make production mounts writable.
    inputs = output / 'idl-inputs'
    inputs.mkdir()
    input_directory = source / relative
    input_hashes = {}
    for path in sorted(input_directory.glob('*.idl')):
        target = inputs / path.name
        shutil.copy2(path, target)
        input_hashes[path.name] = digest(path)
        if digest(target) != input_hashes[path.name]:
            raise ValueError('copied IDL input changed')
    original_inputs = command[command.index('--src-idl') + 1].split(',')
    if any(Path(path).parent != input_directory for path in original_inputs):
        raise ValueError('unexpected Camera IDL input directory')
    command[command.index('--src-idl') + 1] = ','.join(str(inputs / Path(path).name) for path in original_inputs)
    with (output / 'idl-generate.log').open('x') as stream:
        subprocess.run(command, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT, check=True)
    headers = sorted(destination.glob('*.h'))
    if not (destination / required_header).is_file() or len(headers) < minimum:
        raise ValueError('actual Camera IDL generation incomplete')
    return dict(original_argv=original, argv=command, input_sha256=input_hashes,
                headers={path.name: digest(path) for path in headers}), [
        {'type': 'file', 'name': str(source_destination / path.name), 'external-contents': str(path)}
        for path in headers]


def run(args):
    source = args.source_root.resolve()
    if not all(os.statvfs(path).f_flag & os.ST_RDONLY for path in (source, source / 'out')):
        raise ValueError('source and product outputs must both be read-only')
    args.output.mkdir(parents=True, exist_ok=False)
    spec = importlib.util.spec_from_file_location('camera_record_baseline', COMPONENT / 'verify_source.py')
    baseline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(baseline)
    if baseline.validate(source):
        raise ValueError('isolated candidate requires the original source')
    original = digest(source / RELATIVE)
    report = dict(status='fail', scope='three_real_translation_units_NOT_link_or_runtime',
                  closed=[], first_artifact_behavior_gate_passed=False, commands=[], original_sha256=original)
    try:
        with tempfile.TemporaryDirectory(prefix='camera-record-tu-') as directory:
            staged = Path(directory)
            (staged / RELATIVE).parent.mkdir(parents=True)
            shutil.copy2(source / RELATIVE, staged / RELATIVE)
            for attempt in (1, 2):
                with (args.output / ('apply-' + str(attempt) + '.log')).open('x') as log:
                    subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(staged)],
                                   stdout=log, stderr=subprocess.STDOUT, check=True)
            baseline.validate(staged, require_patched=True)
            report['candidate_sha256'] = digest(staged / RELATIVE)
            overlay = args.output / 'candidate-vfs.json'
            overlay.write_text(json.dumps({'version': 0, 'roots': [
                {'type': 'file', 'name': str(source / RELATIVE),
                 'external-contents': str(staged / RELATIVE)}]}, indent=2) + '\n')
            for product, triple in PRODUCTS.items():
                cwd = source / 'out' / product
                generated, roots = {}, []
                for service, required_header, minimum in IDL_RULES:
                    generation = args.output / (product + '-' + service + '-idl')
                    generation.mkdir()
                    generated[service], entries = generate_headers(source, cwd, generation, service,
                                                                   required_header, minimum)
                    roots.extend(entries)
                generation = args.output / (product + '-hdi')
                generation.mkdir()
                generated['hdi'], entries = generate_hdi(source, cwd, generation)
                roots.extend(entries)
                overlay.write_text(json.dumps({'version': 0, 'roots': roots + [
                    {'type': 'file', 'name': str(source / RELATIVE),
                     'external-contents': str(staged / RELATIVE)}]}, indent=2) + '\n')
                query = subprocess.run([str(source / 'prebuilts/build-tools/linux-x86/bin/ninja'),
                    '-w', 'dupbuild=warn', '-C', str(cwd), '-t', 'commands', '-s', TARGET],
                    capture_output=True, text=True, check=True)
                (args.output / (product + '-query.log')).write_text(query.stdout + query.stderr)
                argv = shlex.split(query.stdout.splitlines()[-1])
                if Path(argv[0]).name == 'ccache':
                    argv.pop(0)
                if (Path(argv[0]).name != 'clang++' or '--target=' + triple not in argv or
                        any(x in argv for x in ('&&', ';', '|')) or
                        any(argv.count(x) != 1 for x in ('-c', '-o', '-MF')) or
                        (cwd / argv[argv.index('-c') + 1]).resolve() != source / RELATIVE):
                    raise ValueError('unexpected actual product compiler command: ' + product)
                actual = argv[:]
                argv[1:1] = ['-ivfsoverlay', str(overlay)]
                obj, deps = args.output / (product + '.o'), args.output / (product + '.d')
                argv[argv.index('-o') + 1] = str(obj)
                argv[argv.index('-MF') + 1] = str(deps)
                log = args.output / (product + '-compile.log')
                with log.open('x') as stream:
                    result = subprocess.run(argv, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT,
                                            env=dict(os.environ, CCACHE_DISABLE='1'))
                row = dict(product=product, original_argv=actual, candidate_argv=argv,
                           exit_code=result.returncode, log_sha256=digest(log), generated_idl=generated)
                report['commands'].append(row)
                if result.returncode:
                    raise ValueError('actual camera initializer compilation failed: ' + product)
                if str(staged / RELATIVE) not in deps.read_text():
                    raise ValueError('candidate source was not consumed: ' + product)
                row.update(object_sha256=digest(obj), dependencies_sha256=digest(deps))
            if digest(source / RELATIVE) != original:
                raise ValueError('original source changed during compile')
            report['status'] = 'pass'
    except Exception as error:
        report['error'] = str(error)
    (args.output / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    return int(report['status'] != 'pass')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    raise SystemExit(run(parser.parse_args()))

