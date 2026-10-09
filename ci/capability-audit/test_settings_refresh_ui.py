"""Synthetic selection boundaries, never real screen or guest evidence."""
import copy
import json
import unittest

from settings_refresh_ui import BUNDLE, controls, verify_caller


def node(kind, children=None, **attrs):
    return {'attributes': dict(type=kind, visible='true', enabled='true', clickable='true',
                              bounds='[0,40][120,80]', **attrs), 'children': children or []}


class RefreshUiTests(unittest.TestCase):
    def setUp(self):
        self.modes = [{'id': 4, 'width': 1280, 'height': 800, 'refreshRate': 60},
                      {'id': 17, 'width': 1280, 'height': 800, 'refreshRate': 75}]
        self.readback = {'main_screen': {'activeModeIndex': 17}, 'refresh_choices': self.modes}
        self.tree = node('root', [node('Row', [
            node('Text', id='qemu-refresh-rate-' + str(mode['id']), text=str(mode['refreshRate']) + ' Hz'),
            node('Radio', checked=str(mode['id'] == 17).lower())]) for mode in self.modes], bundleName=BUNDLE)

    def test_exact_modes_not_array_indices(self):
        result = controls(self.tree, self.readback)
        self.assertEqual(set(result), {4, 17})
        self.assertEqual(result[17]['radio']['attributes']['checked'], 'true')

    def test_missing_extra_duplicate_or_other_bundle_rejected(self):
        for change in (lambda t: t['children'].pop(), lambda t: t['children'].append(copy.deepcopy(t['children'][0])),
                       lambda t: t['attributes'].update(bundleName='unrelated.application')):
            tree = copy.deepcopy(self.tree)
            change(tree)
            with self.assertRaises(ValueError): controls(tree, self.readback)

    def test_label_rate_and_real_radio_selection_must_match(self):
        for target, field, value in ((0, 'text', '120 Hz'), (0, 'id', 'qemu-refresh-rate-04'),
                                     (1, 'checked', 'true'), (1, 'enabled', 'false'),
                                     (1, 'bundleName', 'other.application')):
            tree = copy.deepcopy(self.tree)
            tree['children'][0]['children'][target]['attributes'][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError): controls(tree, self.readback)

    def test_real_service_error_and_ambiguous_radio_rejected(self):
        tree = copy.deepcopy(self.tree)
        tree['children'].append(node('Text', id='qemu-refresh-rate-error', text='failed'))
        with self.assertRaises(ValueError): controls(tree, self.readback)
        tree = copy.deepcopy(self.tree)
        tree['children'][0]['children'].append(node('Radio', checked='false'))
        with self.assertRaises(ValueError): controls(tree, self.readback)

    def test_caller_requires_actual_202_after_fresh_navigation_and_refresh(self):
        from test_settings_navigation_results import NONCE, SettingsResultsTests
        fixture = SettingsResultsTests()
        fixture.setUp()
        rows = fixture.rows + [
            dict(runId=NONCE, sequence=9, name='refresh.request-returned', value='void', **{'pass': True}),
            dict(runId=NONCE, sequence=10, name='screen.ordinary-denial', value='{"code":202}', **{'pass': True})]
        self.assertEqual(len(verify_caller('\n'.join(map(json.dumps, rows)), NONCE)), 2)
        for field, value in (('runId', 'a' * 32), ('pass', False), ('sequence', 9),
                             ('value', '{"code":201}'), ('value', '{"code":"202"}')):
            changed = copy.deepcopy(rows)
            changed[-1][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                verify_caller('\n'.join(map(json.dumps, changed)), NONCE)
        with self.assertRaises(ValueError): verify_caller('\n'.join(map(json.dumps, rows[:-1])), NONCE)


if __name__ == '__main__':
    unittest.main()
