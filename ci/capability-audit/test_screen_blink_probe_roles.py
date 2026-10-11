"""Exact test signing scope only; no packaged service permission proof."""
import copy
import unittest
from build_screen_blink_probe import BUNDLE, PERMISSIONS, ROLES, module, page
from sign_screen_blink_probe import configure_profile


class ScreenBlinkRoleTests(unittest.TestCase):
    def test_only_explicit_system_role_can_write_flash_master(self):
        for role in ROLES:
            profile = {'bundle-info': {}, 'debug-info': {}, 'acls': {}, 'permissions': {}}
            compiled = module(role, compiled=True)
            actual = configure_profile(profile, role, 'a' * 64, compiled)
            permissions = list(PERMISSIONS) if role == 'system' else []
            self.assertEqual(actual['acls']['allowed-acls'], permissions)
            self.assertEqual(actual['permissions']['restricted-permissions'], permissions)
            self.assertEqual(actual['bundle-info']['bundle-name'], BUNDLE)
            self.assertEqual(actual['bundle-info']['app-feature'],
                             'hos_normal_app' if role == 'normal' else 'hos_system_app')
            for changed in (dict(name='ohos.permission.INTERNET'), dict(name='ohos.permission.MANAGE_VPN')):
                bad = copy.deepcopy(compiled)
                bad['module']['requestPermissions'].append(changed)
                with self.assertRaises(ValueError):
                    configure_profile(copy.deepcopy(profile), role, 'a' * 64, bad)
            bad = copy.deepcopy(compiled)
            bad['app']['bundleName'] += '.other'
            with self.assertRaises(ValueError):
                configure_profile(copy.deepcopy(profile), role, 'a' * 64, bad)

    def test_real_public_calls_nonce_roles_and_disabled_initial_state_are_required(self):
        text = page('a' * 32, 'system')
        for call in ('config.startBlinking(mode, scenario)', 'config.stopBlinking(mode, scenario)',
                     'settings.setValueSync', 'settings.getValueSync', "this.original !== '0'",
                     "id('blink-pixel-surface')"):
            self.assertIn(call, text)
        self.assertNotIn('__BLINK_RUN__', text)
        for run_id, role in (('stale', 'system'), ('a' * 32, 'root')):
            with self.assertRaises(ValueError):
                page(run_id, role)


if __name__ == '__main__':
    unittest.main()
