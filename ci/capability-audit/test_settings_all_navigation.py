"""Synthetic observation/profile rejection vectors, never guest completion proof."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from PIL import Image
from settings_all_navigation_runtime import observation, painted
from verify_gap_closure import behavior_results
from verify_settings_all_navigation_results import PARAMETERS, ROUTES, supported_routes, verify_rows


class SettingsAllNavigationResultsTests(unittest.TestCase):
    nonce = 'a' * 32
    uid, pid = 20010038, 2559

    def observations(self):
        methods = [{'name': 'test.ime', 'id': 'ServiceExtAbility', 'label': 'Synthetic IME'}]
        values = [('identity', json.dumps([self.uid, self.uid, self.pid])),
                  ('installed-input-methods', json.dumps(methods))]
        values += [(name, json.dumps({'code': 16900010})) for name in
                   ('empty-identity.0', 'empty-identity.1', 'invalid-app.0', 'invalid-app.1')]
        values.append(('ready', 'synthetic fixture, not native origin'))
        for _ in (1, 2):
            for route in ROUTES:
                values.append(('network.result' if route == 'network' else route+'.request-returned',
                    'true' if route == 'network' else json.dumps(methods[0]) if route == 'detail' else
                    'void-return-only-not-render-proof'))
        return [dict(runId=self.nonce, sequence=i+1, name=name, value=value, pass_=True)
                for i, (name, value) in enumerate(values)]

    def raw(self, rows):
        return ''.join(json.dumps({('pass' if key == 'pass_' else key): value
                                  for key, value in row.items()})+'\n' for row in rows)

    def test_complete_sequence_and_reordered_missing_foreign_or_false_rejected(self):
        rows = self.observations()
        self.assertEqual(verify_rows(self.raw(rows), self.nonce, self.uid, self.pid)['observations'], 31)
        for change in ('missing', 'reorder', 'nonce', 'pass', 'pid', 'code-type', 'network', 'detail'):
            changed = copy.deepcopy(rows)
            if change == 'missing': changed.pop()
            elif change == 'reorder': changed[7:9] = reversed(changed[7:9])
            elif change == 'nonce': changed[-1]['runId'] = 'b' * 32
            elif change == 'pass': changed[-1]['pass_'] = 1
            elif change == 'pid': changed[0]['value'] = json.dumps([self.uid, self.uid, True])
            elif change == 'code-type': changed[2]['value'] = json.dumps({'code': '16900010'})
            elif change == 'network': changed[9]['value'] = '1'
            else: changed[8]['value'] = json.dumps({'name': 'foreign', 'id': 'foreign'})
            with self.subTest(change=change), self.assertRaises(ValueError):
                verify_rows(self.raw(changed), self.nonce, self.uid, self.pid)

    def test_profile_boundaries_are_exact_and_parameter_failures_not_support(self):
        missing = {name: ('phone' if i == 0 else 'Get parameter "'+name+'" fail! errNum is:106!')
                   for i, name in enumerate(PARAMETERS)}
        result = supported_routes('phone', missing)
        self.assertFalse(result['nfc']); self.assertFalse(result['double-click'])
        self.assertTrue(result['mobile']); self.assertTrue(result['sound'])
        enabled = dict(missing); enabled[PARAMETERS[1]] = 'true'; enabled[PARAMETERS[2]] = 'false'
        self.assertTrue(supported_routes('phone', enabled)['nfc'])
        enabled[PARAMETERS[0]] = '2in1'
        pc = supported_routes('2in1', enabled)
        self.assertFalse(pc['nfc']); self.assertFalse(pc['mobile']); self.assertFalse(pc['sound'])
        self.assertTrue(pc['display']); self.assertTrue(pc['app-detail'])
        for name, value in ((PARAMETERS[0], 'tablet'), (PARAMETERS[1], True),
                            (PARAMETERS[1], 'errNum is:13'), (PARAMETERS[2], 'unknown')):
            changed = dict(missing); changed[name] = value
            with self.subTest(name=name, value=value), self.assertRaises(ValueError):
                supported_routes('phone', changed)


class SettingsAllNavigationCaptureTests(unittest.TestCase):
    fixtures = Path(__file__).with_name('fixtures') / 'settings_all_navigation_diagnostic_02'

    def setUp(self):
        self.captured = json.loads((self.fixtures / 'samples.json').read_text())

    def observe(self, route, *, nonce=None, uid=None, pid=None, picture=None):
        data = self.captured
        sample = data['samples'][route]
        return observation(json.loads((self.fixtures / sample['layout']['path']).read_text()),
            picture or self.fixtures / sample['screenshot']['path'],
            (self.fixtures / sample['AMS']['path']).read_text(), route,
            data['supported_routes'][route], nonce or data['run_id'], data['methods'],
            data['app_label'], data['settings_uid'], uid or data['caller_uid'], pid or data['caller_pid'])

    def test_actual_extension_main_page_and_no_navigation_samples(self):
        for route, sample in self.captured['samples'].items():
            with self.subTest(route=route):
                self.assertEqual(self.observe(route), sample['observation'])

    def test_foreign_uid_pid_and_no_navigation_challenge_rejected(self):
        for route in self.captured['samples']:
            for change in (dict(uid=self.captured['caller_uid']+1), dict(pid=self.captured['caller_pid']+1)):
                with self.subTest(route=route, change=change), self.assertRaises(ValueError):
                    self.observe(route, **change)
        for route in ('nfc', 'double-click'):
            with self.subTest(route=route), self.assertRaises(ValueError):
                self.observe(route, nonce='0'*32)

    def test_blank_pixels_and_outside_text_cannot_borrow_layout(self):
        with tempfile.TemporaryDirectory() as temporary:
            picture = Path(temporary) / 'blank.png'
            Image.new('RGB', (1280, 800), 'white').save(picture)
            for route in self.captured['samples']:
                with self.subTest(route=route), self.assertRaisesRegex(ValueError, 'not painted'):
                    self.observe(route, picture=picture)
            node = copy.deepcopy(self.captured['samples']['display']['observation']['node'])
            node['rect'] = [1279, 799, 100, 100]
            with self.assertRaisesRegex(ValueError, 'outside'):
                painted(picture, node)

    def test_raw_or_diagnostic_settings_cannot_close_acceptance_ledger(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'settings-all-navigation').mkdir(); (root/'boot').mkdir()
            (root/'settings-all-navigation/evidence.json').write_text(json.dumps(
                dict(status='pass', boot_id='fixture', archive_sha256='0'*64)))
            boot = dict(status='pass', purpose='diagnostic', archive_sha256='0'*64,
                scope='fresh_packaged_QEMU_boot_NOT_full_behavior_gate',
                test_environment=dict(boot_id='fixture', external_keepalive=False, device_type='phone'))
            for change in ({}, dict(purpose='acceptance', diagnostic_assistance=True)):
                (root/'boot/boot.json').write_text(json.dumps(dict(boot, **change)))
                with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'unchanged fresh acceptance'):
                    behavior_results(root, 'fixture', '0'*64, 'phone')


if __name__ == '__main__':
    unittest.main()
