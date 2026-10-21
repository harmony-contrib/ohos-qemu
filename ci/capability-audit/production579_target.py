"""Finite actual package context for normal producers; no resource constructor."""
from pathlib import Path
import hashlib
import json
import tarfile

from batch_system_build_runtime_helpers import target_spec


def require(value, message):
    if not value:
        raise ValueError(message)


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate actual manifest key')
        result[key] = value
    return result


def context(document):
    require(type(document) is dict, 'actual complete archive manifest required')
    product = document['product']; target = target_spec(product)
    device = document['device_type']
    require(device in ('phone', '2in1') and document['guest_arch'] == target['arch'] and
        document['kernel'] == target['kernel'] and document['qemu_unix'] == target['qemu'] and
        document['device_type_profile'] == 'qemu_' + device + '_full_source',
        'actual package product/arch/full-device metadata differs')
    return dict(product=product, arch=target['arch'], device=device,
        metadata_relative='vendor/ohemu/virt/virt_' + device + '_full.meta.json',
        physical_staging='out/' + product + '/packages/phone',
        package_root='openharmony-qemu-' + target['arch'] + '-' + product + '-' + device,
        abi={'arm64':'arm64-v8a', 'armv7a':'armeabi-v7a', 'x86_64':'x86_64'}[target['arch']])


def archive_manifest(path):
    """Read the actual single bounded root manifest, never invent its fields."""
    path = Path(path)
    require(path.is_absolute() and path.is_file() and not path.is_symlink(), 'actual archive required')
    member = path.name.removesuffix('.tar.gz') + '/manifest.json'
    require(path.name.endswith('.tar.gz'), 'actual normal package name required')
    with tarfile.open(path, 'r:gz') as stream:
        matches = [row for row in stream if row.name == member]
        require(len(matches) == 1 and matches[0].isfile() and 0 < matches[0].size <= 4 * 1024 * 1024,
            'one bounded regular actual package manifest required')
        source = stream.extractfile(matches[0])
        require(source is not None, 'actual package manifest stream absent')
        with source:
            raw = source.read()
    document = json.loads(raw, object_pairs_hook=unique)
    actual = context(document)
    require(member == actual['package_root'] + '/manifest.json', 'actual package basename/context differs')
    return dict(member=member, raw=raw, document=document, context=actual,
        sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))


def bound_profile(path, expected_sha256):
    path = Path(path)
    require(path.is_absolute() and path.is_file() and not path.is_symlink() and
        hashlib.sha256(path.read_bytes()).hexdigest() == expected_sha256,
        'actual full installed profile external hash differs')
    value = json.loads(path.read_text(), object_pairs_hook=unique)
    from batch_system_build_runtime_helpers import validate_installed_profile
    validate_installed_profile(value)
    return value
