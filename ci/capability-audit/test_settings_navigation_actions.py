"""Synthetic UI/AMS fixtures test rejection only, not actual Settings capability."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageDraw
from guest_ui import select_node
from run_root_probe import digest
from settings_navigation_evidence import CALLER, embedded_title, provider_binding
from settings_navigation_ui import verify_actions
from test_settings_navigation_evidence import DUMP, node


class SettingsActionsTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.methods = [{'name': 'real.ime', 'id': 'ServiceExtAbility', 'label': 'real input'}]
        identity = self.root / 'settings.json'
        identity.write_text(json.dumps({'applicationInfo': {'name': 'com.ohos.settings', 'uid': 20010011,
                            'isSystemApp': True, 'appPrivilegeLevel': 'system_basic'}}))
        self.actions = {'settings_identity': str(identity), 'settings_identity_sha256': digest(identity),
                        'settings_uid': 20010011, 'caller_uid': 20010038, 'pages': []}
        for index, (cycle, route) in enumerate(((1, 'input'), (1, 'detail'), (2, 'input'), (2, 'detail'))):
            def layout_file(label, tree):
                path = self.root / (str(index) + '-' + label + '.json')
                path.write_text(json.dumps(tree))
                return {'layout': str(path), 'layout_sha256': digest(path)}
            button = node('Button', id='settings-probe-' + route, clickable='true', enabled='true')
            tree = node('root', children=[button], bundleName=CALLER)
            request = layout_file('request', tree)
            request['selected_node'] = select_node(tree, CALLER, identifier='settings-probe-' + route, clickable=True)
            title = '输入法' if route == 'input' else 'real input'
            tree = node('root', children=[node('UIExtensionComponent', children=[node('TitleBar', title)])], bundleName=CALLER)
            provider = layout_file('provider', tree)
            dump = self.root / (str(index) + '.ams.txt')
            dump.write_text(DUMP)
            provider.update(title=title, node=embedded_title(tree, title), provider_dump=str(dump),
                            provider_dump_sha256=digest(dump), provider_binding=provider_binding(DUMP, 20010011, 20010038))
            tree = node('root', children=[node('Button', id='settings-probe-input')], bundleName=CALLER)
            returned = layout_file('returned', tree)
            returned['node'] = select_node(tree, CALLER, identifier='settings-probe-input')
            screen = self.root / (str(index) + '.png')
            image = Image.new('RGB', (1280, 800), 'white')
            ImageDraw.Draw(image).rectangle((10, 40, 40, 60), fill='black')
            image.save(screen)
            self.actions['pages'].append(dict(cycle=cycle, route=route, request=request, provider=provider,
                                               returned=returned, screenshot=str(screen), screenshot_sha256=digest(screen)))

    def test_all_routes_require_independent_ui_and_process_binding(self):
        self.assertEqual(verify_actions(self.actions, self.methods, 20010038), {'pages': 4, 'cycles': 2})
        for mutate in ('missing', 'wrong-provider', 'wrong-caller', 'wrong-route'):
            value = copy.deepcopy(self.actions)
            if mutate == 'missing':
                value['pages'].pop()
            elif mutate == 'wrong-provider':
                value['pages'][0]['provider']['provider_binding']['provider_pid'] = 9999
            elif mutate == 'wrong-caller':
                value['caller_uid'] = 20010039
            else:
                value['pages'][0]['route'] = 'detail'
            with self.subTest(mutate=mutate), self.assertRaises(ValueError):
                verify_actions(value, self.methods, 20010038)

    def test_same_title_outside_extension_is_not_provider_proof(self):
        provider = self.actions['pages'][0]['provider']
        path = Path(provider['layout'])
        tree = json.loads(path.read_text())
        tree['children'][0]['attributes']['type'] = 'Column'
        path.write_text(json.dumps(tree))
        provider['layout_sha256'] = digest(path)
        with self.assertRaises(ValueError):
            verify_actions(self.actions, self.methods, 20010038)

    def test_tampered_or_unpainted_screenshot_rejected(self):
        page = self.actions['pages'][0]
        path = Path(page['screenshot'])
        Image.new('RGB', (1280, 800), 'white').save(path)
        with self.assertRaises(ValueError):
            verify_actions(self.actions, self.methods, 20010038)
        page['screenshot_sha256'] = digest(path)
        with self.assertRaises(ValueError):
            verify_actions(self.actions, self.methods, 20010038)


if __name__ == '__main__':
    unittest.main()
