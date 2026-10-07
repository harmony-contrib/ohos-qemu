"""Diagnostic harness ownership fixtures; never image acceptance evidence."""
import argparse
import json
from pathlib import Path
import tempfile
import unittest

from run_owned_hap_diagnostic import power_timeout, run, validate_boot, validate_policy_mode, verify_policy_states


class OwnedHapDiagnosticTests(unittest.TestCase):
    def test_preserved_policy_mode_is_only_one_bounded_root_diagnostic(self):
        validate_policy_mode([], [('binder-sender', '/probe')], True)
        validate_policy_mode(['worker'], [], False)
        for personas, roots in ((['worker'], [('binder-sender', '/probe')]), ([], []),
                                 ([], [('bitmap', '/one'), ('binder-sender', '/two')])):
            with self.assertRaises(ValueError):
                validate_policy_mode(personas, roots, True)

    def test_actual_policy_query_retains_override_and_backup_values(self):
        self.assertEqual(power_timeout('ScreenOffTime: Timeout=10000ms\n'),
                         {'base_ms': 10000, 'override_ms': None})
        self.assertEqual(power_timeout('ScreenOffTime: Timeout=10000ms  OverrideTimeout=86400000ms\n'),
                         {'base_ms': 10000, 'override_ms': 86400000})
        for text in ('', 'ScreenOffTime: Timeout=0ms\n', 'ScreenOffTime: Timeout=10000ms failed\n',
                     'ScreenOffTime: Timeout=10000ms  OverrideTimeout=0ms\n',
                     'ScreenOffTime: Timeout=10000ms\nScreenOffTime: malformed\n',
                     'ScreenOffTime: Timeout=10000ms\nScreenOffTime: Timeout=10000ms\n'):
            with self.assertRaises(ValueError):
                power_timeout(text)

    def test_policy_restore_requires_exact_original_positive_typed_values(self):
        original = {'base_ms': 10000, 'override_ms': None}
        setup = dict(original, override_ms=86400000)
        verify_policy_states(original, setup, original)
        for before, after, restored in (
                (original, setup, dict(original, base_ms=9000000)),
                (original, dict(setup, override_ms=True), original),
                (original, None, original),
                (dict(original, override_ms=86400000), setup, original),
                ({'base_ms': 1, 'override_ms': None}, {'base_ms': 1, 'override_ms': 86400000},
                 {'base_ms': True, 'override_ms': None})):
            with self.assertRaises(ValueError):
                verify_policy_states(before, after, restored)

    def test_only_explicit_owned_diagnostic_boot_is_permitted(self):
        boot = {'status': 'pass', 'purpose': 'diagnostic', 'test_environment': {
            'external_keepalive': False, 'qemu_pid': 99999, 'qemu_command': 'owned /tmp/task.sock',
            'qmp_socket': '/tmp/task.sock', 'boot_id': 'diagnostic'}}
        self.assertEqual(validate_boot(boot), boot['test_environment'])
        for key, value in (('status', 'fail'), ('purpose', 'acceptance')):
            with self.assertRaises(ValueError):
                validate_boot(dict(boot, **{key: value}))
        for key, value in (('qemu_pid', True), ('qemu_pid', 1), ('qemu_command', ''),
                           ('qmp_socket', 'relative.sock'), ('external_keepalive', True)):
            with self.assertRaises(ValueError):
                validate_boot(dict(boot, test_environment=dict(boot['test_environment'], **{key: value})))

    def test_missing_boot_is_recorded_without_touching_VM_or_claiming_gate(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            args = argparse.Namespace(output=root / 'attempt', boot=root / 'missing.json')
            report = run(args)
            self.assertEqual(report['status'], 'fail')
            self.assertFalse(report['first_artifact_behavior_gate_passed'])
            self.assertEqual(report['commands'], [])
            self.assertFalse(report['screen_timeout_restore_attempted'])
            self.assertEqual(json.loads((args.output / 'evidence.json').read_text()), report)


if __name__ == '__main__':
    unittest.main()
