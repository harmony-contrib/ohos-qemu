"""Exact fixed-source installer/rollback checks for the system sensor batch."""
import base64
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
COMPONENTS = [
    ('qemu_sensor', ROOT / 'patches/common/drivers/peripheral/sensor/qemu_external'),
    ('msdp_input', ROOT / 'patches/common/base/msdp/device_status/sensor_input'),
]


def prepare(root, fixture):
    provenance = json.loads((fixture / 'provenance.json').read_text())
    for row in provenance['files']:
        data = gzip.decompress(base64.b64decode((fixture / row['fixture']).read_bytes()))
        if hashlib.sha256(data).hexdigest() != row['sha256']:
            raise ValueError('fixture hash mismatch')
        path = root / row['path']
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)


class ExactInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='batch-system-sensor-guard-')
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)

    def candidates(self):
        for name, component in COMPONENTS:
            root = self.base / name
            prepare(root, HERE / 'fixtures/batch_system' / name)
            spec = importlib.util.spec_from_file_location('batch_system_apply_' + name, component / 'apply.py')
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            manifest, _ = module.load_manifest()
            yield name, root, component, module, manifest

    def snapshot(self, root, manifest):
        return {relative: (root / relative).read_bytes() if (root / relative).exists() else None
                for relative in [*manifest['originals'], *manifest['files']]}

    def test_full_installer_applies_twice(self):
        for name, root, component, guard, manifest in self.candidates():
            with self.subTest(component=name):
                self.assertFalse(guard.validate(root, manifest))
                for expected in ['applied', 'already_applied']:
                    run = subprocess.run(['bash', str(component / 'apply.sh'), '--source-root', str(root)],
                                         capture_output=True, text=True)
                    self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
                    self.assertEqual(json.loads(run.stdout)['status'], expected)
                    self.assertTrue(guard.validate(root, manifest, require_patched=True))

    def test_unknown_source_preserved(self):
        for name, root, _, guard, manifest in self.candidates():
            with self.subTest(component=name):
                path = root / next(iter(manifest['originals']))
                path.write_bytes(path.read_bytes() + b'// unrelated edit\n')
                original = self.snapshot(root, manifest)
                with self.assertRaisesRegex(ValueError, 'unknown source'):
                    guard.apply(root)
                self.assertEqual(self.snapshot(root, manifest), original)

    def test_mixed_state_preserved(self):
        for name, root, _, guard, manifest in self.candidates():
            with self.subTest(component=name):
                path = root / next(iter(manifest['originals']))
                original = path.read_bytes()
                guard.apply(root)
                path.write_bytes(original)
                mixed = self.snapshot(root, manifest)
                with self.assertRaisesRegex(ValueError, 'mixed'):
                    guard.apply(root)
                self.assertEqual(self.snapshot(root, manifest), mixed)

    def test_symlink_and_parent_symlink_preserved(self):
        for name, root, _, guard, manifest in self.candidates():
            with self.subTest(component=name):
                path = root / next(iter(manifest['originals']))
                external = self.base / (name + '-external')
                original = path.read_bytes()
                external.write_bytes(original)
                path.unlink()
                path.symlink_to(external)
                with self.assertRaisesRegex(ValueError, 'symlink'):
                    guard.apply(root)
                self.assertEqual(external.read_bytes(), original)
                path.unlink()
                path.write_bytes(original)
                moved = self.base / (name + '-directory')
                path.parent.rename(moved)
                path.parent.symlink_to(moved, target_is_directory=True)
                with self.assertRaisesRegex(ValueError, 'symlink'):
                    guard.apply(root)
                self.assertEqual((moved / path.name).read_bytes(), original)

    def test_wrong_project_revision_preserved(self):
        for name, root, _, guard, manifest in self.candidates():
            with self.subTest(component=name):
                project = root / manifest['project']
                subprocess.run(['git', 'init', '-q', str(project)], check=True)
                subprocess.run(['git', '-C', str(project), '-c', 'user.name=Fixture',
                                '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture',
                                '--allow-empty'], check=True)
                before = self.snapshot(root, manifest)
                with self.assertRaisesRegex(ValueError, 'fixed upstream revision'):
                    guard.apply(root)
                self.assertEqual(self.snapshot(root, manifest), before)

    def test_component_tamper_refused(self):
        for name, root, component, guard, manifest in self.candidates():
            with self.subTest(component=name):
                private = self.base / (name + '-component')
                shutil.copytree(component, private)
                patch = next(private.glob('*.patch'))
                patch.write_bytes(patch.read_bytes() + b'\n')
                before = self.snapshot(root, manifest)
                with mock.patch.object(guard, 'COMPONENT', private):
                    with self.assertRaisesRegex(ValueError, 'unknown component patch'):
                        guard.apply(root)
                self.assertEqual(self.snapshot(root, manifest), before)

    def test_rollback_after_replaced_file(self):
        for name, root, _, guard, manifest in self.candidates():
            with self.subTest(component=name):
                before = self.snapshot(root, manifest)
                real_write = guard.atomic_write
                calls = 0
                def fail_after_replace(path, data, mode):
                    nonlocal calls
                    real_write(path, data, mode)
                    calls += 1
                    if calls == len(manifest['originals']) + len(manifest['files']):
                        raise OSError('injected after final rename')
                with mock.patch.object(guard, 'atomic_write', fail_after_replace):
                    with self.assertRaisesRegex(OSError, 'injected'):
                        guard.apply(root)
                self.assertEqual(self.snapshot(root, manifest), before)
                self.assertFalse(guard.validate(root, manifest))

    def test_unknown_overlay_preserved(self):
        for name, root, _, guard, manifest in self.candidates():
            if not manifest['files']:
                continue
            with self.subTest(component=name):
                target = root / next(iter(manifest['files']))
                target.write_bytes(b'foreign overlay\n')
                before = self.snapshot(root, manifest)
                with self.assertRaisesRegex(ValueError, 'unknown existing overlay'):
                    guard.apply(root)
                self.assertEqual(self.snapshot(root, manifest), before)


if __name__ == '__main__':
    unittest.main()
