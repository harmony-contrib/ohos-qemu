"""Product parameter transaction boundaries, not a private-start runtime proof."""
from pathlib import Path
import importlib.util
import os
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
PATH = ROOT / 'patches/common/vendor/ohemu/virt/settings_select/apply.py'
SPEC = importlib.util.spec_from_file_location('settings_select_params375', PATH)
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


class SelectParameters(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.target = self.root / M.PARAM_FILE
        self.target.parent.mkdir(parents=True)
        self.original = b'# Existing product\nconst.window.multiWindowUIType=HandsetSmartWindow\n'
        self.target.write_bytes(self.original)
        self.target.chmod(0o640)

    def test_complete_native_guard_apply_and_replay_preserve_profile_and_mode(self):
        with patch.object(M, 'require_chooser') as guard:
            self.assertEqual(M.configure(self.root), 'applied')
            once = self.target.read_bytes()
            self.assertEqual(M.configure(self.root), 'already_applied')
            self.assertEqual(M.configure(self.root, True), 'already_applied')
            self.assertEqual(guard.call_count, 3)
        self.assertTrue(once.startswith(self.original))
        self.assertEqual(self.target.read_bytes(), once)
        self.assertEqual(self.target.stat().st_mode & 0o777, 0o640)
        for key, value in M.VALUES.items():
            self.assertEqual(once.count((key + '=' + value).encode()), 1)

    def test_unknown_or_incomplete_native_vector_never_changes_parameters(self):
        with patch.object(M, 'require_chooser', side_effect=ValueError('unknown native/UI vector')):
            with self.assertRaisesRegex(ValueError, 'unknown native'):
                M.configure(self.root)
        self.assertEqual(self.target.read_bytes(), self.original)

    def test_missing_pair_fails_readonly_verification(self):
        with patch.object(M, 'require_chooser'):
            with self.assertRaisesRegex(ValueError, 'complete Settings'):
                M.configure(self.root, True)
        self.assertEqual(self.target.read_bytes(), self.original)

    def test_conflict_duplicate_and_partial_pair_reject_without_changes(self):
        cases = [
            b'const.system.sharePicker.bundleName=foreign\n',
            b'const.system.sharePicker.bundleName=com.ohos.settings\n',
            b'const.system.sharePicker.bundleName=com.ohos.settings\n' * 2,
            b'const.system.sharePicker.bundleName=com.ohos.settings\nconst.system.sharePicker.abilityName=foreign\n',
        ]
        for extra in cases:
            with self.subTest(extra=extra), patch.object(M, 'require_chooser'):
                before = self.original + extra
                self.target.write_bytes(before)
                with self.assertRaises(ValueError):
                    M.configure(self.root)
                self.assertEqual(self.target.read_bytes(), before)

    def test_symlink_and_hardlink_targets_rejected(self):
        outside = self.root / 'outside'
        outside.write_bytes(self.original)
        self.target.unlink()
        for symbolic in (True, False):
            if symbolic:
                self.target.symlink_to(outside)
            else:
                os.link(outside, self.target)
            with self.subTest(symbolic=symbolic), patch.object(M, 'require_chooser'):
                with self.assertRaises(ValueError):
                    M.configure(self.root)
                self.assertEqual(outside.read_bytes(), self.original)
            self.target.unlink()

    def test_replace_failure_preserves_original_and_removes_staging_file(self):
        with patch.object(M, 'require_chooser'), patch.object(M.os, 'replace', side_effect=OSError('publication failed')):
            with self.assertRaisesRegex(OSError, 'publication failed'):
                M.configure(self.root)
        self.assertEqual(self.target.read_bytes(), self.original)
        self.assertEqual(list(self.target.parent.glob('.settings-select-*')), [])


if __name__ == '__main__':
    unittest.main()
