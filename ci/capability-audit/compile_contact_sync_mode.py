#!/usr/bin/env python3
"""Compile the full repaired ContactsData TU with three real product commands.

Uses an owned candidate and read-only source/build inputs. This is not linking,
loading the public wrapper, a contacts provider test, or guest acceptance.
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
COMPONENT = ROOT / 'patches/common/applications/standard/contacts_data/sync_mode'
SOURCE = Path('applications/standard/contacts_data/contacts/src/contacts_api.cpp')
TARGET = 'obj/applications/standard/contacts_data/contacts/src/contact/contacts_api.o'
PRODUCTS = {'arm64_virt': 'aarch64-linux-ohos', 'armv7a_virt': 'arm-linux-ohos',
            'x86_64_virt': 'x86_64-linux-ohos'}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(args, component=COMPONENT, source_file=SOURCE, target=TARGET, caller=None, candidate_defines=(),
        overlay_component_headers=False, prepare_component_idl=False):
    """Shared full-TU check with the complete exact component; no stub headers."""
    component, source_file = Path(component), Path(source_file)
    if candidate_defines not in ((), ('QEMU_VIVID_CAPTURE_ENABLED',)):
        raise ValueError('only the explicit QEMU Camera candidate feature can be selected')
    if args.output.exists() or args.output.is_symlink():
        raise ValueError('fresh exact-component compilation evidence path required')
    root = args.source_root.resolve()
    if not os.statvfs(root).f_flag & os.ST_RDONLY:
        raise ValueError('actual component source must be mounted read-only')
    spec = importlib.util.spec_from_file_location('exact_component_baseline', component / 'verify_source.py')
    baseline = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(baseline)
    if source_file not in {Path(baseline.PROJECT) / entry[0] for entry in baseline.FILES}:
        raise ValueError('isolated full-TU check must match the exact component source')
    baseline.validate(root)
    originals = {str(Path(baseline.PROJECT) / entry[0]): digest(root / baseline.PROJECT / entry[0])
                 for entry in baseline.FILES}
    if any(originals[str(Path(baseline.PROJECT) / entry[0])] != entry[1] for entry in baseline.FILES):
        raise ValueError('requires pristine pinned component for isolated candidate compilation')
    head = subprocess.check_output(['git', '-C', str(root / baseline.PROJECT), 'rev-parse', 'HEAD'],
                                   text=True).strip()
    source = root / source_file
    inputs = [Path(__file__).resolve(), *(sorted(component.glob('*.patch'))),
              component / 'apply.sh', component / 'verify_source.py',
              ROOT / 'patches/lib/apply_exact_component.py', ROOT / 'patches/lib/apply_component_stack.py',
              ROOT / 'patches/lib/exact_source_states.py']
    if caller is not None:
        inputs.append(Path(caller).resolve())
    before = {str(path): digest(path) for path in inputs}
    products = args.product or list(PRODUCTS)
    if len(set(products)) != len(products):
        raise ValueError('duplicate isolated product checks cannot count as separate architectures')
    report = {'status': 'fail', 'scope': 'actual_selected_full_product_TU_objects_NOT_link_or_guest',
              'source_head': head, 'source_original_sha256': digest(source), 'objects': [],
              'component_source_original_sha256': originals,
              'candidate_feature_defines': list(candidate_defines),
              'candidate_GN_feature_selection_verified': False if candidate_defines else None,
              'requested_products': products, 'all_three_products_checked': set(products) == set(PRODUCTS),
              'component': str(component.relative_to(ROOT)),
              'component_inputs_sha256': before, 'first_artifact_behavior_gate_passed': False}
    logs = args.output.with_suffix('.logs')
    logs.mkdir(exist_ok=False)
    with tempfile.TemporaryDirectory(prefix='exact-component-compile-') as directory:
        staged = Path(directory)
        candidate = staged / source_file
        for relative in originals:
            destination = staged / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / relative, destination)
        for attempt in (1, 2):
            with (logs / ('apply-' + str(attempt) + '.log')).open('x') as stream:
                subprocess.run(['bash', str(component / 'apply.sh'), '--source-root', str(staged)],
                               stdout=stream, stderr=subprocess.STDOUT, check=True)
        baseline.validate(staged, require_patched=True)
        report['source_final_sha256'] = digest(candidate)
        report['component_source_final_sha256'] = {name: digest(staged / name) for name in originals}
        for product in products:
            triple = PRODUCTS[product]
            cwd = root / 'out' / product
            queried = subprocess.run([str(root / 'prebuilts/build-tools/linux-x86/bin/ninja'),
                '-w', 'dupbuild=warn', '-C', str(cwd), '-t', 'commands', '-s', target],
                text=True, capture_output=True, check=True)
            query_log = logs / (product + '-query.log')
            query_log.write_text(queried.stdout + queried.stderr)
            argv = shlex.split(queried.stdout.splitlines()[-1])
            if Path(argv[0]).name == 'ccache':
                argv.pop(0)
            if (Path(argv[0]).name != 'clang++' or any(token in argv for token in ('&&', ';', '|'))
                    or '--target=' + triple not in argv or argv.count('-c') != 1 or argv.count('-o') != 1
                    or argv.count('-MF') != 1 or (cwd / argv[argv.index('-c') + 1]).resolve() != source):
                raise ValueError('unexpected actual component compile command for ' + product)
            original_command = argv[:]
            # This explicit isolated branch check is not a regenerated GN
            # command or proof of product feature selection. The package build
            # must still generate GN and compile its own real feature flags.
            for define in candidate_defines:
                if '-D' + define not in argv:
                    argv.insert(1, '-D' + define)
            argv[argv.index('-c') + 1] = str(candidate)
            object_path = staged / (product + '.o')
            dependency_path = staged / (product + '.d')
            argv[argv.index('-o') + 1] = str(object_path)
            argv[argv.index('-MF') + 1] = str(dependency_path)
            if overlay_component_headers:
                # Only exact component-owned directories precede real includes;
                # retain every original include and the TU's quoted-header path.
                revised = []
                for token in argv:
                    if token.startswith('-I') and len(token) > 2:
                        original = (cwd / token[2:]).resolve()
                        if original.is_relative_to(root):
                            overlay = staged / original.relative_to(root)
                            if overlay.is_dir():
                                revised.append('-I' + str(overlay))
                    revised.append(token)
                argv = revised + ['-iquote', str(source.parent)]
            generated_inputs = []
            if prepare_component_idl:
                from compile_render_connection_reply import prepare_missing_idl
                owned_generated = logs / (product + '-generated')
                owned_generated.mkdir(exist_ok=False)
                argv, generated_inputs = prepare_missing_idl(
                    root, cwd, argv, owned_generated, copy_readonly_inputs=True)
            compile_log = logs / (product + '-compile.log')
            with compile_log.open('x') as stream:
                subprocess.run(argv, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT, check=True)
            used_candidate_headers = []
            if overlay_component_headers:
                dependency_text = dependency_path.read_text()
                for relative in originals:
                    header = staged / relative
                    if header.suffix in ('.h', '.hpp'):
                        if str(header) not in dependency_text:
                            raise ValueError('actual compiler did not consume candidate header: ' + relative)
                        used_candidate_headers.append(relative)
            report['objects'].append({'product': product, 'triple': triple,
                'object_sha256': digest(object_path), 'dependency_sha256': digest(dependency_path),
                'queried_command_sha256': hashlib.sha256(json.dumps(original_command).encode()).hexdigest(),
                'query_log': str(query_log), 'query_log_sha256': digest(query_log),
                'compile_log': str(compile_log), 'compile_log_sha256': digest(compile_log),
                'executed_argv': argv, 'source_sha256': digest(candidate),
                'actual_owned_idl_generation': generated_inputs,
                'used_candidate_headers': used_candidate_headers})
    if ({name: digest(root / name) for name in originals} != originals or
            {str(path): digest(path) for path in inputs} != before):
        raise ValueError('read-only source or component recipe changed during compilation')
    report.update(status='pass', objects_count=len(report['objects']), source_inputs_unchanged=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--product', choices=tuple(PRODUCTS), action='append',
                        help='restrict isolated object checks; default is all three products')
    args = parser.parse_args()
    result = run(args)
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({name: result[name] for name in ('status', 'source_final_sha256', 'objects_count')}))
