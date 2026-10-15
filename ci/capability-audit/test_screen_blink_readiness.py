"""Actual diagnostic captures and controlled rejection mutations; no full-gate proof."""
import copy
import json
from pathlib import Path
import unittest

from screen_blink_readiness import verify_startup_readiness
from verify_screen_blink_evidence import checked
from verify_screen_blink_results import classify_pixels, verify_frames

FIXTURES = Path(__file__).with_name('fixtures') / 'screen_blink_readiness_diagnostic_02'


class ScreenBlinkReadinessTests(unittest.TestCase):
    def setUp(self):
        self.capture = json.loads((FIXTURES / 'captures.json').read_text())

    def row(self, value):
        row = copy.deepcopy(value)
        for frame in row['frames']:
            frame['path'] = str(FIXTURES / frame['path'])
        return row

    def verify(self, row, budget=180):
        return verify_startup_readiness(row, self.capture['rect'], checked,
                                       classify_pixels, verify_frames,
                                       expected_wait_seconds=budget)

    def test_actual_new_capture_windows_and_original_missing_window(self):
        self.assertEqual(len(self.capture['recorded_windows']), 2)
        for captured in self.capture['recorded_windows']:
            with self.subTest(phase=captured['name']):
                self.verify(self.row(captured))
        old = self.row(self.capture['original_missing_window'])
        self.assertGreater(old['frames'][0]['after'] - old['frames'][0]['before'], 3)
        with self.assertRaisesRegex(ValueError, 'captured bounded startup'):
            self.verify(old)

    def test_budget_chronology_identity_and_classification_tampering(self):
        for captured in self.capture['recorded_windows']:
            original = self.row(captured)
            for mutation in ('budget', 'bool-budget', 'missing-start', 'deadline',
                             'late-capture', 'nonfinite', 'reorder', 'duplicate', 'kind', 'hash'):
                row = copy.deepcopy(original)
                if mutation == 'budget':
                    row.update(wait_seconds=600, deadline=row['started'] + 600)
                elif mutation == 'bool-budget': row['wait_seconds'] = True
                elif mutation == 'missing-start': row.pop('started')
                elif mutation == 'deadline': row['deadline'] += .01
                elif mutation == 'late-capture': row['frames'][-1]['after'] = row['deadline'] + .01
                elif mutation == 'nonfinite': row['frames'][0]['before'] = float('nan')
                elif mutation == 'reorder': row['frames'][0:2] = reversed(row['frames'][0:2])
                elif mutation == 'duplicate': row['frames'][1] = copy.deepcopy(row['frames'][0])
                elif mutation == 'kind': row['frames'][0]['kind'] = 'off'
                else: row['frames'][0]['sha256'] = '0' * 64
                with self.subTest(phase=captured['name'], mutation=mutation), self.assertRaises(ValueError):
                    self.verify(row)

    def test_final_baseline_capture_bound_still_applies_inside_startup_window(self):
        for captured in self.capture['recorded_windows']:
            row = self.row(captured)
            frame = row['frames'][-1]
            frame['after'] = frame['before'] + 3.01
            self.assertLess(frame['after'], row['deadline'])
            with self.subTest(phase=captured['name']), self.assertRaises(ValueError):
                self.verify(row)

    def test_explicit_custom_budget_cannot_replace_default_acceptance_budget(self):
        row = self.row(self.capture['recorded_windows'][0])
        # Controlled parameter mutation; the source run actually used 180 seconds.
        row.update(wait_seconds=90, deadline=row['started'] + 90)
        self.verify(row, 90)
        with self.assertRaises(ValueError): self.verify(row)


if __name__ == '__main__':
    unittest.main()
