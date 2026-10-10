"""Synthetic key/UI boundaries, never actual packaged keyboard evidence."""
import unittest
from run_shortkey_keyboard_diagnostic import key_request, title_node, SHORTCUT, SCOPE


class ShortkeyKeyboardDiagnosticTests(unittest.TestCase):
    def test_bounded_real_key_requests(self):
        for modifier in ('meta_l', 'ctrl'):
            for duration in (100, 800):
                value = key_request(modifier, duration)
                self.assertEqual(value, {'keys': [{'type': 'qcode', 'data': modifier},
                    {'type': 'qcode', 'data': 'i'}], 'hold-time': duration})
        for modifier, duration in (('power', 100), ('meta_l', True), ('meta_l', 0),
                                   ('meta_l', 60000), ('ctrl', 100.0)):
            with self.subTest(modifier=modifier, duration=duration), self.assertRaises(ValueError):
                key_request(modifier, duration)

    def test_actual_settings_bundle_and_visible_title_required(self):
        node = {'attributes': {'bundleName': 'com.ohos.settings', 'text': '设置',
            'visible': 'true', 'enabled': 'true', 'bounds': '[0,0][100,40]'}, 'children': []}
        self.assertEqual(title_node(node)['bundle'], 'com.ohos.settings')
        for field, value in (('bundleName', 'org.test'), ('visible', 'false'), ('text', 'not Settings')):
            changed = {'attributes': dict(node['attributes'], **{field: value}), 'children': []}
            with self.subTest(field=field), self.assertRaises(ValueError): title_node(changed)
        with self.assertRaises(ValueError): title_node([node, node])

    def test_does_not_claim_duration_API_or_all_gap_closure(self):
        self.assertIn('NOT_duration_API_or_full_gate', SCOPE)
        self.assertEqual(SHORTCUT['businessId'], 'qemu.settings')
        self.assertEqual(SHORTCUT['keyDownDuration'], 500)


if __name__ == '__main__':
    unittest.main()
