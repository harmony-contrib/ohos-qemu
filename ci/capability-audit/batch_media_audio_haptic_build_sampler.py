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
from batch_media_audio_haptic_project import FIX, HERE, checked, load, record, require, sha

NAME = 'audio_haptic_sampler'
FIXTURE = 'audio_haptic_runtime/sampler.cpp'
REQUIRED = {'libvibrator_proxy_2.0.z.so', 'libaccesstoken_sdk.z.so'}
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


def helper_binding(spec):
    configure()
    root = Path(spec['output_directory']).resolve()
    binary = root / NAME / NAME
    proof = artifacts.helper_binding('audio_haptic', binary, FIX / 'sampler.cpp', spec['build'], root, spec.get('path_map', {}))
    report = load(checked(spec['build']))
    require(report.get('audio_haptic_extension', {}).get('sha256') == sha(Path(__file__)),
            'actual helper extension source/anchor configuration changed')
    return dict(proof, binary=record(binary), source=record(FIX / 'sampler.cpp'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--plan-only', action='store_true')
    args = parser.parse_args()
    configure()
    builder = product.Builder(args.source_root, args.output, [NAME], args.plan_only)
    builder.report['audio_haptic_extension'] = record(Path(__file__))
    result = builder.run()
    print(json.dumps({'status': result['status'], 'helpers': result['helpers']}, indent=2))
    raise SystemExit(result['status'] not in ('planned_NOT_compiled', 'pass_compile_link_ONLY'))


if __name__ == '__main__': main()
