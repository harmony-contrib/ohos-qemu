#!/usr/bin/env python3
"""Pinned QEMU AudioPolicy XML contract; not PCM or hardware acceptance."""
import argparse
import hashlib
from pathlib import Path
import subprocess
import xml.etree.ElementTree as ET

VENDOR_REVISION = 'b56c5a95ec590543691278b85afe9fe228744163'
FRAMEWORK_REVISION = '6932fa64335b8272ca4a59de7808ab0d6c9eae7a'
XML_PATH = 'virt/hals/audio/config/audio_policy_config_new.xml'
ORIGINAL_SHA256 = 'fc49bb846bf8a6455a150ebaac08ec8661dba7aa4ee400797e0819bc68aa62c1'
PREVIOUS_REPAIRED_SHA256 = '5adbfe3e7366d3cd20cfe2091cda8b295ecf1a889e3b4db4aef3a8c19afbf038'
REPAIRED_SHA256 = 'de3498e4246c439d27eb435237dda795ad73c1ff79eb942401e7219af5e35d04'
FRAMEWORK_INPUTS = {
    'services/audio_policy/server/infra/config/parser/src/audio_policy_config_parser.cpp':
        '500f0837e5fa0a9e0b6504bd19836feccb1e28a214f2dbc637ce9f340a8a460c',
    'services/audio_policy/server/domain/pipe/src/audio_definition_adapter_info.cpp':
        '4d6be0be54c0248847347b7118fae27e909b419c43dd5aeb635f8a26eacfc14a',
    'services/audio_policy/server/domain/pipe/src/audio_definition_policy_utils.cpp':
        '22607fdf53914cb057018c37eaea808cc226c7fe17ea721f5db7e6fcd93cf1b0',
}
ROUTES = {
    ('primary', 'primary_output'): ('output', 'Speaker_Out,Wired_Headset_Out,Wired_Headphones_Out'),
    ('primary', 'primary_input'): ('input', 'Builtin_Mic_In,Wired_Headset_In'),
    ('a2dp', 'a2dp_output'): ('output', 'Bt_A2dp_Out'),
    ('remote', 'distributed_output'): ('output', 'Distributed_Out'),
    ('remote', 'distributed_input'): ('input', 'Distributed_In'),
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def validate_document(data, require_hash=True):
    if require_hash and sha(data) != REPAIRED_SHA256:
        raise ValueError('AudioPolicy XML differs from the pinned repaired configuration')
    root = ET.fromstring(data)
    if root.tag != 'audioPolicyConfiguration' or root.get('version') != '2.0':
        raise ValueError('AudioPolicy requires the 7.0 pipe schema, version2.0')
    observed, mapping = {}, {}
    for adapter in root.findall('./adapters/adapter'):
        name = adapter.get('name')
        devices = {device.get('name'): device for device in adapter.findall('./devices/device')}
        if len(devices) != len(adapter.findall('./devices/device')):
            raise ValueError('duplicate AudioPolicy device')
        for pipe in adapter.findall('./pipes/pipe'):
            key = (name, pipe.get('name'))
            if key not in ROUTES or key in observed:
                raise ValueError('unexpected/duplicate AudioPolicy pipe')
            role, expected_devices = ROUTES[key]
            expected_devices = set(expected_devices.split(','))
            flag = 'AUDIO_' + role.upper() + '_FLAG_NORMAL'
            flags = pipe.findall('./attributes/attribute[@name="flag"]')
            if pipe.get('role') != role or len(flags) != 1 or flags[0].get('value') != flag:
                raise ValueError('missing/incorrect normal route flag: ' + str(key))
            streams = pipe.findall('./streamProps/streamProp')
            if len(streams) != (3 if name == 'a2dp' else 1):
                raise ValueError('incomplete AudioPolicy stream properties')
            for stream in streams:
                support = {item.strip() for item in stream.get('supportDevices', '').split(',') if item.strip()}
                if support != expected_devices or not support.issubset(devices):
                    raise ValueError('missing/incorrect stream supportDevices: ' + str(key))
                for device_name in support:
                    device = devices[device_name]
                    if (device.get('role') != role or
                            pipe.get('name') not in device.get('supportPipes', '').split(',')):
                        raise ValueError('device/pipe route is not reciprocal')
                    mapping[(device_name, flag)] = pipe.get('name')
                if name == 'primary':
                    expected_rate = '48000' if key[1] == 'primary_input' else '44100'
                    expected_buffer = '8192' if key[1] == 'primary_input' else '4096'
                    if (stream.get('sampleRates') != expected_rate or stream.get('format') != 's16le' or
                            stream.get('bufferSize') != expected_buffer):
                        raise ValueError('primary capture/render format contract differs')
                sample_rate = int(stream.get('sampleRates', '0'))
                buffer_size = int(stream.get('bufferSize', '0'))
                sample_bytes = {'s16le': 2, 's24le': 3}.get(stream.get('format'), 0)
                if (sample_rate not in (44100, 48000, 96000) or
                        stream.get('channelLayout') != 'CH_LAYOUT_STEREO' or
                        sample_bytes == 0 or buffer_size <= 0 or buffer_size % (2 * sample_bytes) != 0 or
                        stream.get('buffer_size') is not None):
                    raise ValueError('invalid/ignored stream format or bufferSize')
            observed[key] = {'role': role, 'flag': flag, 'devices': sorted(expected_devices)}
    if set(observed) != set(ROUTES) or len(mapping) != 8:
        raise ValueError('incomplete AudioPolicy route/device map')
    default = root.find('./globalConfigs/defaultOutput')
    if default is None or default.attrib != {'adapter': 'primary', 'pipe': 'primary_output', 'device': 'Speaker'}:
        raise ValueError('default Speaker output was changed')
    return {'pipes': len(observed), 'device_routes': len(mapping), 'schema_version': '2.0',
            'routes': {adapter + '/' + pipe: value for (adapter, pipe), value in observed.items()}}


def real_file(root, relative):
    current = root
    for part in Path(relative).parts:
        current = current / part
        if current.is_symlink():
            raise ValueError('AudioPolicy input must not traverse a symlink: ' + str(current))
    if not current.is_file():
        raise ValueError('missing AudioPolicy source input: ' + str(current))
    return current


def validate_source(root, require_patched=False):
    vendor = root / 'vendor/ohemu'
    xml = real_file(root, 'vendor/ohemu/' + XML_PATH)
    revision = subprocess.check_output(['git', '-C', str(vendor), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != VENDOR_REVISION:
        raise ValueError('AudioPolicy repair requires pinned 7.0 vendor/ohemu revision')
    original = subprocess.check_output(['git', '-C', str(vendor), 'show', 'HEAD:' + XML_PATH])
    if sha(original) != ORIGINAL_SHA256:
        raise ValueError('unknown pinned vendor AudioPolicy XML')
    framework = root / 'foundation/multimedia/audio_framework'
    framework_revision = subprocess.check_output(['git', '-C', str(framework), 'rev-parse', 'HEAD'], text=True).strip()
    if framework_revision != FRAMEWORK_REVISION:
        raise ValueError('AudioPolicy repair requires pinned 7.0 audio_framework')
    for relative, expected in FRAMEWORK_INPUTS.items():
        if sha(real_file(root, 'foundation/multimedia/audio_framework/' + relative).read_bytes()) != expected:
            raise ValueError('AudioPolicy parser/map semantics changed; re-audit before patching')
    data = xml.read_bytes()
    accepted = (REPAIRED_SHA256,) if require_patched else (ORIGINAL_SHA256, PREVIOUS_REPAIRED_SHA256, REPAIRED_SHA256)
    if sha(data) not in accepted:
        raise ValueError('unknown AudioPolicy XML edits; preserving source')
    if sha(data) == REPAIRED_SHA256:
        return validate_document(data)
    return {'status': 'known_previous_requires_upgrade' if sha(data) == PREVIOUS_REPAIRED_SHA256 else 'known_original_requires_patch'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, required=True)
    parser.add_argument('--require-patched', action='store_true')
    args = parser.parse_args()
    validate_source(args.source_root.resolve(), args.require_patched)
    print('fixed 7.0 QEMU AudioPolicy source contract verified; not PCM behavior acceptance')


if __name__ == '__main__':
    main()
