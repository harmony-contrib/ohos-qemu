"""Synthetic policy/transaction host checks. No actual source, SDK or signing."""
from pathlib import Path
import copy
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
P = ROOT / 'patches'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


helper = module('number375_profile', P / 'lib/number_identity_provider.py')


def original():
    # Deliberately synthetic, never presented as a decoded official profile.
    return {'bundle-info': {'bundle-name': helper.BUNDLE, 'apl': 'system_core',
            'app-feature': 'hos_system_app', 'distribution-certificate': 'synthetic-old-leaf',
            'developer-id': 'synthetic-developer'}, 'type': 'release',
            'app-distribution-type': 'os_integration',
            'validity': {'not-before': 1, 'not-after': helper.ORIGINAL_NOT_AFTER},
            'acls': {'allowed-acls': ['synthetic-existing-ACL']},
            'permissions': {'restricted-permissions': ['synthetic-existing-permission']},
            'version-code': 1}


class Policy(unittest.TestCase):
    def test_only_distribution_certificate_and_not_after_change(self):
        value = original()
        before = copy.deepcopy(value)
        with patch.object(helper, 'fingerprint', return_value=helper.OS_LEAF):
            desired = helper.desired_profile(value, b'synthetic-new-leaf\n')
        self.assertEqual(value, before)
        self.assertEqual(desired['bundle-info']['distribution-certificate'], 'synthetic-new-leaf\n')
        self.assertEqual(desired['validity']['not-after'], 2208988800)
        desired['bundle-info']['distribution-certificate'] = before['bundle-info']['distribution-certificate']
        desired['validity']['not-after'] = before['validity']['not-after']
        self.assertEqual(desired, before)

    def test_identity_apl_feature_distribution_and_expiry_tamper_reject(self):
        variants = [('bundle-info', 'bundle-name', 'com.numberidentity'),
                    ('bundle-info', 'apl', 'normal'), ('bundle-info', 'app-feature', 'normal'),
                    ('validity', 'not-after', True), ('validity', 'not-after', 1689473258.0)]
        with patch.object(helper, 'fingerprint', return_value=helper.OS_LEAF):
            for section, key, value in variants:
                item = original();item[section][key] = value
                with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                    helper.desired_profile(item, b'leaf')
            for key, value in [('type', 'debug'), ('app-distribution-type', 'enterprise')]:
                item = original();item[key] = value
                with self.assertRaises(ValueError):helper.desired_profile(item, b'leaf')

    def test_foreign_os_leaf_reject(self):
        with patch.object(helper, 'fingerprint', return_value='FOREIGN'), self.assertRaises(ValueError):
            helper.desired_profile(original(), b'foreign-leaf')

    def test_typed_complete_json_and_duplicate_nonfinite_bounds(self):
        self.assertFalse(helper.same_json({'x': True}, {'x': 1}))
        self.assertFalse(helper.same_json({'x': 1}, {'x': 1.0}))
        for value in [b'{"x":1,"x":2}', b'{"x":NaN}', b'[]', b' ' * 1048577]:
            with self.assertRaises(ValueError):helper.decode(value)



class AuthenticatedProfile(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.profile = self.root / 'candidate.p7b';self.profile.write_bytes(b'synthetic-CMS')
        self.expected = original()

    def cms_result(self, content, signers=1):
        def verify(path, signer):
            signer.write_bytes(b'\n'.join([b'-----BEGIN CERTIFICATE-----synthetic-----END CERTIFICATE-----'] * signers))
            return content
        return verify

    def test_exact_content_and_authenticated_pinned_issuer_accept(self):
        with patch.object(helper, 'cms', side_effect=self.cms_result(self.expected)), \
                patch.object(helper, 'fingerprint', return_value='pinned-issuer'):
            helper.profile_matches(self.profile, self.expected, 'pinned-issuer', self.root)

    def test_same_json_with_foreign_or_multiple_signers_reject(self):
        for count, fingerprint in [(1, 'foreign-issuer'), (2, 'pinned-issuer'), (0, 'pinned-issuer')]:
            with self.subTest(count=count, issuer=fingerprint), \
                    patch.object(helper, 'cms', side_effect=self.cms_result(self.expected, count)), \
                    patch.object(helper, 'fingerprint', return_value=fingerprint), self.assertRaises(ValueError):
                helper.profile_matches(self.profile, self.expected, 'pinned-issuer', self.root)

    def test_same_issuer_cannot_expand_acl_or_permissions_or_numeric_types(self):
        for change in ('ACL', 'permission', 'apl', 'type'):
            actual = copy.deepcopy(self.expected)
            if change == 'ACL':actual['acls']['allowed-acls'].append('forbidden')
            if change == 'permission':actual['permissions']['restricted-permissions'].append('forbidden')
            if change == 'apl':actual['bundle-info']['apl'] = 'normal'
            if change == 'type':actual['version-code'] = True
            with self.subTest(change=change), patch.object(helper, 'cms', side_effect=self.cms_result(actual)), \
                    patch.object(helper, 'fingerprint', return_value='pinned-issuer'), self.assertRaises(ValueError):
                helper.profile_matches(self.profile, self.expected, 'pinned-issuer', self.root)

    def test_invalid_cms_not_decoded_as_trusted_json(self):
        with patch.object(helper, 'cms', side_effect=subprocess.CalledProcessError(1, ['openssl'])), \
                self.assertRaises(subprocess.CalledProcessError):
            helper.profile_matches(self.profile, self.expected, 'pinned-issuer', self.root)

    def test_cms_uses_signature_verification_and_signer_output(self):
        signer = self.root / 'signer.pem'
        with patch.object(helper.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, stdout=b'{"ok":true}')) as run:
            self.assertEqual(helper.cms(self.profile, signer), {'ok': True})
        command = run.call_args.args[0]
        self.assertEqual(command[:3], ['openssl', 'cms', '-verify'])
        self.assertIn('-signer', command)
        self.assertNotIn('-nosigs', command)

    def test_original_is_diagnostic_only_verify_refuses(self):
        self.profile.write_bytes(b'original')
        identity = {'current': b'original', 'raw': b'original', 'path': self.profile}
        self.assertEqual(helper.classify(identity, self.root), 'original_expired_not_ready')
        with self.assertRaises(ValueError):helper.classify(identity, self.root, True)

    def test_profile_race_during_cryptographic_check_reject(self):
        identity = {'current': b'synthetic-CMS', 'raw': b'original', 'path': self.profile,
                    'desired': self.expected, 'issuer': 'pinned-issuer'}
        def change(*args):self.profile.write_bytes(b'foreign')
        with patch.object(helper, 'profile_matches', side_effect=change), self.assertRaises(ValueError):
            helper.classify(identity, self.root, True)


class SourceInputs(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.profile = self.root / helper.PROJECT / helper.PROFILE
        self.profile.parent.mkdir(parents=True);self.profile.write_bytes(b'synthetic-original')
        self.scratch = self.root / 'scratch';self.scratch.mkdir()
        pem = b'-----BEGIN CERTIFICATE-----synthetic-----END CERTIFICATE-----'
        self.public = {'hap-sign-tool.jar': b'synthetic-public-jar',
                       'OpenHarmonyApplication.pem': b'\n'.join([pem]*3),
                       'OpenHarmonyProfileRelease.pem': b'\n'.join([pem]*3)}
        self.expected = {name: hashlib.sha256(data).hexdigest() for name, data in self.public.items()}

    def git(self, command, **kwargs):
        return helper.REVISION + '\n' if command[-2:] == ['rev-parse', 'HEAD'] else b'synthetic-original'

    def read(self, path):
        path = Path(path)
        if path.name == 'OpenHarmony.p12':raise AssertionError('verify must not access keystore')
        return self.public[path.name] if path.name in self.public else path.read_bytes()

    def call(self):
        with patch.object(helper, 'PUBLIC_INPUTS', self.expected), \
                patch.object(helper, 'PROFILE_SHA', hashlib.sha256(b'synthetic-original').hexdigest()), \
                patch.object(helper, 'read', side_effect=self.read), \
                patch.object(helper.subprocess, 'check_output', side_effect=self.git), \
                patch.object(helper, 'cms', return_value=original()), \
                patch.object(helper, 'fingerprint', return_value=helper.OS_LEAF):
            return helper.source_identity(self.root, self.scratch)

    def test_exact_public_inputs_original_git_blob_and_fixed_head(self):
        result = self.call()
        self.assertEqual(result['raw'], b'synthetic-original')
        self.assertEqual(result['current'], b'synthetic-original')
        self.assertEqual(result['desired']['validity']['not-after'], 2208988800)
        self.assertEqual(set(result['public']), set(helper.PUBLIC_INPUTS))

    def test_changed_public_input_refuses_without_source_write(self):
        self.public['OpenHarmonyApplication.pem'] += b'changed'
        with self.assertRaises(ValueError):self.call()
        self.assertEqual(self.profile.read_bytes(), b'synthetic-original')

    def test_foreign_project_head_refuses_before_public_reads(self):
        with patch.object(helper.subprocess, 'check_output', return_value='foreign-head\n'), \
                patch.object(helper, 'read') as read, self.assertRaises(ValueError):
            helper.source_identity(self.root, self.scratch)
        read.assert_not_called()

    def test_production_public_pin_values_equal_canonical_os_signer_contract(self):
        self.assertEqual(helper.OS_LEAF, '8E93863FC32EE238060BF69A9B37E2608FFFB21F93C862DD511CBAC9F30024B5')
        self.assertEqual(helper.PUBLIC_INPUTS, {
            'hap-sign-tool.jar': 'a434b6747e6c5d0b14e73837a46b39f4816ab25b42d1833d6f767bf867cf616d',
            'OpenHarmonyApplication.pem': 'b5c1d6254faa91eab645a32fc3ce136128c94d88a739a0e956e6a49b331387e5',
            'OpenHarmonyProfileRelease.pem': '515f0bd8173fabb8bf8f146cd61207baa0e2d6ab8693ae7623df7ee6f16af70e'})


class Transaction(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.profile = self.root / 'profile.p7b';self.profile.write_bytes(b'original')
        self.identity = {'root': self.root, 'path': self.profile, 'current': b'original',
                         'raw': b'original', 'public': {'public-pem': b'fixed'},
                         'desired': original(), 'issuer': 'pinned-issuer', 'dist': self.root}

    def test_renewal_publish_and_replay_preserve_gate_false(self):
        def sign(identity, template, signed):
            self.assertEqual(json.loads(template.read_text()), identity['desired'])
            signed.write_bytes(b'authenticated-renewed')
        with patch.object(helper, 'source_identity', return_value=self.identity), \
                patch.object(helper, 'profile_matches') as match, patch.object(helper, 'sign_profile', side_effect=sign):
            result = helper.prepare(self.root)
        self.assertEqual(self.profile.read_bytes(), b'authenticated-renewed')
        self.assertTrue(result['changed'])
        self.assertFalse(result['first_artifact_behavior_gate_passed'])
        self.assertFalse(result['final_hap_signature_or_BMS_acceptance_proven'])
        self.identity['current'] = self.profile.read_bytes()
        with patch.object(helper, 'source_identity', return_value=self.identity), \
                patch.object(helper, 'profile_matches'), patch.object(helper, 'sign_profile') as sign:
            self.assertFalse(helper.prepare(self.root)['changed'])
            sign.assert_not_called()

    def test_unknown_current_policy_refuses_before_sign_or_write(self):
        self.profile.write_bytes(b'unknown');self.identity['current'] = b'unknown'
        with patch.object(helper, 'source_identity', return_value=self.identity), \
                patch.object(helper, 'profile_matches', side_effect=ValueError('unknown policy')), \
                patch.object(helper, 'sign_profile') as sign, self.assertRaises(ValueError):
            helper.prepare(self.root)
        sign.assert_not_called();self.assertEqual(self.profile.read_bytes(), b'unknown')

    def test_signed_candidate_must_authenticate_before_publication(self):
        def sign(identity, template, signed):signed.write_bytes(b'bad-signature')
        with patch.object(helper, 'source_identity', return_value=self.identity), \
                patch.object(helper, 'sign_profile', side_effect=sign), \
                patch.object(helper, 'profile_matches', side_effect=ValueError('invalid CMS')), \
                self.assertRaises(ValueError):helper.prepare(self.root)
        self.assertEqual(self.profile.read_bytes(), b'original')

    def test_raced_current_or_public_inputs_refuse(self):
        for key, value in [('current', b'foreign'), ('public', {'public-pem': b'changed'}), ('issuer', 'foreign')]:
            changed = dict(self.identity);changed[key] = value
            with self.subTest(key=key), patch.object(helper, 'source_identity', return_value=changed), self.assertRaises(ValueError):
                helper.publish(self.identity, b'pending', self.root)
            self.assertEqual(self.profile.read_bytes(), b'original')

    def test_post_publish_failure_rolls_back_only_own_bytes(self):
        with patch.object(helper, 'source_identity', return_value=self.identity), \
                patch.object(helper, 'profile_matches', side_effect=ValueError('postcheck')), self.assertRaises(ValueError):
            helper.publish(self.identity, b'pending', self.root)
        self.assertEqual(self.profile.read_bytes(), b'original')
        def foreign(*args):
            self.profile.write_bytes(b'foreign-writer')
            raise ValueError('foreign changed source')
        with patch.object(helper, 'source_identity', return_value=self.identity), \
                patch.object(helper, 'profile_matches', side_effect=foreign), self.assertRaises(ValueError):
            helper.publish(self.identity, b'pending', self.root)
        self.assertEqual(self.profile.read_bytes(), b'foreign-writer')

    def test_verify_never_uses_signer_or_keystore(self):
        self.identity['current'] = b'authenticated-renewed';self.profile.write_bytes(b'authenticated-renewed')
        with patch.object(helper, 'source_identity', return_value=self.identity), patch.object(helper, 'profile_matches'), \
                patch.object(helper, 'sign_profile') as signer:
            self.assertEqual(helper.verify(self.root)['state'], 'authenticated_renewed')
        signer.assert_not_called()

    def test_alias_and_hardlink_profile_reject(self):
        alias = self.root / 'alias';alias.symlink_to(self.profile)
        with self.assertRaises(ValueError):helper.read(alias)
        link = self.root / 'hardlink';os.link(self.profile, link)
        with self.assertRaises(ValueError):helper.read(link)




if __name__ == '__main__':
    unittest.main()
