"""Synthetic UI parser fixtures; these are not device presentation evidence."""
import unittest
import subprocess
import tempfile
import json
import re

from guest_ui import GuestUi, GuestUiCommandError, LayoutNotReady, bounds, select_node


def node(identifier, *, bundle='', children=None, visible='true', **extra):
    return {'attributes': {'id': identifier, 'bundleName': bundle, 'visible': visible,
        'enabled': 'true', 'clickable': 'true', 'bounds': '[20,30][340,210]', **extra},
        'children': children or []}


class GuestUiTests(unittest.TestCase):
    def test_only_exact_window_enumeration_error_is_classified_as_not_ready(self):
        with tempfile.TemporaryDirectory() as work:
            for code, text, expected in (
                (1, 'DumpLayout failed:Get window nodes failed', LayoutNotReady),
                (2, 'DumpLayout failed:Get window nodes failed', GuestUiCommandError),
                (1, 'DumpLayout failed:permission denied', GuestUiCommandError),
                (1, '[Fail] connection lost', GuestUiCommandError)):
                def command(argv, label):
                    marker = re.search(r'(__UITEST_EXIT_[0-9a-f]+__=)', argv[-1])[1]
                    return text + '\n\n' + marker + str(code) + '\n'
                ui = GuestUi(command, 'fixture', 'fixture', work)
                with self.subTest(code=code, text=text), self.assertRaises(expected):
                    ui.layout()
            ui = GuestUi(lambda argv, label: 'DumpLayout failed:Get window nodes failed\n',
                         'fixture', 'fixture', work)
            with self.assertRaises(GuestUiCommandError): ui.layout()

    def test_real_window_bundle_is_inherited_and_exact_id_is_required(self):
        layout = node('', children=[node('', bundle='org.example', children=[node('surface')]),
                                    node('surface', bundle='org.other')])
        self.assertEqual(select_node(layout, 'org.example', identifier='surface')['rect'], [20, 30, 320, 180])
        for value in ('sur', 'not-present'):
            with self.assertRaises(ValueError):
                select_node(layout, 'org.example', identifier=value)

    def test_list_windows_format_and_text_selector(self):
        layout = [node('allow', bundle='permission.dialog', text='Allow')]
        self.assertEqual(select_node(layout, 'permission.dialog', text='Allow', clickable=True)['attributes']['id'], 'allow')

    def test_selected_node_survives_evidence_JSON_roundtrip_exactly(self):
        selected = select_node(node('surface', bundle='org.example'), 'org.example', identifier='surface')
        self.assertEqual(selected, json.loads(json.dumps(selected)))

    def test_duplicate_hidden_disabled_and_other_bundle_rejected(self):
        for layout in ([node('control', bundle='b'), node('control', bundle='b')],
                       node('control', bundle='b', visible='false'),
                       node('control', bundle='b', enabled='false'),
                       node('control', bundle='b', clickable='false'),
                       node('control', bundle='other')):
            with self.assertRaises(ValueError):
                select_node(layout, 'b', identifier='control', clickable=True)

    def test_no_guessed_coordinate_or_invalid_geometry(self):
        for value in ('[0,0][0,1]', '[-1,0][10,10]', '0,0,100,100', '[0,0][999999,10]', None):
            with self.assertRaises(ValueError):
                bounds(value)
        for arguments in ({}, {'identifier': 'x', 'text': 'x'}):
            with self.assertRaises(ValueError):
                select_node(node('x', bundle='b'), 'b', **arguments)

    def test_malformed_children_or_missing_attributes_fail_closed(self):
        for layout in ({'children': []}, {'attributes': {}, 'children': {}}, {'attributes': {}, 'children': [None]}):
            with self.assertRaises(ValueError):
                select_node(layout, 'b', identifier='x')

    def test_shell_exit_nonce_is_on_new_line_even_for_unterminated_json(self):
        def command(argv, label):
            return subprocess.run(['sh', '-c', argv[-1]], check=True, capture_output=True, text=True).stdout
        with tempfile.TemporaryDirectory() as work:
            ui = GuestUi(command, 'fixture-hdc', 'fixture-target', work)
            self.assertEqual(ui.shell("printf '%s' '{\"test\":true}'", 'fixture'), '{"test":true}')
            with self.assertRaises(ValueError):
                ui.shell("printf '%s' no-newline; false", 'fixture-failure')


if __name__ == '__main__':
    unittest.main()
