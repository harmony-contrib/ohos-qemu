"""Reject fabricated happy paths; synthetic fixtures test the verifier only."""
import copy
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest

from photos_asset_ui import button_ancestor, dialog_control, verify_actions
from photos_asset_contract import TEMPLATE, inputs, verify_inputs
from run_normal_hap_probe import BUNDLE, verifier_arguments
from run_root_probe import digest
from verify_photos_asset_results import verify

RUN = '1234567890abcdef1234567890abcdef'
IDENTITY = json.dumps({'applicationInfo': {'appPrivilegeLevel': 'normal', 'isSystemApp': False,
                                          'uid': 20010001}})


def fixture():
    rows = []
    def add(name, value):
        rows.append({'runId': RUN, 'sequence': len(rows) + 1, 'name': name, 'pass': True,
                     'value': value if isinstance(value, str) else json.dumps(value)})
    for cycle in (1, 2):
        add('default-album.' + str(cycle), 'All photos')
        add('recent-empty-or-current.' + str(cycle), {'dateTaken': 0, 'identifier': '0'})
        add('recent-explicit-options.' + str(cycle), {'dateTaken': 0, 'identifier': '0'})
        add('recent-options-unmodified.' + str(cycle), '{}')
    add('picker.invalid-count', {'code': 401})
    add('metadata.complete', 'Observations only; no asset/FA-card/backend closure claimed')
    add('picker.opened', 'Awaiting actual user UI action')
    add('picker.user-cancel-result', {'photoUris': []})
    add('asset.dialog-requested', 'file://' + BUNDLE + '/data/storage/el2/base/files/photos-source-' + RUN + '.jpg')
    uri = 'file://media/Photo/1/IMG_test/qemu-' + RUN + '.jpg'
    add('asset.dialog-result', [uri])
    add('asset.written', uri)
    identifier = 0
    for letter in 'qemu-' + RUN:
        identifier = (identifier * 13 + ord(letter)) % 9999991
    add('asset.recent', {'dateTaken': 1791542308069, 'identifier': str(identifier)})
    add('asset.read-picker-requested', uri)
    add('asset.selected', {'photoUris': [uri]})
    add('asset.readback', {'width': 64, 'height': 64, 'red': 37, 'green': 149, 'blue': 212, 'alpha': 255})
    return rows


def serialized(rows):
    return '\n'.join(json.dumps(row) for row in rows) + '\n'


def node(identifier, kind='Button', children=(), **extra):
    attrs = {'id': identifier, 'type': kind, 'bundleName': BUNDLE, 'visible': 'true',
             'enabled': 'true', 'clickable': 'true', 'bounds': '[10,20][110,70]'}
    attrs.update(extra)
    return {'attributes': attrs, 'children': list(children)}


class PhotosAssetTests(unittest.TestCase):
    def test_exact_round_trip_does_not_claim_whole_provider(self):
        result = verify(serialized(fixture()), RUN, IDENTITY)
        self.assertEqual(result['observations'], 19)
        self.assertEqual(result['closed'], [])
        self.assertIn('cloud provider', result['not_claimed'])

    def test_failed_stale_reordered_or_truncated_rows_rejected(self):
        rows = fixture()
        for index in range(len(rows)):
            for key, value in [('pass', False), ('pass', 'true'), ('runId', '0' * 32),
                               ('sequence', True), ('sequence', 0), ('name', 'pretend')]:
                with self.subTest(index=index, key=key, value=value):
                    altered = copy.deepcopy(rows)
                    altered[index][key] = value
                    with self.assertRaises(ValueError):
                        verify(serialized(altered), RUN, IDENTITY)
        for altered in (rows[:-1], rows + [rows[-1]], list(reversed(rows))):
            with self.assertRaises(ValueError):
                verify(serialized(altered), RUN, IDENTITY)

    def test_pass_boolean_does_not_override_invalid_actual_values(self):
        for name, value in [('picker.invalid-count', {'code': 201}),
                            ('picker.user-cancel-result', {'photoUris': ['unwanted']}),
                            ('asset.dialog-requested', 'file://other/asset.jpg'),
                            ('asset.dialog-result', []), ('asset.dialog-result', ['file://media/Photo/1/old.jpg']),
                            ('asset.written', 'different'), ('asset.read-picker-requested', 'different'),
                            ('asset.selected', {'photoUris': []}),
                            ('asset.recent', {'dateTaken': 1, 'identifier': '0'}),
                            ('recent-options-unmodified.1', '{"modified":true}'),
                            ('recent-empty-or-current.1', {'dateTaken': -1, 'identifier': '-1'}),
                            ('recent-explicit-options.1', {'dateTaken': True, 'identifier': '0'})]:
            with self.subTest(name=name, value=value):
                rows = fixture()
                next(row for row in rows if row['name'] == name)['value'] = value if isinstance(value, str) else json.dumps(value)
                with self.assertRaises(ValueError):
                    verify(serialized(rows), RUN, IDENTITY)

    def test_pixel_content_and_dimensions_are_checked_independently(self):
        for key, value in [('width', 63), ('height', 65), ('red', 46), ('green', 140),
                           ('blue', 202), ('alpha', 254), ('red', True), ('red', 37.0)]:
            rows = fixture()
            pixels = json.loads(rows[-1]['value'])
            pixels[key] = value
            rows[-1]['value'] = json.dumps(pixels)
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                verify(serialized(rows), RUN, IDENTITY)

    def test_ordinary_identity_is_mandatory(self):
        for key, value in [('appPrivilegeLevel', 'system_basic'), ('isSystemApp', True), ('uid', 0)]:
            identity = json.loads(IDENTITY)
            identity['applicationInfo'][key] = value
            with self.assertRaises(ValueError):
                verify(serialized(fixture()), RUN, json.dumps(identity))

    def test_close_selects_only_same_bundle_enabled_button_ancestor(self):
        icon = node('Third_Select_PickerClose', 'Image', clickable='false')
        tree = node('close-button', children=[icon])
        self.assertEqual(button_ancestor(tree, BUNDLE, 'Third_Select_PickerClose')['attributes']['id'], 'close-button')
        for changed in (node('close-button', children=[icon], bundleName='other.app'),
                        node('close-button', children=[icon], enabled='false'), [tree, tree]):
            with self.assertRaises(ValueError):
                button_ancestor(changed, BUNDLE, 'Third_Select_PickerClose')

    def test_save_and_selection_need_exact_visible_consent_and_count(self):
        prompt = node('', 'Text', text='允许“Capability audit”保存 1 张图片？', clickable='false')
        allow = node('advanced_dialog_button_1', text='允许')
        self.assertEqual(dialog_control([prompt, allow], BUNDLE, 'save')['attributes']['id'], 'advanced_dialog_button_1')
        for bad in ([allow], [prompt, node('advanced_dialog_button_1', text='禁止')], [prompt, allow, allow]):
            with self.assertRaises(ValueError):
                dialog_control(bad, BUNDLE, 'save')
        complete = node('Complete', text='完成')
        count = node('currentSelectCount', 'Text', text='已选 1/1')
        self.assertEqual(dialog_control([count, complete], BUNDLE, 'select')['attributes']['id'], 'Complete')
        with self.assertRaises(ValueError):
            dialog_control([node('currentSelectCount', 'Text', text='已选 0/1'), complete], BUNDLE, 'select')

    def test_compiled_input_and_public_sdk_hashes_are_bound(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary) / 'project'
            page = project / 'entry/src/main/ets/pages/Index.ets'
            page.parent.mkdir(parents=True)
            page.write_text(TEMPLATE.read_text().replace('__PHOTO_ASSET_RUN__', RUN))
            module = project / 'entry/src/main/module.json5'
            module.write_text(json.dumps({'module': {'requestPermissions': []}}))
            sdk = Path(temporary) / 'sdk'
            api = sdk / 'ets/api'
            api.mkdir(parents=True)
            for name in ('@ohos.file.photoAccessHelper.d.ts', '@ohos.file.fs.d.ts',
                         '@ohos.file.fileuri.d.ts', '@ohos.multimedia.image.d.ts'):
                (api / name).write_text('synthetic verifier fixture, not a real SDK')
            recorded = inputs(project, sdk, 'arm64', RUN)
            verify_inputs(recorded, RUN, 'arm64')
            page.write_text(page.read_text().replace('srcPixelFormat:', 'wrongSourceFormat:'))
            with self.assertRaises(ValueError):
                verify_inputs(recorded, RUN, 'arm64')
            module.write_text(json.dumps({'module': {'requestPermissions': ['ohos.permission.WRITE_IMAGEVIDEO']}}))
            with self.assertRaises(ValueError):
                inputs(project, sdk, 'arm64', RUN)

    def test_runner_supplies_identity_and_architecture(self):
        arguments = verifier_arguments('photos-asset', 'archive', 'raw', 'identity', RUN, 'arm64', 'output')
        self.assertIn('--application-identity', arguments)
        self.assertIn('--arch', arguments)

    def test_new_persona_is_mutually_exclusive_before_any_build(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / 'must-not-be-created'
            for other in ('--photos-recent-only', '--web-only', '--worker-thread-only'):
                result = subprocess.run([sys.executable, str(Path(__file__).with_name('build_hap_probe.py')),
                                         '--photos-asset-only', other, '--udid', 'offline-cli-test',
                                         '--sdk', temporary, '--output', str(output)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 2)
                self.assertIn('personas are mutually exclusive', result.stderr)
                self.assertFalse(output.exists())

    def test_all_UI_actions_bind_layout_selection_and_screenshot(self):
        from guest_ui import select_node
        from PIL import Image
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cases = [
                ('open-picker', node('photos-open-picker'), 'photos-open-picker'),
                ('cancel', node('close-button', children=[node('Third_Select_PickerClose', 'Image')]), None),
                ('create-test-asset', node('photos-save-asset'), 'photos-save-asset'),
                ('save', [node('', 'Text', text='允许“Capability audit”保存 1 张图片？'),
                          node('advanced_dialog_button_1', text='允许')], None),
                ('read-test-asset', node('photos-read-asset'), 'photos-read-asset'),
                ('select', [node('currentSelectCount', 'Text', text='已选 1/1'), node('Complete', text='完成')], None),
            ]
            actions = []
            for kind, layout, identifier in cases:
                path = root / (kind + '.json')
                path.write_text(json.dumps(layout))
                selected = (select_node(layout, BUNDLE, identifier=identifier, clickable=True)
                            if identifier else dialog_control(layout, BUNDLE, kind))
                action = {'kind': kind, 'layout': str(path), 'layout_sha256': digest(path), 'selected_node': selected}
                if identifier is None:
                    image = root / (kind + '.png')
                    Image.new('RGB', (128, 128)).save(image)
                    action.update(screenshot=str(image), screenshot_sha256=digest(image))
                actions.append(action)
            verify_actions(actions, BUNDLE)
            with self.assertRaises(ValueError):
                verify_actions(actions[:-1], BUNDLE)
            changed = copy.deepcopy(actions)
            changed[0]['selected_node']['rect'][0] += 1
            with self.assertRaises(ValueError):
                verify_actions(changed, BUNDLE)
            Path(actions[-1]['screenshot']).write_bytes(b'not a screenshot')
            with self.assertRaises(ValueError):
                verify_actions(actions, BUNDLE)

    def test_objects_cannot_be_replaced_by_scalar_results(self):
        for name in ('asset.recent', 'asset.readback', 'asset.selected', 'picker.invalid-count',
                     'picker.user-cancel-result', 'recent-explicit-options.1'):
            for value in ('null', '[]', 'true', '"pretend"'):
                rows = fixture()
                next(row for row in rows if row['name'] == name)['value'] = value
                with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                    verify(serialized(rows), RUN, IDENTITY)


if __name__ == '__main__':
    unittest.main()
