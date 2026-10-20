"""Execute the actual lifecycle/provenance recipe on pinned source vectors."""
import base64
import gzip
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / 'ci/capability-audit'
PLAYER = 'foundation/multimedia/player_framework'
CODEC = 'foundation/multimedia/av_codec'
COMP = ROOT / 'patches/common' / PLAYER / 'audio_haptic_source_provenance'
FIXTURE = AUDIT / 'fixtures/audio_haptic_source_provenance/before'


def function(text, name):
    begin = text.index(name + '() {\n')
    return text[begin:text.index('\n}\n', begin) + 3]


class ProvenanceRecipe(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='audio-provenance-recipe-')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.source = self.base / 'source with spaces'
        shutil.copytree(FIXTURE, self.source)
        (self.base / 'cache/logs').mkdir(parents=True)
        (self.source / 'out/arm64_virt').mkdir(parents=True)
        self.package = self.base / 'existing package'
        self.package.mkdir()
        (self.package / 'payload').write_bytes(b'existing artifact')
        self.environment = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        self.environment.update(
            OHOS_ROOT=str(self.source), SOURCE_ROOT=str(self.source),
            CACHE_ROOT=str(self.base / 'cache'), SCRIPT_DIR=str(ROOT / 'scripts'),
            AUDIO_HAPTIC_LIFECYCLE_COMPONENT_SCRIPT=str(COMP.parent / 'audio_haptic_lifecycle/apply.sh'),
            AUDIO_VIVID_INTEGRITY_COMPONENT_SCRIPT=str(ROOT / 'patches/common' / CODEC / 'audio_vivid_integrity/apply.sh'),
            AUDIO_HAPTIC_SOURCE_PLAYER_COMPONENT_SCRIPT=str(COMP / 'apply.sh'),
            AUDIO_HAPTIC_SOURCE_CODEC_COMPONENT_SCRIPT=str(ROOT / 'patches/common' / CODEC / 'audio_haptic_source_provenance/apply.sh'),
            PRODUCT='arm64_virt', DEVICE_TYPE_PROFILE='qemu_phone_full_source',
            PACKAGE_DIR=str(self.package), GIT_CEILING_DIRECTORIES=str(self.base),
            GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_NOSYSTEM='1', PYTHONDONTWRITEBYTECODE='1')
        builder = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        self.prepare = '\n'.join(function(builder, name) for name in
                                ('prepare_audio_haptic_source_lifecycle', 'apply_audio_haptic_source_provenance'))
        self.prepare += '\nprepare_audio_haptic_source_lifecycle\napply_audio_haptic_source_provenance\n'
        self.package_function = function((ROOT / 'scripts/package_standard_qemu.sh').read_text(),
                                         'verify_audio_haptic_source_provenance')

    def run_shell(self, text, **updates):
        return subprocess.run(['bash', '-euo', 'pipefail', '-c', text],
                              env=dict(self.environment, **updates), text=True,
                              capture_output=True, timeout=45)

    def assert_ok(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def snapshot(self):
        return {str(p.relative_to(self.source)): p.read_bytes() for p in self.source.rglob('*')
                if p.is_file() and not {'out', '.ohos-qemu-patches'}.intersection(p.relative_to(self.source).parts)}

    def test_every_historical_whole_vector_upgrades_then_final_skips_legacy(self):
        historical = json.loads((AUDIT / 'fixtures/batch_media/audio_haptic_generation/source_states.json').read_text())
        for name, vector in historical['states'].items():
            with self.subTest(state=name):
                shutil.rmtree(self.source)
                shutil.copytree(FIXTURE, self.source)
                for rel, row in vector.items():
                    target = self.source / PLAYER / rel
                    if row['gzip_base64'] is None:
                        target.unlink(missing_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(gzip.decompress(base64.b64decode(row['gzip_base64'], validate=True)))
                self.assert_ok(self.run_shell(self.prepare))
                after = self.snapshot()
                # The complete final vector must bypass an unavailable legacy installer.
                self.assert_ok(self.run_shell(self.prepare, AUDIO_HAPTIC_LIFECYCLE_COMPONENT_SCRIPT='/missing/legacy/apply.sh',
                                              AUDIO_VIVID_INTEGRITY_COMPONENT_SCRIPT='/missing/vivid/apply.sh'))
                self.assertEqual(after, self.snapshot())

    def test_vivid_preimage_is_upgraded_before_provenance_then_repeat_skips_both(self):
        baseline = json.loads((AUDIT / 'fixtures/batch_media375_audio_vivid/baseline.json').read_text())
        historical = json.loads((AUDIT / 'fixtures/batch_media/audio_haptic_generation/source_states.json').read_text())
        for name, vector in historical['states'].items():
            with self.subTest(state=name):
                shutil.rmtree(self.source)
                shutil.copytree(FIXTURE, self.source)
                target = self.source / baseline['name']
                target.write_bytes(gzip.decompress(base64.b64decode(baseline['gzip_base64'], validate=True)))
                for rel, row in vector.items():
                    target = self.source / PLAYER / rel
                    if row['gzip_base64'] is None:
                        target.unlink(missing_ok=True)
                    else:
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(gzip.decompress(base64.b64decode(row['gzip_base64'], validate=True)))
                self.assert_ok(self.run_shell(self.prepare))
                after = self.snapshot()
                self.assert_ok(self.run_shell(self.prepare, AUDIO_HAPTIC_LIFECYCLE_COMPONENT_SCRIPT='/missing/legacy/apply.sh',
                                              AUDIO_VIVID_INTEGRITY_COMPONENT_SCRIPT='/missing/vivid/apply.sh'))
                self.assertEqual(after, self.snapshot())

    def test_partial_component_cannot_skip_legacy_or_modify_source(self):
        self.assert_ok(self.run_shell('bash "${AUDIO_HAPTIC_SOURCE_PLAYER_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}"'))
        before = self.snapshot()
        result = self.run_shell(self.prepare)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(before, self.snapshot())
        self.assertFalse((self.source / '.ohos-qemu-patches/audio-haptic-incarnation.lock').exists())
        self.assertFalse((self.base / 'cache/logs/apply_audio_haptic_lifecycle_component.log').exists())

    def test_other_lifecycle_member_drift_cannot_skip_legacy(self):
        self.assert_ok(self.run_shell(self.prepare))
        target = self.source / PLAYER / 'frameworks/native/audio_haptic/audio_haptic_player_impl.h'
        target.write_bytes(target.read_bytes() + b'\n// foreign\n')
        before = self.snapshot()
        self.assertNotEqual(self.run_shell(self.prepare).returncode, 0)
        self.assertEqual(before, self.snapshot())

    def test_package_gate_requires_whole_final_before_old_artifact_removal(self):
        program = self.package_function + '\nverify_audio_haptic_source_provenance\n'
        before = self.snapshot()
        self.assertNotEqual(self.run_shell(program + 'rm -rf "${PACKAGE_DIR}"\n').returncode, 0)
        self.assertEqual((self.package / 'payload').read_bytes(), b'existing artifact')
        self.assertEqual(before, self.snapshot())
        self.assert_ok(self.run_shell(self.prepare))
        for profile in ('qemu_phone_full_source', 'qemu_2in1_full_source'):
            self.assert_ok(self.run_shell(program, DEVICE_TYPE_PROFILE=profile))
            receipt = json.loads((self.source / 'out/arm64_virt/audio-haptic-source-provenance.json').read_text())
            self.assertEqual(receipt['state'], 'final505')
            self.assertFalse(receipt['accepted'])
            self.assertFalse(receipt['onset_proven'])
            self.assertFalse(receipt['first_artifact_behavior_gate_passed'])
        text = (ROOT / 'scripts/package_standard_qemu.sh').read_text()
        self.assertLess(text.index('\nverify_audio_haptic_source_provenance\n'), text.index('rm -rf "${PACKAGE_DIR}"'))


if __name__ == '__main__':
    unittest.main()
