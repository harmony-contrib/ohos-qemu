"""Synthetic frame-wait fixtures; none is a real guest/compositor pass."""
import hashlib
from pathlib import Path
import tempfile
import unittest

from PIL import Image
from vulkan_frame_capture import capture_presented_frame, presented_geometry

BUNDLE = 'org.fixture'
PRESENT = 'vulkan_window.present|frames=5 width=16 height=14 cleaned=1 destroyed=0 generation=1\n'


class FixtureClock:
    def __init__(self):
        self.now = 0

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class FixtureUi:
    def __init__(self, root, colors):
        self.root, self.colors, self.sequence = root, colors, 0
        self.geometry = '[2,3][18,17]'
        self.bundle = BUNDLE
        self.after_capture = lambda: None

    def layout(self, *, bundle, label):
        document = {'attributes': {'id': 'qemu-vulkan-surface', 'bundleName': self.bundle,
                    'visible': 'true', 'enabled': 'true', 'bounds': self.geometry}, 'children': []}
        path = self.root / (label + '.fixture-layout')
        path.write_text('synthetic hierarchy, not a guest capture')
        return document, path

    def screenshot(self, *, label):
        path = self.root / (label + '.png')
        Image.new('RGBA', (30, 30), self.colors[min(self.sequence, len(self.colors) - 1)]).save(path)
        self.sequence += 1
        self.after_capture()
        return path


class VulkanFrameCaptureTests(unittest.TestCase):
    def fixture(self, colors):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        return FixtureUi(Path(temporary.name), colors), FixtureClock(), []

    def capture(self, ui, clock, attempts, seconds=3):
        return capture_presented_frame(ui, BUNDLE, 1, PRESENT, attempts,
            lambda path: hashlib.sha256(path.read_bytes()).hexdigest(),
            wait_seconds=seconds, clock=clock, sleep=clock.sleep)

    def test_wait_preserves_startup_and_bad_color_then_requires_exact_interior(self):
        ui, clock, attempts = self.fixture([(255, 255, 255, 255), (51, 101, 150, 255), (51, 102, 153, 255)])
        result = self.capture(ui, clock, attempts)
        self.assertEqual([row['status'] for row in attempts], ['fail', 'fail', 'pass'])
        self.assertEqual(result['verified_rgba_pixels'], 24)
        self.assertEqual(len({row['screenshot'] for row in attempts}), 3)

    def test_persistent_startup_frame_fails_at_finite_deadline(self):
        ui, clock, attempts = self.fixture([(255, 255, 255, 255)])
        with self.assertRaisesRegex(ValueError, 'finite deadline'):
            self.capture(ui, clock, attempts)
        self.assertEqual(clock.now, 3)
        self.assertTrue(all(row['status'] == 'fail' for row in attempts))

    def test_success_after_slow_command_deadline_is_not_accepted(self):
        ui, clock, attempts = self.fixture([(51, 102, 153, 255)])
        ui.after_capture = lambda: clock.sleep(4)
        with self.assertRaisesRegex(ValueError, 'finite deadline'):
            self.capture(ui, clock, attempts)
        self.assertEqual(attempts[0]['status'], 'fail')

    def test_native_geometry_wrong_bundle_and_offscreen_fail_without_retry(self):
        for field, value in (('geometry', '[2,3][19,17]'), ('geometry', '[-1,3][15,17]'), ('bundle', 'other')):
            ui, clock, attempts = self.fixture([(51, 102, 153, 255)])
            setattr(ui, field, value)
            with self.assertRaises(ValueError):
                self.capture(ui, clock, attempts)
            self.assertEqual(ui.sequence, 0)

    def test_native_stage_rejects_stale_mixed_and_missing_cleanup(self):
        for result in ('', PRESENT + PRESENT, PRESENT.replace('cleaned=1', 'cleaned=0'),
                       PRESENT.replace('generation=1', 'generation=2'), PRESENT + 'vulkan_window.timeout|x\n'):
            with self.assertRaises(ValueError):
                presented_geometry(result, 1)
        recreated = PRESENT + PRESENT.replace('present|', 'destroyed|').replace('destroyed=0', 'destroyed=1') + PRESENT.replace('generation=1', 'generation=2')
        self.assertEqual(presented_geometry(recreated, 2), {'width': 16, 'height': 14})

    def test_wait_parameters_are_finite_integer_bounds(self):
        for seconds in (0, 61, True, 1.0):
            ui, clock, attempts = self.fixture([(51, 102, 153, 255)])
            with self.assertRaises(ValueError):
                self.capture(ui, clock, attempts, seconds)
            self.assertEqual(ui.sequence, 0)


if __name__ == '__main__':
    unittest.main()
