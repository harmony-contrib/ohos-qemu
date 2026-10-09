"""Narrow parameter policy application; compilation/guest proofs are separate."""
import importlib.util
from pathlib import Path
import subprocess
import unittest

import test_fusion_service_domains as domains

COMPONENT = domains.COMPONENT.parent / 'fusion_partner_parameter'
spec = importlib.util.spec_from_file_location('fusion_parameter_baseline', COMPONENT / 'verify_source.py')
baseline = importlib.util.module_from_spec(spec)
spec.loader.exec_module(baseline)


class FusionPartnerParameterTests(domains.FusionServiceDomainsTests):
    def apply(self):
        first = super().apply()
        if first.returncode:
            return first
        return subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(self.root)],
                              capture_output=True, text=True)

    def snapshot(self):
        return {relative: path.read_bytes() if path.exists() else None
                for relative, _, _ in baseline.FILES
                for path in [self.root / baseline.PROJECT / relative]}

    def test_new_policy_requires_complete_domains(self):
        before = self.snapshot()
        result = subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(self.root)],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(before, self.snapshot())

    def test_partial_parameter_policy_fails_without_source_changes(self):
        self.assertEqual(self.apply().returncode, 0)
        for relative, _, _ in baseline.FILES[-3:]:
            path = self.root / baseline.PROJECT / relative
            data = path.read_bytes()
            path.unlink()
            before = self.snapshot()
            self.assertNotEqual(self.apply().returncode, 0)
            self.assertEqual(before, self.snapshot())
            path.write_bytes(data)

    def test_only_one_owned_flag_is_labeled_and_writable(self):
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(baseline.validate(self.root, require_patched=True))
        content = [(self.root / baseline.PROJECT / row[0]).read_text() for row in baseline.FILES[-3:]]
        meaningful = lambda value: [line for line in value.splitlines() if line and not line.startswith('#')]
        self.assertEqual(meaningful(content[0]), [
            'type fusion_partner_enable_param, parameter_attr, system_parameter_attr, system_internal_parameter_attr;'])
        self.assertEqual(meaningful(content[1]), [
            'persist.fusion_connectivity.enable_partner_agent u:object_r:fusion_partner_enable_param:s0'])
        self.assertEqual(meaningful(content[2]), [
            'allow partner_device_agent fusion_partner_enable_param:parameter_service { set };',
            'allow init fusion_partner_enable_param:parameter_service { set };',
            'allow { partner_device_agent samgr init } fusion_partner_enable_param:file { map open read };'])

    def test_parameter_preparation_follows_domains_before_traversal(self):
        recipe = (domains.ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        marker = 'bash "${FUSION_PARTNER_PARAMETER_COMPONENT_SCRIPT}"'
        self.assertEqual(recipe.count(marker), 1)
        self.assertLess(recipe.index('bash "${FUSION_SERVICE_DOMAINS_COMPONENT_SCRIPT}"'), recipe.index(marker))
        self.assertLess(recipe.index(marker), recipe.index('  write_source_preparation_metadata\n}'))

    def test_unknown_parameter_content_is_preserved(self):
        self.assertEqual(super().apply().returncode, 0)
        target = self.root / baseline.PROJECT / baseline.FILES[-2][0]
        target.write_text('# unrelated existing context\n')
        before = self.snapshot()
        result = subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(self.root)],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(before, self.snapshot())


if __name__ == '__main__':
    unittest.main()
