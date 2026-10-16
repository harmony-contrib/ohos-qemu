#!/usr/bin/env python3
"""Exact-source installer boundaries; no native compiler or runtime claim."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import batch_system_public_still as batch


def installer():
    spec = importlib.util.spec_from_file_location('public_still_installer', batch.COMPONENT / 'apply.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PublicStillSourceGuards(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='public-still-guards-')
        self.root = Path(self.temporary.name) / 'source'
        self.root.mkdir()
        batch.materialize(self.root)
        self.module = installer()
        self.manifest, _ = self.module.load_manifest()

    def tearDown(self):
        self.temporary.cleanup()

    def snapshot(self):
        return {n: (self.root / n).read_bytes() for n in self.manifest['originals']}

    def test_composition_and_idempotence(self):
        self.assertEqual(len(self.manifest['originals']), 14)
        old = json.loads((batch.ROOT / 'patches/common/base/msdp/device_status/sensor_input/manifest.json').read_text())
        for name in set(old['originals']) & set(self.manifest['originals']):
            self.assertEqual(old['originals'][name]['after'], self.manifest['originals'][name]['before'])
        self.assertEqual(self.module.apply(self.root)['status'], 'applied')
        self.assertEqual(self.module.apply(self.root)['status'], 'already_applied')
        for name, row in self.manifest['originals'].items():
            self.assertEqual(hashlib.sha256((self.root / name).read_bytes()).hexdigest(), row['after'])

    def test_unknown_source_preserved(self):
        target = self.root / next(iter(self.manifest['originals']))
        target.write_bytes(target.read_bytes() + b'\n// local edit\n')
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'unknown source bytes'):
            self.module.apply(self.root)
        self.assertEqual(self.snapshot(), before)

    def test_mixed_state_preserved(self):
        before = self.snapshot()
        self.module.apply(self.root)
        name = next(iter(before)); (self.root / name).write_bytes(before[name])
        mixed = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'mixed patch state'):
            self.module.apply(self.root)
        self.assertEqual(self.snapshot(), mixed)

    def test_symlink_preserved(self):
        target = self.root / next(iter(self.manifest['originals']))
        saved = target.with_suffix('.outside'); target.rename(saved); target.symlink_to(saved)
        with self.assertRaisesRegex(ValueError, 'source symlink refused'):
            self.module.apply(self.root)
        self.assertTrue(target.is_symlink())

    def test_atomic_failure_restores_all_files(self):
        before = self.snapshot()
        real = self.module.atomic_write
        calls = 0
        def fail_after_write(*args):
            nonlocal calls
            calls += 1
            real(*args)
            if calls == 7:
                raise RuntimeError('injected after atomic replace')
        with patch.object(self.module, 'atomic_write', fail_after_write):
            with self.assertRaisesRegex(RuntimeError, 'injected after atomic replace'):
                self.module.apply(self.root)
        self.assertEqual(self.snapshot(), before)

    def test_prepare_extracts_actual_death_declaration(self):
        output = Path(self.temporary.name) / 'prepared'
        result = batch.prepare(output)
        self.assertFalse(result['compiler_invoked'])
        header = (output / 'after' / batch.PREFIX / 'services/native/include/devicestatus_manager.h').read_text()
        declaration = (output / 'actual_manager_death.inc').read_text()
        self.assertEqual(declaration, batch.function(header, 'class DeviceStatusCallbackDeathRecipient :').rstrip() + ';\n')
        self.assertIn('virtual ~DeviceStatusCallbackDeathRecipient() = default;', declaration)
        self.assertIn('std::weak_ptr<DeviceStatusManager> manager_;', declaration)
        self.assertNotIn('~explicit', declaration)


if __name__ == '__main__':
    unittest.main()
