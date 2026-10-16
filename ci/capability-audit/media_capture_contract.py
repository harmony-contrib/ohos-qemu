"""Bind ordinary Recorder and audio-event HAPs to actual SDK/native input bytes."""
import json
from pathlib import Path
import re
import zipfile

from avc_media_contract import ABIS, runtime_identity, sha, verify_elf
from audio_capture_contract import PERMISSIONS as MIC

HERE = Path(__file__).resolve().parent
BUNDLES = ('org.harmonycontrib.capabilityaudit', 'org.harmonycontrib.capabilityauditfocus')
KINDS = {'recorder': ('batchmediarecorder', '-lavrecorder', '-lnative_window', '-lnative_buffer', '-lace_napi.z'),
         'audio-event': ('batchmediaaudioevent', '-lohaudio', '-lace_napi.z')}


def validate(kind, run, denied=False, mode=0, bundle=BUNDLES[0]):
    if (kind not in KINDS or re.fullmatch('[0-9a-f]{32}', run or '') is None or type(denied) is not bool or
            type(mode) is not int or mode not in (0, 1, 2) or bundle not in BUNDLES):
        raise ValueError('explicit ordinary media persona and fresh run required')
    if (kind == 'recorder' and (mode != 0 or bundle != BUNDLES[0]) or
            kind == 'audio-event' and (denied or bundle != BUNDLES[1 if mode == 2 else 0])):
        raise ValueError('media role/mode/bundle contract differs')


def names(kind):
    stem = 'batch_media_recorder' if kind == 'recorder' else 'batch_media_audio_event'
    return (stem + '_probe.ets', stem + '_hap.cpp', stem + '_probe.cpp')


def permissions(kind, mode=0):
    return MIC + ([{'name': 'ohos.permission.KEEP_BACKGROUND_RUNNING'}]
                  if kind == 'audio-event' and mode in (1, 2) else [])


def source(kind, run, denied=False, mode=0, bundle=BUNDLES[0]):
    validate(kind, run, denied, mode, bundle)
    text = (HERE / names(kind)[0]).read_text()
    if kind == 'recorder':
        return text.replace('__BATCH_MEDIA_RECORDER_RUN_ID__', run).replace(
            '__BATCH_MEDIA_RECORDER_EXPECT_DENIED__', str(denied).lower())
    return text.replace('__BATCH_MEDIA_AUDIO_EVENT_RUN_ID__', run).replace('__BATCH_MEDIA_AUDIO_EVENT_MODE__', str(mode))


def declaration(kind):
    return ('interface Probe { run: (runId: string, ' +
            ('expectedDenied: boolean) => boolean; ' if kind == 'recorder' else
             'mode: number) => boolean; status: (runId: string) => number; abort: (runId: string) => boolean; ') +
            '}\ndeclare const probe: Probe;\nexport default probe;\n')


def compile_command(project, sdk, arch, kind):
    abi, triple, _, _ = ABIS[arch]
    native = Path(sdk).resolve() / 'native'
    flags = ['-march=armv7-a', '-mfloat-abi=softfp', '-mfpu=neon'] if arch == 'armv7a' else []
    return [str(native / 'llvm/bin/clang++'), '--target=' + triple, '--sysroot=' + str(native / 'sysroot'),
            *flags, '-std=c++17', '-pthread', '-shared', '-fPIC', '-O2', '-Wall', '-Wextra', '-Werror',
            '-Wl,--no-undefined', *[str(HERE / n) for n in names(kind)[1:]], *KINDS[kind][1:],
            '-o', str(Path(project).resolve() / 'entry/libs' / abi / ('lib' + KINDS[kind][0] + '.so'))]


def inputs(project, sdk, arch, kind, run, denied=False, mode=0, bundle=BUNDLES[0]):
    validate(kind, run, denied, mode, bundle)
    project, sdk = Path(project).resolve(), Path(sdk).resolve()
    page = project / 'entry/src/main/ets/pages/Index.ets'
    module = project / 'entry/src/main/module.json5'
    config = json.loads(module.read_text())['module']
    actual_bundle = json.loads((project / 'AppScope/app.json5').read_text())['app']['bundleName']
    if (page.read_text() != source(kind, run, denied, mode, bundle) or actual_bundle != bundle or
            config.get('requestPermissions') != permissions(kind, mode) or
            config['abilities'][0].get('backgroundModes', []) != (
                ['audioRecording'] if kind == 'audio-event' and mode in (1, 2) else [])):
        raise ValueError('ordinary media source/identity/permissions/background modes differ')
    paths = []
    for component in ('native', 'ets'):
        path = sdk / component / 'oh-uni-package.json'
        info = json.loads(path.read_text())
        if (info.get('apiVersion') != '26' or info.get('releaseType') != 'Release' or info.get('platformVersion') != '26.0.0'):
            raise ValueError('ordinary media HAP requires actual API26 Release SDK')
        paths.append(path)
    for directory in ('ohaudio', 'multimedia/player_framework', 'native_window', 'native_buffer'):
        paths.extend(sorted((sdk / 'native/sysroot/usr/include' / directory).glob('*.h')))
    binary = project / 'entry/libs' / ABIS[arch][0] / ('lib' + KINDS[kind][0] + '.so')
    verify_elf(binary.read_bytes(), arch)
    return {'schema_version': 1, 'scope': 'ordinary_public_' + kind + '_with_independent_capture_proof_required',
            'kind': kind, 'role': 'ordinary_app', 'bundle': bundle, 'run_id': run, 'arch': arch,
            'expected_denied': denied, 'mode': mode, 'sdk': str(sdk),
            'request_permissions': permissions(kind, mode), 'background_modes': config['abilities'][0].get('backgroundModes', []),
            'generated_source': str(page), 'generated_source_sha256': sha(page), 'module_sha256': sha(module),
            'source_sha256': {n: sha(HERE / n) for n in names(kind)}, 'contract_sha256': sha(Path(__file__)),
            'builder_sha256': sha(HERE / 'build_hap_probe.py'), 'sdk_files_sha256': {str(p): sha(p) for p in paths},
            'native_compile_command': compile_command(project, sdk, arch, kind), 'native_library_sha256': sha(binary),
            'native_runtime_sha256': runtime_identity(binary.read_bytes(), arch)}


def verify_inputs(value):
    page = Path(value['generated_source'])
    if not page.is_absolute() or value != inputs(page.parents[5], value['sdk'], value['arch'], value['kind'],
            value['run_id'], value['expected_denied'], value['mode'], value['bundle']):
        raise ValueError('ordinary media compiled inputs changed')
    return value


def verify_hap(path, value):
    name = 'libs/' + ABIS[value['arch']][0] + '/lib' + KINDS[value['kind']][0] + '.so'
    with zipfile.ZipFile(path) as archive:
        if archive.namelist().count(name) != 1 or archive.namelist().count('module.json') != 1:
            raise ValueError('one actual compiled media library/module required')
        if runtime_identity(archive.read(name), value['arch']) != value['native_runtime_sha256']:
            raise ValueError('actual media HAP code/data differ')
        config = json.loads(archive.read('module.json'))['module']
        normalized = []
        for row in config.get('requestPermissions', []):
            row = dict(row)
            resource = row.pop('reasonId', None)
            if resource is not None and (type(resource) is not int or resource <= 0):
                raise ValueError('compiled media reason resource invalid')
            normalized.append(row)
        if normalized != value['request_permissions'] or config['abilities'][0].get('backgroundModes', []) != value['background_modes']:
            raise ValueError('actual media HAP permissions/background modes differ')
