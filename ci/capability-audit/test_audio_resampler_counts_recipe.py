"""Run the actual prepare and package guards on pinned resampler sources."""
import base64
import gzip
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/multimedia/audio_framework/audio_resampler_counts'


def function(text, name):
    start = text.index(name + '() {\n')
    return text[start:text.index('\n}\n', start) + 3]


class ResamplerRecipe(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='audio-resampler-recipe-')
        self.addCleanup(temporary.cleanup)
        self.base = Path(temporary.name).resolve()
        self.source = self.base / 'source with spaces'
        fixture = json.loads((ROOT / 'ci/capability-audit/fixtures/audio_resampler_counts/before.json').read_text())
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
            AUDIO_RESAMPLER_COUNTS_COMPONENT_SCRIPT=str(COMPONENT / 'apply.sh'),
            PRODUCT='arm64_virt', DEVICE_TYPE_PROFILE='qemu_phone_full_source',
            PACKAGE_DIR=str(self.package), PYTHONDONTWRITEBYTECODE='1')
        self.prepare = function((ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text(),
                                'apply_audio_resampler_counts') + '\napply_audio_resampler_counts\n'
        self.package_function = function((ROOT / 'scripts/package_standard_qemu.sh').read_text(),
                                        'verify_audio_resampler_counts_source')

    def run_shell(self, text, **updates):
        return subprocess.run(['bash', '-euo', 'pipefail', '-c', text],
                              env=dict(self.environment, **updates), capture_output=True,
                              text=True, timeout=30)

    def assert_ok(self, result):
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def snapshot(self):
        return {str(p.relative_to(self.source)): p.read_bytes() for p in self.source.rglob('*')
                if p.is_file() and 'out' not in p.relative_to(self.source).parts}

    def test_real_prepare_repeat_keeps_filter_and_public_vtable(self):
        manifest = json.loads((COMPONENT / 'manifest.json').read_text())
        guards = {name: (self.source / name).read_bytes() for name in manifest['prerequisites']}
        self.assert_ok(self.run_shell(self.prepare))
        after = self.snapshot()
        self.assert_ok(self.run_shell(self.prepare))
        self.assertEqual(after, self.snapshot())
        self.assertEqual(guards, {name: (self.source / name).read_bytes() for name in guards})

    def test_preimage_refused_before_old_package_removal_then_both_profiles_pass(self):
        program = self.package_function + '\nverify_audio_resampler_counts_source\n'
        before = self.snapshot()
        self.assertNotEqual(self.run_shell(program + 'rm -rf "${PACKAGE_DIR}"\n').returncode, 0)
        self.assertEqual((self.package / 'payload').read_bytes(), b'existing artifact')
        self.assertEqual(before, self.snapshot())
        self.assert_ok(self.run_shell(self.prepare))
        for profile in ('qemu_phone_full_source', 'qemu_2in1_full_source'):
            self.assert_ok(self.run_shell(program, DEVICE_TYPE_PROFILE=profile))
            receipt = json.loads((self.source / 'out/arm64_virt/audio-resampler-counts-source.json').read_text())
            self.assertEqual(receipt['state'], 'after')
            self.assertFalse(receipt['hardware_playback_proven'])

    def test_partial_product_vector_refused_without_source_or_package_changes(self):
        manifest = json.loads((COMPONENT / 'manifest.json').read_text())
        name = next(iter(manifest['files']))
        before = (self.source / name).read_bytes()
        self.assert_ok(self.run_shell(self.prepare))
        (self.source / name).write_bytes(before)
        snapshot = self.snapshot()
        self.assertNotEqual(self.run_shell(self.prepare).returncode, 0)
        program = self.package_function + '\nverify_audio_resampler_counts_source\nrm -rf "${PACKAGE_DIR}"\n'
        self.assertNotEqual(self.run_shell(program).returncode, 0)
        self.assertEqual(snapshot, self.snapshot())
        self.assertEqual((self.package / 'payload').read_bytes(), b'existing artifact')

    def test_filter_drift_refused_before_prepare_mutation(self):
        manifest = json.loads((COMPONENT / 'manifest.json').read_text())
        name = next(iter(manifest['prerequisites']))
        target = self.source / name
        target.write_bytes(target.read_bytes() + b'\n/* different filter */\n')
        before = self.snapshot()
        self.assertNotEqual(self.run_shell(self.prepare).returncode, 0)
        self.assertEqual(before, self.snapshot())

    def test_gate_order_and_profiles_without_full_source(self):
        package = (ROOT / 'scripts/package_standard_qemu.sh').read_text()
        self.assertLess(package.index('\nverify_audio_resampler_counts_source\n'),
                        package.index('rm -rf "${PACKAGE_DIR}"'))
        self.assertIn('"${PACKAGE_DIR}/audio-resampler-counts-source.json"', package)
        builder = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        self.assertLess(builder.index('\n  apply_audio_resampler_counts\n'),
                        builder.index('  # Hash actual, fully patched kernel/config/HDI sources'))
        for profile in ('default', 'param_only'):
            self.assert_ok(self.run_shell(self.package_function + '\nverify_audio_resampler_counts_source\n',
                                          DEVICE_TYPE_PROFILE=profile))
            self.assertFalse((self.source / 'out/arm64_virt/audio-resampler-counts-source.json').exists())


if __name__ == '__main__':
    unittest.main()
