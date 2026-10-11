#!/usr/bin/env python3
"""Compile the complete fixed AVC wrapper with three real product commands.

Only exact owned scratch inputs are changed. This is not linking, installing,
encoding/decoding, surface acceptance or a first-artifact behavior gate.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/multimedia/av_codec/avc_eos'
PROJECT = Path('foundation/multimedia/av_codec')
TARGET = 'obj/foundation/multimedia/av_codec/services/engine/codec/video/avcencoder/avc_encoder/avc_encoder.o'
PRODUCTS = {'arm64_virt': 'aarch64-linux-ohos', 'armv7a_virt': 'arm-linux-ohos',
            'x86_64_virt': 'x86_64-linux-ohos'}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(args):
    root = args.source_root.resolve()
    if not os.statvfs(root).f_flag & os.ST_RDONLY:
        raise ValueError('source must be mounted read-only')
    if args.output.exists() or args.output.is_symlink():
        raise ValueError('fresh full-wrapper evidence required')
    spec = importlib.util.spec_from_file_location('avc_wrapper_source', COMPONENT / 'verify_source.py')
    baseline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(baseline)
    baseline.validate(root)
    source = root / PROJECT / baseline.FILE
    original = subprocess.check_output(['git', '-C', str(root / PROJECT), 'show',
                                        baseline.REVISION + ':' + baseline.FILE])
    expected = baseline.repaired_source(original.decode()).encode()
    inputs = [Path(__file__), *sorted(COMPONENT.glob('*.patch')), COMPONENT / 'apply.sh',
              COMPONENT / 'verify_source.py', ROOT / 'patches/lib/apply_component_stack.py', source]
    before = {str(path): sha(path) for path in inputs}
    products = args.product or list(PRODUCTS)
    if len(products) != len(set(products)):
        raise ValueError('duplicate product cannot count as another ABI')
    report = {'status': 'fail', 'scope': 'actual_full_AVC_wrapper_three_product_TU_objects_NOT_link_or_guest',
              'source_head': baseline.REVISION, 'source_original_sha256': hashlib.sha256(original).hexdigest(),
              'source_final_sha256': hashlib.sha256(expected).hexdigest(), 'requested_products': products,
              'all_three_products_checked': set(products) == set(PRODUCTS), 'objects': [],
              'component_inputs_sha256': before, 'first_artifact_behavior_gate_passed': False}
    logs = args.output.with_suffix('.logs')
    logs.mkdir(exist_ok=False)
    try:
        with tempfile.TemporaryDirectory(prefix='exact-avc-wrapper-compile-') as directory:
            staged = Path(directory)
            project = staged / PROJECT
            project.parent.mkdir(parents=True)
            with (logs / 'fixed-source-clone.log').open('x') as stream:
                subprocess.run(['git', 'clone', '--quiet', '--shared', '--no-checkout',
                                str(root / PROJECT), str(project)], stdout=stream, stderr=subprocess.STDOUT, check=True)
                subprocess.run(['git', '-C', str(project), 'checkout', baseline.REVISION, '--', baseline.FILE],
                               stdout=stream, stderr=subprocess.STDOUT, check=True)
            candidate = project / baseline.FILE
            if candidate.read_bytes() != original:
                raise ValueError('owned checkout must contain the exact fixed original')
            # Deliberately stale old markers must not skip either patch.
            markers = staged / '.ohos-qemu-patches'
            markers.mkdir()
            for numbered in COMPONENT.glob('*.patch'):
                (markers / (sha(numbered) + '.applied')).write_text('stale fixture marker\n')
            report['stale_legacy_markers_ignored'] = True
            for attempt in (1, 2):
                with (logs / ('apply-' + str(attempt) + '.log')).open('x') as stream:
                    subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(staged)],
                                   stdout=stream, stderr=subprocess.STDOUT, check=True)
                baseline.validate(staged, require_patched=True)
                if candidate.read_bytes() != expected:
                    raise ValueError('full wrapper differs from exact repair after application')
            for product in products:
                cwd = root / 'out' / product
                if not os.statvfs(cwd).f_flag & os.ST_RDONLY:
                    raise ValueError('product commands must also be mounted read-only')
                queried = subprocess.run([str(root / 'prebuilts/build-tools/linux-x86/bin/ninja'),
                    '-w', 'dupbuild=warn', '-C', str(cwd), '-t', 'commands', '-s', TARGET],
                    text=True, capture_output=True, check=True)
                query_log = logs / (product + '-query.log')
                query_log.write_text(queried.stdout + queried.stderr)
                argv = shlex.split(queried.stdout.splitlines()[-1])
                if Path(argv[0]).name == 'ccache': argv.pop(0)
                if (Path(argv[0]).name != 'clang++' or '--target=' + PRODUCTS[product] not in argv or
                        any(token in argv for token in ('&&', ';', '|')) or argv.count('-c') != 1 or
                        argv.count('-o') != 1 or argv.count('-MF') != 1 or
                        (cwd / argv[argv.index('-c') + 1]).resolve() != source):
                    raise ValueError('unexpected actual AVC product command: ' + product)
                actual = argv.copy()
                argv[argv.index('-c') + 1] = str(candidate)
                object_path, dependency = staged / (product + '.o'), staged / (product + '.d')
                argv[argv.index('-o') + 1], argv[argv.index('-MF') + 1] = str(object_path), str(dependency)
                compile_log = logs / (product + '-compile.log')
                with compile_log.open('x') as stream:
                    subprocess.run(argv, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT, check=True)
                if str(candidate) not in dependency.read_text():
                    raise ValueError('compiler did not consume the actual repaired wrapper')
                report['objects'].append({'product': product, 'triple': PRODUCTS[product],
                    'object_sha256': sha(object_path), 'dependency_sha256': sha(dependency),
                    'query_log': str(query_log), 'query_log_sha256': sha(query_log),
                    'actual_product_command': actual, 'executed_argv': argv,
                    'compile_log': str(compile_log), 'compile_log_sha256': sha(compile_log),
                    'source_sha256': sha(candidate)})
        if {str(path): sha(path) for path in inputs} != before:
            raise ValueError('source or component recipe changed during actual compilation')
        report.update(status='pass', objects_count=len(report['objects']), source_inputs_unchanged=True)
    except Exception as error:
        report['error'] = type(error).__name__ + ': ' + str(error)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--product', choices=PRODUCTS, action='append')
    result = run(parser.parse_args())
    print(json.dumps({name: result.get(name) for name in ('status', 'objects_count', 'error')}))
    raise SystemExit(0 if result['status'] == 'pass' else 1)
