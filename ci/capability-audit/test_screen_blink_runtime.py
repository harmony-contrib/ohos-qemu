"""Orchestration doubles only: these never count as packaged guest evidence."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
from build_screen_blink_probe import BUNDLE
from screen_blink_runtime import exercise
import test_screen_blink_results as fixtures


class RuntimeTests(unittest.TestCase):
    def execute(self, directory, *, cleanup_fail=False, stale_repeat=False):
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
                if state['single']:
                    on = True
                    state['single'] = 0
                path = Path(directory) / f"frame-{state['sequence']}.png"
                Image.new('RGB', (200, 200), (130, 140, 36) if on else (32, 48, 64)).save(path)
                return path

        def clock():
            state['clock'] += .15
            return state['clock']

        identity = json.dumps({'applicationInfo': dict(appPrivilegeLevel='system_core',
                              isSystemApp=True, uid=20000001)})
        with patch('screen_blink_runtime.time.monotonic', clock), patch('screen_blink_runtime.time.sleep'):
            return exercise(Ui(), lambda *args: fixtures.BlinkResultTests.encode(actual), '/owned/result',
                Path(directory) / 'result', nonce, 'system', identity, wait_seconds=2)

    def test_full_sequence_and_cleanup(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.execute(directory)
            self.assertEqual(result['status'], 'pass', result['failures'])
            self.assertTrue(result['cleanup_verified'])
            self.assertFalse(result['first_artifact_behavior_gate_passed'])

    def test_cleanup_failure_cannot_pass(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.execute(directory, cleanup_fail=True)
            self.assertEqual(result['status'], 'fail')
            self.assertFalse(result['cleanup_verified'])

    def test_repeated_action_cannot_reuse_previous_observation(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.execute(directory, stale_repeat=True)
            self.assertEqual(result['status'], 'fail')
            self.assertTrue(any('timed out' in value for value in result['failures']))


if __name__ == '__main__':
    unittest.main()
