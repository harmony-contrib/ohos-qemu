"""Orchestration doubles only: these never count as packaged guest evidence."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from build_screen_blink_probe import BUNDLE
from screen_blink_runtime import exercise
from run_root_probe import digest
import test_screen_blink_results as fixtures


class RuntimeTests(unittest.TestCase):
    def execute(self, directory, *, cleanup_fail=False, stale_repeat=False, caller_exit=False, splash=False,
                permanent_splash=False, stop_residual=False, missed_single=False):
        actual = fixtures.BlinkResultTests().observations()
        nonce = 'a' * 32
        state = dict(active=False, enabled=False, sequence=0, clock=0., single=0)

        def row(name, values, text=''):
            actual.append(dict(runId=nonce, role='system', name=name, values=values, text=text))

        class Ui:
            def layout(self, **kwargs):
                value = dict(attributes=dict(bundleName=BUNDLE, id='blink-pixel-surface',
                    visible='true', bounds='[0,0][200,200]'), children=[])
                path = Path(directory) / 'layout.json'
                path.write_text(json.dumps(value))
                return value, path

            def click(self, bundle, *, identifier, label):
                if identifier == 'blink-enable':
                    state['enabled'] = True
                    row('master.enabled', [1], '1')
                elif identifier == 'blink-disable':
                    state.update(enabled=False, active=False)
                    row('master.disabled', [1], '0')
                elif identifier == 'blink-start':
                    value = 5 if not state['enabled'] else 1 if state['active'] else 0
                    if value == 1 and stale_repeat:
                        return {}
                    state['active'] = state['enabled']
                    row('continuous.start', [value, 0, 1])
                elif identifier == 'blink-wrong-stop':
                    row('wrong.stop', [2, 0, 1])
                elif identifier == 'blink-stop':
                    state['active'] = False
                    row('continuous.stop', [0, 0, 1])
                elif identifier == 'blink-single':
                    state['single'] = 1
                    row('single.start', [0, 0, 1])
                elif identifier == 'blink-restore':
                    state.update(enabled=False, active=False)
                    row('cleanup.stop', [0, 0, 1])
                    row('cleanup.master', [0 if cleanup_fail else 1], '1' if cleanup_fail else '0')
                else:
                    raise AssertionError(identifier)
                return {}

            def screenshot(self, *, label):
                state['sequence'] += 1
                on = state['active'] and state['sequence'] % 2 == 0
                if stop_residual and label == 'stopped' and not state.get('residual_seen'):
                    on = True
                    state['residual_seen'] = True
                if state['single']:
                    on = not missed_single
                    state['single'] = 0
                path = Path(directory) / f"frame-{state['sequence']}.png"
                color = (130, 140, 36) if on else (32, 48, 64)
                if permanent_splash or (splash and state['sequence'] == 1):
                    color = (255, 255, 255)
                Image.new('RGB', (200, 200), color).save(path)
                return path

        def clock():
            state['clock'] += .15
            return state['clock']

        def shell(command, label):
            if command.startswith('aa force-stop '):
                state['active'] = False
                return 'stopped'
            if command.startswith('if test -d /proc/'):
                return 'ABSENT'
            if command.startswith('aa start '):
                actual[:] = fixtures.BlinkResultTests().observations(restarted=True)
                actual[0]['values'][2] = 456
                return 'start ability successfully'
            return fixtures.BlinkResultTests.encode(actual)

        identity = json.dumps({'applicationInfo': dict(appPrivilegeLevel='system_core',
                              isSystemApp=True, uid=20000001)})
        background = None
        if caller_exit:
            path = Path(directory) / 'before-launch.png'
            Image.new('RGB', (200, 200), (32, 48, 64)).save(path)
            background = dict(path=str(path), sha256=digest(path))
        with patch('screen_blink_runtime.time.monotonic', clock), patch('screen_blink_runtime.time.sleep'):
            return exercise(Ui(), shell, '/owned/result', Path(directory) / 'result', nonce, 'system', identity,
                            wait_seconds=2, background=background)

    def test_full_sequence_and_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.execute(directory)
            self.assertEqual(result['status'], 'pass', result['failures'])
            self.assertTrue(result['cleanup_verified'])
            self.assertFalse(result['first_artifact_behavior_gate_passed'])

    def test_starting_window_wait_is_only_a_precondition_and_is_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.execute(directory, splash=True)
            self.assertEqual(result['status'], 'pass', result['failures'])
            readiness = next(p for p in result['phases'] if p['name'] == 'baseline-readiness')
            self.assertEqual([f['kind'] for f in readiness['frames']], ['not-baseline', 'off', 'off', 'off'])

    def test_permanent_starting_window_cannot_pass_or_start_blinking(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.execute(directory, permanent_splash=True)
            self.assertEqual(result['status'], 'fail')
            self.assertNotIn('master.enabled-control', [p['name'] for p in result['phases']])
            self.assertTrue(any('baseline never' in error for error in result['failures']))

    def test_stop_failure_stays_failed_while_later_cases_run_after_proven_off(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.execute(directory, stop_residual=True, caller_exit=True)
            self.assertEqual(result['status'], 'fail')
            self.assertTrue(any(error.startswith('stopped:') for error in result['failures']))
            phases = [phase['name'] for phase in result['phases']]
            self.assertIn('stopped-recovery', phases)
            self.assertIn('single-auto-clear', phases)
            self.assertIn('caller_exit', result)
            self.assertTrue(result['cleanup_verified'])

    def test_cleanup_failure_cannot_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.execute(directory, cleanup_fail=True)
            self.assertEqual(result['status'], 'fail')
            self.assertFalse(result['cleanup_verified'])

    def test_missing_single_pulse_stays_failed_but_restored_later_cases_run(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.execute(directory, missed_single=True, caller_exit=True)
            self.assertEqual(result['status'], 'fail')
            self.assertTrue(any(error.startswith('single-auto-clear:') for error in result['failures']))
            self.assertIn('single-auto-clear-recovery', [p['name'] for p in result['phases']])
            self.assertIn('disabled-clears', [p['name'] for p in result['phases']])
            self.assertIn('caller_exit', result)
            self.assertTrue(result['cleanup_verified'])

    def test_caller_exit_and_new_generation_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.execute(directory, caller_exit=True)
            self.assertEqual(result['status'], 'pass', result['failures'])
            self.assertEqual(result['caller_exit']['pid'], 123)
            self.assertEqual(result['caller_exit']['restarted_pid'], 456)
            self.assertTrue(result['cleanup_verified'])

    def test_repeated_action_cannot_reuse_previous_observation(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.execute(directory, stale_repeat=True)
            self.assertEqual(result['status'], 'fail')
            self.assertTrue(any('timed out' in value for value in result['failures']))


if __name__ == '__main__':
    unittest.main()
