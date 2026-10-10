#!/usr/bin/env python3
"""Compile real taskpool manager/worker TUs for three ABIs with a VFS candidate.

Source/output mounts remain read-only. Not linking, guest testing or closure.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/commonlibrary/ets_utils/thread_info_snapshot'
PREFIX = 'commonlibrary/ets_utils/js_concurrent_module/taskpool/'
PRODUCTS = {'arm64_virt': 'aarch64-linux-ohos', 'armv7a_virt': 'arm-linux-ohos',
            'x86_64_virt': 'x86_64-linux-ohos'}


def digest(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def run(args):
    source = args.source_root.resolve()
    if not os.statvfs(source).f_flag & os.ST_RDONLY or not os.statvfs(source / 'out').f_flag & os.ST_RDONLY:
        raise ValueError('both source and product outputs must be read-only')
    args.output.mkdir(parents=True, exist_ok=False)
    spec = importlib.util.spec_from_file_location('thread_info_baseline', COMPONENT / 'verify_source.py')
    baseline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(baseline)
    if baseline.validate(source):
        raise ValueError('isolated candidate requires original source')
    paths = [Path(baseline.PROJECT) / item[0] for item in baseline.FILES]
    before = {str(path): digest(source / path) for path in paths}
    report = dict(status='fail', scope='six_real_translation_units_NOT_link_or_runtime',
                  closed=[], first_artifact_behavior_gate_passed=False, commands=[], original_sha256=before)
    try:
        with tempfile.TemporaryDirectory(prefix='taskpool-thread-info-tu-') as directory:
            staged = Path(directory)
            for path in paths:
                (staged / path).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source / path, staged / path)
            for attempt in (1, 2):
                with (args.output / ('apply-' + str(attempt) + '.log')).open('x') as log:
                    subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(staged)],
                                   stdout=log, stderr=subprocess.STDOUT, check=True)
            baseline.validate(staged, require_patched=True)
            report['candidate_sha256'] = {str(path): digest(staged / path) for path in paths}
            overlay = args.output / 'candidate-vfs.json'
            overlay.write_text(json.dumps({'version': 0, 'roots': [
                {'type': 'file', 'name': str(source / path), 'external-contents': str(staged / path)}
                for path in paths]}, indent=2) + '\n')
            for product, triple in PRODUCTS.items():
                cwd = source / 'out' / product
                for unit in ('task_manager', 'worker'):
                    target = 'obj/' + PREFIX + 'taskpool/' + unit + '.o'
                    query = subprocess.run([str(source / 'prebuilts/build-tools/linux-x86/bin/ninja'),
                        '-w', 'dupbuild=warn', '-C', str(cwd), '-t', 'commands', '-s', target],
                        capture_output=True, text=True, check=True)
                    name = product + '-' + unit
                    (args.output / (name + '-query.log')).write_text(query.stdout + query.stderr)
                    argv = shlex.split(query.stdout.splitlines()[-1])
                    if Path(argv[0]).name == 'ccache':
                        argv.pop(0)
                    if (Path(argv[0]).name != 'clang++' or '--target=' + triple not in argv or
                            any(x in argv for x in ('&&', ';', '|')) or
                            any(argv.count(x) != 1 for x in ('-c', '-o', '-MF')) or
                            (cwd / argv[argv.index('-c') + 1]).resolve() != source / (PREFIX + unit + '.cpp')):
                        raise ValueError('unexpected actual product command: ' + name)
                    actual = argv[:]
                    argv[1:1] = ['-ivfsoverlay', str(overlay)]
                    obj, deps = args.output / (name + '.o'), args.output / (name + '.d')
                    argv[argv.index('-o') + 1] = str(obj)
                    argv[argv.index('-MF') + 1] = str(deps)
                    log = args.output / (name + '-compile.log')
                    with log.open('x') as stream:
                        result = subprocess.run(argv, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT,
                                                env=dict(os.environ, CCACHE_DISABLE='1'))
                    row = dict(product=product, unit=unit, original_argv=actual, candidate_argv=argv,
                               exit_code=result.returncode, log_sha256=digest(log))
                    report['commands'].append(row)
                    if result.returncode:
                        raise ValueError('actual full TU compilation failed: ' + name)
                    if str(staged / (PREFIX + 'worker.h')) not in deps.read_text():
                        raise ValueError('candidate header was not consumed: ' + name)
                    row.update(object_sha256=digest(obj), dependencies_sha256=digest(deps))
            if before != {str(path): digest(source / path) for path in paths}:
                raise ValueError('read-only source changed during compile')
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
