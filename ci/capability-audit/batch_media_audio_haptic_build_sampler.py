#!/usr/bin/env python3
"""Root-only helper builder using real product GN flags; no source/out writes.

This extends the existing builder configuration in this process only. No shared
runner or helper definition is edited. Root must hold its source/out read lease.
"""
import argparse
import json
from pathlib import Path

import batch_system_build_runtime_helpers as product
import batch_media_wallpaper_artifacts as artifacts
from build_audio_capture_tools import ALSA
from batch_media_audio_haptic_project import FIX, HERE, checked, load, record, require, sha

NAME = 'audio_haptic_sampler'
FIXTURE = 'audio_haptic_runtime/sampler.cpp'
REQUIRED = {'libvibrator_proxy_2.0.z.so', 'libaccesstoken_sdk.z.so'}
CLOCK_NAME = 'audio_observation_clock'
CLOCK_FIXTURE = 'audio_observation_clock/clock.cpp'
VDI = {'graph': 'obj/vendor/ohemu/virt/hals/vibrator/libhdi_product_vibrator_impl.ninja',
       'object': 'obj/vendor/ohemu/virt/hals/vibrator/libhdi_product_vibrator_impl/qemu_virtual_vibrator.o',
       'source': 'vendor/ohemu/virt/hals/vibrator/qemu_virtual_vibrator.cpp',
       'header': 'drivers/interface/vibrator/v2_0/IVibratorInterface.idl'}


def configure():
    product.HELPERS[NAME] = {'fixture': 'batch_media/' + FIXTURE, 'anchors': [VDI, product.TOKEN],
        'libraries': ['hdf/drivers_interface_vibrator/libvibrator_proxy_2.0.z.so',
                      'security/access_token/libaccesstoken_sdk.z.so'],
        'headers': [VDI['header'], product.TOKEN['header']], 'extra_includes': []}
    artifacts.HELPERS['audio_haptic'] = (NAME, FIXTURE, REQUIRED)
    product.HELPERS[CLOCK_NAME] = {'fixture':'batch_media/'+CLOCK_FIXTURE,
        'anchors':[product.TOKEN,ALSA], 'libraries':['thirdparty/alsa-lib/libasound.so'],
        'headers':[ALSA['header'],product.TOKEN['header']], 'extra_includes':['third_party/alsa-lib/include']}
    artifacts.HELPERS['audio_clock'] = (CLOCK_NAME,CLOCK_FIXTURE,{'libasound.so'})


def helper_binding(spec):
    configure()
    root = Path(spec['output_directory']).resolve()
    binary = root / NAME / NAME
    proof = artifacts.helper_binding('audio_haptic', binary, FIX / 'sampler.cpp', spec['build'], root, spec.get('path_map', {}))
    report = load(checked(spec['build']))
    require(report.get('audio_haptic_extension', {}).get('sha256') == sha(Path(__file__)),
            'actual helper extension source/anchor configuration changed')
    row = report['helpers'][NAME]
    require(report.get('verify_existing') is not True and row.get('installed_runtime_profile') == report.get('installed_runtime_profile') and
            report.get('installed_runtime_image_proof', {}).get('dsos'), 'fresh actual installed-runtime relink/image proof required')
    runtime = {key: row[key] for key in ('installed_runtime_profile', 'actual_link_inputs', 'actual_link_input_sonames')}
    for soname in proof['DT_NEEDED']: product.runtime_link_records(runtime, soname)
    return dict(proof, **runtime, binary=record(binary), source=record(FIX / 'sampler.cpp'))


def clock_binding(spec):
    configure()
    root = Path(spec['output_directory']).resolve()
    source = HERE/'fixtures/batch_media'/CLOCK_FIXTURE
    binary = root/CLOCK_NAME/CLOCK_NAME
    proof = artifacts.helper_binding('audio_clock',binary,source,spec['build'],root,spec.get('path_map',{}))
    report = load(checked(spec['build']));row=report['helpers'][CLOCK_NAME]
    require(report.get('audio_haptic_extension',{}).get('sha256') == sha(Path(__file__)) and
        report.get('verify_existing') is not True and row.get('installed_runtime_profile') == report.get('installed_runtime_profile') and
        report.get('installed_runtime_image_proof',{}).get('dsos'), 'fresh real clock helper/source/image binding required')
    runtime={key:row[key] for key in ('installed_runtime_profile','actual_link_inputs','actual_link_input_sonames')}
    for soname in proof['DT_NEEDED']:product.runtime_link_records(runtime,soname)
    return dict(proof,**runtime,binary=record(binary),source=record(source))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--plan-only', action='store_true')
    parser.add_argument('--runtime-profile', type=Path, required=True)
    parser.add_argument('--runtime-profile-sha256', required=True)
    parser.add_argument('--normal-link-target')
    args = parser.parse_args()
    configure()
    from production579_target import bound_profile
    actual_profile = bound_profile(args.runtime_profile, args.runtime_profile_sha256)
    builder = product.Builder(args.source_root, args.output, [NAME,CLOCK_NAME], args.plan_only,
                              runtime_profile=args.runtime_profile, runtime_profile_sha256=args.runtime_profile_sha256,
                              product=actual_profile['product'], normal_link_target=args.normal_link_target)
    builder.report['audio_haptic_extension'] = record(Path(__file__))
    result = builder.run()
    print(json.dumps({'status': result['status'], 'helpers': result['helpers']}, indent=2))
    raise SystemExit(result['status'] not in ('planned_NOT_compiled', 'pass_compile_link_ONLY'))


if __name__ == '__main__': main()
