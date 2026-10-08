#!/usr/bin/env python3
"""Read-only three-ABI registration TU checks, not fresh GN/link/guest proof."""
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
PRODUCTS = {'arm64_virt': 'aarch64-linux-ohos', 'armv7a_virt': 'arm-linux-ohos',
            'x86_64_virt': 'x86_64-linux-ohos'}
PLAN = (
    ('audio', 'foundation/multimedia/audio_framework/api26_public_enums',
     'foundation/multimedia/audio_framework/frameworks/js/napi/common/napi_audio_entry.cpp',
     'obj/foundation/multimedia/audio_framework/frameworks/js/napi/common/audio/napi_audio_entry.o'),
    ('uieffect', 'foundation/graphic/graphic_2d/ui_effect/api26_public_modes',
     'foundation/graphic/graphic_2d/interfaces/kits/napi/graphic/ui_effect/src/native_module_ohos_ui_effect.cpp',
     'obj/foundation/graphic/graphic_2d/interfaces/kits/napi/graphic/ui_effect/src/uieffect_napi/native_module_ohos_ui_effect.o'),
    ('bluetooth-control', 'foundation/communication/bluetooth/api26_control_enums',
     'foundation/communication/bluetooth/frameworks/js/napi/src/connection/native_module_connection.cpp',
     'obj/foundation/communication/bluetooth/frameworks/js/napi/src/connection/connection/native_module_connection.o'),
)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def relocate(argv, cwd, root, source, staged, obj, dep, triple):
    argv = list(argv)
    if Path(argv[0]).name == 'ccache':
        argv.pop(0)
    if (Path(argv[0]).name != 'clang++' or '--target=' + triple not in argv or
            any(value in argv for value in ('&&', ';', '|')) or
            any(argv.count(flag) != 1 for flag in ('-c', '-o', '-MF')) or
            (cwd / argv[argv.index('-c') + 1]).resolve() != root / source):
        raise ValueError('unexpected actual product compiler command')
    original = argv[:]
    argv[1:1] = ['-iquote', str((root / source).parent)]
    for flag, path in (('-c', staged / source), ('-o', obj), ('-MF', dep)):
        argv[argv.index(flag) + 1] = str(path)
    return original, argv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = args.source_root.resolve()
    if not all(os.statvfs(path).f_flag & os.ST_RDONLY for path in (root, root / 'out')):
        raise ValueError('source and output mounts must both be read-only')
    args.output.mkdir(exist_ok=False)
    inputs = [Path(__file__), ROOT / 'patches/lib/apply_patch.sh',
              ROOT / 'patches/lib/apply_component_dir.sh']
    targets = set()
    for _, relative, _, _ in PLAN:
        component = ROOT / 'patches/common' / relative
        inputs += [component / 'apply.sh', *sorted(component.glob('*.patch'))]
        for patch in component.glob('*.patch'):
            targets.update(re.findall(r'^\+\+\+ b/(.+)$', patch.read_text(), re.M))
    if targets != {row[2] for row in PLAN}:
        raise ValueError('unexpected registration patch target')
    before = {str(path): digest(path) for path in inputs}
    source_before = {name: digest(root / name) for name in targets}
    report = {'status': 'fail', 'scope': 'actual_cached_product_registration_TUs_NOT_fresh_GN_link_guest',
              'first_artifact_behavior_gate_passed': False, 'objects': [], 'failures': [],
              'recipe_sha256': before, 'source_sha256_before': source_before}
    try:
        with tempfile.TemporaryDirectory(prefix='public-module-registration-') as temporary:
            staged = Path(temporary)
            for name in targets:
                destination = staged / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes((root / name).read_bytes())
            for label, relative, source, target in PLAN:
                component = ROOT / 'patches/common' / relative
                for attempt in (1, 2):
                    log = args.output / (label + '-apply-' + str(attempt) + '.log')
                    with log.open('x') as stream:
                        subprocess.run(['bash', str(component / 'apply.sh'), '--source-root', str(staged)],
                                       stdout=stream, stderr=subprocess.STDOUT, check=True)
                for product, triple in PRODUCTS.items():
                    cwd = root / 'out' / product
                    query = subprocess.run([str(root / 'prebuilts/build-tools/linux-x86/bin/ninja'),
                        '-w', 'dupbuild=warn', '-C', str(cwd), '-t', 'commands', '-s', target],
                        capture_output=True, text=True, check=True)
                    query_log = args.output / (label + '-' + product + '-query.log')
                    query_log.write_text(query.stdout + query.stderr)
                    obj, dep = staged / (label + '-' + product + '.o'), staged / (label + '-' + product + '.d')
                    original, argv = relocate(shlex.split(query.stdout.splitlines()[-1]),
                                             cwd, root, source, staged, obj, dep, triple)
                    log = args.output / (label + '-' + product + '-compile.log')
                    with log.open('x') as stream:
                        subprocess.run(argv, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT, check=True)
                    report['objects'].append({'component': label, 'product': product, 'triple': triple,
                        'original_command': original, 'executed_command': argv, 'object_sha256': digest(obj),
                        'dependency_sha256': digest(dep), 'query_sha256': digest(query_log), 'log_sha256': digest(log)})
        if (before != {str(path): digest(path) for path in inputs} or
                source_before != {name: digest(root / name) for name in targets}):
            raise ValueError('actual source or patch inputs changed during the check')
        report.update(status='pass', source_and_output_mounts_read_only=True,
                      actual_source_inputs_unchanged=True)
    except Exception as error:
        report['failures'].append(str(error))
        raise
    finally:
        (args.output / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'objects': len(report['objects']), 'scope': report['scope']}))


if __name__ == '__main__':
    main()
