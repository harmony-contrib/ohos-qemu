"""Whole-source and application regressions for real UIExtension GN CFI wiring."""
from pathlib import Path
import hashlib
import importlib.util
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/arkui/ace_engine/ui_extension_identity_cfi'
PROJECT = 'foundation/arkui/ace_engine'
spec = importlib.util.spec_from_file_location('location375_exact_cfi', COMPONENT / 'verify_source.py')
source = importlib.util.module_from_spec(spec); spec.loader.exec_module(source)


class ExactGNTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='location375-gn-HOST-')
        self.addCleanup(temporary.cleanup); self.root = Path(temporary.name).resolve()
        self.write('original')

    def write(self, state, selected=None):
        for name, _, _ in source.FILES:
            if selected is not None and selected != name: continue
            path = self.root / PROJECT / name; path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes((COMPONENT / 'fixtures' / state / PROJECT / name).read_bytes())

    def data(self):
        return {name: (self.root / PROJECT / name).read_bytes() for name, _, _ in source.FILES}

    def apply(self, expected=0):
        result = subprocess.run([sys.executable, '-B', str(ROOT / 'patches/lib/apply_exact_component.py'),
            '--component-dir', str(COMPONENT), '--source-root', str(self.root)],
            capture_output=True, text=True, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'))
        self.assertEqual(result.returncode == 0, expected == 0, result.stdout + result.stderr)
        return result

    def test_authentic_whole_file_pre_and_post_fixtures(self):
        source.metadata()
        self.assertFalse(source.validate(self.root))
        for name, before, after in source.FILES:
            self.assertEqual(hashlib.sha256((COMPONENT / 'fixtures/original' / PROJECT / name).read_bytes()).hexdigest(), before)
            self.assertEqual(hashlib.sha256((COMPONENT / 'fixtures/final' / PROJECT / name).read_bytes()).hexdigest(), after)
        self.write('final'); self.assertTrue(source.validate(self.root, require_patched=True))

    def test_apply_then_replay_preserves_exact_final_bytes(self):
        self.apply(); self.assertTrue(source.validate(self.root, require_patched=True)); before = self.data()
        self.apply(); self.assertEqual(self.data(), before)

    def test_both_mixed_directions_reject_before_any_mutation(self):
        for name, _, _ in source.FILES:
            self.write('original'); self.write('final', selected=name); before = self.data()
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'partial component'):
                source.validate(self.root)
            self.apply(expected=1); self.assertEqual(before, self.data())

    def test_original_cannot_be_promoted_to_build_ready(self):
        before = self.data()
        with self.assertRaises(ValueError): source.validate(self.root, require_patched=True)
        self.assertEqual(before, self.data())

    def test_unknown_edit_or_partial_added_flag_preserved(self):
        for name, _, _ in source.FILES:
            self.write('original'); path = self.root / PROJECT / name
            path.write_bytes(path.read_bytes() + b'\n# HOST unreviewed edit\n'); before = self.data()
            self.apply(expected=1); self.assertEqual(before, self.data())

    def test_unpaired_cfi_flag_is_not_final_source(self):
        self.write('final'); path = self.root / PROJECT / source.FILES[0][0]
        path.write_text(path.read_text().replace('          cfi_cross_dso = true\n', '', 1)); before = self.data()
        self.apply(expected=1); self.assertEqual(before, self.data())

    def test_source_symlink_rejected(self):
        path = self.root / PROJECT / source.FILES[0][0]; original = self.root / 'original'
        path.replace(original); path.symlink_to(original)
        with self.assertRaisesRegex(ValueError, 'symlink'): source.validate(self.root)

    def test_real_verifier_CLI_rejects_original_partial_and_unknown(self):
        argv = [sys.executable, '-B', str(COMPONENT / 'verify_source.py'), '--source-root', str(self.root), '--require-patched']
        for state in ('original', 'partial', 'unknown'):
            self.write('original')
            if state == 'partial': self.write('final', selected=source.FILES[0][0])
            if state == 'unknown':
                path = self.root / PROJECT / source.FILES[0][0]; path.write_bytes(path.read_bytes() + b'\n# HOST unknown\n')
            before = self.data(); result = subprocess.run(argv, capture_output=True, text=True)
            with self.subTest(state=state): self.assertNotEqual(result.returncode, 0)
            self.assertEqual(before, self.data())

    def test_real_verifier_CLI_only_accepts_complete_final_and_remains_readonly(self):
        import json
        self.write('final'); before = self.data()
        result = subprocess.run([sys.executable, '-B', str(COMPONENT / 'verify_source.py'), '--source-root', str(self.root), '--require-patched'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr); report = json.loads(result.stdout)
        self.assertTrue(report['patched']); self.assertFalse(report['compiled']); self.assertFalse(report['first_artifact_behavior_gate_passed'])
        self.assertEqual(before, self.data())

    def test_only_narrow_ohos_component_sanitizer_scope_added(self):
        name = source.FILES[0][0]; original = (COMPONENT / 'fixtures/original' / PROJECT / name).read_text()
        final = (COMPONENT / 'fixtures/final' / PROJECT / name).read_text()
        block = '''      # Keep the real UIExtension identity carrier instrumented in libace_compatible.
      # Other component targets and non-OHOS platforms keep their existing policy.
      if (current_os == "ohos" && platform == "ohos" &&
          component_name == "ui_extension_pattern_ng") {
        sanitize = {
          cfi = true
          cfi_cross_dso = true
        }
      }
'''
        self.assertEqual(final.count(block), 1); self.assertEqual(final.replace(block, '', 1), original)
        # No target CPU whitelist or sanitizer override changes other components.
        for cpu in ('arm', 'arm64', 'x64'):
            self.assertNotIn('target_cpu == "' + cpu + '"', block)
        for forbidden in ('use_cfi =', 'allow_sanitize_debug', '-fsanitize=', 'cfi = false'):
            self.assertNotIn(forbidden, block)

    def test_only_real_final_library_existing_sanitize_block_extended(self):
        name = source.FILES[1][0]; original = (COMPONENT / 'fixtures/original' / PROJECT / name).read_text()
        final = (COMPONENT / 'fixtures/final' / PROJECT / name).read_text()
        start = final.index('ohos_shared_library("libace_compatible") {')
        stop = final.index('\nohos_shared_library("libace_compatible_components")', start)
        block = final[start:stop]
        addition = '      cfi = true\n      cfi_cross_dso = true\n'
        self.assertEqual(block.count(addition), 1)
        self.assertEqual(final[:start] + block.replace(addition, '', 1) + final[stop:], original)
        self.assertIn('integer_overflow = true', block); self.assertIn('boundary_sanitize = true', block)
        self.assertIn('debug = ace_sanitize_debug', block)
        self.assertIn('if (is_ohos) {\n    sanitize', block)


if __name__ == '__main__': unittest.main()
