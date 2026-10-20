"""Exercise the ordered Sonic and audio-framework prepare/package contracts."""
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
SONIC = ROOT / 'patches/common/third_party/sonic/defined_arithmetic'
SYNC = ROOT / 'patches/common/foundation/multimedia/audio_framework/audio_haptic_sync_id'


def function(text, name):
    begin = text.index(name + '() {\n')
    return text[begin:text.index('\n}\n', begin) + 3]


class SonicAudioRecipe(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='sonic-audio-recipe-')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.source = self.base / 'source with spaces'
        shutil.copytree(ROOT / 'ci/capability-audit/fixtures/audio_haptic_sync_id/before', self.source)
        fixture = json.loads((ROOT / 'ci/capability-audit/fixtures/sonic_defined_arithmetic/before.json').read_text())
        for row in fixture['files']:
            target = self.source / row['path']
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(gzip.decompress(base64.b64decode(row['gzip_base64'], validate=True)))
            target.chmod(row['mode'])
        (self.source / 'out/arm64_virt').mkdir(parents=True)
        (self.base / 'cache/logs').mkdir(parents=True)
        self.package = self.base / 'existing package'
        self.package.mkdir()
        (self.package / 'payload').write_bytes(b'existing artifact')
        self.environment = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        self.environment.update(
            OHOS_ROOT=str(self.source), SOURCE_ROOT=str(self.source),
            CACHE_ROOT=str(self.base / 'cache'), SCRIPT_DIR=str(ROOT / 'scripts'),
            SONIC_DEFINED_ARITHMETIC_COMPONENT_SCRIPT=str(SONIC / 'apply.sh'),
            AUDIO_HAPTIC_SYNC_ID_COMPONENT_SCRIPT=str(SYNC / 'apply.sh'),
            PRODUCT='arm64_virt', DEVICE_TYPE_PROFILE='qemu_phone_full_source',
            PACKAGE_DIR=str(self.package), GIT_CEILING_DIRECTORIES=str(self.base),
            GIT_CONFIG_GLOBAL='/dev/null', GIT_CONFIG_NOSYSTEM='1',
            PYTHONDONTWRITEBYTECODE='1')
        self.builder = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        self.sonic_prepare = function(self.builder, 'apply_sonic_defined_arithmetic') + '\napply_sonic_defined_arithmetic\n'
        begin = self.builder.index('  bash "${AUDIO_HAPTIC_SYNC_ID_COMPONENT_SCRIPT}"')
        end = self.builder.index('  # Hash actual, fully patched kernel/config/HDI sources', begin)
        self.sync_prepare = self.builder[begin:end]
        self.packager = (ROOT / 'scripts/package_standard_qemu.sh').read_text()
        self.package_gates = '\n'.join(function(self.packager, name) for name in
                                     ('verify_sonic_defined_arithmetic_source', 'verify_audio_haptic_sync_id_source'))
        self.package_gates += '\nverify_sonic_defined_arithmetic_source\nverify_audio_haptic_sync_id_source\n'

    def run_shell(self, text, **updates):
        return subprocess.run(['bash', '-euo', 'pipefail', '-c', text],
                              env=dict(self.environment, **updates), capture_output=True,
                              text=True, timeout=30)

    def assert_ok(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def snapshot(self):
        return {str(p.relative_to(self.source)): p.read_bytes() for p in self.source.rglob('*')
                if p.is_file() and 'out' not in p.relative_to(self.source).parts}

    def test_cold_whole_sources_upgrade_in_real_order_and_repeat(self):
        self.assertLess(self.builder.index('\n  apply_sonic_defined_arithmetic\n'),
                        self.builder.index('  bash "${AUDIO_HAPTIC_SYNC_ID_COMPONENT_SCRIPT}"'))
        self.assert_ok(self.run_shell(self.sonic_prepare + self.sync_prepare))
        after = self.snapshot()
        self.assert_ok(self.run_shell(self.sonic_prepare + self.sync_prepare))
        self.assertEqual(after, self.snapshot())
        for profile in ('qemu_phone_full_source', 'qemu_2in1_full_source'):
            self.assert_ok(self.run_shell(self.package_gates, DEVICE_TYPE_PROFILE=profile))
            receipt = json.loads((self.source / 'out/arm64_virt/audio-haptic-sync-id-source.json').read_text())
            self.assertTrue(receipt['patched'])
            self.assertFalse(receipt['compiled'])
            self.assertFalse(receipt['first_artifact_behavior_gate_passed'])

    def test_framework_refuses_old_sonic_without_changing_its_sources(self):
        before = self.snapshot()
        self.assertNotEqual(self.run_shell(self.sync_prepare).returncode, 0)
        self.assertEqual(before, self.snapshot())
        self.assert_ok(self.run_shell(self.sonic_prepare + self.sync_prepare))

    def test_package_guards_preserve_existing_artifact_for_old_or_changed_sonic(self):
        program = self.package_gates + 'rm -rf "${PACKAGE_DIR}"\n'
        before = self.snapshot()
        self.assertNotEqual(self.run_shell(program).returncode, 0)
        self.assertEqual(before, self.snapshot())
        self.assertEqual((self.package / 'payload').read_bytes(), b'existing artifact')
        self.assert_ok(self.run_shell(self.sonic_prepare + self.sync_prepare))
        target = self.source / 'third_party/sonic/sonic.c'
        target.write_bytes(target.read_bytes() + b'\n/* other source */\n')
        before = self.snapshot()
        self.assertNotEqual(self.run_shell(program).returncode, 0)
        self.assertEqual(before, self.snapshot())
        self.assertEqual((self.package / 'payload').read_bytes(), b'existing artifact')
        self.assertLess(self.packager.index('\nverify_sonic_defined_arithmetic_source\n'),
                        self.packager.index('\nverify_audio_haptic_sync_id_source\n'))
        self.assertLess(self.packager.index('\nverify_audio_haptic_sync_id_source\n'),
                        self.packager.index('rm -rf "${PACKAGE_DIR}"'))
        self.assertIn('"${PACKAGE_DIR}/sonic-defined-arithmetic-source.json"', self.packager)


if __name__ == '__main__':
    unittest.main()
