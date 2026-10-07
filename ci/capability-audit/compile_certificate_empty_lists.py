#!/usr/bin/env python3
"""Compile the exact CertificateManager candidate with three real GN commands.

Only an owned scratch copy is patched. This does not link or replace a system
library, execute a guest, or attest certificate access/cryptographic behavior.
"""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile

SOURCE = Path('base/security/certificate_manager/interfaces/kits/napi/src/cm_napi_common.cpp')
TARGET = 'obj/base/security/certificate_manager/interfaces/kits/napi/src/certmanager/cm_napi_common.o'
HEAD = '57bd41128a07c5289987cf98e04dfc66421029a6'
ORIGINAL_SHA = '1886825f602b6d391fea761abb752490c81289efb9567fc28fb70a9d561ecbfd'
PRODUCTS = {'arm64_virt': 'aarch64-linux-ohos', 'armv7a_virt': 'arm-linux-ohos',
            'x86_64_virt': 'x86_64-linux-ohos'}
COMPONENT = Path(__file__).resolve().parents[2] / 'patches/common/base/security/certificate_manager/empty_lists'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args):
    if args.output.exists() or args.output.is_symlink():
        raise ValueError('fresh certificate compilation evidence path required; preserve existing results')
    root = args.source_root.resolve()
    source = root / SOURCE
    project = root / 'base/security/certificate_manager'
    head = subprocess.check_output(['git', '-C', str(project), 'rev-parse', 'HEAD'], text=True).strip()
    if head != HEAD or digest(source) != ORIGINAL_SHA:
        raise ValueError('expected exact pristine pinned CertificateManager source')
    report = {'status': 'fail', 'scope': 'actual_product_objects_only_NOT_link_guest_or_permissions',
              'source_head': head, 'source_original_sha256': digest(source), 'objects': [],
              'first_artifact_behavior_gate_passed': False}
    patch = COMPONENT / '0001-preserve-empty-certificate-lists-and-free-list-owners.patch'
    report['patch_sha256'] = digest(patch)
    inputs = [Path(__file__).resolve()]
    inputs += [COMPONENT / name for name in (patch.name, 'apply.sh', 'verify_source.py')]
    inputs += [COMPONENT.parents[4] / 'lib' / name for name in
               ('apply_exact_component.py', 'exact_source_states.py')]
    report['component_inputs_sha256'] = {str(path): digest(path) for path in inputs}
    spec = importlib.util.spec_from_file_location('certificate_empty_baseline', COMPONENT / 'verify_source.py')
    baseline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(baseline)
    if baseline.validate(root):
        raise ValueError('expected pristine source for isolated candidate compilation')
    logs = args.output.with_suffix('.logs')
    logs.mkdir(exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='certificate-empty-lists-compile-') as directory:
        staged = Path(directory)
        candidate = staged / SOURCE
        candidate.parent.mkdir(parents=True)
        shutil.copy2(source, candidate)
        command = ['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(staged)]
        for _ in range(2):
            subprocess.run(command, check=True)
        baseline.validate(staged, require_patched=True)
        report['source_final_sha256'] = digest(candidate)
        for product, triple in PRODUCTS.items():
            cwd = root / 'out' / product
            queried = subprocess.run([str(root / 'prebuilts/build-tools/linux-x86/bin/ninja'),
                '-w', 'dupbuild=warn', '-C', str(cwd), '-t', 'commands', TARGET], text=True,
                capture_output=True, check=True)
            query_log = logs / (product + '-query.log')
            query_log.write_text(queried.stdout + queried.stderr)
            argv = shlex.split(queried.stdout.splitlines()[-1])
            if Path(argv[0]).name == 'ccache':
                argv.pop(0)
            if (Path(argv[0]).name != 'clang++' or any(token in argv for token in ('&&', ';', '|')) or
                    '--target=' + triple not in argv or argv.count('-c') != 1 or argv.count('-o') != 1 or
                    (cwd / argv[argv.index('-c') + 1]).resolve() != source):
                raise ValueError('unexpected actual CertificateManager compile command for ' + product)
            original_command = argv[:]
            argv[argv.index('-c') + 1] = str(candidate)
            object_path = staged / (product + '.o')
            dependency_path = staged / (product + '.d')
            argv[argv.index('-o') + 1] = str(object_path)
            argv[argv.index('-MF') + 1] = str(dependency_path)
            compile_log = logs / (product + '-compile.log')
            with compile_log.open('w') as stream:
                subprocess.run(argv, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT, check=True)
            report['objects'].append({'product': product, 'triple': triple,
                'object_sha256': digest(object_path), 'dependency_sha256': digest(dependency_path),
                'queried_command_sha256': hashlib.sha256(json.dumps(original_command).encode()).hexdigest(),
                'query_log': str(query_log), 'query_log_sha256': digest(query_log),
                'compile_log': str(compile_log), 'compile_log_sha256': digest(compile_log),
                'executed_argv': argv, 'source_sha256': digest(candidate)})
    if (digest(source) != ORIGINAL_SHA or digest(patch) != report['patch_sha256'] or
            {str(path): digest(path) for path in inputs} != report['component_inputs_sha256']):
        raise ValueError('read-only source or patch input changed during compilation')
    report.update(status='pass', objects_count=len(report['objects']), source_inputs_unchanged=True)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    report = run(args)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({key: report[key] for key in ('status', 'source_final_sha256', 'objects_count')}))


if __name__ == '__main__':
    main()
