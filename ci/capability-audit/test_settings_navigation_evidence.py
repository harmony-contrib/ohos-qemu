"""Synthetic parser tests; these fixtures never count as guest evidence."""
import copy
import unittest

from settings_navigation_evidence import CALLER, embedded_title, provider_binding

DUMP = '''  ExtensionRecords:
    uri [/com.ohos.settings/phone/ExternalCommonUIExtensionAbility1]
      AbilityRecord ID #13   state #FOREGROUND   start time [96684]
      main name [ExternalCommonUIExtensionAbility]
      bundle name [com.ohos.settings]
      ability type [UIEXTENSION]
      app state #FOREGROUND
      root host bundle name [org.harmonycontrib.capabilityaudit]
      root host module name [entry]
      root host ability name [EntryAbility]
      pid: 2968
  AppRunningRecords:
    AppRunningRecord ID #3
      process name [org.harmonycontrib.capabilityaudit]
      pid #2632  uid #20010038
      state #FOREGROUND
      uiextension provider #0
        pid #2968
    AppRunningRecord ID #4
      process name [com.ohos.settings:ExternalCommonUIExtensionAbility:1]
      pid #2968  uid #20010011
      state #FOREGROUND
      root caller #0
        pid #2632
'''


def node(kind, text='', children=None, **attributes):
    return {'attributes': dict(type=kind, text=text, visible='true', bounds='[3,37][1277,97]', **attributes),
            'children': children or []}


class SettingsNavigationEvidenceTests(unittest.TestCase):
    def test_reciprocal_real_process_identity_is_required(self):
        result = provider_binding(DUMP, 20010011, 20010038)
        self.assertEqual(result['provider_pid'], 2968)
        self.assertEqual(result['host_pid'], 2632)
        for old, new in (('state #FOREGROUND', 'state #BACKGROUND'),
                         ('root host bundle name [' + CALLER, 'root host bundle name [another.app'),
                         ('pid #2632\n', 'pid #9999\n'),
                         ('pid #2968\n', 'pid #9999\n'),
                         ('uid #20010011', 'uid #20010012'),
                         ('ability type [UIEXTENSION]', 'ability type [PAGE]')):
            with self.subTest(old=old), self.assertRaises(ValueError):
                provider_binding(DUMP.replace(old, new), 20010011, 20010038)

    def test_wrong_user_and_duplicate_provider_rejected(self):
        for provider, caller in ((20010011, 20010011), (10011, 20010038), (True, 20010038)):
            with self.assertRaises(ValueError):
                provider_binding(DUMP, provider, caller)
        with self.assertRaises(ValueError):
            provider_binding(DUMP + DUMP, 20010011, 20010038)

    def test_title_must_be_inside_host_extension_not_caller_text(self):
        title = node('TitleBar', '输入法', [node('Text', '输入法')])
        tree = node('root', children=[node('UIExtensionComponent', children=[title])], bundleName=CALLER)
        self.assertEqual(embedded_title(tree, '输入法')['host_bundle'], CALLER)
        wrong = copy.deepcopy(tree)
        wrong['children'][0]['attributes']['type'] = 'Column'
        with self.assertRaises(ValueError):
            embedded_title(wrong, '输入法')
        for kind, value in (('bundleName', 'other.application'), ('visible', 'false')):
            wrong = copy.deepcopy(tree)
            wrong['children'][0]['attributes'][kind] = value
            with self.assertRaises(ValueError):
                embedded_title(wrong, '输入法')
        tree['children'][0]['children'].append(title)
        with self.assertRaises(ValueError):
            embedded_title(tree, '输入法')


if __name__ == '__main__':
    unittest.main()
