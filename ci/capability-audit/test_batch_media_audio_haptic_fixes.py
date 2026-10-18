#!/usr/bin/env python3
"""F source/installer and actual NAPI transport regressions; no guest success claim."""
import base64
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

import batch_media_audio_haptic_project as project

ROOT = Path(__file__).resolve().parents[2]
COMP = ROOT / 'patches/common/foundation/multimedia/player_framework/audio_haptic_public_errors'
LIFECYCLE = ROOT / 'patches/common/foundation/multimedia/player_framework/audio_haptic_lifecycle'
FIX = Path(__file__).parent / 'fixtures/batch_media/audio_haptic_public_errors'
GEN = Path(__file__).parent / 'fixtures/batch_media/audio_haptic_generation'


def method(source, signature):
    begin = source.index(signature)
    return source[begin:source.index('\n}', begin) + 2]


def originals():
    result = {}
    for name, row in json.loads((FIX / 'source.json').read_text())['files'].items():
        data = gzip.decompress(base64.b64decode(row['gzip_base64']))
        if hashlib.sha256(data).hexdigest() != row['sha256']:
            raise ValueError('E source fixture differs: ' + name)
        result[name] = data
    return result

def legacy_postimage():
    manifest = json.loads((COMP / 'source_states.json').read_text())
    result = {}
    for name, row in manifest['files'].items():
        payload = row.get('after_bool_legacy_gzip_base64', row['after_gzip_base64'])
        data = gzip.decompress(base64.b64decode(payload))
        if hashlib.sha256(data).hexdigest() != manifest['states']['after_bool_legacy'][name]:
            raise ValueError('exact former F bool-parent fixture differs: ' + name)
        result[name] = data
    return result


class AudioHapticF(unittest.TestCase):
    def test_real_bad_resources_are_distinct_from_observation_modes(self):
        rows = project.phases(); by_name = {row['name']: row for row in rows}
        for prefix, key, filename in (('bad-wav', 'audio', 'bad.wav'), ('bad-json', 'haptic', 'bad.json'),
                                      ('missing-wav', 'audio', 'missing.wav')):
            register = by_name[prefix + '-register']
            self.assertEqual(register['options'], {key: filename})
            self.assertIsNone(register['audio']); self.assertIsNone(register['haptic'])
            create = by_name[prefix + '-create']
            self.assertEqual((create['expected'], create['errors']), ('error', [5400103, 5400106]))
            self.assertEqual((create['audio'], create['haptic']), ('quiet', 'quiet'))
            self.assertEqual(by_name[prefix + '-retry-register']['options'], {})
            self.assertEqual(by_name[prefix + '-retry-start']['audio'], 'active')
            self.assertEqual(by_name[prefix + '-retry-start']['haptic'], 'active')
        self.assertEqual(by_name['denied-create']['errors'], [201])
        self.assertEqual(by_name['post-release-start']['errors'], [5400102])
        self.assertEqual(by_name['loop-start']['hold_ms'], 9200)
        self.assertEqual(by_name['mute-audio-create']['options'], {'mute_audio': True, 'mute_haptics': False})

    def test_seven_member_exact_E_upgrade_repeat_and_all_rollbacks(self):
        spec = importlib.util.spec_from_file_location('napi_errors_installer', COMP / 'install.py')
        installer = importlib.util.module_from_spec(spec); spec.loader.exec_module(installer)
        before = originals()
        self.assertEqual(len(before), 7)
        for count in (None, *range(1, len(before) + 1)):
            with self.subTest(count=count), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for name, data in before.items():
                    path = root / installer.PROJECT / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
                self.assertEqual(installer.state(root), 'before')
                def fail(name, actual):
                    if actual == count:
                        raise OSError('controlled NAPI write failure')
                if count is not None:
                    with self.assertRaisesRegex(OSError, 'controlled'):
                        installer.install(root, after_write=fail)
                    self.assertEqual(installer.snapshot(root), before)
                else:
                    self.assertEqual(installer.install(root), 'after')
                    self.assertEqual(installer.install(root), 'after')
                    # Even a single E/F member mixture remains invalid, with no writes.
                    name = next(iter(before)); (root / installer.PROJECT / name).write_bytes(before[name])
                    mixed = installer.snapshot(root)
                    with self.assertRaises(ValueError): installer.install(root)
                    self.assertEqual(installer.snapshot(root), mixed)

    def test_exact_legacy_bool_parent_upgrade_repeat_and_all_rollbacks(self):
        spec = importlib.util.spec_from_file_location('napi_errors_legacy_installer', COMP / 'install.py')
        installer = importlib.util.module_from_spec(spec); spec.loader.exec_module(installer)
        legacy = legacy_postimage()
        self.assertEqual(len(legacy), 7)
        for count in (None, *range(1, len(legacy) + 1)):
            with self.subTest(count=count), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                for name, data in legacy.items():
                    path = root / installer.PROJECT / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
                self.assertEqual(installer.state(root), 'after_bool_legacy')
                def fail(name, actual):
                    if actual == count: raise OSError('controlled legacy upgrade failure')
                if count is not None:
                    with self.assertRaisesRegex(OSError, 'controlled legacy'):
                        installer.install(root, after_write=fail)
                    self.assertEqual(installer.snapshot(root), legacy)
                    self.assertEqual(installer.state(root), 'after_bool_legacy')
                else:
                    self.assertEqual(installer.install(root), 'after')
                    self.assertEqual(installer.install(root), 'after')
                    for name, data in legacy.items():
                        repaired = installer.snapshot(root)
                        (root / installer.PROJECT / name).write_bytes(data)
                        if data != repaired[name]:
                            mixed = installer.snapshot(root)
                            with self.assertRaises(ValueError): installer.install(root)
                            self.assertEqual(installer.snapshot(root), mixed)
                        (root / installer.PROJECT / name).write_bytes(repaired[name])

    def test_real_private_header_is_part_of_exact_readonly_state_gate(self):
        spec = importlib.util.spec_from_file_location('napi_errors_header_installer', COMP / 'install.py')
        installer = importlib.util.module_from_spec(spec); spec.loader.exec_module(installer)
        before = originals()
        name = 'frameworks/js/audio_haptic/include/audio_haptic_player/audio_haptic_player_napi.h'
        self.assertIn(name, installer.MANIFEST['files'])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for relative, data in before.items():
                path = root / installer.PROJECT / relative; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(data)
            (root / installer.PROJECT / name).write_bytes(before[name] + b'\n// foreign private context\n')
            snapshot = installer.snapshot(root)
            with self.assertRaises(ValueError): installer.install(root)
            self.assertEqual(installer.snapshot(root), snapshot)
            self.assertFalse((root / '.ohos-qemu-patches').exists())

    def test_complete_actual_player_cpp_private_header_native_status_chain(self):
        # No selected-method substitute: all player/common/callback CPP bytes
        # below are the complete installed production payload files.
        with tempfile.TemporaryDirectory(prefix='audio-haptic-player-status-') as directory:
            root = Path(directory)
            manifest = json.loads((COMP / 'source_states.json').read_text())
            for name, row in manifest['files'].items():
                data = gzip.decompress(base64.b64decode(row['after_gzip_base64']))
                self.assertEqual(hashlib.sha256(data).hexdigest(), manifest['states']['after'][name])
                self.assertEqual(data, (COMP / 'files' / Path(name).name).read_bytes())
                (root / Path(name).name).write_bytes(data)
            lifecycle = json.loads((LIFECYCLE / 'source_states.json').read_text())
            for name, row in lifecycle['files'].items():
                if Path(name).name in ('audio_haptic_playback_session.h', 'audio_haptic_publication_callback.h'):
                    data = gzip.decompress(base64.b64decode(row['incarnation_gzip_base64']))
                    self.assertEqual(hashlib.sha256(data).hexdigest(), lifecycle['states']['incarnation'][name])
                    (root / Path(name).name).write_bytes(data)
            extra = FIX / 'player_status'
            binary = root / 'complete-player-native-status'
            compiler = os.environ.get('OHOS_QA_CXX', '/usr/bin/clang++')
            version = subprocess.run([compiler, '--version'], capture_output=True, text=True, timeout=15)
            self.assertEqual(version.returncode, 0, version.stderr)
            # GCC's -Wall/-Wextra also diagnoses bool/error-code comparisons;
            # the named Clang warning is not a valid GCC option.
            warning = ['-Wtautological-constant-out-of-range-compare'] if 'clang' in version.stdout.lower() else []
            argv = [compiler, '-std=c++17', '-pthread', '-fno-rtti',
                '-Wall', '-Wextra', '-Werror', *warning,
                '-Wno-unused-parameter', '-Wno-unused-const-variable',
                '-fsanitize=address,undefined', '-fno-omit-frame-pointer',
                '-include', str(extra / 'prelude.h'), '-I' + str(root), '-I' + str(extra),
                '-I' + str(extra / 'stubs'), '-I' + str(FIX / 'stubs'),
                '-I' + str(GEN / 'include'), '-I' + str(GEN / 'stubs'),
                str(root / 'audio_haptic_player_napi.cpp'), str(root / 'audio_haptic_common_napi.cpp'),
                str(root / 'audio_haptic_player_callback_napi.cpp'), str(extra / 'player_status_harness.cpp'),
                '-o', str(binary)]
            compiled = subprocess.run(argv, capture_output=True, text=True, timeout=120)
            self.assertEqual(compiled.returncode, 0, 'argv=' + repr(argv) + '\nstdout:\n' + compiled.stdout + '\nstderr:\n' + compiled.stderr)
            ran = subprocess.run([str(binary)], capture_output=True, text=True, timeout=30,
                env=dict(os.environ, ASAN_OPTIONS='detect_leaks=1' if os.uname().sysname == 'Linux' else 'detect_leaks=0'))
            self.assertEqual(ran.returncode, 0, 'stdout:\n' + ran.stdout + '\nstderr:\n' + ran.stderr)

    def test_actual_napi_callback_class_and_common_methods(self):
        # Complete actual callback CPP/class. The common class header is actual;
        # only its changed named methods are linked, against controlled external NAPI/AT.
        with tempfile.TemporaryDirectory(prefix='audio-haptic-napi-') as directory:
            root = Path(directory)
            for path in (COMP / 'files').glob('*'):
                (root / path.name).write_bytes(path.read_bytes())
            manifest = json.loads((LIFECYCLE / 'source_states.json').read_text())
            for name, entry in manifest['files'].items():
                if Path(name).name in ('audio_haptic_playback_session.h', 'audio_haptic_publication_callback.h'):
                    data = gzip.decompress(base64.b64decode(entry['incarnation_gzip_base64']))
                    self.assertEqual(hashlib.sha256(data).hexdigest(), manifest['states']['incarnation'][name])
                    (root / Path(name).name).write_bytes(data)
            source = (COMP / 'files/audio_haptic_common_napi.cpp').read_text()
            constants = source[source.index('const std::string NAPI_ERR_INPUT_INVALID_INFO'):source.index('void AudioHapticCommonNapi::ThrowError')]
            selected = '\n'.join(method(source, signature) for signature in (
                'void AudioHapticCommonNapi::PromiseReject(napi_env env, napi_deferred deferred,\n',
                'void AudioHapticCommonNapi::PromiseReject(napi_env env, napi_deferred deferred, int32_t errCode)',
                'bool AudioHapticCommonNapi::VerifyVibratePermission()',
                'std::string AudioHapticCommonNapi::GetMessageByCode('))
            common = root / 'selected-common.cpp'
            common.write_text('#include "audio_haptic_common_napi.h"\nnamespace OHOS { namespace Media {\n' + constants + selected + '\n} }\n')
            binary = root / 'napi-boundaries'
            argv = [os.environ.get('OHOS_QA_CXX', '/usr/bin/clang++'), '-std=c++17', '-pthread', '-fno-rtti',
                    '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter', '-Wno-unused-const-variable',
                    '-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-include', str(GEN / 'stubs/host_prelude.h'),
                    '-I' + str(root), '-I' + str(FIX / 'stubs'), '-I' + str(GEN / 'include'), '-I' + str(GEN / 'stubs'),
                    str(root / 'audio_haptic_player_callback_napi.cpp'), str(common), str(FIX / 'napi_harness.cpp'), '-o', str(binary)]
            compiled = subprocess.run(argv, capture_output=True, text=True, timeout=120)
            self.assertEqual(compiled.returncode, 0, 'argv=' + repr(argv) + '\nstdout:\n' + compiled.stdout + '\nstderr:\n' + compiled.stderr)
            ran = subprocess.run([str(binary)], capture_output=True, text=True, timeout=30,
                                 env=dict(os.environ, ASAN_OPTIONS='detect_leaks=1' if os.uname().sysname == 'Linux' else 'detect_leaks=0'))
            self.assertEqual(ran.returncode, 0, 'stdout:\n' + ran.stdout + '\nstderr:\n' + ran.stderr)

    def test_factory_and_sink_are_bound_without_public_ABI_or_RTTI_change(self):
        state = json.loads((LIFECYCLE / 'source_states.json').read_text())
        sources = {Path(name).name: gzip.decompress(base64.b64decode(row['incarnation_gzip_base64'])).decode()
                   for name, row in state['files'].items()}
        factory = method(sources['audio_haptic_player_impl.cpp'], 'std::shared_ptr<AudioHapticPlayer> AudioHapticPlayerFactory::CreateAudioHapticPlayer(')
        self.assertIn('make_shared<AudioHapticPlayerImpl>()', factory)
        constructor = method((COMP / 'files/audio_haptic_player_napi.cpp').read_text(), 'napi_value AudioHapticPlayerNapi::Constructor(')
        self.assertIn('static_pointer_cast<AudioHapticPlayerImpl>', constructor)
        self.assertIn('SetPublicationCallback(obj->callbackNapi_)', constructor)
        for suffix in ('EndOfStream', 'Interrupt'):
            body = method(sources['audio_haptic_player_impl.cpp'], 'void AudioHapticPlayerImpl::HandlePlayback' + suffix + '(')
            self.assertIn('if (publication != nullptr)', body)
            self.assertIn('else if (callback != nullptr)', body)
        joined = ''.join(sources.values()) + constructor
        self.assertNotIn('dynamic_cast', joined); self.assertNotIn('dynamic_pointer_cast', joined)
        # Original public callback/player API remains the fixed actual dependency header.
        self.assertNotIn('SetPublicationCallback', (GEN / 'include/audio_haptic_player.h').read_text())
        creation = method((COMP / 'files/audio_haptic_manager_napi.cpp').read_text(), 'napi_value AudioHapticManagerNapi::CreatePlayer(')
        self.assertLess(creation.index('VerifyVibratePermission()'), creation.index('napi_create_async_work('))
        self.assertIn('NAPI_ERR_VIBRATE_PERMISSION_DENIED', creation)


if __name__ == '__main__':
    unittest.main()
