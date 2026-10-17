#!/usr/bin/env python3
"""Bind the packaged VPN programs/configuration to current source build inputs.

This is an offline packaging check. Connection, ownership, permissions and
cleanup still require acceptance in the newly packaged guest.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tarfile
import tempfile

from build_openvpn_ohos import digest, recipe_identity
from ext_image_entries import dump_unique_file
from prepare_qemu_openvpn_backend import COMPONENT, PROJECT, POLICY_BASE, POLICY_FILES, NATIVE_CFG, checked
from verify_alsa_config_image import debugfs_path

ROOT = Path(__file__).resolve().parents[1]
PRODUCTS = {'armv7a_virt': (1, 40), 'arm64_virt': (2, 183), 'x86_64_virt': (2, 62)}
LOGS = tuple(name + '.log' for name in (
    'port-check', 'port-apply', 'autoreconf', 'configure', 'make-compat',
    'make-openvpn', 'ELF-identity'))
PROGRAMS = ('qemu_openvpn', 'qemu_openvpn_service', 'qemu_openvpn_tun')
CONFIGS = {'etc/init/qemu_openvpn.cfg': 'qemu_openvpn.cfg',
           'etc/init/netsysnative.cfg': 'netsysnative.cfg',
           'etc/param/qemu_openvpn.para.dac': 'qemu_openvpn.para.dac'}
LICENSES = ('COPYING', 'COPYRIGHT.GPL')
IMAGE_FILES = tuple('bin/' + name for name in PROGRAMS) + tuple(CONFIGS) + tuple(
    'etc/licenses/qemu_openvpn/' + name for name in LICENSES)


def regular(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('regular VPN evidence file required: ' + str(path))
    return path


def payload_identity():
    return {p.name: digest(p) for p in sorted(COMPONENT.iterdir()) if p.is_file()}


def validate_staged_payloads(source):
    for name, sha in payload_identity().items():
        relative = (POLICY_BASE + POLICY_FILES[name] if name in POLICY_FILES else
                    NATIVE_CFG if name == 'netsysnative.cfg' else PROJECT + '/qemu_openvpn/' + name)
        target = checked(source, relative)
        if digest(regular(target)) != sha:
            raise ValueError('stale staged VPN source input: ' + str(target))


def record(path, product, executable=False):
    data = regular(path).read_bytes()
    result = {'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data)}
    if executable:
        cls, machine = PRODUCTS[product]
        if (len(data) < 64 or data[:7] != b'\x7fELF' + bytes((cls, 1, 1)) or
                struct.unpack_from('<H', data, 18)[0] != machine or
                struct.unpack_from('<H', data, 16)[0] not in (2, 3)):
            raise ValueError('wrong VPN executable ABI: ' + str(path))
        result['elf_machine'] = machine
    return result


def check_build(directory, product, require_product=True):
    build = json.loads(regular(directory / 'build-evidence.json').read_text())
    lock_path = ROOT / 'scripts/openvpn_source_lock.json'
    lock = json.loads(lock_path.read_text())
    if (build.get('schema_version') != 2 or
            build.get('component') != 'fixed source OpenVPN for QEMU OHOS' or
            build.get('status') != 'pass_source_build_ONLY_NOT_packaged_or_runtime' or
            build.get('product') != product or build.get('recipe') != recipe_identity() or
            build.get('source_lock_sha256') != digest(lock_path) or
            build.get('source_archive_sha256') != lock['archive_sha256'] or
            build.get('source_commit') != lock['commit'] or
            build.get('runtime_gate_passed') is not False or
            build.get('first_artifact_behavior_gate_passed') is not False or
            (require_product and build.get('product_build') is not True)):
        raise ValueError('VPN build differs from the current product/source recipe')
    main_lock = ROOT / 'scripts/openharmony_7_0_release_source_lock.json'
    projects = json.loads(main_lock.read_text())['projects']
    expected = [{**p, 'observed_head': p['revision']} for p in projects]
    main = build.get('main_source', {})
    if (main.get('source_lock_sha256') != digest(main_lock) or
            main.get('checked_projects') != len(expected) or main.get('projects') != expected):
        raise ValueError('VPN main source HEAD evidence differs from the fixed release')
    commands = build.get('commands', [])
    if [c.get('log') for c in commands] != list(LOGS):
        raise ValueError('complete VPN configure/compile/link evidence required')
    for c in commands:
        if c.get('exit_code') != 0 or digest(regular(directory / c['log'])) != c.get('sha256'):
            raise ValueError('changed or failed VPN build command: ' + c['log'])
    return build


def check_inventory(inventory, build, product, archive):
    if set(inventory) != set(IMAGE_FILES):
        raise ValueError('all three VPN programs, configuration and licenses required')
    for name, item in inventory.items():
        if (not isinstance(item.get('sha256'), str) or len(item['sha256']) != 64 or
                any(c not in '0123456789abcdef' for c in item['sha256']) or
                type(item.get('size')) is not int or item['size'] <= 0):
            raise ValueError('invalid VPN image inventory: ' + name)
        if name.startswith('bin/') and item.get('elf_machine') != PRODUCTS[product][1]:
            raise ValueError('VPN image inventory ABI mismatch')
    if inventory['bin/qemu_openvpn']['sha256'] != build.get('binary_sha256'):
        raise ValueError('packaged VPN differs from its actual source build')
    for name, payload in CONFIGS.items():
        if record(COMPONENT / payload, product) != inventory[name]:
            raise ValueError('VPN init/authorization input differs: ' + name)
    lock = json.loads((ROOT / 'scripts/openvpn_source_lock.json').read_text())
    if digest(regular(archive)) != lock['archive_sha256'] or archive.stat().st_size != lock['archive_bytes']:
        raise ValueError('pinned VPN source archive required in package provenance')
    # Read fixed named regular members, never extract caller-controlled paths.
    with tarfile.open(archive, 'r:gz') as source:
        for name in LICENSES:
            member = source.getmember('openvpn-' + lock['commit'] + '/' + name)
            if not member.isfile():
                raise ValueError('regular upstream VPN license required')
            data = source.extractfile(member).read()
            if inventory['etc/licenses/qemu_openvpn/' + name] != {
                    'sha256': hashlib.sha256(data).hexdigest(), 'size': len(data)}:
                raise ValueError('VPN license differs from its pinned source: ' + name)


def verify_image(image, inventory, product):
    result = {}
    with tempfile.TemporaryDirectory(prefix='qemu-vpn-image-') as scratch:
        for index, name in enumerate(IMAGE_FILES):
            directory = Path(scratch) / str(index)
            directory.mkdir()
            path, inode = dump_unique_file(image, tuple('/' + prefix + name
                for prefix in ('', 'system/')), directory, debugfs_path())
            actual = record(path, product, name.startswith('bin/'))
            if actual != inventory[name]:
                raise ValueError('installed VPN bytes differ from checked product output: ' + name)
            result[name] = {**actual, **inode}
    return result


def load_provenance(directory, product):
    manifest = json.loads(regular(directory / 'provenance.json').read_text())
    names = {'build-evidence.json', 'inventory.json', 'source.tar.gz', *LOGS}
    if (manifest.get('schema_version') != 1 or manifest.get('product') != product or
            manifest.get('runtime_gate_passed') is not False or
            manifest.get('backend_inputs_sha256') != payload_identity() or
            set(manifest.get('files', {})) != names):
        raise ValueError('invalid or stale VPN source/package provenance')
    for name in names:
        if digest(regular(directory / name)) != manifest['files'][name]:
            raise ValueError('changed VPN package provenance: ' + name)
    build = check_build(directory, product)
    inventory = json.loads((directory / 'inventory.json').read_text())
    check_inventory(inventory, build, product, directory / 'source.tar.gz')
    return inventory


def create_provenance(source, product, destination, image):
    output = source / 'out' / product
    generated = output / ('gen/' + PROJECT + '/qemu_openvpn/source-build')
    build = check_build(generated, product)
    # The complete installer stages the current helpers, GN, init and policy.
    validate_staged_payloads(source)
    paths = {'bin/qemu_openvpn': generated / 'openvpn'}
    paths.update({'bin/' + name: output / 'communication/netmanager_ext' / name
                  for name in PROGRAMS[1:]})
    paths.update({name: COMPONENT / payload for name, payload in CONFIGS.items()})
    paths.update({'etc/licenses/qemu_openvpn/' + name: generated / name for name in LICENSES})
    inventory = {name: record(path, product, name.startswith('bin/')) for name, path in paths.items()}
    archive = source / PROJECT / 'qemu_openvpn/upstream' / (
        'openvpn-' + build['source_commit'] + '.tar.gz')
    check_inventory(inventory, build, product, archive)
    result = verify_image(image, inventory, product)
    destination.mkdir(exist_ok=False)
    for name in ('build-evidence.json', *LOGS):
        shutil.copyfile(generated / name, destination / name)
    shutil.copyfile(archive, destination / 'source.tar.gz')
    (destination / 'inventory.json').write_text(json.dumps(inventory, indent=2) + '\n')
    names = ('build-evidence.json', 'inventory.json', 'source.tar.gz', *LOGS)
    manifest = {'schema_version': 1, 'product': product, 'runtime_gate_passed': False,
                'backend_inputs_sha256': payload_identity(),
                'files': {name: digest(destination / name) for name in names}}
    (destination / 'provenance.json').write_text(json.dumps(manifest, indent=2) + '\n')
    if any(record(path, product, name.startswith('bin/')) != inventory[name]
           for name, path in paths.items()):
        raise ValueError('VPN source outputs changed during packaging')
    load_provenance(destination, product)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--system-image', type=Path, required=True)
    parser.add_argument('--product', choices=PRODUCTS, required=True)
    parser.add_argument('--source-root', type=Path)
    parser.add_argument('--write-provenance', type=Path)
    parser.add_argument('--packaged-provenance', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    creating = bool(args.source_root and args.write_provenance)
    if creating == bool(args.packaged_provenance) or (not creating and
            any((args.source_root, args.write_provenance))):
        parser.error('use source-root/write-provenance together, or packaged-provenance')
    result = {'status': 'fail', 'product': args.product, 'runtime_behavior_tested': False,
              'first_artifact_behavior_gate_passed': False,
              'scope': 'offline current VPN source/ABI/image packaging ONLY', 'failures': []}
    try:
        before = args.system_image.stat()
        result['system_image_sha256'] = digest(args.system_image)
        result['files'] = (create_provenance(args.source_root, args.product,
            args.write_provenance, args.system_image) if creating else verify_image(
            args.system_image, load_provenance(args.packaged_provenance, args.product), args.product))
        after = args.system_image.stat()
        if (before.st_ino, before.st_size, before.st_mtime_ns) != (
                after.st_ino, after.st_size, after.st_mtime_ns):
            raise ValueError('system image changed during VPN packaging validation')
        result['status'] = 'pass'
    except (OSError, ValueError, KeyError, TypeError, tarfile.TarError, subprocess.SubprocessError) as error:
        result['failures'].append(str(error))
    if args.output:
        args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: result[key] for key in ('status', 'product', 'failures')}))
    return 0 if result['status'] == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
