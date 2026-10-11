import copy
import json
import unittest

from verify_image_metadata_results import EXPECTED, verify


class ImageMetadataResultsTests(unittest.TestCase):
    def setUp(self):
        self.nonce = '12' * 16
        self.identity = json.dumps({'applicationInfo': {
            'appPrivilegeLevel': 'normal', 'isSystemApp': False, 'uid': 20010001}})
        self.rows = [dict(runId=self.nonce, name=name, values=values, text=text, error='')
                     for name, (values, text) in EXPECTED.items()]

    def check(self, rows=None):
        return verify('\n'.join(json.dumps(row) for row in (self.rows if rows is None else rows)),
                      self.nonce, self.identity)

    def test_narrow_contract_does_not_claim_complete_release_closure(self):
        self.assertEqual(self.check()['closed'], ['arkts_export:@ohos.multimedia.image:AvisMetadata'])
        self.assertEqual(self.check()['observations'], 22)

    def test_missing_class_wrong_factory_prototype_or_shared_defaults_fail(self):
        for index, original in enumerate(self.rows):
            if not original['name'].startswith(('avis.constructor', 'avis.instance.')):
                continue
            for position in range(len(original['values'])):
                rows = copy.deepcopy(self.rows)
                rows[index]['values'][position] = 0
                with self.subTest(name=original['name'], position=position), self.assertRaises(ValueError):
                    self.check(rows)

    def test_each_missing_or_duplicate_record_fails(self):
        for index in range(len(self.rows)):
            with self.subTest(index=index), self.assertRaises(ValueError):
                self.check(self.rows[:index] + self.rows[index + 1:])
        with self.assertRaises(ValueError):
            self.check(self.rows + self.rows[:1])

    def test_stale_reordered_wrong_value_and_hidden_error_fail(self):
        for field, value in (('runId', '34' * 16), ('name', 'other'), ('values', [0]),
                             ('text', 'invented'), ('error', 'failed')):
            rows = copy.deepcopy(self.rows)
            rows[0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.check(rows)
        with self.assertRaises(ValueError):
            self.check(list(reversed(self.rows)))

    def test_boolean_cannot_substitute_integer(self):
        rows = copy.deepcopy(self.rows)
        rows[0]['values'][0] = True
        with self.assertRaises(ValueError):
            self.check(rows)

    def test_actual_string_error_code_regression_is_not_normalized(self):
        rows = copy.deepcopy(self.rows)
        rows[2]['values'][1] = '7700204'
        with self.assertRaises(ValueError):
            self.check(rows)

    def test_privileged_app_cannot_supply_ordinary_proof(self):
        for key, value in (('uid', 0), ('appPrivilegeLevel', 'system_basic'), ('isSystemApp', True)):
            data = json.loads(self.identity)
            data['applicationInfo'][key] = value
            identity = self.identity
            self.identity = json.dumps(data)
            with self.subTest(key=key), self.assertRaises(ValueError):
                self.check()
            self.identity = identity
