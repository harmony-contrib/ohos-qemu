#!/usr/bin/env python3
"""Compile the actual image module initializer for three ABIs via a VFS overlay.

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
COMPONENT = ROOT / 'patches/common/foundation/multimedia/image_framework/avis_class_export'
RELATIVE = Path('foundation/multimedia/image_framework/frameworks/kits/js/common/native_module_ohos_image.cpp')
TARGET = 'obj/foundation/multimedia/image_framework/frameworks/kits/js/common/image_napi/native_module_ohos_image.o'


def run(args):
    source = args.source_root.resolve()
    if not all(os.statvfs(path).f_flag & os.ST_RDONLY for path in (source, source / 'out')):
        raise ValueError('source and product outputs must both be read-only')
    args.output.mkdir(parents=True, exist_ok=False)
    spec = importlib.util.spec_from_file_location('avis_baseline', COMPONENT / 'verify_source.py')
    baseline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(baseline)
    if baseline.validate(source):
        raise ValueError('isolated candidate requires the original source')
    original = digest(source / RELATIVE)
    report = dict(status='fail', scope='three_real_translation_units_NOT_link_or_runtime',
                  closed=[], first_artifact_behavior_gate_passed=False, commands=[], original_sha256=original)
    try:
        with tempfile.TemporaryDirectory(prefix='avis-class-export-tu-') as directory:
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
                           exit_code=result.returncode, log_sha256=digest(log))
                report['commands'].append(row)
                if result.returncode:
                    raise ValueError('actual image initializer compilation failed: ' + product)
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
