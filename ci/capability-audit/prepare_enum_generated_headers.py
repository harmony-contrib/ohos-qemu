#!/usr/bin/env python3
"""Run the cached VPN IDL action on byte-identical private writable inputs.

Source is read-only at its original GN absolute root /openharmony. Only the
two named products' generated IDL files are written to the output volume.
The real IDL tool incorrectly requires source W_OK. Stage only the two actual
IDL files without modifying their contents; never hand-write generated headers.
This is compilation prerequisite preparation, not package or runtime evidence.
"""
import argparse
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile

from compile_ethernet_enum import digest

PROJECT = 'foundation/communication/netmanager_ext/interfaces/innerkits/netvpnclient'
OUTPUT_NAMES = (
    'inetwork_vpn_service.h', 'network_vpn_service_proxy.cpp', 'network_vpn_service_stub.cpp',
    'network_vpn_service_proxy.h', 'network_vpn_service_stub.h', 'ivpn_event_callback.h',
    'vpn_event_callback_proxy.cpp', 'vpn_event_callback_stub.cpp',
    'vpn_event_callback_proxy.h', 'vpn_event_callback_stub.h',
)


def validate_action(argv, product, root=Path('/openharmony')):
    if product not in ('armv7a_virt', 'x86_64_virt'):
        raise ValueError('unexpected IDL preparation product')
    flags = ('--src-idl', '--dst-path', '--idl-tool-path', '--dst-file', '--language')
    if len(argv) != 12 or any(argv.count(flag) != 1 for flag in flags):
        raise ValueError('unexpected duplicated/missing/extra IDL action flags')
    suffix = '/' + PROJECT + '/INetworkVpnService.idl'
    source_arg = argv[argv.index('--src-idl') + 1]
    if not source_arg.endswith(suffix):
        raise ValueError('unexpected product IDL source')
    cached_root = source_arg[:-len(suffix)]
    if cached_root not in ('/openharmony', '/Volumes/PSSD/qemu/openharmony'):
        raise ValueError('unknown original GN source root')
    cached_cwd = Path(cached_root) / 'out' / product
    if (argv[:2] != ['/usr/bin/env', '../../build/config/components/idl_tool/idl.py'] or
            any(token in argv for token in ('&&', ';', '|')) or
            argv[argv.index('--dst-path') + 1] != str(cached_cwd / 'gen' / PROJECT) or
            argv[argv.index('--idl-tool-path') + 1] != str(cached_cwd / 'clang_x64/ability/idl_tool') or
            argv[-2:] != ['--language', 'cpp']):
        raise ValueError('unexpected original product IDL action')
    wanted = [str(cached_cwd / 'gen' / PROJECT / name) for name in OUTPUT_NAMES]
    if argv[argv.index('--dst-file') + 1].split(',') != wanted:
        raise ValueError('IDL outputs differ from the exact two interfaces')
    cwd = root / 'out' / product
    generated = [cwd / 'gen' / PROJECT / name for name in OUTPUT_NAMES]
    actual = argv[:]
    actual[actual.index('--dst-path') + 1] = str(cwd / 'gen' / PROJECT)
    actual[actual.index('--idl-tool-path') + 1] = str(cwd / 'clang_x64/ability/idl_tool')
    actual[actual.index('--dst-file') + 1] = ','.join(map(str, generated))
    return actual, generated, cached_root


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    root = Path('/openharmony')
    if not os.statvfs(root).f_flag & os.ST_RDONLY:
        raise ValueError('actual source must be read-only at its original GN root')
    args.output.mkdir(exist_ok=False)
    report = {'status': 'fail', 'scope': 'real_two_cached_product_IDL_actions_byte_identical_staged_inputs_NOT_feature_validation',
              'first_artifact_behavior_gate_passed': False, 'actions': [], 'failures': []}
    try:
        for product in ('armv7a_virt', 'x86_64_virt'):
            cwd = root / 'out' / product
            target = 'gen/' + PROJECT + '/inetwork_vpn_service.h'
            process = subprocess.run([str(root / 'prebuilts/build-tools/linux-x86/bin/ninja'),
                '-w', 'dupbuild=warn', '-C', str(cwd), '-t', 'commands', '-s', target],
                capture_output=True, text=True, check=True)
            log = args.output / (product + '-query.log')
            log.write_text(process.stdout + process.stderr)
            lines = process.stdout.splitlines()
            if len(lines) != 1:
                raise ValueError('expected one real product IDL action')
            argv = shlex.split(lines[0])
            original = argv[:]
            # Preserve all action flags/content, relocating only the already
            # validated volume-root aliases used by the two cached GN graphs.
            argv, generated, cached_root = validate_action(argv, product, root)
            sources = [root / PROJECT / name for name in ('INetworkVpnService.idl', 'IVpnEventCallback.idl')]
            inputs = {str(path): digest(path) for path in sources}
            inputs[str(cwd / 'clang_x64/ability/idl_tool/idl')] = digest(cwd / 'clang_x64/ability/idl_tool/idl')
            with tempfile.TemporaryDirectory(prefix='actual-vpn-idl-') as temporary:
                staged = Path(temporary)
                for source in sources:
                    shutil.copy2(source, staged / source.name)
                    if digest(source) != digest(staged / source.name):
                        raise ValueError('staged IDL content differs from actual read-only input')
                argv[argv.index('--src-idl') + 1] = str(staged / sources[0].name)
                with (args.output / (product + '-action.log')).open('x') as stream:
                    subprocess.run(argv, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT, check=True)
            if any(digest(Path(path)) != value for path, value in inputs.items()):
                raise ValueError('IDL inputs changed during preparation')
            report['actions'].append({'product': product, 'original_command': original, 'executed_command': argv,
                'staging_reason': 'real_IDL_CheckValid_requires_F_OK_R_OK_W_OK_even_for_input', 'inputs_sha256': inputs,
                'cached_source_root': cached_root, 'actual_readonly_source_root': str(root),
                'query_sha256': digest(log), 'outputs_sha256': {str(path): digest(path) for path in generated}})
        report['status'] = 'pass'
    except Exception as error:
        report['failures'].append(str(error))
        raise
    finally:
        (args.output / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'status': report['status'], 'scope': report['scope']}))


if __name__ == '__main__':
    main()
