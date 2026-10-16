#!/usr/bin/env python3
"""Force only the owned MSDP outputs to rebuild and retain a build witness."""
import argparse
import json
import os
import re
from pathlib import Path
import secrets
import time

import verify_qemu_msdp_image as M


def outputs(product):
    libdir = 'lib' if product == 'armv7a_virt' else 'lib64'
    objects = ['obj/' + M.BASE + '/' + unit for units in M.UNITS.values() for unit in units]
    libraries = [prefix + filename for filename in M.LIBRARIES.values() for prefix in
                 ('msdp/device_status/', 'lib.unstripped/msdp/device_status/', 'packages/phone/system/' + libdir + '/')]
    return objects + libraries


def write(path, value):
    temporary = path.with_name(path.name + '.' + secrets.token_hex(8))
    with temporary.open('x') as stream:json.dump(value, stream, indent=2);stream.write('\n')
    os.replace(temporary, path)


def begin(source, product):
    build = source / 'out' / product
    expected = M.source_hashes()
    if {n: M.file_sha256(M.regular(source / n)) for n in expected} != expected:
        raise ValueError('MSDP witness requires complete current sources')
    build.mkdir(parents=True, exist_ok=True)
    nonce = secrets.token_hex(16);archive = build / '.qemu-msdp-witness' / nonce;archive.mkdir(parents=True)
    value = {'schema_version': 1, 'phase': 'prepared', 'nonce': nonce, 'product': product,
             'source_sha256': expected, 'recipe': M.recipe(), 'start_ns': time.time_ns(), 'preserved': {}}
    # Preserve the previous attempt, including an old completion witness.
    # No general output cleanup, source deletion or unrelated target is allowed.
    for name in [*outputs(product), 'qemu-msdp-build-witness.json']:
        path = build / name
        if path.exists() or path.is_symlink():
            M.regular(path)
            destination = archive / name;destination.parent.mkdir(parents=True, exist_ok=True)
            value['preserved'][name] = {'sha256': M.file_sha256(path), 'path': str(destination)}
            os.replace(path, destination)
    write(archive / 'prepared.json', value)
    write(build / 'qemu-msdp-build-pending.json', value)
    return value


def finish(source, product, log):
    build = source / 'out' / product
    value = json.loads(M.regular(build / 'qemu-msdp-build-pending.json').read_text())
    if (value.get('phase') != 'prepared' or value.get('product') != product or value.get('recipe') != M.recipe() or
            value.get('source_sha256') != M.source_hashes()):
        raise ValueError('missing/stale MSDP build preparation')
    inventory, _ = M.inventory_without_witness(source, product)
    artifacts = {}
    for name in outputs(product):
        path = M.regular(build / name);stat = path.stat()
        if stat.st_mtime_ns < value['start_ns']:
            raise ValueError('MSDP output was not rebuilt in this attempt: ' + name)
        artifacts[name] = {'sha256': M.file_sha256(path), 'mtime_ns': stat.st_mtime_ns, 'bytes': stat.st_size}
    for filename in M.LIBRARIES.values():
        libdir = 'lib' if product == 'armv7a_virt' else 'lib64'
        if artifacts['msdp/device_status/' + filename]['sha256'] != artifacts[
                'packages/phone/system/' + libdir + '/' + filename]['sha256']:
            raise ValueError('staged MSDP DSO differs from this actual linked output')
    value.update(phase='completed', finished_ns=time.time_ns(), artifacts=artifacts,
                 graphs=inventory['graphs'], files_sha256={n: inventory['files_sha256'][n] for n in M.LIBRARIES.values()},
                 build_log={'path': str(log), 'sha256': M.file_sha256(M.regular(log))})
    check_completed(value, inventory)
    write(build / 'qemu-msdp-build-witness.json', value)
    return value


def check_completed(witness, inventory):
    product = inventory['product']
    if (witness.get('schema_version') != 1 or witness.get('phase') != 'completed' or
            witness.get('product') != product or witness.get('source_sha256') != inventory['source_sha256'] or
            witness.get('recipe') != M.recipe() or witness.get('graphs') != inventory['graphs'] or
            type(witness.get('start_ns')) is not int or witness['start_ns'] <= 0 or
            type(witness.get('finished_ns')) is not int or witness['finished_ns'] < witness['start_ns'] or
            re.fullmatch('[0-9a-f]{32}', witness.get('nonce', '')) is None or
            set(witness.get('artifacts', {})) != set(outputs(product))):
        raise ValueError('incomplete current MSDP actual-build witness')
    files = {name: inventory['files_sha256'][name] for name in M.LIBRARIES.values()}
    if witness.get('files_sha256') != files:raise ValueError('MSDP witness linked payload mismatch')
    for row in witness['artifacts'].values():
        if (re.fullmatch('[0-9a-f]{64}', row.get('sha256', '')) is None or
                type(row.get('mtime_ns')) is not int or row['mtime_ns'] < witness['start_ns'] or
                type(row.get('bytes')) is not int or row['bytes'] <= 0):
            raise ValueError('MSDP output predates this forced build')
    for name, graph in inventory['graphs'].items():
        for unit, checksum in graph['objects_sha256'].items():
            if witness['artifacts']['obj/' + M.BASE + '/' + unit]['sha256'] != checksum:
                raise ValueError('MSDP witness compiled object mismatch')
        filename = M.LIBRARIES[name];libdir = 'lib' if product == 'armv7a_virt' else 'lib64'
        for prefix in ('msdp/device_status/', 'packages/phone/system/' + libdir + '/'):
            if witness['artifacts'][prefix + filename]['sha256'] != files[filename]:
                raise ValueError('MSDP actual link/staging witness mismatch')
    if re.fullmatch('[0-9a-f]{64}', witness.get('build_log', {}).get('sha256', '')) is None:
        raise ValueError('MSDP actual build log is missing')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('phase', choices=('begin', 'finish'))
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--product', choices=M.PRODUCTS, required=True)
    parser.add_argument('--build-log', type=Path)
    args = parser.parse_args()
    if args.phase == 'finish' and args.build_log is None:parser.error('finish requires actual build log')
    value = begin(args.source_root.resolve(), args.product) if args.phase == 'begin' else finish(
        args.source_root.resolve(), args.product, args.build_log.resolve())
    print(json.dumps({'phase': value['phase'], 'nonce': value['nonce'], 'product': value['product']}))
