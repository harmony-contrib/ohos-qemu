"""Orchestration failure fixtures only, never guest evidence."""
import unittest

from batch_probe_policy import independent_probe


class BatchProbePolicyTests(unittest.TestCase):
    def setUp(self):
        self.report = dict(status='fail', failures=[], first_artifact_behavior_gate_passed=False)
        self.health_calls = []
        self.saved = 0

    def save(self):
        self.saved += 1

    def test_failed_probe_does_not_skip_independent_next_or_become_acceptance(self):
        with independent_probe(self.report, 'first', self.health_calls.append, self.save):
            raise ValueError('actual command failed')
        with independent_probe(self.report, 'second', self.health_calls.append, self.save):
            pass
        self.assertEqual(self.health_calls, ['before-first', 'after-first', 'before-second', 'after-second'])
        self.assertEqual(self.report['independent_probes']['first']['status'], 'fail')
        self.assertEqual(self.report['independent_probes']['second']['status'], 'pass')
        self.assertEqual(len(self.report['failures']), 1)
        self.assertEqual(self.report['status'], 'fail')
        self.assertIs(self.report['first_artifact_behavior_gate_passed'], False)

    def test_health_failure_before_or_after_is_never_swallowed(self):
        for position in ('before', 'after'):
            def health(label):
                if label.startswith(position):
                    raise ValueError('changed boot or cleanup failed')
            with self.subTest(position=position), self.assertRaises(ValueError):
                with independent_probe(self.report, position, health, self.save):
                    pass
        self.assertNotIn('before', self.report['independent_probes'])
        self.assertEqual(self.report['independent_probes']['after']['status'], 'fail')

    def test_interrupts_and_unclassified_errors_stop_the_batch(self):
        for exception in (KeyboardInterrupt, SystemExit, RuntimeError):
            with self.subTest(exception=exception), self.assertRaises(exception):
                with independent_probe(self.report, exception.__name__, self.health_calls.append, self.save):
                    raise exception('stop')

    def test_all_successful_samples_still_do_not_grant_a_complete_gate(self):
        with independent_probe(self.report, 'sample', self.health_calls.append, self.save):
            pass
        self.assertEqual(self.report['failures'], [])
        self.assertEqual(self.report['independent_probes']['sample']['status'], 'pass')
        self.assertIs(self.report['first_artifact_behavior_gate_passed'], False)


if __name__ == '__main__':
    unittest.main()
