"""Complete module selection fixtures, not actual bindings device evidence."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from run_native_bindings_e2e import (EXPECTED_MODULES, adapt_owned_device_profiles,
    adapt_owned_hypium_verifier, declared_modules)


class NativeBindingsE2eRunnerTests(unittest.TestCase):
    def driver(self, names):
        return 'declare -a MODULES=(\n' + '\n'.join(name + ':Fixture' for name in names) + '\n)\n'

    def test_requires_all_modules_and_accepts_extra_current_literal_tests(self):
        names = sorted(EXPECTED_MODULES)
        self.assertEqual(len(declared_modules(self.driver(names))), 32)
        self.assertEqual(len(declared_modules(self.driver(names + ['extra_test']))), 33)
        for invalid in (names[:-1], names + [names[0]]):
            with self.assertRaises(ValueError):
                declared_modules(self.driver(invalid))
        with self.assertRaises(ValueError):
            declared_modules(self.driver(names).replace('ark_web:Fixture', '${MODULE}:Fixture'))

    def test_actual_driver_current_suite_and_no_original_source_mutations(self):
        text = Path(__file__).with_name('run_native_bindings_e2e.py').read_text()
        self.assertIn('snapshot(args.source,', text)
        self.assertIn("sha(owned_source / name) != source_record['files_sha256'][name]", text)
        self.assertIn('verify_modules(project,', text)
        self.assertIn("'first_artifact_behavior_gate_passed': False", text)
        self.assertNotIn("'-s', 'module'", text)

    def test_owned_device_adaptation_changes_only_literal_device_array(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            originals = {}
            for relative, key in (('entry/src/main/module.json5', 'deviceTypes'),
                                  ('entry/src/ohosTest/module.json5', '"deviceTypes"')):
                path = project / relative
                path.parent.mkdir(parents=True)
                source = '{\n  ' + key + ": ['phone'],\n  requestPermissions: ['fixture'],\n}\n"
                path.write_text(source)
                originals[relative] = source
            result = adapt_owned_device_profiles(project, 'phone')
            self.assertFalse(any(row['changed'] for row in result['files'].values()))
            result = adapt_owned_device_profiles(project, '2in1')
            for relative, row in result['files'].items():
                self.assertTrue(row['changed'])
                self.assertEqual(row['device_types'], ['phone', '2in1'])
                self.assertEqual((project / relative).read_text(), originals[relative].replace(
                    "['phone']", "['phone', '2in1']"))
            self.assertFalse(any(row['changed'] for row in adapt_owned_device_profiles(project, '2in1')['files'].values()))

    def test_unknown_ambiguous_or_nonliteral_device_configuration_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory)
            path = project / 'entry/src/main/module.json5'
            path.parent.mkdir(parents=True)
            for source in ('deviceTypes: profiles', "deviceTypes: ['tablet']", "deviceTypes: ['phone', 'phone']",
                           "deviceTypes: ['phone']\ndeviceTypes: ['phone']"):
                path.write_text(source)
                with self.assertRaises(ValueError):
                    adapt_owned_device_profiles(project, '2in1')

    def test_owned_hypium_tool_correction_requires_exact_original_and_keeps_assertions(self):
        relative = 'examples-ui/scripts/verify-ohostest-results.py'
        expected = '2b92192557f40452287bf09b23238c294da3c10f8accc1db5b4da8f54a828fe5'
        corrected = '324b4bd832eef303222fcaaf963fad0d5d97285ac84c024e0e41a725d69d5f29'
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / 'examples-ui'
            target = project / 'scripts/verify-ohostest-results.py'
            target.parent.mkdir(parents=True)
            target.write_text('fixture original verifier\n')
            def fixture_sha(path):
                if path == target and path.read_text() == 'fixture original verifier\n':
                    return expected
                from snapshot_native_bindings import sha
                return sha(path)
            with patch('run_native_bindings_e2e.sha', side_effect=fixture_sha):
                with self.assertRaises(ValueError):
                    adapt_owned_hypium_verifier(project, {'files_sha256': {relative: 'unknown'}})
                self.assertEqual(target.read_text(), 'fixture original verifier\n')
                report = adapt_owned_hypium_verifier(project, {'files_sha256': {relative: expected}})
            self.assertEqual(report['before_sha256'], expected)
            self.assertEqual(report['after_sha256'], corrected)
            self.assertEqual(target.read_bytes(), Path(__file__).with_name('verify_ohostest_results.py').read_bytes())


if __name__ == '__main__':
    unittest.main()
