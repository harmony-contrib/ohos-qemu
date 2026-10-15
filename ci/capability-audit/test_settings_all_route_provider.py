"""Actual diagnostic AMS records and rejection mutations; not a navigation gate."""
from pathlib import Path
import unittest

from settings_navigation_evidence import page_binding, provider_binding

FIXTURES = Path(__file__).with_name('fixtures') / 'settings_all_route_provider_diagnostic_02'
SETTINGS_UID, CALLER_UID = 20010011, 20010038


class SettingsAllRouteProviderTests(unittest.TestCase):
    def text(self, name):
        return (FIXTURES / (name + '.txt')).read_text()

    def test_actual_input_and_network_extensions(self):
        for name, ability in (('1-input', 'ExternalCommonUIExtensionAbility'),
                              ('1-network', 'OpenNetworkUIExtensionAbility'),
                              ('2-network', 'OpenNetworkUIExtensionAbility')):
            with self.subTest(name=name):
                binding = provider_binding(self.text(name), SETTINGS_UID, CALLER_UID, ability=ability)
                self.assertEqual(binding['provider_uid'], SETTINGS_UID)
                self.assertEqual(binding['host_uid'], CALLER_UID)
                self.assertNotEqual(binding['provider_pid'], binding['host_pid'])
        with self.assertRaises(ValueError):
            provider_binding(self.text('1-network'), SETTINGS_UID, CALLER_UID)
        with self.assertRaises(ValueError):
            provider_binding(self.text('1-network'), SETTINGS_UID, CALLER_UID, ability='foreign')

    def test_network_reciprocal_host_and_uid_cannot_be_forged(self):
        original = self.text('1-network')
        for text, settings, caller in (
                (original, SETTINGS_UID + 1, CALLER_UID),
                (original, SETTINGS_UID, CALLER_UID + 1),
                (original, SETTINGS_UID, SETTINGS_UID),
                (original.replace('root caller #0\n        pid #2559',
                                  'root caller #0\n        pid #99999'), SETTINGS_UID, CALLER_UID),
                (original.replace('state #FOREGROUND', 'state #BACKGROUND'), SETTINGS_UID, CALLER_UID)):
            with self.subTest(settings=settings, caller=caller), self.assertRaises(ValueError):
                provider_binding(text, settings, caller, ability='OpenNetworkUIExtensionAbility')

    def test_actual_main_pages_and_distinct_background_caller(self):
        for name in ('1-display', '1-app-detail', '2-display'):
            with self.subTest(name=name):
                binding = page_binding(self.text(name), SETTINGS_UID, CALLER_UID)
                self.assertEqual(binding['provider_ability'], 'com.ohos.settings.MainAbility')
                self.assertEqual(binding['caller_pid'], 2559)
                self.assertNotEqual(binding['provider_pid'], binding['caller_pid'])
        with self.assertRaises(ValueError):
            page_binding(self.text('1-network'), SETTINGS_UID, CALLER_UID)

    def test_foreign_or_background_main_page_cannot_qualify(self):
        original = self.text('1-display')
        for text, settings, caller in (
                (original, SETTINGS_UID + 1, CALLER_UID),
                (original, SETTINGS_UID, CALLER_UID + 1),
                (original, SETTINGS_UID, True),
                (original, SETTINGS_UID, SETTINGS_UID),
                (original.replace('com.ohos.settings.MainAbility', 'foreign.MainAbility'), SETTINGS_UID, CALLER_UID),
                (original.replace('state #FOREGROUND', 'state #BACKGROUND'), SETTINGS_UID, CALLER_UID),
                (original.replace('process name [org.harmonycontrib.capabilityaudit]',
                                  'process name [foreign]'), SETTINGS_UID, CALLER_UID)):
            with self.subTest(settings=settings, caller=caller), self.assertRaises(ValueError):
                page_binding(text, settings, caller)


if __name__ == '__main__':
    unittest.main()
