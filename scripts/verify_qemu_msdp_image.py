#!/usr/bin/env python3
"""Bind the current real MSDP sources, feature selection and DSOs to an image."""
import argparse
import hashlib
import json
from pathlib import Path
import re
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
UNITS = {'algo': ['libs/src/algorithm/devicestatus_algo/' + n + '.o' for n in
                  ('algo_absolute_still', 'algo_base', 'algo_horizontal', 'algo_vertical')] +
                 ['libs/src/datahub/devicestatus_algo/sensor_data_callback.o',
                  'libs/src/devicestatus_algo/devicestatus_algorithm_manager.o'],
         'service': ['services/native/src/devicestatus_service/' + n + '.o' for n in
                     ('devicestatus_manager', 'devicestatus_msdp_client_impl', 'devicestatus_service')]}


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
    files = [Path(__file__), ROOT / 'patches/lib/sensor_features.py']
    for name in ('sensor_input', 'public_still'):
        files.extend(p for p in (COMPONENT / name).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    return {str(p.relative_to(ROOT)): file_sha256(p) for p in sorted(files)}


def elf(path, product, cfi):
    data = regular(path).read_bytes();cls, machine = PRODUCTS[product]
    if (len(data) < 64 or data[:7] != b'\x7fELF' + bytes((cls, 1, 1)) or
            struct.unpack_from('<HH', data, 16) != (3, machine)):
        raise ValueError('actual MSDP DSO ABI/type differs')
    if cfi and '__cfi_check' not in read_elf(path).defined:
        raise ValueError('MSDP product selected cross-DSO CFI but ELF lacks __cfi_check')


def inventory(source, product):
    expected = source_hashes()
    if {n: file_sha256(regular(source / n)) for n in expected} != expected:
        raise ValueError('MSDP complete current source composition required')
    features = json.loads(regular(source / 'out/preloader' / product / 'features.json').read_text())['features']
    verify_features(features, 'phone')
    build = source / 'out' / product;libdir = 'lib' if product == 'armv7a_virt' else 'lib64'
    graphs = {};payloads = {}
    for name, filename in LIBRARIES.items():
        graph = regular(build / 'obj' / BASE / GRAPHS[name]);text = graph.read_text()
        if any('obj/' + BASE + '/' + unit not in text for unit in UNITS[name]):
            raise ValueError('MSDP GN omitted actual current unit: ' + name)
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
            commands[unit] = command
        graphs[name] = {'sha256': file_sha256(graph), 'objects_sha256': objects,
                        'compile_commands': commands, 'cross_dso_cfi': cfi}
        payloads[filename] = library
    return {'schema_version': 1, 'product': product, 'source_sha256': expected, 'recipe': recipe(),
            'features': {n: features[n] for n in EXPECTED}, 'graphs': graphs,
            'files_sha256': {n: file_sha256(p) for n, p in payloads.items()},
            'first_artifact_behavior_gate_passed': False}, payloads


def check_inventory(value, product, directory):
    verify_features(value.get('features', {}), 'phone')
    if (value.get('schema_version') != 1 or value.get('product') != product or value.get('recipe') != recipe() or
            value.get('source_sha256') != source_hashes() or value.get('features') != EXPECTED or
            value.get('first_artifact_behavior_gate_passed') is not False or
            set(value.get('graphs', {})) != set(GRAPHS) or set(value.get('files_sha256', {})) != set(LIBRARIES.values())):
        raise ValueError('stale/incomplete MSDP source inventory')
    for name, filename in LIBRARIES.items():
        graph = value['graphs'][name]
        if (re.fullmatch('[0-9a-f]{64}', graph.get('sha256', '')) is None or
                set(graph.get('objects_sha256', {})) != set(UNITS[name]) or
                set(graph.get('compile_commands', {})) != set(UNITS[name]) or type(graph.get('cross_dso_cfi')) is not bool or
                any(re.fullmatch('[0-9a-f]{64}', h) is None for h in graph['objects_sha256'].values()) or
                any(' -c ' not in c for c in graph['compile_commands'].values())):
            raise ValueError('actual MSDP graph/objects/commands missing')
        path = directory / filename
        if file_sha256(regular(path)) != value['files_sha256'][filename]:raise ValueError('MSDP DSO provenance changed')
        elf(path, product, graph['cross_dso_cfi'])


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
