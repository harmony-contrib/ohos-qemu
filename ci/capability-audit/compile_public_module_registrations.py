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
    ('camera-depth', 'foundation/multimedia/camera_framework/api26_depth_contracts',
     'foundation/multimedia/camera_framework/frameworks/js/camera_napi/src/native_module_ohos_camera.cpp',
     'obj/foundation/multimedia/camera_framework/frameworks/js/camera_napi/src/camera_napi/native_module_ohos_camera.o'),
    ('camera-depth-data', 'foundation/multimedia/camera_framework/api26_depth_contracts',
     'foundation/multimedia/camera_framework/frameworks/js/camera_napi_for_sys/src/output/depth_data_napi.cpp',
     'obj/foundation/multimedia/camera_framework/frameworks/js/camera_napi_for_sys/src/output/camera_napi_ex/depth_data_napi.o'),
    ('bluetooth-opp', 'foundation/communication/bluetooth/api26_opp_enums',
     'foundation/communication/bluetooth/frameworks/js/napi/src/opp/native_module_opp.cpp',
     'obj/foundation/communication/bluetooth/frameworks/js/napi/src/opp/opp/native_module_opp.o'),
    ('photo-enums', 'foundation/multimedia/media_library/api26_photo_enums',
     'foundation/multimedia/media_library/frameworks/js/src/media_library_napi.cpp',
     'obj/foundation/multimedia/media_library/frameworks/js/src/medialibrary_nutils/media_library_napi.o'),
    ('photo-cover-source', 'foundation/multimedia/media_library/api26_photo_enums',
     'foundation/multimedia/media_library/frameworks/js/src/photo_album_napi.cpp',
     'obj/foundation/multimedia/media_library/frameworks/js/src/medialibrary_nutils/photo_album_napi.o'),
    ('effect-light-degree', 'foundation/graphic/graphic_2d/effect_kit/api26_light_degree',
     'foundation/graphic/graphic_2d/interfaces/kits/napi/graphic/effect_kit/src/native_module_ohos_effect.cpp',
     'obj/foundation/graphic/graphic_2d/interfaces/kits/napi/graphic/effect_kit/src/effectkit/native_module_ohos_effect.o'),
    ('mission-continue-state', 'foundation/ability/ability_runtime/api26_mission_state',
     'foundation/ability/ability_runtime/frameworks/js/napi/mission_manager/distributed_mission_manager.cpp',
     'obj/foundation/ability/ability_runtime/frameworks/js/napi/mission_manager/distributedmissionmanager/distributed_mission_manager.o'),
    ('curve-enum', 'foundation/arkui/ace_engine/api26_curve_enum',
     'foundation/arkui/ace_engine/frameworks/bridge/declarative_frontend/engine/jsi/modules/jsi_curves_module.cpp',
     'obj/foundation/arkui/ace_engine/frameworks/bridge/declarative_frontend/engine/jsi/modules/declarative_js_engine_bridge_ark_ohos/jsi_curves_module.o'),
    ('location-enums', 'base/location/location/api26_public_enums',
     'base/location/location/frameworks/js/napi/source/location_napi_entry.cpp',
     'obj/base/location/location/frameworks/js/napi/source/geolocationmanager/location_napi_entry.o'),
)
COMPONENTS = tuple(dict.fromkeys(row[1] for row in PLAN))


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
    parser.add_argument('--products', choices=tuple(PRODUCTS), nargs='+', default=list(PRODUCTS))
    parser.add_argument('--components', choices=COMPONENTS, nargs='+', default=list(COMPONENTS))
    args = parser.parse_args()
    if len(args.products) != len(set(args.products)):
        parser.error('duplicate requested product')
    if len(args.components) != len(set(args.components)):
        parser.error('duplicate requested component')
    plan = tuple(row for row in PLAN if row[1] in args.components)
    root = args.source_root.resolve()
    if not all(os.statvfs(path).f_flag & os.ST_RDONLY for path in (root, root / 'out')):
        raise ValueError('source and output mounts must both be read-only')
    args.output.mkdir(exist_ok=False)
    inputs = [Path(__file__), ROOT / 'patches/lib/apply_patch.sh',
              ROOT / 'patches/lib/apply_component_dir.sh']
    targets = set()
    for _, relative, _, _ in plan:
        component = ROOT / 'patches/common' / relative
        inputs += [component / 'apply.sh', *sorted(component.glob('*.patch'))]
        for patch in component.glob('*.patch'):
            targets.update(re.findall(r'^\+\+\+ b/(.+)$', patch.read_text(), re.M))
    if targets != {row[2] for row in plan}:
        raise ValueError('unexpected registration patch target')
    before = {str(path): digest(path) for path in inputs}
    source_before = {name: digest(root / name) for name in targets}
    report = {'status': 'fail', 'scope': 'actual_cached_product_registration_TUs_NOT_fresh_GN_link_guest',
              'first_artifact_behavior_gate_passed': False, 'objects': [], 'failures': [],
              'recipe_sha256': before, 'source_sha256_before': source_before,
              'requested_products': args.products, 'requested_components': args.components}
    try:
        with tempfile.TemporaryDirectory(prefix='public-module-registration-') as temporary:
            staged = Path(temporary)
            for name in targets:
                destination = staged / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes((root / name).read_bytes())
            for label, relative, source, target in plan:
                component = ROOT / 'patches/common' / relative
                for attempt in (1, 2):
                    log = args.output / (label + '-apply-' + str(attempt) + '.log')
                    with log.open('x') as stream:
                        subprocess.run(['bash', str(component / 'apply.sh'), '--source-root', str(staged)],
                                       stdout=stream, stderr=subprocess.STDOUT, check=True)
                for product in args.products:
                    triple = PRODUCTS[product]
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
