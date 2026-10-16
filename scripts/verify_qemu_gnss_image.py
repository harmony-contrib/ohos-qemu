#!/usr/bin/env python3
"""Bind real GNSS vendor, HDI bridge, service and standalone inputs to images.

This is static source/build/image evidence. Actual loading and public location
results still require the newly packaged guest and independent live input.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile

from ext_image_entries import dump_unique_file
from prepare_qemu_gnss_runtime import DIRECTORY, FILES, DEPENDENCY, BUILD
from verify_qemu_runtime_assets_image import regular, PRODUCTS
from verify_alsa_config_image import file_sha256 as sha, debugfs_path
from verify_runtime_elf_contract import read_elf

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / 'patches/common/device/qemu/external_gnss'
LOCATION = ROOT / 'patches/common/base/location/location/api26_runtime/source_states.json'
LIBRARIES = {'provider.so': ('vendor', 'vendorGnssAdapter.so'),
             'bridge.so': ('vendor', 'libgnss_interface_service_2.0.z.so'),
             'service.so': ('system', 'liblbsservice_gnss.z.so')}
GRAPHS = {
    'obj/device/qemu/common/virt_full/external_gnss/qemu_external_gnss.ninja':
        ('/qemu_gnss_input.o', '/qemu_gnss_vendor.o', 'vendorGnssAdapter.so'),
    'obj/drivers/peripheral/location/gnss/hdi_service/libgnss_interface_service_2.0.ninja':
        ('/gnss_interface_impl.o', '/location_vendor_interface.o'),
    'obj/base/location/location/services/location_gnss/gnss/lbsservice_gnss.ninja':
        ('/gnss_ability.o', '/gnss_event_callback.o'),
}


def recipe():
    return {str(p.relative_to(ROOT)): sha(regular(p)) for p in (
        Path(__file__), ROOT / 'scripts/prepare_qemu_gnss_runtime.py', COMPONENT / 'manifest.json', LOCATION,
        ROOT / 'scripts/ext_image_entries.py', ROOT / 'scripts/verify_runtime_elf_contract.py')}


def source_hashes():
    value = json.loads((COMPONENT / 'manifest.json').read_text())
    result = {**{n: r['after'] for n, r in value['originals'].items()},
              **{n: r['sha256'] for n, r in value['files'].items()}, **value['dependencies']}
    state = json.loads(LOCATION.read_text())
    result.update({state['project'] + '/' + n: h for n, h in state['states']['final'].items()
                   if n.startswith('services/location_gnss/gnss/')})
    return result


def elf(path, product, provider=False):
    raw = regular(path).read_bytes()
    cls, machine = PRODUCTS[product]
    if (len(raw) < 64 or raw[:7] != b'\x7fELF' + bytes((cls, 1, 1)) or
            struct.unpack_from('<H', raw, 16)[0] != 3 or read_elf(path).machine != machine):
        raise ValueError('actual native ABI GNSS shared library required')
    if provider and 'GnssVendorInterface' not in read_elf(path).defined:
        raise ValueError('vendor GNSS data interface is not exported')


def inventory(source, product):
    expected = source_hashes()
    if {n: sha(regular(source / n)) for n in expected} != expected:
        raise ValueError('actual GNSS source differs from complete current components')
    if regular(source / BUILD).read_text().count(DEPENDENCY) != 1:
        raise ValueError('actual QEMU device group lacks explicit GNSS runtime dependency')
    for name, content in FILES.items():
        if regular(source / name).read_bytes() != content.encode():
            raise ValueError('actual GNSS init/parameter/policy source differs')
    graph = {}
    for name, terms in GRAPHS.items():
        path = source / 'out' / product / name
        text = regular(path).read_text()
        if not all(term in text for term in terms):
            raise ValueError('fresh product GN omits the real GNSS target inputs: ' + name)
        graph[name] = sha(path)
    libdir = 'lib' if product == 'armv7a_virt' else 'lib64'
    payloads = {name: source / 'out' / product / 'packages/phone' / image / libdir / library
                for name, (image, library) in LIBRARIES.items()}
    payloads.update({'init.json': source / DIRECTORY / 'qemu_gnss_input.cfg',
                     'gnss.para': source / DIRECTORY / 'qemu_gnss.para'})
    for name in LIBRARIES:
        elf(payloads[name], product, name == 'provider.so')
    value = {'schema_version': 1, 'product': product, 'recipe': recipe(), 'source_sha256': expected,
             'GN_sha256': graph, 'files_sha256': {n: sha(regular(p)) for n, p in payloads.items()},
             'first_artifact_behavior_gate_passed': False}
    return value, payloads


def check_inventory(value, product, directory):
    if (type(value.get('schema_version')) is not int or value.get('schema_version') != 1 or value.get('product') != product or
            value.get('recipe') != recipe() or value.get('source_sha256') != source_hashes() or
            value.get('first_artifact_behavior_gate_passed') is not False or
            set(value.get('GN_sha256', {})) != set(GRAPHS) or
            any(re.fullmatch('[0-9a-f]{64}', h) is None for h in value['GN_sha256'].values()) or
            set(value.get('files_sha256', {})) != {*LIBRARIES, 'init.json', 'gnss.para'}):
        raise ValueError('GNSS source/build inventory is stale or incomplete')
    if any(sha(regular(directory / n)) != h for n, h in value['files_sha256'].items()):
        raise ValueError('GNSS packaged provenance changed')
    for name, original in [('init.json', 'qemu_gnss_input.cfg'), ('gnss.para', 'qemu_gnss.para')]:
        if (directory / name).read_bytes() != FILES[DIRECTORY + original].encode():
            raise ValueError('GNSS private input identity or standalone mode differs')
    for name in LIBRARIES:
        elf(directory / name, product, name == 'provider.so')


def images(system, vendor, product, value):
    libdir = 'lib' if product == 'armv7a_virt' else 'lib64'
    wanted = {name: (vendor if image == 'vendor' else system,
                    tuple(prefix + '/' + libdir + '/' + library for prefix in ('', '/' + image)))
              for name, (image, library) in LIBRARIES.items()}
    wanted.update({'init.json': (system, ('/etc/init/qemu_gnss_input.cfg', '/system/etc/init/qemu_gnss_input.cfg')),
                   'gnss.para': (system, ('/etc/param/qemu_gnss.para', '/system/etc/param/qemu_gnss.para'))})
    result = {}
    with tempfile.TemporaryDirectory(prefix='qemu-gnss-image-') as temporary:
        for index, (name, (image, paths)) in enumerate(wanted.items()):
            directory = Path(temporary) / str(index)
            directory.mkdir()
            path, inode = dump_unique_file(image, paths, directory, debugfs_path())
            if sha(path) != value['files_sha256'][name]:
                raise ValueError('actual installed GNSS bytes differ: ' + name)
            result[name] = {**inode, 'sha256': sha(path)}
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--system-image', type=Path, required=True)
    p.add_argument('--vendor-image', type=Path, required=True)
    p.add_argument('--product', choices=PRODUCTS, required=True)
    group = p.add_mutually_exclusive_group(required=True)
    group.add_argument('--source-root', type=Path)
    group.add_argument('--packaged-provenance', type=Path)
    p.add_argument('--write-provenance', type=Path)
    p.add_argument('--output', type=Path)
    a = p.parse_args()
    result = {'status': 'fail', 'scope': 'GNSS_source_build_image_binding_ONLY_NOT_loaded_or_public_location',
              'first_artifact_behavior_gate_passed': False, 'failures': []}
    try:
        with tempfile.TemporaryDirectory(prefix='qemu-gnss-source-') as temporary:
            directory = a.packaged_provenance or Path(temporary)
            if a.source_root:
                value, payloads = inventory(a.source_root, a.product)
                for name, source in payloads.items(): shutil.copyfile(regular(source), directory / name)
                (directory / 'inventory.json').write_text(json.dumps(value, indent=2) + '\n')
            else:
                if a.write_provenance: raise ValueError('write provenance requires source mode')
                value = json.loads(regular(directory / 'inventory.json').read_text())
            check_inventory(value, a.product, directory)
            result['image_assets'] = images(a.system_image, a.vendor_image, a.product, value)
            if a.write_provenance: shutil.copytree(directory, a.write_provenance)
            result.update(status='pass', product=a.product, inventory_sha256=sha(directory / 'inventory.json'),
                          system_image_sha256=sha(a.system_image), vendor_image_sha256=sha(a.vendor_image))
    except (OSError, ValueError, KeyError, TypeError, struct.error, subprocess.SubprocessError) as e:
        result['failures'].append(str(e))
    if a.output: a.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
    return result['status'] != 'pass'


if __name__ == '__main__': raise SystemExit(main())
