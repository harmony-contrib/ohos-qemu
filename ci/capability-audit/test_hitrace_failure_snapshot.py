"""Failure diagnostic orchestration only; no simulated trace counts as a pass."""
import unittest

from hitrace_failure_snapshot import capture


class FailureSnapshotTests(unittest.TestCase):
    remote = ('/data/app/el2/100/base/org.harmonycontrib.hitraceaudit/files/'
              'hitrace-' + 'a' * 32 + '-results.log')

    def test_capture_continues_after_independent_command_failures(self):
        calls = []

        def shell(script, label):
            calls.append((script, label))
            if label in ('failure-kernel-trace', 'failure-hilog'):
                raise ValueError('actual transport failure retained by caller')
            return ''

        result = capture(shell, self.remote)
        self.assertEqual(len(calls), 7)
        self.assertIn('capture_error', result['observations']['kernel-trace'])
        self.assertEqual(result['observations']['ability-state'], {'captured': True})
        self.assertEqual(calls[-1], ('hilog -x', 'failure-hilog'))
        self.assertFalse(any(token in script for script, _ in calls for token in
                             ('force-stop', 'kill ', 'param set', 'echo 0 >', 'hilog -r')))

    def test_foreign_or_injected_journals_never_reach_shell(self):
        for remote in ('', self.remote + '; true', self.remote.replace('a' * 32, 'X' * 32),
                       self.remote.replace('hitraceaudit', 'anotherapp')):
            with self.subTest(remote=remote), self.assertRaises(ValueError):
                capture(lambda *_: self.fail('invalid path reached guest'), remote)


if __name__ == '__main__':
    unittest.main()
