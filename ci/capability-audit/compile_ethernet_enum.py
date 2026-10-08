#!/usr/bin/env python3
"""Compile the repaired Ethernet TU with three actual product commands.

Read-only source/output volumes; private candidate objects only. This is not
linking or guest acceptance, and cannot unlock the package matrix gate.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/communication/netmanager_ext/ethernet_api26'
PROJECT = Path('foundation/communication/netmanager_ext')
SOURCE = PROJECT / 'frameworks/js/napi/ethernet/ethernet_module.cpp'
TARGET = 'obj/' + str(PROJECT) + '/frameworks/js/napi/ethernet/ethernet/ethernet_module.o'
PRODUCTS = {'arm64_virt': 'aarch64-linux-ohos', 'armv7a_virt': 'arm-linux-ohos',
            'x86_64_virt': 'x86_64-linux-ohos'}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(args, *, component=COMPONENT, project_path=PROJECT, source_path=SOURCE,
        target=TARGET, caller=None, scope='three_actual_Ethernet_TU_objects_NOT_link_or_guest', extra_defines=()):
    root = args.source_root.resolve()
    if any(re.fullmatch('[A-Za-z_][A-Za-z0-9_]*', name) is None for name in extra_defines):
        raise ValueError('invalid explicitly recorded candidate feature define')
    component, project_path, source_path = Path(component), Path(project_path), Path(source_path)
    if not os.statvfs(root).f_flag & os.ST_RDONLY:
        raise ValueError('compile check requires read-only actual source inputs')
    args.output.mkdir(exist_ok=False)
    inputs = [Path(__file__).resolve(), component / 'apply.sh', *sorted(component.glob('*.patch')),
              ROOT / 'patches/lib/apply_component_dir.sh']
    if caller is not None:
        inputs.append(Path(caller).resolve())
    before = {str(path): digest(path) for path in inputs}
    report = {'status': 'fail', 'scope': scope,
              'first_artifact_behavior_gate_passed': False, 'objects': [],
              'recipe_sha256': before, 'source_sha256': digest(root / source_path)}
    project = root / project_path
    head = subprocess.check_output(['git', '-C', str(project), 'rev-parse', 'HEAD'], text=True).strip()
    report['source_head'] = head
    paths = set()
    for patch in component.glob('*.patch'):
        paths.update(Path(value) for value in re.findall(r'^\+\+\+ b/(.+)$', patch.read_text(), re.M))
    if source_path not in paths or any(project_path not in path.parents for path in paths):
        raise ValueError('unexpected component patch target')
    with tempfile.TemporaryDirectory(prefix='ethernet-enum-compile-') as directory:
        staged = Path(directory)
        for path in paths:
            relative = path.relative_to(project_path)
            pristine = subprocess.check_output(['git', '-C', str(project), 'show', head + ':' + str(relative)])
            destination = staged / path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(pristine)
        for attempt in (1, 2):
            with (args.output / ('apply-' + str(attempt) + '.log')).open('x') as stream:
                subprocess.run(['bash', str(component / 'apply.sh'), '--source-root', str(staged)],
                               stdout=stream, stderr=subprocess.STDOUT, check=True)
        candidate = staged / source_path
        if digest(candidate) != report['source_sha256']:
            raise ValueError('actual TU does not match this complete pinned-source component recipe')
        for product, triple in PRODUCTS.items():
            cwd = root / 'out' / product
            query = subprocess.run([str(root / 'prebuilts/build-tools/linux-x86/bin/ninja'),
                '-w', 'dupbuild=warn', '-C', str(cwd), '-t', 'commands', '-s', target],
                capture_output=True, text=True, check=True)
            query_log = args.output / (product + '-query.log')
            query_log.write_text(query.stdout + query.stderr)
            argv = shlex.split(query.stdout.splitlines()[-1])
            if Path(argv[0]).name == 'ccache':
                argv.pop(0)
            if (Path(argv[0]).name != 'clang++' or '--target=' + triple not in argv or
                    any(token in argv for token in ('&&', ';', '|')) or
                    any(argv.count(flag) != 1 for flag in ('-c', '-o', '-MF')) or
                    (cwd / argv[argv.index('-c') + 1]).resolve() != root / source_path):
                raise ValueError('unexpected real Ethernet product compile command: ' + product)
            original = argv[:]
            added_defines = ['-D' + name for name in extra_defines if '-D' + name not in argv]
            argv[1:1] = added_defines
            # Moving only the TU into the private candidate must preserve its
            # original quote-include directory. No generated/stub headers.
            argv[1:1] = ['-iquote', str((root / source_path).parent)]
            object_path = staged / (product + '.o')
            dep_path = staged / (product + '.d')
            argv[argv.index('-c') + 1] = str(candidate)
            argv[argv.index('-o') + 1] = str(object_path)
            argv[argv.index('-MF') + 1] = str(dep_path)
            compile_log = args.output / (product + '-compile.log')
            with compile_log.open('x') as stream:
                subprocess.run(argv, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT, check=True)
            report['objects'].append({'product': product, 'triple': triple,
                'object_sha256': digest(object_path), 'dependency_sha256': digest(dep_path),
                'query_log_sha256': digest(query_log), 'compile_log_sha256': digest(compile_log),
                'explicit_candidate_feature_defines_added': added_defines,
                'original_command': original, 'executed_command': argv})
    if digest(root / source_path) != report['source_sha256'] or {str(path): digest(path) for path in inputs} != before:
        raise ValueError('component inputs changed during compile verification')
    report.update(status='pass', all_three_products_checked=True, source_inputs_unchanged=True)
    (args.output / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    result = run(parser.parse_args())
    print(json.dumps({'status': result['status'], 'objects': len(result['objects']), 'scope': result['scope']}))
