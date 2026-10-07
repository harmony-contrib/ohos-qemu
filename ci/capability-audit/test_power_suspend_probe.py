"""Suspend/display verifier fixtures; these do not attest a guest/kernel."""
from pathlib import Path
import tempfile
import unittest

from PIL import Image
from run_power_suspend_probe import screen_metrics, visible_nodes


class PowerSuspendProbeTests(unittest.TestCase):
    def test_visible_actual_window_required(self):
        root = {'attributes': {}, 'children': [
            {'attributes': {'visible': 'true', 'bundleName': 'fixture.system',
                            'bounds': '[0,0][1280,800]'}, 'children': []}]}
        self.assertEqual(visible_nodes(root), [{'bundle': 'fixture.system', 'rect': (0, 0, 1280, 800)}])
        for key, value in (('visible', 'false'), ('bundleName', ''), ('bounds', '[0,0][0,0]')):
            root['children'][0]['attributes'][key] = value
            with self.assertRaises(ValueError):
                visible_nodes(root)
            root['children'][0]['attributes'].update(visible='true', bundleName='fixture.system',
                                                    bounds='[0,0][1280,800]')

    def test_malformed_hierarchy_rejected(self):
        for layout in (None, {'attributes': [], 'children': []}, {'children': [None]},
                       {'attributes': {}, 'children': 'invalid'}):
            with self.assertRaises(ValueError):
                visible_nodes(layout)

    def test_uniform_display_rejected_and_real_dimensions_retained(self):
        with tempfile.TemporaryDirectory() as work:
            path = Path(work) / 'synthetic-fixture.png'
            for color in ('black', 'white', '#336699'):
                Image.new('RGB', (1280, 800), color).save(path)
                with self.assertRaises(ValueError):
                    screen_metrics(path)
            picture = Image.new('RGB', (128, 128))
            picture.putdata([(x * 2, y * 2, (x + y) % 256) for y in range(128) for x in range(128)])
            picture.save(path)
            result = screen_metrics(path)
            self.assertEqual((result['width'], result['height']), (128, 128))
            self.assertGreaterEqual(result['sample_color_count'], 64)


if __name__ == '__main__':
    unittest.main()
