#!/usr/bin/env python3
"""Compile/link whole VPN helpers with product client flags in private scratch.

The helper targets are new: this diagnostic borrows the actual product client's
compile flags. It does not claim fresh GN selection or newly packaged behavior.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess

from compile_always_on_vpn import TARGETS, query
from compile_native_repair_batch import PRODUCTS, verify_object
from compile_taskpool_thread_info import digest

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/communication/netmanager_ext/openvpn_backend/files'


def run(args):
    source = args.source_root.resolve()
    if any(not os.statvfs(p).f_flag & os.ST_RDONLY for p in (source, source / 'out')):
        raise ValueError('source and product output must be read-only')
    output = args.output.absolute()
    output.mkdir(parents=True, exist_ok=False)
    inputs = output / 'inputs'
    inputs.mkdir()
    originals = sorted(p for p in COMPONENT.iterdir() if p.suffix in ('.h', '.cpp'))
    checksums = {p.name: digest(p) for p in originals}
    for p in originals:
        shutil.copyfile(p, inputs / p.name)
    header_relative = 'foundation/communication/netmanager_ext/interfaces/innerkits/netvpnclient/include/networkvpn_client.h'
    private_root = output / 'client-candidate'
    header = private_root / header_relative
    header.parent.mkdir(parents=True)
    header_before = digest(source / header_relative)
    shutil.copyfile(source / header_relative, header)
    warning_component = ROOT / 'patches/common/foundation/communication/netmanager_ext/netvpn_callback_unused'
    for attempt in (1, 2):
        with (output / f'client-header-apply-{attempt}.log').open('xb') as log:
            subprocess.run(['bash', str(warning_component / 'apply.sh'), '--source-root', str(private_root)],
                           stdout=log, stderr=subprocess.STDOUT, check=True)
    overlay = output / 'client-headers.json'
    overlay.write_text(json.dumps({'version': 0, 'roots': [{'type': 'file',
        'name': str(source / header_relative), 'external-contents': str(header),
        'use-external-name': True}]}) + '\n')
    cwd = source / 'out' / args.product
    original = query(source, cwd, TARGETS[3], output / 'query.log')
    if Path(original[0]).name == 'ccache':
        original.pop(0)
    arch, machine, elf_class = PRODUCTS[args.product]
    if (Path(original[0]).name != 'clang++' or '--target=' + arch + '-linux-ohos' not in original or
            '-DSUPPORT_SYSVPN' not in original or
            any(original.count(k) != 1 for k in ('-c', '-o', '-MF'))):
        raise ValueError('actual SYSVPN-enabled product client command required')
    library = cwd / 'communication/netmanager_ext/libnet_vpn_manager_if.z.so'
    library_before = digest(library)
    report = {'status': 'fail', 'product': args.product,
              'scope': 'whole_native_helpers_product_client_flags_and_executable_links_ONLY_NOT_fresh_GN_selection_or_runtime',
              'original_product_argv': original, 'inputs_sha256': checksums,
              'library_sha256': library_before, 'objects': [],
              'actual_client_header_before_sha256': header_before,
              'current_client_header_sha256': digest(header),
              'client_header_component_sha256': {p.name: digest(p) for p in warning_component.iterdir() if p.is_file()},
              'first_artifact_behavior_gate_passed': False}

    def save():
        (output / 'evidence.json').write_text(json.dumps(report, indent=2) + '\n')

    for name in ('supervisor', 'tun_bridge'):
        row = {'unit': name, 'status': 'fail'}
        try:
            unit = inputs / (name + '.cpp')
            obj, dep = output / (name + '.o'), output / (name + '.d')
            argv = original[:]
            argv[argv.index('-c') + 1] = str(unit)
            argv[argv.index('-o') + 1] = str(obj)
            argv[argv.index('-MF') + 1] = str(dep)
            argv += ['-Wall', '-Wextra', '-Werror']
            argv += ['-ivfsoverlay', str(overlay)]
            row['compile_argv'] = argv
            log = output / (name + '-compile.log')
            with log.open('xb') as stream:
                result = subprocess.run(argv, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT,
                                        env=dict(os.environ, CCACHE_DISABLE='1'), timeout=600)
            row.update(compile_exit_code=result.returncode, compile_log_sha256=digest(log))
            if result.returncode:
                raise ValueError('complete native helper compilation failed')
            tools = source / 'prebuilts/clang/ohos/linux-x86_64/llvm/bin'
            row.update(verify_object(obj, tools / 'llvm-dis', arch, machine, elf_class))
            row['object_sha256'] = digest(obj)
            row['consumed_candidate_headers'] = [p for p in checksums if p.endswith('.h') and
                                                str(inputs / p) in dep.read_text()]
            if str(unit) not in dep.read_text() or str(header) not in dep.read_text() or not row['consumed_candidate_headers']:
                raise ValueError('actual current helper source/headers were not consumed')
            binary = output / name
            argv = [str(tools / 'clang++'), '--target=' + arch + '-linux-ohos',
                    '--sysroot=' + str(cwd / 'obj/third_party/musl'), str(obj), str(library),
                    '-Wl,-rpath-link=' + str(cwd / 'communication/netmanager_base'),
                    '-Wl,-rpath-link=' + str(cwd / 'communication/netmanager_ext'), '-o', str(binary)]
            row['link_argv'] = argv
            log = output / (name + '-link.log')
            with log.open('xb') as stream:
                result = subprocess.run(argv, cwd=cwd, stdout=stream, stderr=subprocess.STDOUT, timeout=600)
            row.update(link_exit_code=result.returncode, link_log_sha256=digest(log))
            if result.returncode:
                raise ValueError('actual native executable link failed')
            elf_header = binary.read_bytes()[:64]
            if elf_header[:6] != bytes((127, 69, 76, 70, elf_class, 1)) or int.from_bytes(elf_header[18:20], 'little') != machine:
                raise ValueError('linked executable has wrong actual ABI')
            row.update(status='pass', binary_sha256=digest(binary), dependency_sha256=digest(dep))
        except Exception as error:
            row['error'] = type(error).__name__ + ': ' + str(error)
        report['objects'].append(row)
        save()
    report['inputs_unchanged'] = (checksums == {p.name: digest(p) for p in originals} ==
                                  {p.name: digest(p) for p in inputs.iterdir()})
    report['library_unchanged'] = library_before == digest(library)
    report['client_header_inputs_unchanged'] = (digest(source / header_relative) == header_before and
        digest(header) == report['current_client_header_sha256'])
    if report['inputs_unchanged'] and report['library_unchanged'] and all(
            row['status'] == 'pass' for row in report['objects']) and report['client_header_inputs_unchanged']:
        report['status'] = 'pass'
    save()
    print(json.dumps({'status': report['status'], 'objects': len(report['objects'])}))
    return report['status'] == 'pass'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--product', choices=PRODUCTS, required=True)
    raise SystemExit(0 if run(parser.parse_args()) else 1)
