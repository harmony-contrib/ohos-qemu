"""Synthetic evidence contract tests; these fixtures are not device acceptance."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image
from guest_ui import select_node
from photos_asset_contract import SCOPE, TEMPLATE, inputs
from photos_asset_ui import dialog_control
from run_root_probe import digest
from test_photos_asset_results import BUNDLE, IDENTITY, RUN, fixture, node, serialized
import verify_photos_asset_results as verifier


class PhotosAssetGateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='photos-gate-fixture-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        project = self.root / 'project'
        page = project / 'entry/src/main/ets/pages/Index.ets'
        page.parent.mkdir(parents=True)
        page.write_text(TEMPLATE.read_text().replace('__PHOTO_ASSET_RUN__', RUN))
        module = project / 'entry/src/main/module.json5'
        module.write_text(json.dumps({'module': {'requestPermissions': []}}))
        sdk = self.root / 'sdk'
        api = sdk / 'ets/api'
        api.mkdir(parents=True)
        for name in ('@ohos.file.photoAccessHelper.d.ts', '@ohos.file.fs.d.ts',
                     '@ohos.file.fileuri.d.ts', '@ohos.multimedia.image.d.ts'):
            (api / name).write_text('synthetic SDK fixture; never actual compiler evidence')
        contract = project / 'photos-asset-probe-inputs.json'
        contract.write_text(json.dumps(inputs(project, sdk, 'arm64', RUN)))
        self.raw = self.root / 'results.log'
        self.raw.write_text(serialized(fixture()))
        identity = self.root / 'application-identity.json'
        identity.write_text(IDENTITY)
        hap = self.root / 'ordinary-probe-signed.hap'
        hap.write_bytes(b'outer contract fixture only, not an actual signed HAP')
        actions = []
        cases = [
            ('open-picker', node('photos-open-picker'), 'photos-open-picker'),
            ('cancel', node('close-button', children=[node('Third_Select_PickerClose', 'Image')]), None),
            ('create-test-asset', node('photos-save-asset'), 'photos-save-asset'),
            ('save', [node('', 'Text', text='允许“Capability audit”保存 1 张图片？'),
                      node('advanced_dialog_button_1', text='允许')], None),
            ('read-test-asset', node('photos-read-asset'), 'photos-read-asset'),
            ('select', [node('currentSelectCount', 'Text', text='已选 1/1'), node('Complete', text='完成')], None),
        ]
        for kind, layout, identifier in cases:
            path = self.root / (kind + '.json')
            path.write_text(json.dumps(layout))
            selected = (select_node(layout, BUNDLE, identifier=identifier, clickable=True)
                        if identifier else dialog_control(layout, BUNDLE, kind))
            action = {'kind': kind, 'layout': str(path), 'layout_sha256': digest(path), 'selected_node': selected}
            if identifier is None:
                screen = self.root / (kind + '.png')
                Image.new('RGB', (128, 128)).save(screen)
                action.update(screenshot=str(screen), screenshot_sha256=digest(screen))
            actions.append(action)
        action_file = self.root / 'photos-asset-actions.json'
        action_file.write_text(json.dumps(actions))
        self.verified = {'status': 'pass', 'scope': SCOPE, 'failures': [], 'archive_sha256': 'a' * 64,
            'run_id': RUN, 'arch': 'arm64', 'first_artifact_behavior_gate_passed': False,
            'verifier_sha256': digest(Path(verifier.__file__)),
            'ui_verifier_sha256': digest(Path(verifier.__file__).with_name('photos_asset_ui.py')),
            'results_sha256': digest(self.raw), 'application_identity_sha256': digest(identity),
            'compiled_inputs_sha256': digest(contract), 'actions_sha256': digest(action_file),
            'result': verifier.verify(self.raw.read_text(), RUN, IDENTITY)}
        self.result_path = self.root / 'verified-result.json'
        self.result_path.write_text(json.dumps(self.verified))
        self.document = {'status': 'pass', 'persona': 'photos-asset', 'archive_sha256': 'a' * 64,
            'boot_id': 'fixture-boot', 'arch': 'arm64', 'run_id': RUN, 'failures': [],
            'first_artifact_behavior_gate_passed': False, 'result': str(self.result_path),
            'compiled_contract_inputs': str(contract), 'photos_asset_actions': str(action_file),
            'result_sha256': digest(self.result_path), 'raw_results_sha256': digest(self.raw),
            'ordinary_identity_sha256': digest(identity), 'compiled_contract_inputs_sha256': digest(contract),
            'photos_asset_actions_sha256': digest(action_file), 'hap_sha256': digest(hap)}

    def check(self, document=None):
        return verifier.verify_evidence(document or self.document, 'a' * 64, 'fixture-boot', 'arm64')

    def test_recomputes_complete_asset_UI_and_pixel_contract(self):
        self.assertEqual(self.check()['observations'], 19)
        self.assertEqual(self.check()['closed'], [])

    def test_old_boot_wrong_archive_or_arch_cannot_reuse_proof(self):
        for key, value in (('boot_id', 'old'), ('archive_sha256', 'b' * 64), ('arch', 'x86_64'),
                           ('first_artifact_behavior_gate_passed', True), ('status', 'fail')):
            document = copy.deepcopy(self.document)
            document[key] = value
            with self.assertRaises(ValueError): self.check(document)

    def test_changed_observations_rejected_even_when_outer_hashes_are_recomputed(self):
        rows = fixture()
        rows[-1]['pass'] = False
        self.raw.write_text(serialized(rows))
        self.verified['results_sha256'] = digest(self.raw)
        self.result_path.write_text(json.dumps(self.verified))
        self.document.update(raw_results_sha256=digest(self.raw), result_sha256=digest(self.result_path))
        with self.assertRaises(ValueError): self.check()

    def test_updated_verifier_or_UI_cannot_accept_an_old_success_flag(self):
        for key in ('verifier_sha256', 'ui_verifier_sha256'):
            value = copy.deepcopy(self.verified)
            value[key] = '0' * 64
            self.result_path.write_text(json.dumps(value))
            self.document['result_sha256'] = digest(self.result_path)
            with self.assertRaises(ValueError): self.check()

    def test_screenshot_change_is_checked_again_at_delivery(self):
        (self.root / 'select.png').write_bytes(b'replaced')
        with self.assertRaises(ValueError): self.check()

    def test_both_profile_suites_and_independent_gate_require_the_asset_probe(self):
        root = Path(__file__).resolve().parents[2]
        suite = (root / 'ci/capability-audit/run_packaged_qemu_suite.py').read_text()
        self.assertIn("'photos-recent', 'photos-asset')", suite)
        self.assertIn("check('photos-asset', path, [record])", suite)
        from verify_first_artifact_gate import REQUIRED_CHECKS
        self.assertIn('photos-asset', REQUIRED_CHECKS)


if __name__ == '__main__':
    unittest.main()
