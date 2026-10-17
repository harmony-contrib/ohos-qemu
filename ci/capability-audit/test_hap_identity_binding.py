import json
import unittest

from hap_identity_binding import IDENTITY_SCHEMA, bms_application_identity, verify_hap_token_identity


class HapIdentityBindingTest(unittest.TestCase):
    def record(self):
        return dict(identity_schema=IDENTITY_SCHEMA, expected_uid=20010040,
                    at_reported_uid=0, at_query_rc=0, token_id=537042608,
                    at_token_id=537042608, at_user_id=100, at_inst_index=0,
                    bundle='org.example.audit', at_bundle='org.example.audit')

    def verify(self, value, **changes):
        expected = dict(bundle='org.example.audit', uid=20010040, token_id=537042608)
        expected.update(changes)
        verify_hap_token_identity(value, **expected)

    def test_native_uid_diagnostic_does_not_claim_application_uid(self):
        self.verify(self.record())
        value = self.record()
        value['at_reported_uid'] = 20010099
        self.verify(value)

    def test_each_actual_identity_component_is_bound(self):
        for key, wrong in dict(expected_uid=20010041, at_query_rc=-1,
                               token_id=537042609, at_token_id=537042609,
                               at_user_id=101, at_inst_index=1,
                               at_bundle='org.example.other',
                               bundle='org.example.other').items():
            with self.subTest(key=key):
                value = self.record()
                value[key] = wrong
                with self.assertRaises(ValueError):
                    self.verify(value)

    def test_original_bms_uid_and_token_are_required(self):
        for changes in (dict(uid=20010041), dict(token_id=537042609),
                        dict(bundle='org.example.other'), dict(uid=10040),
                        dict(uid=True), dict(token_id=0), dict(token_id=2**32)):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.verify(self.record(), **changes)

    def test_legacy_or_incomplete_identity_is_rejected(self):
        for change in ('uid', 'missing', 'version', 'bool', 'diagnostic_range'):
            value = self.record()
            if change == 'uid': value['uid'] = 20010040
            if change == 'missing': del value['at_bundle']
            if change == 'version': value['identity_schema'] = 'legacy'
            if change == 'bool': value['at_query_rc'] = False
            if change == 'diagnostic_range': value['at_reported_uid'] = 2**31
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.verify(value)

    def test_bms_application_and_original_account_record_must_agree(self):
        app = dict(name='org.example.audit', bundleName='org.example.audit', uid=20010040,
                   accessTokenId=537042608, appIndex=0)
        account = dict(bundleUserInfo=dict(userId=100), bundleName='org.example.audit',
                       uid=20010040, accessTokenId=537042608)
        document = dict(name='org.example.audit', appIndex=0, applicationInfo=app, userInfo=[account])
        raw = 'org.example.audit:\n\n' + json.dumps(document) + '\n'
        self.assertEqual(bms_application_identity(raw, 'org.example.audit')['token_id'], 537042608)
        for field, wrong in (('uid', 20010041), ('accessTokenId', 537042609),
                             ('bundleName', 'org.example.other')):
            bad = json.loads(json.dumps(document))
            bad['userInfo'][0][field] = wrong
            with self.subTest(field=field), self.assertRaises(ValueError):
                bms_application_identity('org.example.audit:\n' + json.dumps(bad), 'org.example.audit')
        for bad in (raw + '{}', raw.replace('org.example.audit:', 'org.example.other:', 1),
                    raw.replace('"appIndex": 0', '"appIndex": 0, "appIndex": 0', 1)):
            with self.subTest(raw=bad), self.assertRaises(ValueError):
                bms_application_identity(bad, 'org.example.audit')


if __name__ == '__main__':
    unittest.main()
