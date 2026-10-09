import copy
import json
from pathlib import Path
import unittest

from verify_screen_modes import verify


class ScreenModesReadbackTests(unittest.TestCase):
    def setUp(self):
        self.value = {'scope': 'root_readonly_actual_display_service', 'screens': [
            {'id': 2, 'sourceMode': 0, 'activeModeIndex': 0, 'modes': [
                {'id': 7, 'width': 1280, 'height': 800, 'refreshRate': 60},
                {'id': 11, 'width': 1280, 'height': 800, 'refreshRate': 75},
                {'id': 20, 'width': 640, 'height': 480, 'refreshRate': 60}]}]}

    def check(self, value):
        return verify('QEMU_SCREEN_MODES:' + json.dumps(value))

    def test_actual_mode_ids_and_resolution_are_preserved(self):
        result = self.check(self.value)
        self.assertEqual([mode['id'] for mode in result['refresh_choices']], [7, 11])
        self.assertEqual(result['main_screen']['activeModeIndex'], 0)
        self.assertEqual(result['active_mode']['id'], 7)
        self.assertEqual(result['closed'], [])

    def test_empty_duplicate_ambiguous_and_invalid_main_rejected(self):
        for screens in ([], self.value['screens'] * 2,
                        [dict(self.value['screens'][0], sourceMode=3)],
                        [dict(self.value['screens'][0], activeModeIndex=3)],
                        [dict(self.value['screens'][0], id=True)]):
            value = copy.deepcopy(self.value)
            value['screens'] = screens
            with self.assertRaises(ValueError):
                self.check(value)

    def test_descending_ids_do_not_change_array_index_meaning(self):
        value = copy.deepcopy(self.value)
        value['screens'][0]['modes'].reverse()
        value['screens'][0]['activeModeIndex'] = 2
        result = self.check(value)
        self.assertEqual(result['active_mode']['id'], 7)
        self.assertEqual([item['id'] for item in result['refresh_choices']], [11, 7])

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

    def test_root_runner_requires_real_success_and_keeps_readonly_scope(self):
        from run_root_probe import probe_command, verify_result
        raw = 'QEMU_SCREEN_MODES:' + json.dumps(self.value)
        self.assertEqual(verify_result('screen-modes', raw, 'arm64', 'nonce', 0), self.check(self.value))
        for code in (1, 143, None, False):
            with self.assertRaises(ValueError):
                verify_result('screen-modes', raw, 'arm64', 'nonce', code)
        command = probe_command('screen-modes', '/data/local/tmp/test', 'nonce')
        self.assertIn('unset LD_LIBRARY_PATH LD_PRELOAD;', command)
        self.assertNotIn('--privileged', command)

    def test_future_package_gate_requires_actual_modes(self):
        import sys
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
        from verify_first_artifact_gate import REQUIRED_CHECKS
        self.assertIn('screen-modes', REQUIRED_CHECKS)
        suite = Path(__file__).with_name('run_packaged_qemu_suite.py').read_text()
        self.assertIn("check('screen-modes', work / 'screen-modes/result.json'", suite)


if __name__ == '__main__':
    unittest.main()
