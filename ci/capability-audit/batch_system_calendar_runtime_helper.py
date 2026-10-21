#!/usr/bin/env python3
"""Root-only Calendar observer extension, confined to this Python process."""
import argparse
import json
from pathlib import Path
import batch_system_build_runtime_helpers as product
from batch_system_calendar_runtime_project import record

NAME = 'calendar_runtime_observer'


def configure():
    product.HELPERS[NAME] = {'fixture': 'batch_system/calendar_runtime/observer.cpp',
        'anchors': [product.APP, product.TOKEN],
        'libraries': ['ability/ability_runtime/libapp_manager.z.so', 'security/access_token/libaccesstoken_sdk.z.so'],
        'headers': [product.APP['header'], product.TOKEN['header'], 'third_party/json/include/nlohmann/json.hpp'],
        'extra_includes': ['third_party/json/include/nlohmann']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--plan-only', action='store_true')
    parser.add_argument('--runtime-profile', type=Path)
    parser.add_argument('--runtime-profile-sha256')
    parser.add_argument('--verify-spec', type=Path, help='read-only actual helper artifact/receipt spec')
    parser.add_argument('--normal-link-target')
    args = parser.parse_args()
    configure()
    if args.verify_spec:
        if args.runtime_profile or args.runtime_profile_sha256:
            parser.error('--verify-spec cannot retrofit a runtime profile')
        from batch_system_calendar_runtime_capture import helper_proof
        value = helper_proof(json.loads(args.verify_spec.read_text()))
        print(json.dumps({'status': 'actual_product_helper_artifacts_verified_NOT_guest',
                          'binary_sha256': value['binary_sha256']}, indent=2))
        return 0
    if not args.source_root or not args.output:
        parser.error('--source-root and --output are required for actual product plan/build')
    from production579_target import bound_profile
    actual_profile = bound_profile(args.runtime_profile, args.runtime_profile_sha256)
    builder = product.Builder(args.source_root, args.output, [NAME], args.plan_only,
                              runtime_profile=args.runtime_profile, runtime_profile_sha256=args.runtime_profile_sha256,
                              product=actual_profile['product'], normal_link_target=args.normal_link_target)
    builder.report['calendar_runtime_extension'] = record(Path(__file__))
    report = builder.run()
    print(json.dumps({'status': report['status'], 'helpers': report['helpers']}, indent=2))
    return report['status'] not in ('planned_NOT_compiled', 'pass_compile_link_ONLY')


if __name__ == '__main__':
    raise SystemExit(main())
