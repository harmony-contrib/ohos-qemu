"""Exact ordinary caller provenance for default public AVCodec selections."""
import hashlib
import json
from pathlib import Path
import re
import struct
import zipfile

HERE = Path(__file__).resolve().parent
SCOPE = 'ordinary_default_AVC_MIME_and_name_48_challenged_pixels_NOT_HEVC_encoder_or_media_pipelines'
ABIS = {'arm64': ('arm64-v8a', 'aarch64-linux-ohos', 183, 2),
        'armv7a': ('armeabi-v7a', 'arm-linux-ohos', 40, 1),
        'x86_64': ('x86_64', 'x86_64-linux-ohos', 62, 2)}
SOURCES = ('avc_media_probe.ets', 'avc_media_hap_probe.cpp', 'probes/avc_media.cpp')
HEADERS = ('native_avbuffer.h', 'native_avbuffer_info.h', 'native_avcapability.h',
           'native_avcodec_videoencoder.h', 'native_avcodec_videodecoder.h', 'native_avcodec_base.h',
           'native_avcodec_videobase.h', 'native_avformat.h', 'native_averrors.h')


def sha(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('regular AVC contract input required: ' + str(path))
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source(run):
    if re.fullmatch('[0-9a-f]{32}', run or '') is None:
        raise ValueError('fresh AVC nonce required')
    return (HERE / SOURCES[0]).read_text().replace('__AVC_RUN_ID__', run)


def compile_command(project, sdk, arch):
    abi, triple, _, _ = ABIS[arch]
    native = Path(sdk).resolve() / 'native'
    flags = ['-march=armv7-a', '-mfloat-abi=softfp', '-mfpu=neon'] if arch == 'armv7a' else []
    return [str(native / 'llvm/bin/clang++'), '--target=' + triple, '--sysroot=' + str(native / 'sysroot'),
            *flags, '-std=c++17', '-shared', '-fPIC', '-O2', '-Wall', '-Wextra', '-Werror',
            str(HERE / SOURCES[1]), str(HERE / SOURCES[2]), '-lace_napi.z', '-lnative_media_venc',
            '-lnative_media_vdec', '-lnative_media_codecbase', '-lnative_media_core',
            '-o', str(Path(project).resolve() / 'entry/libs' / abi / 'libavcmediaprobe.so')]


def verify_elf(data, arch):
    _, _, machine, class_ = ABIS[arch]
    if (len(data) < 20 or data[:4] != b'\x7fELF' or data[4] != class_ or data[5] != 1 or
            struct.unpack_from('<H', data, 16)[0] != 3 or struct.unpack_from('<H', data, 18)[0] != machine):
        raise ValueError('actual AVC shared caller ELF ABI differs from this packaged architecture')


def inputs(project, sdk, arch, run):
    source(run)
    if arch not in ABIS:
        raise ValueError('supported AVC ABI required')
    project, sdk = Path(project).resolve(), Path(sdk).resolve()
    page = project / 'entry/src/main/ets/pages/Index.ets'
    module = project / 'entry/src/main/module.json5'
    if page.read_text() != source(run) or json.loads(module.read_text())['module'].get('requestPermissions') != []:
        raise ValueError('AVC caller source/nonce or zero-permission role changed')
    header_root = sdk / 'native/sysroot/usr/include/multimedia/player_framework'
    paths = [header_root / name for name in HEADERS]
    for component in ('native', 'ets'):
        path = sdk / component / 'oh-uni-package.json'
        metadata = json.loads(path.read_text())
        if (metadata.get('apiVersion') != '26' or metadata.get('releaseType') != 'Release' or
                metadata.get('platformVersion') != '26.0.0'):
            raise ValueError('actual API26 Release SDK required')
        paths.append(path)
    binary = project / 'entry/libs' / ABIS[arch][0] / 'libavcmediaprobe.so'
    verify_elf(binary.read_bytes(), arch)
    return {'schema_version': 1, 'scope': SCOPE, 'role': 'ordinary_app', 'request_permissions': [],
            'run_id': run, 'arch': arch, 'sdk': str(sdk), 'generated_source': str(page),
            'source_sha256': {name: sha(HERE / name) for name in SOURCES},
            'contract_sha256': sha(Path(__file__)), 'builder_sha256': sha(HERE / 'build_hap_probe.py'),
            'module_sha256': sha(module), 'generated_source_sha256': sha(page),
            'sdk_files_sha256': {str(path): sha(path) for path in paths},
            'native_compile_command': compile_command(project, sdk, arch),
            'native_library_sha256': sha(binary)}


def verify_inputs(value, run, arch):
    page = Path(value['generated_source'])
    if not page.is_absolute() or value != inputs(page.parents[5], value['sdk'], arch, run):
        raise ValueError('AVC compiled inputs/source/SDK/native ABI differ from this run')
    return value


def verify_hap(path, value, arch):
    name = 'libs/' + ABIS[arch][0] + '/libavcmediaprobe.so'
    with zipfile.ZipFile(path) as archive:
        if archive.namelist().count(name) != 1:
            raise ValueError('actual signed HAP must contain one exact AVC caller binary')
        data = archive.read(name)
        verify_elf(data, arch)
        if hashlib.sha256(data).hexdigest() != value['native_library_sha256']:
            raise ValueError('signed HAP AVC binary differs from actual compiled caller')
