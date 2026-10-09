"""Exact policy transitions and narrow grants; not guest runtime evidence."""
import hashlib
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
COMPONENT = ROOT / 'patches/common/base/security/selinux_adapter/fusion_service_domains'
spec = importlib.util.spec_from_file_location('fusion_domains_baseline', COMPONENT / 'verify_source.py')
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)


class FusionServiceDomainsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='fusion-domain-contract-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / 'source'
        relative, before, _ = baseline.FILES[0]
        original = HERE / 'fixtures/fusion_service_domains/type.te'
        self.assertEqual(hashlib.sha256(original.read_bytes()).hexdigest(), before)
        target = self.root / baseline.PROJECT / relative
        target.parent.mkdir(parents=True)
        shutil.copy2(original, target)

    def apply(self):
        return subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(self.root)],
                              capture_output=True, text=True)

    def snapshot(self):
        return {relative: path.read_bytes() if path.exists() else None
                for relative, _, _ in baseline.FILES
                for path in [self.root / baseline.PROJECT / relative]}

    def test_apply_and_repeat_exact_complete_policy(self):
        self.assertFalse(baseline.validate(self.root))
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(baseline.validate(self.root, True))
        original = self.snapshot()
        for _ in range(2):
            result = self.apply()
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(self.snapshot(), original)

    def test_missing_final_sibling_rejects_before_any_write(self):
        self.assertEqual(self.apply().returncode, 0)
        for relative, _, _ in baseline.FILES[1:]:
            target = self.root / baseline.PROJECT / relative
            saved = target.read_bytes()
            target.unlink()
            before = self.snapshot()
            self.assertNotEqual(self.apply().returncode, 0)
            self.assertEqual(self.snapshot(), before)
            target.write_bytes(saved)

    def test_unknown_existing_new_file_rejects_before_any_write(self):
        target = self.root / baseline.PROJECT / baseline.FILES[1][0]
        target.write_text('# existing user policy\n')
        before = self.snapshot()
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertEqual(self.snapshot(), before)

    def test_symlink_is_rejected_without_mutation(self):
        target = self.root / baseline.PROJECT / baseline.FILES[0][0]
        preserved = target.with_suffix('.preserved')
        target.rename(preserved)
        target.symlink_to(preserved)
        before = self.snapshot()
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertEqual(self.snapshot(), before)

    def test_only_dedicated_sa_registration_grants_are_added(self):
        self.assertEqual(self.apply().returncode, 0)
        policy = (self.root / baseline.PROJECT / baseline.FILES[3][0]).read_text()
        rules = [line for line in policy.splitlines() if line and not line.startswith('#')]
        self.assertEqual(rules, [
            'allow fusion_ranging sa_fusion_ranging_service:samgr_class { add get };',
            'allow partner_device_agent sa_partner_device_agent_service:samgr_class { add get };'])
        patch = next(COMPONENT.glob('*.patch')).read_text()
        additions = '\n'.join(line[1:] for line in patch.splitlines()
                              if line.startswith('+') and not line.startswith('+++'))
        for forbidden in ('permissive ', 'unconfined', 'allow domain ', 'capability', 'neverallow'):
            self.assertNotIn(forbidden, additions)

    def test_preparation_precedes_source_traversal(self):
        recipe = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        marker = 'bash "${FUSION_SERVICE_DOMAINS_COMPONENT_SCRIPT}"'
        self.assertEqual(recipe.count(marker), 1)
        self.assertLess(recipe.index('bash "${FUSION_ACCOUNTS_COMPONENT_SCRIPT}"'), recipe.index(marker))
        self.assertLess(recipe.index(marker), recipe.index('  write_source_preparation_metadata\n}'))


if __name__ == '__main__':
    unittest.main()
