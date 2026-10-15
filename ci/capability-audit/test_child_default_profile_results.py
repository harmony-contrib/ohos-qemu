"""Captured disabled-phone observations and rejection mutations; not acceptance."""
import copy
import json
from pathlib import Path
import unittest
from verify_child_default_profile_results import verify


class ChildDefaultProfileResultsTests(unittest.TestCase):
    fixtures = Path(__file__).with_name('fixtures')/'child_default_profile_diagnostic_02'

    def setUp(self):
        self.provenance = json.loads((self.fixtures/'provenance.json').read_text())
        self.raw = (self.fixtures/'actual-child-profile-results.jsonl').read_text()

    def check(self, text, **kwargs):
        p = self.provenance
        args = dict(nonce=p['run_id'], uid=p['uid'], pid=p['pid'], parameters=p['parameters'], device='phone')
        return verify(text, original_diagnostic=True, **dict(args, **kwargs))

    def test_actual_disabled_profile_retains_distinct_C_and_ArkTS_codes(self):
        result = self.check(self.raw)
        self.assertEqual(result['observations'], 12)
        self.assertEqual(result['native_observations'], 11)
        self.assertFalse(result['supported_lifecycle_verified'])
        p = self.provenance
        with self.assertRaises(ValueError):
            verify(self.raw, p['run_id'], p['uid'], p['pid'], p['parameters'], 'phone')

    def test_wrong_profile_identity_nonce_and_native_success_rejected(self):
        for args in (dict(nonce='0'*32), dict(uid=self.provenance['uid']+1),
                     dict(pid=self.provenance['pid']+1), dict(pid=True),
                     dict(parameters=dict(self.provenance['parameters'], **{'const.max_native_child_process':'50'})),
                     dict(device='2in1')):
            with self.subTest(args=args), self.assertRaises(ValueError):self.check(self.raw, **args)
        original = [json.loads(line) for line in self.raw.splitlines()]
        for change in ('missing', 'reordered', 'boolean', 'string-code', 'C-801', 'C-started', 'callback-message', 'const-object'):
            rows = copy.deepcopy(original)
            if change == 'missing':rows.pop()
            elif change == 'reordered':rows[4:6] = reversed(rows[4:6])
            elif change == 'boolean':rows[2]['values'] = [False, False]
            elif change == 'string-code':rows[8]['values'] = ['801']
            elif change in ('C-801', 'C-started'):
                native = json.loads(rows[3]['data'])
                native[6]['code'] = 801 if change == 'C-801' else 0
                if change == 'C-started':native[6]['pid'] = 99999
                rows[3]['data'] = json.dumps(native)
            elif change == 'callback-message':rows[5]['data'] = 'string:Operation not supported.'
            else:rows[1]['values'] = ['SELF_FORK', 'APP_SPAWN_FORK']
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.check('\n'.join(json.dumps(row) for row in rows))

    def test_expanded_actual_config_failure_is_rejected_and_synthetic_repair_is_only_a_vector(self):
        p=json.loads((self.fixtures/'extended-provenance.json').read_text())
        raw=(self.fixtures/'extended-original-results.jsonl').read_text()
        args=(p['run_id'],p['uid'],p['pid'],p['parameters'],'phone')
        with self.assertRaisesRegex(ValueError,'destroy.null'):verify(raw,*args)
        rows=[json.loads(line) for line in raw.splitlines()]
        native=json.loads(rows[3]['data'])
        next(row for row in native if row['name']=='destroy.null')['code']=0
        rows[3]['data']=json.dumps(native)
        with self.assertRaisesRegex(ValueError,'isolation.mode.invalid'):
            verify('\n'.join(json.dumps(row) for row in rows),*args)
        next(row for row in native if row['name']=='isolation.mode.invalid')['code']=401
        rows[3]['data']=json.dumps(native)
        result=verify('\n'.join(json.dumps(row) for row in rows),*args)
        self.assertEqual(result['native_observations'],30)
        self.assertFalse(result['supported_lifecycle_verified'])
        # These two replacements form a synthetic parser vector only. They do
        # not alter captured evidence and are never installed as guest results.


if __name__ == '__main__':unittest.main()
