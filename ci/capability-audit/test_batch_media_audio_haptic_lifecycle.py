"""Real source function regressions and exact installer checks, with controlled dependencies."""
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

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/multimedia/player_framework/audio_haptic_lifecycle'
FIXTURE = Path(__file__).parent / 'fixtures/batch_media/audio_haptic'
BASELINE = json.loads((FIXTURE / 'baseline.json').read_text())
spec = importlib.util.spec_from_file_location('audio_haptic_verify', COMPONENT / 'verify_source.py')
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)


def originals():
    result = {}
    for name, entry in BASELINE['files'].items():
        data = gzip.decompress(base64.b64decode(entry['gzip_base64']))
        if hashlib.sha256(data).hexdigest() != entry['sha256']:
            raise ValueError('baseline fixture differs from exported real source')
        result[name] = data
    return result


def populate(root):
    for name, data in originals().items():
        target = root / BASELINE['project'] / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)


def apply(root):
    return subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(root),
                           '--product', 'arm64_virt'], capture_output=True, text=True)


def function(source, signature):
    start = source.index(signature)
    return source[start:source.index('\n}', start) + 2]


class AudioHaptic(unittest.TestCase):
    def test_actual_source_functions_old_counterexamples_and_repair(self):
        groups = {
            'player': ('audio_haptic_player_impl.cpp', [
                'int32_t AudioHapticPlayerImpl::Start()',
                'int32_t AudioHapticPlayerImpl::GetDelayTime(',
                'int32_t AudioHapticPlayerImpl::StartVibrate()',
                'void AudioHapticPlayerImpl::StopVibrate()',
                'void AudioHapticPlayerImpl::ResetVibrateState()',
                'void AudioHapticPlayerImpl::NotifyStartVibrate(']),
            'normal': ('audio_haptic_sound_normal_impl.cpp', [
                'int32_t AudioHapticSoundNormalImpl::ResetAVPlayer()',
                'void AudioHapticSoundNormalImpl::NotifyPreparedEvent()',
                'void AHSoundNormalCallback::HandleAudioFirstFrameEvent(']),
        }
        for old in (True, False):
            with self.subTest(old=old), tempfile.TemporaryDirectory(prefix='audio-haptic-functions-') as temp:
                root = Path(temp)
                populate(root)
                if not old:
                    result = apply(root)
                    self.assertEqual(result.returncode, 0, result.stderr)
                for group, (name, signatures) in groups.items():
                    source = (root / BASELINE['project'] / 'frameworks/native/audio_haptic' / name).read_text()
                    actual = '\n\n'.join(function(source, signature) for signature in signatures)
                    harness = (FIXTURE / (group + '_harness.cpp')).read_text().replace('// ACTUAL_FUNCTIONS', actual)
                    cpp = root / (group + '.cpp')
                    cpp.write_text(harness)
                    executable = root / group
                    command = ['clang++', '-std=c++17', '-Wall', '-Wextra', '-Werror', '-Wno-unused-parameter',
                               '-pthread', '-fsanitize=address,undefined', '-fno-omit-frame-pointer']
                    if old:
                        command.append('-DEXPECT_OLD')
                    subprocess.run(command + [str(cpp), '-o', str(executable)], check=True)
                    env = dict(os.environ, ASAN_OPTIONS='detect_leaks=0' if os.uname().sysname != 'Linux' else 'detect_leaks=1')
                    subprocess.run([str(executable)], env=env, check=True, timeout=10)

    def test_install_repeat_and_exact_whole_state(self):
        with tempfile.TemporaryDirectory(prefix='audio-haptic-install-') as temp:
            root = Path(temp)
            populate(root)
            self.assertFalse(verify.validate(root))
            result = apply(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(verify.validate(root, require_patched=True))
            before = {p: p.read_bytes() for p in root.rglob('*.cpp')}
            result = apply(root)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(before, {p: p.read_bytes() for p in root.rglob('*.cpp')})

    def test_unknown_partial_and_symlink_preserve_every_file(self):
        for state in ('unknown', 'partial', 'symlink'):
            with self.subTest(state=state), tempfile.TemporaryDirectory(prefix='audio-haptic-reject-') as temp:
                root = Path(temp)
                populate(root)
                project = root / BASELINE['project']
                name = next(iter(BASELINE['files']))
                target = project / name
                if state == 'partial':
                    result = apply(root)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    target.write_bytes(originals()[name])
                elif state == 'unknown':
                    target.write_bytes(target.read_bytes() + b'// independent edit\n')
                else:
                    saved = root / 'saved.cpp'
                    target.rename(saved)
                    target.symlink_to(saved)
                before = {p: p.read_bytes() for p in root.rglob('*.cpp')}
                result = apply(root)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(before, {p: p.read_bytes() for p in root.rglob('*.cpp')})


if __name__ == '__main__':
    unittest.main(verbosity=2)
