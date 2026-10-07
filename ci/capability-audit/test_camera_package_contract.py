"""Owned Camera contract/UI/image fixtures only, never guest acceptance."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from camera_package_capture import allow_camera, current_rows
from camera_probe_contract import inputs, permission_labels, select_permission, sha, verify_inputs
from test_verify_camera_results import RUN, IDENTITY, fixture, render
from verify_camera_results import verify, verify_captures, verify_evidence

ROOT = Path(__file__).resolve().parent


def dialog(bundle='com.ohos.permissionmanager', caller='Capability audit', allow='Allow'):
    return {'attributes': {'bundleName': bundle}, 'children': [
        {'attributes': {'text': caller + ' requests Camera', 'visible': 'true'}, 'children': []},
        {'attributes': {'text': allow, 'visible': 'true', 'enabled': 'true', 'clickable': 'true',
                        'bounds': '[100,100][200,160]'}, 'children': []}]}


LABELS = {'bundle': 'com.ohos.permissionmanager', 'scope': 'actual_trusted_Camera_ALLOW_button_resources_only',
          'files_sha256': {'fixture': 'a' * 64}, 'allow_labels': ['Allow', '允许']}


def captures_fixture(root, arkts):
    from PIL import Image, ImageDraw
    captures = []
    colors = ((192, 192, 192), (192, 192, 0), (0, 192, 192), (0, 192, 0),
              (192, 0, 192), (192, 0, 0), (0, 0, 192), (0, 0, 0))
    for cycle in (1, 2):
        layout = {'attributes': {'bundleName': 'org.harmonycontrib.capabilityaudit'}, 'children': [
            {'attributes': {'text': 'ArkTS preview live cycle ' + str(cycle), 'visible': 'true',
                            'bounds': '[0,0][200,40]'}, 'children': []},
            {'attributes': {'id': 'camera-audit-preview', 'visible': 'true',
                            'bounds': '[40,60][360,240]'}, 'children': []}]}
        path, screen = root / f'layout-{cycle}.json', root / f'screen-{cycle}.png'
        path.write_text(json.dumps(layout))
        image = Image.new('RGB', (400, 400), 'white')
        draw = ImageDraw.Draw(image)
        for i, color in enumerate(colors):
            draw.rectangle((40 + i * 40, 60, 79 + i * 40, 239), fill=color)
        image.save(screen)
        prefix = arkts[:next(i for i, row in enumerate(arkts)
                           if row.get('cycle') == cycle and row.get('name') == 'preview_started') + 1]
        from guest_ui import select_node
        captures.append({'cycle': cycle, 'run_id': RUN, 'layout': str(path), 'layout_sha256': sha(path),
            'selected_node': select_node(layout, 'org.harmonycontrib.capabilityaudit', identifier='camera-audit-preview'),
            'screenshot': str(screen), 'screenshot_sha256': sha(screen),
            'before_records': prefix, 'after_records': prefix})
    return captures


class CameraPackageContractTests(unittest.TestCase):
    def test_current_page_native_sources_SDK_headers_nonce_and_tamper_checks(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            page = root / 'project/entry/src/main/ets/pages/Index.ets'
            page.parent.mkdir(parents=True)
            page.write_text((ROOT / 'camera_probe.ets').read_text().replace('__CAMERA_RUN_ID__', RUN))
            sdk = root / 'sdk'
            headers = sdk / 'native/sysroot/usr/include/ohcamera'
            headers.mkdir(parents=True)
            for i in range(5): (headers / f'fixture-{i}.h').write_text('fixture header ' + str(i))
            declaration = sdk / 'ets/api/@ohos.multimedia.camera.d.ts'
            declaration.parent.mkdir(parents=True)
            declaration.write_text('fixture declaration')
            document = inputs(root / 'project', sdk, 'arm64', RUN)
            verify_inputs(document, root / 'project', RUN, 'arm64')
            for field, value in (('run_id', '0' * 32), ('arch', 'armv7a'), ('role', 'system'),
                                 ('request_permissions', []), ('source_sha256', {}), ('sdk_files_sha256', {})):
                broken = copy.deepcopy(document)
                broken[field] = value
                with self.assertRaises(ValueError): verify_inputs(broken, root / 'project', RUN, 'arm64')
            declaration.write_text('changed fixture declaration')
            with self.assertRaises(ValueError): verify_inputs(document, root / 'project', RUN, 'arm64')

    def test_localized_labels_come_from_actual_resources_with_real_base_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            base = root / 'applications/standard/permission_manager/permissionmanager/src/main'
            model, source = base / 'ets/common/model/permissionGroup.ets', base / 'ets/pages/dialogPlus.ets'
            model.parent.mkdir(parents=True)
            source.parent.mkdir(parents=True)
            model.write_text("new GroupInfo(PermissionGroup.CAMERA, [ButtonStatus.DENY, ButtonStatus.ALLOW]);\n"
                             "[ButtonStatus.ALLOW, $r('app.string.allow')]")
            source.write_text('Button(buttonResource.get(status)); this.processClick(status);')
            strategy = base / 'ets/common/permissionGroupManager/CameraStrategy.ets'
            base_strategy = base / 'ets/common/base/BasePermissionStrategy.ets'
            strategy.parent.mkdir(parents=True)
            base_strategy.parent.mkdir(parents=True)
            strategy.write_text("return $r('app.string.group_label_camera', appName);")
            base_strategy.write_text('getButtonList(): ButtonStatus[] { return [ButtonStatus.DENY, ButtonStatus.ALLOW]; }')
            for locale, strings in (('base', [{'name': 'allow', 'value': 'Allow'}]),
                                    ('zh_CN', [{'name': 'allow', 'value': '允许'}]), ('partial', [])):
                path = base / 'resources' / locale / 'element/string.json'
                path.parent.mkdir(parents=True)
                path.write_text(json.dumps({'string': strings}))
            result = permission_labels(root)
            self.assertEqual(result['allow_labels'], ['Allow', '允许'])
            self.assertEqual(len(result['files_sha256']), 7)
            model.write_text('different permission protocol')
            with self.assertRaises(ValueError): permission_labels(root)

    def test_trusted_dialog_requires_own_app_visible_unique_localized_allow(self):
        self.assertEqual(select_permission(dialog(), LABELS)['rect'], [100, 100, 100, 60])
        self.assertEqual(select_permission(dialog(allow='允许'), LABELS)['attributes']['text'], '允许')
        for layout in (dialog(bundle='other.app'), dialog(caller='other caller'), dialog(allow='Deny')):
            with self.assertRaises(ValueError): select_permission(layout, LABELS)
        layout = dialog()
        layout['children'].append(copy.deepcopy(layout['children'][1]))
        with self.assertRaises(ValueError): select_permission(layout, LABELS)
        layout = dialog()
        layout['children'][1]['attributes']['visible'] = 'false'
        with self.assertRaises(ValueError): select_permission(layout, LABELS)

    def test_lost_UI_click_reply_is_not_retried_or_replaced_by_a_shell_grant(self):
        class UI:
            calls = 0
            def layout(self, **kwargs): return dialog(), Path('/fixture/layout.json')
            def shell(self, script, label):
                self.calls += 1
                self.assert_script = script
                raise ValueError('fixture lost click reply')
        ui = UI()
        with self.assertRaisesRegex(ValueError, 'lost click'):
            allow_camera(ui, LABELS, 1)
        self.assertEqual(ui.calls, 1)
        self.assertEqual(ui.assert_script, 'uitest uiInput click 150 130')

    def test_partial_live_rows_ignore_only_incomplete_line_and_reject_failed_or_old_run(self):
        row = {'run_id': RUN, 'kind': 'arkts_case', 'pass': True}
        self.assertEqual(current_rows(json.dumps(row) + '\n{"partial":', RUN), [row])
        for broken in ({**row, 'run_id': '0' * 32}, {**row, 'pass': False}, {**row, 'kind': 'probe_error'}):
            with self.assertRaises(ValueError): current_rows(json.dumps(broken) + '\n', RUN)

    def test_real_surface_rectangles_two_generations_and_active_log_prefixes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, arkts = fixture(root)
            captures = captures_fixture(root, arkts)
            observed = verify_captures(captures, RUN, render(arkts))
            self.assertEqual([row['cycle'] for row in observed], [1, 2])
            self.assertEqual(observed, json.loads(json.dumps(observed)))
            for field, value in (('run_id', '0' * 32), ('cycle', True), ('screenshot_sha256', '0' * 64),
                                 ('before_records', []), ('selected_node', {})):
                broken = copy.deepcopy(captures)
                broken[0][field] = value
                with self.assertRaises(ValueError): verify_captures(broken, RUN, render(arkts))
            broken = copy.deepcopy(captures)
            broken[0]['after_records'] = arkts[:next(i for i, row in enumerate(arkts)
                if row.get('name') == 'preview_frame_start') + 1]
            with self.assertRaises(ValueError): verify_captures(broken, RUN, render(arkts))

    def test_even_rehashed_blank_preview_or_wrong_archive_boot_is_rejected(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, arkts = fixture(root)
            captures = captures_fixture(root, arkts)
            screen = Path(captures[0]['screenshot'])
            Image.new('RGB', (400, 400), 'white').save(screen)
            captures[0]['screenshot_sha256'] = sha(screen)
            with self.assertRaises(ValueError): verify_captures(captures, RUN, render(arkts))
        for document in ({'status': 'pass'}, {'status': 'pass', 'persona': 'camera', 'archive_sha256': 'a',
                                            'boot_id': 'old'}):
            with self.assertRaises(ValueError): verify_evidence(document, 'new', 'new-boot')

    def test_independent_evidence_reverification_and_result_photo_permission_tamper(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            photos = root / 'photos'
            photos.mkdir()
            native, arkts = fixture(photos)
            captures = captures_fixture(root, arkts)
            page = root / 'project/entry/src/main/ets/pages/Index.ets'
            page.parent.mkdir(parents=True)
            page.write_text((ROOT / 'camera_probe.ets').read_text().replace('__CAMERA_RUN_ID__', RUN))
            sdk = root / 'sdk'
            headers = sdk / 'native/sysroot/usr/include/ohcamera'
            headers.mkdir(parents=True)
            for i in range(5): (headers / f'fixture-{i}.h').write_text('fixture header ' + str(i))
            declaration = sdk / 'ets/api/@ohos.multimedia.camera.d.ts'
            declaration.parent.mkdir(parents=True)
            declaration.write_text('fixture declaration')
            files = {'raw_results': root / 'results.log', 'ordinary_identity': root / 'application-identity.json',
                     'camera_native_results': root / 'native-results.log',
                     'compiled_contract_inputs': root / 'project/camera-probe-inputs.json',
                     'camera_captures': root / 'camera-captures.json',
                     'camera_permission_labels': root / 'permission-labels.json', 'result': root / 'verified-result.json'}
            for name, content in (('raw_results', render(arkts)), ('ordinary_identity', IDENTITY),
                                  ('camera_native_results', render(native))):
                files[name].write_text(content)
            files['compiled_contract_inputs'].write_text(json.dumps(inputs(root / 'project', sdk, 'arm64', RUN)))
            files['camera_captures'].write_text(json.dumps(captures))
            files['camera_permission_labels'].write_text(json.dumps(LABELS))
            result = {'status': 'pass', 'run_id': RUN, 'archive_sha256': 'fixture-archive',
                'observations': verify(render(native), render(arkts), RUN, 'arm64', IDENTITY, photos),
                'preview_observations': verify_captures(captures, RUN, render(arkts)), 'visible_preview_validated': True,
                'native_results_sha256': sha(files['camera_native_results']),
                'arkts_results_sha256': sha(files['raw_results']), 'identity_sha256': sha(files['ordinary_identity']),
                'captures_sha256': sha(files['camera_captures'])}
            files['result'].write_text(json.dumps(result))
            signed = root / 'ordinary-probe-signed.hap'
            with zipfile.ZipFile(signed, 'w') as hap:
                hap.writestr('module.json', json.dumps({'module': {'requestPermissions': [{'name': 'ohos.permission.CAMERA'}]}}))
            layout = root / 'permission-layout.json'
            layout.write_text(json.dumps(dialog()))
            document = {'status': 'pass', 'persona': 'camera', 'archive_sha256': 'fixture-archive',
                'boot_id': 'fixture-boot', 'run_id': RUN, 'arch': 'arm64', 'hap_sha256': sha(signed),
                'camera_permission_action': {'scope': 'actual_user_grant_dialog_NOT_shell_grant', 'decision': 'ALLOW',
                    'layout': str(layout), 'layout_sha256': sha(layout), 'selected_node': select_permission(dialog(), LABELS)}}
            for field, path in files.items():
                document[field] = str(path)
                document[field + '_sha256'] = sha(path)
            self.assertEqual(verify_evidence(document, 'fixture-archive', 'fixture-boot')['native_records'], 67)
            broken = copy.deepcopy(document)
            broken['camera_permission_action']['decision'] = 'DENY'
            with self.assertRaises(ValueError): verify_evidence(broken, 'fixture-archive', 'fixture-boot')
            broken = copy.deepcopy(document)
            broken['raw_results_sha256'] = '0' * 64
            with self.assertRaises(ValueError): verify_evidence(broken, 'fixture-archive', 'fixture-boot')
            files['result'].write_text(json.dumps(dict(result, visible_preview_validated=False)))
            document['result_sha256'] = sha(files['result'])
            with self.assertRaises(ValueError): verify_evidence(document, 'fixture-archive', 'fixture-boot')


if __name__ == '__main__': unittest.main()
