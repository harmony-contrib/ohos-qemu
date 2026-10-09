"""Bounded Photos window transitions; synthetic nodes are not guest evidence."""
from pathlib import Path
import unittest
from unittest.mock import Mock

from guest_ui import GuestUiCommandError, LayoutNotReady
from photos_asset_ui import await_dialog_control
from test_photos_asset_results import BUNDLE, node


class PhotosUiTransitionTests(unittest.TestCase):
    def fixture(self):
        return [node('currentSelectCount', 'Text', text='已选 1/1'), node('Complete', text='完成')]

    def test_transient_dump_never_substitutes_for_actual_selected_control(self):
        ui = Mock()
        ui.layout.side_effect = [LayoutNotReady('actual known failure'), (self.fixture(), Path('actual-layout'))]
        path, selected = await_dialog_control(ui, BUNDLE, 'select', clock=Mock(side_effect=[0, 0, 1]), sleep=Mock())
        self.assertEqual(ui.layout.call_count, 2)
        self.assertEqual(path, Path('actual-layout'))
        self.assertEqual(selected['attributes']['id'], 'Complete')

    def test_persistent_enumeration_failure_has_a_fixed_deadline(self):
        ui = Mock()
        ui.layout.side_effect = LayoutNotReady('known failure')
        with self.assertRaisesRegex(ValueError, 'deadline'):
            await_dialog_control(ui, BUNDLE, 'select', timeout=2,
                                 clock=Mock(side_effect=[0, 0, 1, 2]), sleep=Mock())
        self.assertEqual(ui.layout.call_count, 2)

    def test_transport_nonce_JSON_and_other_commands_are_not_retried(self):
        for error in (GuestUiCommandError('dump', None, 'no nonce'),
                      GuestUiCommandError('dump', 1, 'permission denied'), ValueError('bad JSON')):
            ui = Mock()
            ui.layout.side_effect = error
            with self.assertRaises(type(error)):
                await_dialog_control(ui, BUNDLE, 'select', clock=Mock(side_effect=[0, 0]), sleep=Mock())
            self.assertEqual(ui.layout.call_count, 1)

    def test_transient_recovery_with_wrong_selection_still_fails(self):
        invalid = self.fixture()
        invalid[0]['attributes']['text'] = '已选 0/1'
        ui = Mock()
        ui.layout.side_effect = [LayoutNotReady('known failure'), (invalid, Path('wrong-layout'))]
        with self.assertRaisesRegex(ValueError, 'deadline'):
            await_dialog_control(ui, BUNDLE, 'select', timeout=2,
                                 clock=Mock(side_effect=[0, 0, 1, 2]), sleep=Mock())


if __name__ == '__main__':
    unittest.main()
