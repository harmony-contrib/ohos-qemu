#!/usr/bin/env python3
"""Build the UID0 existing-SA Dump client with actual GNSS product flags."""
import argparse
import json
from pathlib import Path

import batch_system_build_runtime_helpers as product

NAME = 'gnss_existing_sa_dump'
CLIENT_SHA256 = '9f9cfc1d577b4dec926cd4c0f7d79379f8b85bfeabb380c6878b1bbf57e3c624'
BASE = 'base/location/location/services/location_gnss/gnss'
GNSS = {
    'graph': 'obj/' + BASE + '/lbsservice_gnss.ninja',
    'object': 'obj/' + BASE + '/source/lbsservice_gnss/gnss_ability.o',
    'source': BASE + '/source/gnss_ability.cpp',
}
HEADERS = [
    'foundation/systemabilitymgr/samgr/interfaces/innerkits/samgr_proxy/include/iservice_registry.h',
    'foundation/systemabilitymgr/samgr/interfaces/innerkits/samgr_proxy/include/if_system_ability_manager.h',
    'foundation/communication/ipc/interfaces/innerkits/ipc_core/include/iremote_object.h',
    'foundation/systemabilitymgr/samgr/interfaces/innerkits/samgr_proxy/include/system_ability_definition.h',
]
NEEDED = {'libsamgr_proxy.z.so', 'libutils.z.so', 'libc++.so', 'libc.so'}


def validate_symbols(text):
    if not product.defined_symbol(text, '__cfi_check') or '__cfi_slowpath' not in text:
        raise ValueError('existing-SA client must retain actual cross-DSO CFI')
    if any(name in text for name in ('std::__n1::', 'std::__Cr::', 'NSt3__n1', 'NSt4__Cr')):
        raise ValueError('SDK/Chromium standard-library ABI is forbidden')
    needed = product.dynamic_needed(text)
    if needed != NEEDED:
        raise ValueError('actual existing-SA client runtime dependencies differ')
    return needed


class GnssDumpBuilder(product.Builder):
    def anchor(self, spec, name):
        value = super().anchor(spec, name)
        trace = [word for word in value['flags'] if word.startswith('-DQEMU_GNSS_HDI_RAW_TRACE')]
        if trace != ['-DQEMU_GNSS_HDI_RAW_TRACE=1'] or '-DFEATURE_GNSS_SUPPORT' not in value['flags']:
            raise ValueError('actual HDI-enabled QEMU trace graph is required')
        return value

    def check_elf(self, name, binary, direct, row):
        if name != NAME:
            return super().check_elf(name, binary, direct, row)
        row['elf'] = product.elf_header(binary, executable=True, product=self.product,
            interpreter_path=None if self.normal_link is None else self.normal_link['interpreter'])
        text = self.command([self.readelf, '-h', '-l', '-d', '--dyn-syms', '--syms', '--wide',
                             '--demangle', binary], name + '-actual-ELF-ABI')
        needed = validate_symbols(text)
        if row['source']['sha256'] != CLIENT_SHA256 or row['private_source_sha256'] != CLIENT_SHA256:
            raise ValueError('only the fixed existing-SA Dump client is accepted')
        headers = {record['path'] for record in row['actual_compiler_dependencies']}
        if not {str(self.root / path) for path in HEADERS} <= headers:
            raise ValueError('actual SAMgr/IPC headers were not compiled')
        if not {'string', 'vector'} <= {Path(path).name for path in headers}:
            raise ValueError('actual product standard-library headers are required')
        for soname in needed: product.runtime_link_records(row, soname)
        # This small client inlines its string/vector operations. Its namespace
        # proof is the fixed client's and Builder's compiled __h static_asserts,
        # actual product headers and input hashes; no exported std symbol is forced.
        row['system_ABI_proof'] = 'fixed client and product guard compiled __h static_asserts; actual headers and link inputs'
        row['DT_NEEDED'] = sorted(needed)


def configure():
    product.HELPERS[NAME] = {
        'fixture': 'batch_system/gnss_trace/gnss_existing_sa_dump.cpp', 'anchors': [GNSS],
        'libraries': ['systemabilitymgr/samgr/libsamgr_proxy.z.so', 'commonlibrary/c_utils/libutils.z.so'],
        'headers': HEADERS, 'extra_includes': [],
    }


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
    builder = GnssDumpBuilder(args.source_root, args.output, [NAME], args.plan_only,
                              runtime_profile=args.runtime_profile, runtime_profile_sha256=args.runtime_profile_sha256,
                              product=actual_profile['product'], normal_link_target=args.normal_link_target)
    builder.report['gnss_trace_extension'] = builder.remember(Path(__file__), source=False)
    builder.report['scope'] = 'actual diagnostic client compilation only; existing SA, UID and raw callback runtime pending'
    report = builder.run()
    print(json.dumps({'status': report['status'], 'helpers': report['helpers']}, indent=2))
    return report['status'] not in ('planned_NOT_compiled', 'pass_compile_link_ONLY')


if __name__ == '__main__':
    raise SystemExit(main())
