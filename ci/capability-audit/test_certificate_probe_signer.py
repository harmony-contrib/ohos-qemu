"""Profile boundary fixtures only, not actual signing or guest authorization."""
import copy
import unittest

from sign_certificate_probe import BUNDLE, PERMISSIONS, configure_profile


def profile():
    return {'bundle-info': {}, 'debug-info': {}, 'acls': {}, 'permissions': {}}


def module(role):
    return {'app': {'bundleName': BUNDLE}, 'module': {
        'requestPermissions': [{'name': name} for name in PERMISSIONS] if role == 'system' else []}}


class CertificateProbeSignerTests(unittest.TestCase):
    def test_normal_no_privileges_and_system_exact_two_acls(self):
        for role in ('normal', 'system'):
            result = configure_profile(profile(), role, 'a' * 64, module(role))
            self.assertEqual(result['bundle-info']['bundle-name'], BUNDLE)
            self.assertEqual(result['bundle-info']['apl'], 'normal' if role == 'normal' else 'system_core')
            self.assertEqual(result['bundle-info']['app-feature'],
                             'hos_normal_app' if role == 'normal' else 'hos_system_app')
            expected = [] if role == 'normal' else sorted(PERMISSIONS)
            self.assertEqual(result['acls']['allowed-acls'], expected)
            self.assertEqual(result['permissions']['restricted-permissions'], expected)
            self.assertEqual(result['debug-info']['device-ids'], ['a' * 64])

    def test_rejects_other_bundle_role_missing_extra_duplicate_permissions_or_no_real_udid(self):
        fixtures = []
        for role in ('normal', 'system'):
            bad = module(role); bad['app']['bundleName'] = 'unrelated.bundle'; fixtures.append((role, bad))
            bad = module(role); bad['module']['requestPermissions'].append({'name': 'ohos.permission.LOCATION'})
            fixtures.append((role, bad))
        bad = module('system'); bad['module']['requestPermissions'].pop(); fixtures.append(('system', bad))
        bad = module('system'); bad['module']['requestPermissions'].append(copy.deepcopy(
            bad['module']['requestPermissions'][0])); fixtures.append(('system', bad))
        for role, bad in fixtures:
            with self.subTest(role=role, bad=bad), self.assertRaises(ValueError):
                configure_profile(profile(), role, 'a' * 64, bad)
        for role, udid in (('root', 'a' * 64), ('normal', 'COMPILE_ONLY_NOT_GUEST'), ('system', ''),
                           ('system', '*')):
            with self.subTest(role=role, udid=udid), self.assertRaises(ValueError):
                configure_profile(profile(), role, udid, module('system'))


if __name__ == '__main__':
    unittest.main()
