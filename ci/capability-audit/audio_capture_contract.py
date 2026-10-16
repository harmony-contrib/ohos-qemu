"""Bind the public microphone caller to its ordinary HAP, SDK and fresh run."""
import json
from pathlib import Path
import re
import zipfile

from avc_media_contract import ABIS, runtime_identity, sha, verify_elf

HERE = Path(__file__).resolve().parent
SCOPE = 'ordinary_public_MIC_Capturer_PCM_lifecycle_timestamps_with_independent_external_challenge'
SOURCES = ('batch_media_audio_capture_probe.ets', 'batch_media_audio_capture_hap.cpp',
           'batch_media_audio_capture_probe.cpp')
PERMISSIONS = [{'name': 'ohos.permission.MICROPHONE', 'reason': '$string:permission_reason',
                'usedScene': {'abilities': ['EntryAbility'], 'when': 'inuse'}}]


def source(run, denied=False):
    if re.fullmatch('[0-9a-f]{32}', run or '') is None or type(denied) is not bool:
        raise ValueError('fresh microphone run id and explicit permission expectation required')
    return (HERE / SOURCES[0]).read_text().replace('__BATCH_MEDIA_CAPTURE_RUN_ID__', run).replace(
        '__BATCH_MEDIA_CAPTURE_EXPECT_DENIED__', str(denied).lower())


def compile_command(project, sdk, arch):
    abi, triple, _, _ = ABIS[arch]
    native = Path(sdk).resolve() / 'native'
    flags = ['-march=armv7-a', '-mfloat-abi=softfp', '-mfpu=neon'] if arch == 'armv7a' else []
    return [str(native / 'llvm/bin/clang++'), '--target=' + triple, '--sysroot=' + str(native / 'sysroot'),
            *flags, '-std=c++17', '-pthread', '-shared', '-fPIC', '-O2', '-Wall', '-Wextra', '-Werror',
            str(HERE / SOURCES[1]), str(HERE / SOURCES[2]), '-lace_napi.z', '-lohaudio',
            '-o', str(Path(project).resolve() / 'entry/libs' / abi / 'libbatchmediacapture.so')]


def inputs(project, sdk, arch, run, denied=False):
    project, sdk = Path(project).resolve(), Path(sdk).resolve()
    page = project / 'entry/src/main/ets/pages/Index.ets'
    module = project / 'entry/src/main/module.json5'
    if (page.read_text() != source(run, denied) or
            json.loads(module.read_text())['module'].get('requestPermissions') != PERMISSIONS):
        raise ValueError('public microphone caller source/permissions differ')
    paths = sorted((sdk / 'native/sysroot/usr/include/ohaudio').glob('*.h'))
    if not {'native_audiocapturer.h', 'native_audiostreambuilder.h'} <= {p.name for p in paths}:
        raise ValueError('actual public OHAudio SDK headers required')
    for component in ('native', 'ets'):
        path = sdk / component / 'oh-uni-package.json'
        metadata = json.loads(path.read_text())
        if (metadata.get('apiVersion') != '26' or metadata.get('releaseType') != 'Release' or
                metadata.get('platformVersion') != '26.0.0'):
            raise ValueError('public capture requires actual API26 Release SDK')
        paths.append(path)
    binary = project / 'entry/libs' / ABIS[arch][0] / 'libbatchmediacapture.so'
    verify_elf(binary.read_bytes(), arch)
    return {'schema_version': 1, 'scope': SCOPE, 'role': 'ordinary_app', 'run_id': run, 'arch': arch,
            'expected_denied': denied, 'request_permissions': PERMISSIONS, 'sdk': str(sdk),
            'generated_source': str(page), 'generated_source_sha256': sha(page), 'module_sha256': sha(module),
            'source_sha256': {name: sha(HERE / name) for name in SOURCES},
            'contract_sha256': sha(Path(__file__)), 'builder_sha256': sha(HERE / 'build_hap_probe.py'),
            'sdk_files_sha256': {str(path): sha(path) for path in paths},
            'native_compile_command': compile_command(project, sdk, arch),
            'native_library_sha256': sha(binary), 'native_runtime_sha256': runtime_identity(binary.read_bytes(), arch)}


def verify_inputs(value, run, arch, denied=False):
    page = Path(value['generated_source'])
    if not page.is_absolute() or value != inputs(page.parents[5], value['sdk'], arch, run, denied):
        raise ValueError('microphone compiled source/SDK/binary do not match this run')
    return value


def verify_hap(path, value, arch):
    name = 'libs/' + ABIS[arch][0] + '/libbatchmediacapture.so'
    with zipfile.ZipFile(path) as archive:
        if archive.namelist().count(name) != 1 or archive.namelist().count('module.json') != 1:
            raise ValueError('one compiled public microphone library/module required in actual HAP')
        data = archive.read(name)
        if runtime_identity(data, arch) != value['native_runtime_sha256']:
            raise ValueError('actual HAP microphone code/data differ from compiled caller')
        module = json.loads(archive.read('module.json'))
        permissions = module.get('module', {}).get('requestPermissions', [])
        normalized = []
        for permission in permissions:
            item = dict(permission)
            resource_id = item.pop('reasonId', None)
            if resource_id is not None and (type(resource_id) is not int or resource_id <= 0):
                raise ValueError('invalid compiled microphone reason resource')
            normalized.append(item)
        if normalized != PERMISSIONS:
            raise ValueError('compiled HAP microphone permission declaration differs')
