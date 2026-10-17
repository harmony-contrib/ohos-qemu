"""Synthetic host protocol/geometry cases only; no guest or crypto execution."""
import copy
import importlib.util
import json
from pathlib import Path
import re
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from PIL import Image
import batch_media_wallpaper_runtime as runtime
import batch_media_wallpaper_suite as suite
import batch_media_wallpaper_coordinator as coordinator
import batch_media_verify_wallpaper_runtime as verify

SPEC = importlib.util.spec_from_file_location('wallpaper_binding_fixture', runtime.FIXTURE / 'oracle_fixture.py')
fixture = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fixture)


class WallpaperBindingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.case = fixture.Fixture(self.temporary.name)

    def rewrite_observation(self, observation, raw):
        marker = re.findall(r'__UITEST_EXIT_[a-f0-9]{32}__=', observation['command']['argv'][4])[0]
        observation['raw'] = self.case.put(raw)
        observation['command'].update(self.case.put(raw + '\n\n' + marker + '0\n'))
        self.case.value['commands'][observation['command_index']] = copy.deepcopy(observation['command'])

    def token(self):
        record = self.case.token_observation(runtime.SEED, -1)
        return json.loads(verify.checked(record).read_text())

    def check_token(self, proof):
        return verify.verify_token_observation(self.case.js(proof), run=self.case.run, boot=self.case.boot,
            target='127.0.0.1:1234', bundle=runtime.SEED, permission='ohos.permission.SET_WALLPAPER',
            original_BMS=self.case.value['seed_identity'], commands=self.case.value['commands'])

    def test_BMS_is_UID_authority_and_real_AT_UID_diagnostic_is_preserved(self):
        proof = self.token()
        self.assertEqual(0, self.check_token(proof)['at_reported_uid'])
        value = json.loads(verify.checked(proof['raw']).read_text())
        value['at_reported_uid'] = 123
        self.rewrite_observation(proof, json.dumps(value))
        self.assertEqual(123, self.check_token(proof)['at_reported_uid'])
        self.assertEqual(self.case.seed_uid, value['expected_uid'])

    def test_tuple_or_argument_echo_cannot_replace_original_BMS(self):
        for field, wrong in (('expected_uid', 20099999), ('at_query_rc', 1), ('at_token_id', 999),
                ('token_id', 999), ('at_user_id', 99), ('at_inst_index', 1), ('at_bundle', 'foreign'),
                ('permission', 'foreign'), ('boot_id', 'old'), ('at_query_rc', False)):
            with self.subTest(field=field, wrong=wrong):
                proof = self.token()
                value = json.loads(verify.checked(proof['raw']).read_text()); value[field] = wrong
                self.rewrite_observation(proof, json.dumps(value))
                with self.assertRaises(ValueError): self.check_token(proof)
        proof = self.token(); value = json.loads(verify.checked(proof['raw']).read_text())
        value['uid'] = value['expected_uid']
        self.rewrite_observation(proof, json.dumps(value))
        with self.assertRaises(ValueError): self.check_token(proof)

    def test_BMS_before_after_and_actual_command_join_must_stay_exact(self):
        for fault in ('before-uid', 'after-token', 'index', 'argv', 'footer', 'raw', 'partial'):
            with self.subTest(fault=fault):
                proof = self.token()
                if fault in ('before-uid', 'after-token'):
                    observation = proof['before' if fault == 'before-uid' else 'after']
                    value = json.loads(verify.checked(observation['raw']).read_text())
                    value['applicationInfo']['uid' if fault == 'before-uid' else 'accessTokenId'] += 1
                    self.rewrite_observation(observation, json.dumps(value))
                elif fault == 'index': proof['command_index'] += 1
                elif fault == 'argv': proof['command']['argv'][4] = 'foreign command'
                elif fault == 'footer':
                    row = proof['command']; raw = verify.checked({k: row[k] for k in ('path', 'sha256')}).read_text()
                    row.update(self.case.put(raw[:-2] + '1\n'))
                    self.case.value['commands'][proof['command_index']] = copy.deepcopy(row)
                elif fault == 'raw': proof['raw'] = self.case.put(verify.checked(proof['raw']).read_text() + ' ')
                else: proof.pop('after')
                with self.assertRaises((ValueError, KeyError)): self.check_token(proof)

    def test_coordinator_collects_raw_indexed_BMS_query_and_rejects_changed_token(self):
        for changed in (False, True):
            with self.subTest(changed=changed):
                owner = coordinator.Coordinator.__new__(coordinator.Coordinator)
                owner.run = self.case.run; owner.boot_id = self.case.boot
                owner.output = Path(self.temporary.name) / ('collector-' + str(changed)); owner.output.mkdir()
                owner.guest = SimpleNamespace(target='127.0.0.1:1234')
                owner.uids = {'seed': self.case.seed_uid}
                proof = self.token()
                owner.tools = {'token': '/data/local/tmp/wallpaper-coordinator-' + owner.run + '/token'}
                owner.inputs = {'tools': {'token': proof['helper']}}
                owner.value = {'commands': self.case.value['commands'], 'tokens': [],
                    'seed_BMS': self.case.value['seed_identity'],
                    'BMS_observations': {'seed': self.case.bms_observations[runtime.SEED]}}
                owner.save = lambda: None
                def shell(script, label):
                    if script.startswith('bm dump -n '):
                        app = json.loads(verify.checked(owner.value['seed_BMS']).read_text())
                        if changed and label.startswith('token-after-'): app['applicationInfo']['accessTokenId'] += 1
                        raw = json.dumps(app)
                    else: raw = verify.checked(proof['raw']).read_text()
                    self.case.observation(script, raw, label)
                    return raw
                owner.shell = shell
                if changed:
                    with self.assertRaisesRegex(ValueError, 'BMS UID/accessTokenId changed'):
                        owner.token('seed', coordinator.SET)
                else:
                    value, saved = owner.token('seed', coordinator.SET)
                    self.assertEqual(0, value['at_reported_uid'])
                    self.assertEqual(-1, verify.verify_token_observation(saved, run=owner.run, boot=owner.boot_id,
                        target=owner.guest.target, bundle=runtime.SEED, permission=coordinator.SET,
                        original_BMS=owner.value['seed_BMS'], commands=owner.value['commands'])['grant'])
                self.assertEqual(1, len(owner.value['tokens']))

    def test_real_clipped_top_bar_shape_uses_complete_canvas_and_original_pixels(self):
        path = Path(self.temporary.name) / 'full.png'; Image.new('RGB', (1280, 800), 'gray').save(path)
        tree = fixture.system_tree('com.ohos.sceneboard', 'SCBDesktop_Flex_Desktop', 1280, 800, 37)
        bar_window = tree['children'][1]['attributes']
        bar_window.update(bounds='[0,0][1280,54]', origBounds='[0,0][1280,54]')
        value = verify.system_canvas(tree, path, 'com.ohos.sceneboard', 'SCBDesktop_Flex_Desktop')
        self.assertEqual([0, 0, 1280, 800], value['canvas_rect'])
        self.assertEqual([0, 37, 1280, 763], value['visible_rect'])
        self.assertEqual('20', value['top_overlay_host_window_id'])
        # The same geometry cannot turn a flat full compositor into matching
        # challenge pixels or silently crop the system bar away.
        with self.assertRaises(ValueError):
            verify.pixels(path, verify.checked(self.case.challenge['images']['desktop-1']))

    def test_window_preview_foreign_display_clipping_and_partial_capture_rejected(self):
        path = Path(self.temporary.name) / 'canvas.png'; Image.new('RGB', (360, 640)).save(path)
        good = fixture.system_tree('com.ohos.sceneboard', 'SCBDesktop_Flex_Desktop', 360, 640, 25)
        for fault in ('root', 'original', 'display', 'host', 'no-bar', 'foreign-bar', 'wrong-strip',
                      'duplicate', 'foreign-window', 'cropped'):
            with self.subTest(fault=fault):
                tree = copy.deepcopy(good); selected = tree['children'][0]['children'][0]
                if fault == 'root': tree['attributes']['bounds'] = '[0,0][360,639]'
                elif fault == 'original': selected['attributes']['origBounds'] = '[0,25][360,640]'
                elif fault == 'display': selected['attributes']['displayId'] = '1'
                elif fault == 'host': selected['attributes']['hostWindowId'] = '99'
                elif fault == 'no-bar': tree['children'].pop()
                elif fault == 'foreign-bar': tree['children'][1]['attributes']['bundleName'] = 'com.attacker'
                elif fault == 'wrong-strip': tree['children'][1]['children'][0]['attributes']['bounds'] = '[0,0][360,24]'
                elif fault == 'duplicate': tree['children'][0]['children'].append(copy.deepcopy(selected))
                elif fault == 'foreign-window':
                    foreign = fixture.node('com.attacker', kind='WindowScene')
                    foreign['attributes'].update(hostWindowId='90', displayId='0')
                    tree['children'].append(foreign)
                else:
                    cropped = Path(self.temporary.name) / 'crop.png'; Image.new('RGB', (360, 615)).save(cropped)
                with self.assertRaises((ValueError, verify.NodeNotReady)):
                    verify.system_canvas(tree, cropped if fault == 'cropped' else path,
                        'com.ohos.sceneboard', 'SCBDesktop_Flex_Desktop')

    def test_complete_host_oracle_replays_clipped_desktop_without_cropping(self):
        for stage in self.case.value['stages']:
            if stage.get('screen_kind') == 'desktop':
                stage['layout'] = self.case.js(fixture.system_tree('com.ohos.sceneboard',
                    'SCBDesktop_Flex_Desktop', 360, 640, 25))
        self.case.save()
        self.assertEqual('pass', verify.verify(self.case.path)['status'])

    def test_only_exact_initial_readonly_helper_failure_can_support_no_media_mutation(self):
        root = Path(self.temporary.name); run = self.case.run
        request = {'schema_version': 1, 'run_id': run, 'boot_id': self.case.boot, 'sequence': 1,
            'nonce': 'a' * 32, 'action': suite.ordered_actions()[0],
            'details': {'required_permission': 'ohos.permission.SET_WALLPAPER'}}
        request_path = root / (run + '-001-' + 'a' * 32 + '.request.json')
        request_path.write_text(json.dumps(request) + '\n'); request_path.chmod(0o600)
        proof = self.token(); helper = proof['helper']; expected = {'unit': 'bound read-only helper'}
        command = copy.deepcopy(proof['command'])
        raw = verify.checked({k: command[k] for k in ('path', 'sha256')}).read_text()
        command.update(self.case.put(raw[:-2] + '1\n'))
        coo = {'run_id': run, 'boot_id': self.case.boot, 'boot': self.case.value['boot'],
            'actions': [{'action': request['action'], 'request': runtime.record(request_path)}],
            'failures': ['actual readonly preflight failed'], 'commands': copy.deepcopy(self.case.value['commands']),
            'BMS_observations': {'seed': self.case.bms_observations[runtime.SEED],
                                 'settings': self.case.bms_observations[runtime.SETTINGS]},
            'helper_bindings': {'token': {'build': expected}},
            'inputs': self.case.js({'tools': {'token': helper}})}
        index = proof['command_index']; coo['commands'][index] = command
        with patch.object(suite, 'verify_helper_receipt', return_value=expected):
            value = suite.readonly_token_preflight_failure(coo, command, index, '127.0.0.1:1234')
            self.assertEqual(1, value['inner_exit_code'])
            for fault in ('cleanup', 'other-command', 'ACK', 'transport'):
                changed = copy.deepcopy(coo); row = changed['commands'][index]
                if fault == 'cleanup': row['label'] = 'remove-only-owned-wallpaper-helpers'
                elif fault == 'other-command': row['argv'][4] = 'rm /unknown'
                elif fault == 'ACK': changed['actions'][0]['ack'] = {}
                else: row['exit_code'] = 1
                with self.assertRaises(ValueError):
                    suite.readonly_token_preflight_failure(changed, row, index, '127.0.0.1:1234')
