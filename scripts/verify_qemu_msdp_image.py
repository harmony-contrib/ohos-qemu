#!/usr/bin/env python3
"""Bind the current real MSDP sources, feature selection and DSOs to an image."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import struct
import subprocess
import sys
import tempfile

from ext_image_entries import dump_unique_file
from verify_alsa_config_image import debugfs_path, file_sha256
from verify_runtime_elf_contract import read_elf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'patches/lib'))
from sensor_features import EXPECTED, validate as verify_features

PRODUCTS = {'arm64_virt': (2, 183), 'armv7a_virt': (1, 40), 'x86_64_virt': (2, 62)}
BASE = 'base/msdp/device_status'
COMPONENT = ROOT / 'patches/common' / BASE
LIBRARIES = {'algo': 'libdevicestatus_algo.z.so', 'service': 'libdevicestatus_service.z.so'}
GRAPHS = {'algo': 'libs/devicestatus_algo.ninja', 'service': 'services/devicestatus_service.ninja'}
REQUIRED_SYMBOLS = {'algo': {'Create', 'Destroy', '__cfi_check'},
                    'service': {'__cfi_check',
                        '_ZN4OHOS4Msdp12DeviceStatus18DelayedSpSingletonINS1_19DeviceStatusServiceEE9instance_E',
                        '_ZN4OHOS4Msdp12DeviceStatus18DelayedSpSingletonINS1_19DeviceStatusServiceEE6mutex_E'}}
UNITS = {'algo': ['libs/src/algorithm/devicestatus_algo/' + n + '.o' for n in
                  ('algo_absolute_still', 'algo_base', 'algo_horizontal', 'algo_vertical')] +
                 ['libs/src/datahub/devicestatus_algo/sensor_data_callback.o',
                  'libs/src/devicestatus_algo/devicestatus_algorithm_manager.o'],
         'service': ['services/native/src/devicestatus_service/' + n + '.o' for n in
                     ('devicestatus_manager', 'devicestatus_msdp_client_impl', 'devicestatus_service')]}


def unit_source(unit):
    parts = unit.split('/')
    return '/'.join(parts[:-2] + [parts[-1][:-2] + '.cpp'])


def compile_contract(command, product, unit, name):
    argv = shlex.split(command)
    if argv and Path(argv[0]).name == 'ccache':argv = argv[1:]
    target = {'arm64_virt': 'aarch64', 'armv7a_virt': 'arm', 'x86_64_virt': 'x86_64'}[product]
    if (not argv or argv[0] != '../../prebuilts/clang/ohos/linux-x86_64/llvm/bin/clang++' or
            any(s in argv for s in (';', '&&', '|')) or argv.count('-c') != 1 or argv.count('-o') != 1 or
            '--target=' + target + '-linux-ohos' not in argv or '-fsanitize=cfi' not in argv or
            '-fsanitize-cfi-cross-dso' not in argv or '-fno-exceptions' not in argv or '-fno-rtti' not in argv or
            not any(s.startswith('-flto') for s in argv) or
            argv[argv.index('-c') + 1] != '../../' + BASE + '/' + unit_source(unit) or
            argv[argv.index('-o') + 1] != 'obj/' + BASE + '/' + unit):
        raise ValueError('MSDP requires the actual complete protected product compile command')
    if name == 'service' and not {'-DDEVICE_STATUS_SENSOR_ENABLE', '-DDEVICE_STATUS_DISABLE_MOCK_FALLBACK'} <= set(argv):
        raise ValueError('MSDP compiler did not select real sensor without mock')


def graph_contract(text, name):
    for unit in UNITS[name]:
        start = 'build obj/' + BASE + '/' + unit + ': cxx ../../' + BASE + '/' + unit_source(unit)
        if sum(line.startswith(start + ' ') or line == start for line in text.splitlines()) != 1:
            raise ValueError('MSDP graph lacks unique actual source/object rule')
    links = [line for line in text.splitlines() if line.startswith('build msdp/device_status/' + LIBRARIES[name] + ' ')]
    if len(links) != 1 or ': solink ' not in links[0] or any('obj/' + BASE + '/' + unit not in links[0] for unit in UNITS[name]):
        raise ValueError('MSDP graph lacks actual complete object/link binding')


def regular(path):
    if not path.is_file() or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError('regular MSDP build/provenance input required: ' + str(path))
    return path


def source_hashes():
    result = {}
    for name in ('sensor_input', 'public_still'):
        value = json.loads((COMPONENT / name / 'manifest.json').read_text())
        result.update({n: row['after'] for n, row in value['originals'].items()})
        result.update({n: row['sha256'] for n, row in value['files'].items()})
    return result


def recipe():
    files = [Path(__file__), ROOT / 'scripts/qemu_msdp_build_witness.py', ROOT / 'patches/lib/sensor_features.py']
    for name in ('sensor_input', 'public_still'):
        files.extend(p for p in (COMPONENT / name).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    return {str(p.relative_to(ROOT)): file_sha256(p) for p in sorted(files)}


def elf(path, product, cfi):
    data = regular(path).read_bytes();cls, machine = PRODUCTS[product]
    if (len(data) < 64 or data[:7] != b'\x7fELF' + bytes((cls, 1, 1)) or
            struct.unpack_from('<HH', data, 16) != (3, machine)):
        raise ValueError('actual MSDP DSO ABI/type differs')
    if cfi is not True:raise ValueError('all three standard MSDP products require cross-DSO CFI')
    if cls == 2:
        offset = struct.unpack_from('<Q', data, 32)[0]
        size, count = struct.unpack_from('<HH', data, 54)
        fmt = '<IIQQQQQQ'
    else:
        offset = struct.unpack_from('<I', data, 28)[0]
        size, count = struct.unpack_from('<HH', data, 42)
        fmt = '<IIIIIIII'
    if not count or size < struct.calcsize(fmt) or offset + size * count > len(data):
        raise ValueError('MSDP ELF lacks complete program headers')
    types = set();executable = False
    for index in range(count):
        values = struct.unpack_from(fmt, data, offset + index * size)
        kind = values[0];start = values[2] if cls == 2 else values[1]
        length = values[5] if cls == 2 else values[4]
        flags = values[1] if cls == 2 else values[6]
        if start + length > len(data):raise ValueError('truncated MSDP ELF segment')
        types.add(kind);executable |= kind == 1 and bool(flags & 1) and length > 0
    info = read_elf(path)
    required = REQUIRED_SYMBOLS['algo' if path.name == LIBRARIES['algo'] else 'service']
    if not {1, 2} <= types or not executable or not required <= info.defined:
        raise ValueError('MSDP ELF lacks executable/dynamic segments or actual current implementation/CFI symbols')


def inventory_without_witness(source, product):
    expected = source_hashes()
    if {n: file_sha256(regular(source / n)) for n in expected} != expected:
        raise ValueError('MSDP complete current source composition required')
    features = json.loads(regular(source / 'out/preloader' / product / 'features.json').read_text())['features']
    verify_features(features, 'phone')
    build = source / 'out' / product;libdir = 'lib' if product == 'armv7a_virt' else 'lib64'
    graphs = {};payloads = {}
    for name, filename in LIBRARIES.items():
        graph = regular(build / 'obj' / BASE / GRAPHS[name]);text = graph.read_text()
        graph_contract(text, name)
        if name == 'service' and any('-D' + flag not in text for flag in
                ('DEVICE_STATUS_SENSOR_ENABLE', 'DEVICE_STATUS_DISABLE_MOCK_FALLBACK')):
            raise ValueError('MSDP service GN does not select real sensor without mock fallback')
        cfi = '-fsanitize=cfi' in text
        library = regular(build / 'packages/phone/system' / libdir / filename)
        elf(library, product, cfi)
        objects = {unit: file_sha256(regular(build / 'obj' / BASE / unit)) for unit in UNITS[name]}
        # Retain the actual complete compiler commands selected by this fresh
        # graph, rather than inventing a command from a source-name list.
        commands = {}
        for unit in UNITS[name]:
            command = subprocess.check_output([str(source / 'prebuilts/build-tools/linux-x86/bin/ninja'),
                '-w', 'dupbuild=warn', '-C', str(build), '-t', 'commands', '-s', 'obj/' + BASE + '/' + unit],
                text=True, timeout=180).splitlines()[-1]
            if ' -c ' not in command:raise ValueError('MSDP actual compile command missing')
            compile_contract(command, product, unit, name)
            commands[unit] = command
        graphs[name] = {'sha256': file_sha256(graph), 'objects_sha256': objects,
                        'compile_commands': commands, 'cross_dso_cfi': cfi}
        payloads[filename] = library
        payloads[name + '.ninja'] = graph
    return {'schema_version': 1, 'product': product, 'source_sha256': expected, 'recipe': recipe(),
            'features': {n: features[n] for n in EXPECTED}, 'graphs': graphs,
            'files_sha256': {n: file_sha256(p) for n, p in payloads.items()},
            'first_artifact_behavior_gate_passed': False}, payloads


def inventory(source, product):
    value, payloads = inventory_without_witness(source, product)
    witness = regular(source / 'out' / product / 'qemu-msdp-build-witness.json')
    payloads['build-witness.json'] = witness
    value['files_sha256']['build-witness.json'] = file_sha256(witness)
    log = regular(Path(json.loads(witness.read_text())['build_log']['path']))
    payloads['build-log.txt'] = log
    value['files_sha256']['build-log.txt'] = file_sha256(log)
    return value, payloads


def check_inventory(value, product, directory):
    verify_features(value.get('features', {}), 'phone')
    if (value.get('schema_version') != 1 or value.get('product') != product or value.get('recipe') != recipe() or
            value.get('source_sha256') != source_hashes() or value.get('features') != EXPECTED or
            value.get('first_artifact_behavior_gate_passed') is not False or
            set(value.get('graphs', {})) != set(GRAPHS) or
            set(value.get('files_sha256', {})) != set(LIBRARIES.values()) |
                {'build-witness.json', 'build-log.txt', 'algo.ninja', 'service.ninja'}):
        raise ValueError('stale/incomplete MSDP source inventory')
    for name, filename in LIBRARIES.items():
        graph = value['graphs'][name]
        if (re.fullmatch('[0-9a-f]{64}', graph.get('sha256', '')) is None or
                set(graph.get('objects_sha256', {})) != set(UNITS[name]) or
                set(graph.get('compile_commands', {})) != set(UNITS[name]) or graph.get('cross_dso_cfi') is not True or
                any(re.fullmatch('[0-9a-f]{64}', h) is None for h in graph['objects_sha256'].values()) or
                any(' -c ' not in c for c in graph['compile_commands'].values())):
            raise ValueError('actual MSDP graph/objects/commands missing')
        raw_graph = regular(directory / (name + '.ninja'))
        if file_sha256(raw_graph) != graph['sha256'] or file_sha256(raw_graph) != value['files_sha256'][name + '.ninja']:
            raise ValueError('MSDP actual product graph bytes changed')
        graph_contract(raw_graph.read_text(), name)
        for unit, command in graph['compile_commands'].items():compile_contract(command, product, unit, name)
        path = directory / filename
        if file_sha256(regular(path)) != value['files_sha256'][filename]:raise ValueError('MSDP DSO provenance changed')
        elf(path, product, graph['cross_dso_cfi'])
    witness = directory / 'build-witness.json'
    if file_sha256(regular(witness)) != value['files_sha256']['build-witness.json']:
        raise ValueError('MSDP build witness changed')
    from qemu_msdp_build_witness import check_completed
    check_completed(json.loads(witness.read_text()), value)
    log = regular(directory / 'build-log.txt')
    if file_sha256(log) != value['files_sha256']['build-log.txt'] or file_sha256(log) != json.loads(witness.read_text())['build_log']['sha256']:
        raise ValueError('MSDP actual full build log changed')
    text = log.read_text(errors='strict')
    for name in LIBRARIES:
        for unit in UNITS[name]:
            if not re.search(r'\bCXX\s+obj/' + re.escape(BASE + '/' + unit) + r'(?:\s|$)', text):
                raise ValueError('MSDP full build log omits forced source compilation: ' + unit)
        if not re.search(r'\bSOLINK\s+msdp/device_status/' + re.escape(LIBRARIES[name]) + r'(?:\s|$)', text):
            raise ValueError('MSDP full build log omits actual final link')


def images(image, product, value):
    libdir = 'lib' if product == 'armv7a_virt' else 'lib64';rows = {}
    with tempfile.TemporaryDirectory(prefix='msdp-image-') as temporary:
        for filename in LIBRARIES.values():
            scratch = Path(temporary) / filename;scratch.mkdir()
            path, inode = dump_unique_file(image, tuple(p + '/' + libdir + '/' + filename for p in ('', '/system')),
                                           scratch, debugfs_path())
            if file_sha256(path) != value['files_sha256'][filename]:raise ValueError('actual image MSDP DSO differs: ' + filename)
            rows[filename] = {**inode, 'sha256': file_sha256(path)}
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system-image', type=Path, required=True)
    parser.add_argument('--product', choices=PRODUCTS, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--source-root', type=Path);group.add_argument('--packaged-provenance', type=Path)
    parser.add_argument('--write-provenance', type=Path);parser.add_argument('--output', type=Path)
    args = parser.parse_args();result = {'status': 'fail', 'scope': 'current MSDP sources/GN/ELF/image ONLY NOT runtime',
        'first_artifact_behavior_gate_passed': False, 'failures': []}
    try:
        with tempfile.TemporaryDirectory(prefix='msdp-source-') as temporary:
            directory = args.packaged_provenance or Path(temporary)
            if args.source_root:
                value, payloads = inventory(args.source_root, args.product)
                for name, path in payloads.items():shutil.copy2(path, directory / name)
                (directory / 'inventory.json').write_text(json.dumps(value, indent=2) + '\n')
            else:
                if args.write_provenance:raise ValueError('write provenance requires source mode')
                value = json.loads(regular(directory / 'inventory.json').read_text())
            check_inventory(value, args.product, directory)
            result['image_assets'] = images(args.system_image, args.product, value)
            if args.write_provenance:shutil.copytree(directory, args.write_provenance)
            result.update(status='pass', product=args.product, inventory_sha256=file_sha256(directory / 'inventory.json'),
                          system_image_sha256=file_sha256(args.system_image))
    except (OSError, ValueError, KeyError, TypeError, IndexError, struct.error, subprocess.SubprocessError) as error:
        result['failures'].append(str(error))
    if args.output:args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
    return result['status'] != 'pass'


if __name__ == '__main__':raise SystemExit(main())
