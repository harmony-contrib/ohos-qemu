import copy
import json
from pathlib import Path
import unittest

from verify_screen_modes import verify


class ScreenModesReadbackTests(unittest.TestCase):
    def setUp(self):
        self.value = {'scope': 'root_readonly_actual_display_service', 'screens': [
            {'id': 2, 'sourceMode': 0, 'activeModeIndex': 7, 'modes': [
                {'id': 7, 'width': 1280, 'height': 800, 'refreshRate': 60},
                {'id': 11, 'width': 1280, 'height': 800, 'refreshRate': 75},
                {'id': 20, 'width': 640, 'height': 480, 'refreshRate': 60}]}]}

    def check(self, value):
        return verify('QEMU_SCREEN_MODES:' + json.dumps(value))

    def test_actual_mode_ids_and_resolution_are_preserved(self):
        result = self.check(self.value)
        self.assertEqual([mode['id'] for mode in result['refresh_choices']], [7, 11])
        self.assertEqual(result['main_screen']['activeModeIndex'], 7)
        self.assertEqual(result['closed'], [])

    def test_empty_duplicate_ambiguous_and_invalid_main_rejected(self):
        for screens in ([], self.value['screens'] * 2,
                        [dict(self.value['screens'][0], sourceMode=3)],
                        [dict(self.value['screens'][0], activeModeIndex=1)],
                        [dict(self.value['screens'][0], id=True)]):
            value = copy.deepcopy(self.value)
            value['screens'] = screens
            with self.assertRaises(ValueError):
                self.check(value)

    def test_invalid_or_missing_modes_rejected(self):
        for modes in ([], self.value['screens'][0]['modes'] * 2,
                      [dict(self.value['screens'][0]['modes'][0], refreshRate=0)],
                      [dict(self.value['screens'][0]['modes'][0], id=True)],
                      [dict(self.value['screens'][0]['modes'][0], height=-1)]):
            value = copy.deepcopy(self.value)
            value['screens'][0]['modes'] = modes
            with self.assertRaises(ValueError):
                self.check(value)
        line = 'QEMU_SCREEN_MODES:' + json.dumps(self.value)
        with self.assertRaises(ValueError):
            verify(line + '\n' + line)

    def test_probe_only_reads_existing_service_and_never_sets_modes(self):
        source = (Path(__file__).with_name('probes') / 'screen_modes_readback.cpp').read_text()
        self.assertIn('ScreenManager::GetInstance().GetAllScreens(screens)', source)
        self.assertNotIn('SetScreenActiveMode', source)
        self.assertNotIn('SetMode', source)


if __name__ == '__main__':
    unittest.main()
