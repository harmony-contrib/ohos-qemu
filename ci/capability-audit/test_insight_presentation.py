"""Orchestration fixtures preserve transient pixels; never simulate a guest gate."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from insight_form_runtime import capture_phase as capture_form
from insight_navigation_runtime import capture_phase as capture_navigation

FIXTURES = Path(__file__).parent / 'fixtures'
FORM = json.loads((FIXTURES / 'insight_form_diagnostic.json').read_text())
NAV = json.loads((FIXTURES / 'insight_navigation_diagnostic.json').read_text())


class CapturedUiFixture:
    def __init__(self, root, layout, picture):
        self.root, self.document, self.picture = root, layout, picture
        self.sequence = 0

    def layout(self, *, bundle, label):
        self.sequence += 1
        path = self.root / (str(self.sequence) + '.json')
        path.write_text(json.dumps(self.document) + '\n')
        return self.document, path

    def screenshot(self, *, label):
        path = self.root / (str(self.sequence) + '.png')
        source = FIXTURES / 'insight_form_diagnostic_unpresented_white.png' if self.sequence == 1 else self.picture
        shutil.copyfile(source, path)
        return path


class InsightPresentationTests(unittest.TestCase):
    def test_widget_metadata_cannot_accept_first_white_frame_as_presented(self):
        phase = FORM['phases'][0]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ui = CapturedUiFixture(root, phase['acquired_layout'], FIXTURES / phase['acquired_image'])
            with patch('insight_form_runtime.time.sleep'):
                result = capture_form(ui, root / 'evidence.json', FORM['target_nonce'], phase['form_id'], 'added', 'fixture')
            self.assertFalse(result['first_artifact_behavior_gate_passed'])
            self.assertEqual(len(result['samples']), 4)
            self.assertIn('not_ready', result['samples'][0])
            self.assertEqual(result['samples'][-1]['consecutive_identical_presentations'], 3)
            self.assertTrue(Path(result['samples'][0]['screenshot']).exists())

    def test_navigation_requires_three_actual_full_width_text_frames_after_white_transient(self):
        phase = NAV['phases'][0]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ui = CapturedUiFixture(root, json.loads((FIXTURES / phase['layout']).read_text()), FIXTURES / phase['screenshot'])
            with patch('insight_navigation_runtime.time.sleep'):
                result = capture_navigation(ui, root / 'evidence.json', 'page', 0,
                    NAV['target_nonce'], NAV['roles']['system']['run_id'])
            self.assertFalse(result['first_artifact_behavior_gate_passed'])
            self.assertEqual(len(result['samples']), 4)
            self.assertIn('not_ready', result['samples'][0])
            self.assertEqual(result['samples'][-1]['consecutive_identical_presentations'], 3)
            self.assertTrue(Path(result['samples'][0]['screenshot']).exists())


if __name__ == '__main__':
    unittest.main()
