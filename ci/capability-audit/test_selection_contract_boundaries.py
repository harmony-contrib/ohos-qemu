"""Captured owned-guest data tests; these fixtures never satisfy a package gate."""
import copy
import json
from pathlib import Path
import unittest
from guest_ui import NodeNotReady
from selection_contract_common import identity
from selection_permission_runtime import consent_node
from verify_selection_results import rows, verify

FIXTURES = Path(__file__).with_name('fixtures')


class SelectionBoundaries(unittest.TestCase):
    def dialog(self):
        return json.loads((FIXTURES/'selection_permission_dialog_diagnostic.json').read_text())
    def allow(self, value):
        pending = [value]
        while pending:
            node = pending.pop()
            if node['attributes'].get('text') == '仅本次允许': return node
            pending.extend(node.get('children', []))
        self.fail('captured consent button missing')
    def test_actual_consent_selects_the_real_one_time_button(self):
        node = consent_node(self.dialog(),'VPN policy regression')
        self.assertEqual(node['attributes']['text'], '仅本次允许')
        self.assertEqual(node['rect'], [648,446,165,38])
    def test_disabled_or_forged_consent_cannot_use_the_captured_geometry(self):
        for key, value in (('clickable','false'),('enabled','false'),('visible','false'),('type','Text')):
            dialog = self.dialog(); self.allow(dialog)['attributes'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): consent_node(dialog,'VPN policy regression')
        dialog = self.dialog(); self.allow(dialog)['attributes']['bundleName'] = 'other.bundle'
        with self.assertRaises(NodeNotReady): consent_node(dialog,'VPN policy regression')
        with self.assertRaises(NodeNotReady): consent_node(self.dialog(),'another application')
    def test_duplicate_permission_windows_are_rejected(self):
        dialog = self.dialog()
        with self.assertRaises(ValueError): consent_node([dialog,copy.deepcopy(dialog)],'VPN policy regression')
    def test_actual_reader_identity_cannot_be_borrowed_by_other_roles(self):
        text = (FIXTURES/'selection_reader_bms_diagnostic.json').read_text()
        self.assertEqual(identity(text,'reader'),20010038)
        for role in ('normal','reader-denied','system','root'):
            with self.subTest(role=role), self.assertRaises(ValueError): identity(text,role)
    def test_elevated_or_foreign_identity_cannot_close_an_ordinary_contract(self):
        for key, value in (('isSystemApp',True),('appPrivilegeLevel','system_core'),('uid',0),('bundleName','other.bundle')):
            data = json.loads((FIXTURES/'selection_reader_bms_diagnostic.json').read_text())
            data['applicationInfo'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError): identity(json.dumps(data),'reader')
    def test_real_undeclared_status_is_invalid_and_one_cycle_cannot_close(self):
        text = (FIXTURES/'selection_normal_initial_diagnostic.log').read_text()
        values = rows(text,'dc53b86ac00e2623eac60b3c85bc50a9',20010038)
        self.assertEqual(values[1]['values'],[2])
        with self.assertRaises(ValueError): verify(text,'dc53b86ac00e2623eac60b3c85bc50a9',20010038,'normal')
        with self.assertRaises(ValueError): rows(text,'0'*32,20010038)
    def test_captured_new_package_string_201_is_not_sdk_numeric_business_error(self):
        text = (FIXTURES/'selection_pasteboard_string_201_failure.jsonl').read_text()
        observed = [json.loads(line) for line in text.splitlines()]
        rejected = [row for row in observed if row['name'].endswith('.reject')]
        self.assertEqual([row['name'] for row in rejected], [
            'pasteboard.deferred.reject', 'pasteboard.sync.reject', 'pasteboard.callback.reject'])
        self.assertEqual([row['values'] for row in rejected], [['201']]*3)
        with self.assertRaises(ValueError):
            rows(text, observed[0]['runId'], observed[0]['values'][0])


if __name__=='__main__': unittest.main()
