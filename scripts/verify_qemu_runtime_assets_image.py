#!/usr/bin/env python3
"""Bind actual external Sensor VDI and trusted calendar assets to both images.

Offline static evidence only. HDF loading, actual Sensor delivery and public
KnowledgeContent data/permissions still require new-package runtime acceptance.
"""
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
from prepare_qemu_sensor_runtime import FILES as SENSOR_FILES
from prepare_qemu_knowledge_resource import CONTRACT, ASSET, MARKER, contract
from verify_alsa_config_image import debugfs_path, file_sha256
from verify_runtime_elf_contract import read_elf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'patches/lib'))
from sensor_features import EXPECTED, validate as verify_features

PRODUCTS = {'arm64_virt': (2, 183), 'armv7a_virt': (1, 40), 'x86_64_virt': (2, 62)}
COMPONENT = ROOT / 'patches/common/drivers/peripheral/sensor/qemu_external'


def regular(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('regular runtime asset/provenance required: ' + str(path))
    return path


def source_hashes():
    manifest = json.loads((COMPONENT / 'manifest.json').read_text())
    return {**{n: row['after'] for n, row in manifest['originals'].items()},
            **{n: row['sha256'] for n, row in manifest['files'].items()}}


def recipe():
    paths = [Path(__file__), ROOT / 'scripts/prepare_qemu_sensor_runtime.py',
             ROOT / 'scripts/prepare_qemu_knowledge_resource.py', COMPONENT / 'manifest.json',
             ROOT / 'patches/lib/sensor_features.py']
    return {str(p.relative_to(ROOT)): file_sha256(regular(p)) for p in paths}


def elf(path, product):
    cls, machine = PRODUCTS[product]
    data = regular(path).read_bytes()
    if (len(data) < 64 or data[:7] != b'\x7fELF' + bytes((cls, 1, 1)) or
            struct.unpack_from('<H', data, 16)[0] != 3 or struct.unpack_from('<H', data, 18)[0] != machine or
            b'qemu_external_sensor\0' not in data):
        raise ValueError('actual external Sensor VDI ELF/tag/ABI required')
    if 'hdfVdiDesc' not in read_elf(path).defined:
        raise ValueError('Sensor VDI does not export the actual HDF descriptor')


def inventory(source, product):
    observed = {n: file_sha256(regular(source / n)) for n in source_hashes()}
    if observed != source_hashes():
        raise ValueError('actual Sensor source differs from complete current component')
    features = json.loads(regular(source / 'out/preloader' / product / 'features.json').read_text())['features']
    verify_features(features, 'phone')  # Both full device profiles require these same exact features.
    ninja = source / 'out' / product / 'obj/drivers/peripheral/sensor/hdi_impl/libhdi_sensor_impl.ninja'
    graph = regular(ninja).read_text()
    if any('/' + name + '.o' not in graph for name in ('qemu_sensor_input', 'qemu_sensor_vdi')):
        raise ValueError('fresh product GN did not select both actual external Sensor sources')
    libdir = 'lib' if product == 'armv7a_virt' else 'lib64'
    library = source / 'out' / product / 'packages/phone/vendor' / libdir / 'libhdi_sensor_impl.z.so'
    elf(library, product)
    init_name = 'vendor/ohemu/virt/etc/qemu_sensor_input.cfg'
    if regular(source / init_name).read_bytes() != SENSOR_FILES[init_name].encode():
        raise ValueError('current dedicated Sensor init configuration missing')
    metadata = json.loads(regular(source / MARKER).read_text())
    data = regular(source / ASSET).read_bytes() if metadata['asset_sha256'] is not None else None
    if (data is not None and hashlib.sha256(data).hexdigest() != metadata['asset_sha256']) or regular(source / CONTRACT).read_bytes() != contract(data):
        raise ValueError('trusted calendar resource differs from actual source provenance')
    payloads = {'sensor.so': library, 'sensor-init.json': source / init_name, 'resource.json': source / CONTRACT}
    if data is not None:
        payloads['holidays.ics'] = source / ASSET
    value = {'schema_version': 1, 'product': product, 'recipe': recipe(), 'source_sha256': observed,
             'features': {n: features[n] for n in EXPECTED}, 'sensor_GN_sha256': file_sha256(ninja),
             'calendar': metadata, 'files_sha256': {n: file_sha256(regular(p)) for n, p in payloads.items()},
             'first_artifact_behavior_gate_passed': False}
    return value, payloads


def check_inventory(value, product, directory):
    verify_features(value.get('features', {}), 'phone')
    if (value.get('schema_version') != 1 or value.get('product') != product or value.get('recipe') != recipe() or
            value.get('source_sha256') != source_hashes() or value.get('features') != EXPECTED or
            value.get('first_artifact_behavior_gate_passed') is not False or
            re.fullmatch('[0-9a-f]{64}', value.get('sensor_GN_sha256', '')) is None):
        raise ValueError('runtime asset source/build inventory is stale or incomplete')
    files = value.get('files_sha256', {})
    expected = {'sensor.so', 'sensor-init.json', 'resource.json'}
    if value['calendar']['asset_sha256'] is not None:
        expected.add('holidays.ics')
    if set(files) != expected or any(file_sha256(regular(directory / n)) != h for n, h in files.items()):
        raise ValueError('packaged runtime asset provenance is missing, changed or unexpected')
    init_name = 'vendor/ohemu/virt/etc/qemu_sensor_input.cfg'
    if (directory / 'sensor-init.json').read_bytes() != SENSOR_FILES[init_name].encode():
        raise ValueError('packaged Sensor init provenance differs from current dedicated configuration')
    data = (directory / 'holidays.ics').read_bytes() if 'holidays.ics' in expected else None
    if (directory / 'resource.json').read_bytes() != contract(data) or value['calendar']['asset_sha256'] != (
            hashlib.sha256(data).hexdigest() if data is not None else None):
        raise ValueError('calendar contract/actual resource/source digest disagree')
    elf(directory / 'sensor.so', product)


def exists(image, candidates, executable):
    for name in candidates:
        result = subprocess.run([executable, '-R', 'stat ' + name, str(image)], capture_output=True, text=True, check=True)
        if re.search(r'(?m)^Inode: \d+\s+Type:', result.stdout):
            return True
    return False


def images(system, vendor, product, value, directory):
    executable = debugfs_path()
    libdir = 'lib' if product == 'armv7a_virt' else 'lib64'
    rows = {}
    with tempfile.TemporaryDirectory(prefix='qemu-runtime-image-') as temporary:
        scratch = Path(temporary)
        wanted = {'sensor.so': (vendor, tuple(p + '/' + libdir + '/libhdi_sensor_impl.z.so' for p in ('', '/vendor'))),
            'sensor-init.json': (system, ('/etc/init/qemu_sensor_input.cfg', '/system/etc/init/qemu_sensor_input.cfg')),
            'resource.json': (system, ('/etc/knowledge-content/resource.json', '/system/etc/knowledge-content/resource.json'))}
        calendar = ('/etc/knowledge-content/holidays.ics', '/system/etc/knowledge-content/holidays.ics')
        if 'holidays.ics' in value['files_sha256']:
            wanted['holidays.ics'] = system, calendar
        elif exists(system, calendar, executable):
            raise ValueError('unexpected unbound calendar data in the actual image')
        # HDF tries this product-specific filename first. An unused generic
        # implementation cannot satisfy this source-selected backend check.
        for image, prefixes in ((vendor, ('', '/vendor')), (system, ('', '/system'))):
            shadows = tuple(p + '/' + libdir + suffix + '/libhdi_product_sensor_impl.z.so'
                            for p in prefixes for suffix in ('', '/chipset-sdk', '/platformsdk'))
            if exists(image, shadows, executable):
                raise ValueError('higher-priority product Sensor VDI shadows the selected external implementation')
        for name, (image, candidates) in wanted.items():
            destination = scratch / name
            destination.mkdir()
            path, inode = dump_unique_file(image, candidates, destination, executable)
            if file_sha256(path) != value['files_sha256'][name]:
                raise ValueError('actual packaged runtime asset differs from current staging/source: ' + name)
            rows[name] = {**inode, 'sha256': file_sha256(path)}
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system-image', type=Path, required=True)
    parser.add_argument('--vendor-image', type=Path, required=True)
    parser.add_argument('--product', choices=PRODUCTS, required=True)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--source-root', type=Path)
    group.add_argument('--packaged-provenance', type=Path)
    parser.add_argument('--write-provenance', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = {'status': 'fail', 'scope': 'actual_Sensor_VDI_and_trusted_calendar_image_binding_ONLY_NOT_runtime',
              'first_artifact_behavior_gate_passed': False, 'failures': []}
    try:
        with tempfile.TemporaryDirectory(prefix='qemu-runtime-source-') as temporary:
            directory = args.packaged_provenance or Path(temporary)
            if args.source_root:
                value, payloads = inventory(args.source_root, args.product)
                for name, path in payloads.items():
                    shutil.copyfile(regular(path), directory / name)
                (directory / 'inventory.json').write_text(json.dumps(value, indent=2) + '\n')
            else:
                if args.write_provenance:
                    raise ValueError('write provenance requires current source mode')
                value = json.loads(regular(directory / 'inventory.json').read_text())
            check_inventory(value, args.product, directory)
            result['image_assets'] = images(args.system_image, args.vendor_image, args.product, value, directory)
            if args.write_provenance:
                shutil.copytree(directory, args.write_provenance)
            result.update(status='pass', product=args.product, inventory_sha256=file_sha256(directory / 'inventory.json'),
                system_image_sha256=file_sha256(args.system_image), vendor_image_sha256=file_sha256(args.vendor_image))
    except (OSError, ValueError, KeyError, TypeError, struct.error, subprocess.SubprocessError) as error:
        result['failures'].append(str(error))
    if args.output:
        args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
    return result['status'] != 'pass'


if __name__ == '__main__':
    raise SystemExit(main())
