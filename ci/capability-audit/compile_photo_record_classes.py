#!/usr/bin/env python3
"""Compile complete patched photo JS using each product's actual ABC rule.

Read-only production source/output mounts. Not guest/runtime evidence.
"""
import argparse
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from compile_always_on_vpn import query
from compile_taskpool_thread_info import PRODUCTS, digest

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/multimedia/media_library/public_record_classes'


def run(args):
    source = args.source_root.resolve()
    if not all(os.statvfs(p).f_flag & os.ST_RDONLY for p in (source, source / 'out')):
        raise ValueError('source and output mounts must be read-only')
    args.output.mkdir(parents=True, exist_ok=False)
    selected = args.product or list(PRODUCTS)
    report = dict(status='fail', scope='actual_selected_product_ABC_rules_NOT_guest', products=selected, closed=[], commands=[],
                  first_artifact_behavior_gate_passed=False)
    try:
        spec = importlib.util.spec_from_file_location('photo_record_baseline', COMPONENT / 'verify_source.py')
        baseline = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(baseline)
        if baseline.validate(source):
            raise ValueError('isolated candidate requires original source')
        relative = Path(baseline.PROJECT) / baseline.FILES[0][0]
        before = digest(source / relative)
        report['original_sha256'] = before
        with tempfile.TemporaryDirectory(prefix='photo-record-abc-') as directory:
            staged = Path(directory)
            (staged / relative).parent.mkdir(parents=True)
            shutil.copy2(source / relative, staged / relative)
            for attempt in (1, 2):
                with (args.output / f'apply-{attempt}.log').open('x') as log:
                    subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(staged)],
                                   stdout=log, stderr=subprocess.STDOUT, check=True)
            baseline.validate(staged, require_patched=True)
            report['candidate_sha256'] = digest(staged / relative)
            for product in selected:
                cwd = source / 'out' / product
                original = query(source, cwd, 'multimedia/media_library/photoaccesshelper.abc',
                                 args.output / (product + '-query.log'))
                argv = [str(source / token.removeprefix('/openharmony/'))
                        if token.startswith('/openharmony/') else token for token in original]
                if (argv[:2] != ['/usr/bin/env', '../../build/scripts/ohos_abc.py'] or len(argv) != 8 or
                        any(argv.count(flag) != 1 for flag in ('--outputs', '--es2abc', '--sources')) or
                        (cwd / argv[argv.index('--sources') + 1]).resolve() != source / relative or
                        Path(argv[argv.index('--es2abc') + 1]) != cwd / 'clang_x64/arkcompiler/ets_frontend' or
                        Path(argv[argv.index('--outputs') + 1]) != cwd / 'multimedia/media_library/photoaccesshelper.abc'):
                    raise ValueError('unexpected product ABC command: ' + product)
                output = args.output / (product + '.abc')
                argv[argv.index('--outputs') + 1] = str(output)
                argv[argv.index('--sources') + 1] = str(staged / relative)
                log = args.output / (product + '-compile.log')
                with log.open('x') as stream:
                    result = subprocess.run(argv, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT)
                row = dict(product=product, original_argv=original, argv=argv,
                           exit_code=result.returncode, log_sha256=digest(log))
                report['commands'].append(row)
                if result.returncode or not output.is_file() or not output.read_bytes().startswith(b'PANDA'):
                    raise ValueError('actual product ABC compilation failed: ' + product)
                row['abc_sha256'] = digest(output)
            if digest(source / relative) != before:
                raise ValueError('production source changed')
            report['status'] = 'pass'
    except Exception as error:
        report['error'] = str(error)
    (args.output / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    return int(report['status'] != 'pass')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--product', choices=tuple(PRODUCTS), action='append',
                        help='Explicit product subset; omitted means all three')
    raise SystemExit(run(parser.parse_args()))
