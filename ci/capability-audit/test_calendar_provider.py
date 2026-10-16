"""Source/signing fixtures are not CalendarData runtime acceptance."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
COMPONENT = REPO / 'patches/common/applications/standard/calendardata/source_provider'
sys.path.insert(0, str(REPO / 'patches/lib'))
from calendar_provider import ACLS, AUTHORITIES, BUNDLE, EDITOR, SIGNATURE, platform_leaf_fingerprint, validate
spec = importlib.util.spec_from_file_location('calendar_source_apply', COMPONENT / 'apply.py')
apply = importlib.util.module_from_spec(spec)
spec.loader.exec_module(apply)
prepare_spec = importlib.util.spec_from_file_location('calendar_source_prepare', COMPONENT / 'prepare.py')
source_prepare = importlib.util.module_from_spec(prepare_spec)
prepare_spec.loader.exec_module(source_prepare)
vendor_spec = importlib.util.spec_from_file_location('calendar_signing_prepare',
    REPO / 'patches/common/vendor/ohemu/virt/calendar_provider/prepare.py')
vendor_prepare = importlib.util.module_from_spec(vendor_spec)
vendor_spec.loader.exec_module(vendor_prepare)


def policy():
    extensions = [{'name': name, 'type': 'dataShare', 'exported': True, 'uri': uri,
                   'readPermission': read, 'writePermission': write}
                  for name, (uri, read, write) in AUTHORITIES.items()]
    extensions.append({'name': 'ReminderCallbackExtAbility', 'type': 'service', 'exported': True,
                       'permissions': ['ohos.permission.UPDATE_CALENDAR_RRULE']})
    return ({'deviceTypes': ['default', 'tablet'], 'extensionAbilities': extensions},
            {'bundle-info': {'bundle-name': BUNDLE, 'apl': 'system_core', 'app-feature': 'hos_system_app'},
             'acls': {'allowed-acls': sorted(ACLS)}, 'permissions': {'restricted-permissions': []}},
            {'install_list': [{'bundleName': BUNDLE, 'app_signature': [SIGNATURE],
                               'allowAppDesktopIconHide': True, 'allowAppUsePrivilegeExtension': True}]})


class CalendarProviderTests(unittest.TestCase):
    def test_editor_requires_exact_surface_inuse_scene_and_existing_boundaries(self):
        module, profile, capabilities = policy()
        with self.assertRaises(ValueError):
            validate(module, profile, capabilities, SIGNATURE, SIGNATURE, require_editor=True)
        module['extensionAbilities'].append(copy.deepcopy(EDITOR))
        module['requestPermissions'] = [
            {'name': name, 'usedScene': {'abilities': ['DataShareLowerExtAbility',
                'DataShareHighExtAbility', 'ReminderCallbackExtAbility', 'EditorUIExtensionAbility'],
                'when': 'inuse'}} for name in
            ('ohos.permission.READ_WHOLE_CALENDAR', 'ohos.permission.WRITE_WHOLE_CALENDAR')]
        validate(module, profile, capabilities, SIGNATURE, SIGNATURE, require_editor=True)
        for key, value in (('type', 'service'), ('srcEntry', './ets/DataAbility/DataShareHighExtAbility.ets'),
                           ('extensionProcessMode', 'bundle'), ('exported', 1), ('permissions', [])):
            broken = copy.deepcopy(module)
            broken['extensionAbilities'][-1][key] = value
            with self.assertRaises(ValueError):
                validate(broken, profile, capabilities, SIGNATURE, SIGNATURE, True)
        for scene in ({'abilities': ['EditorUIExtensionAbility'], 'when': 'always'},
                      {'abilities': ['DataShareHighExtAbility'], 'when': 'inuse'}):
            broken = copy.deepcopy(module)
            broken['requestPermissions'][0]['usedScene'] = scene
            with self.assertRaises(ValueError):
                validate(broken, profile, capabilities, SIGNATURE, SIGNATURE, True)
        for index, key in ((0, 'readPermission'), (1, 'writePermission')):
            broken = copy.deepcopy(module)
            broken['extensionAbilities'][index][key] = ''
            with self.assertRaises(ValueError):
                validate(broken, profile, capabilities, SIGNATURE, SIGNATURE, True)

    def test_stage_build_migration_is_exact_and_rejects_unknown_or_symlink(self):
        desired = source_prepare.desired_build()
        legacy = desired.decode().replace('  # Hvigor owns Stage resources and all five local HAR dependencies.\n  deps = []',
            '  deps = [\n    ":calendardata_js_assets",\n    ":calendardata_resources",\n  ]').replace(
            '# No separately downloaded CalendarData HAP',
            '\nohos_app_scope("calendardata_app_profile") {\n  app_profile = "AppScope/app.json5"\n  sources = [ "AppScope/resources" ]\n}\n\n'
            'ohos_js_assets("calendardata_js_assets") {\n  ets2abc = true\n  source_dir = "entry/src/main/ets"\n}\n\n'
            'ohos_resources("calendardata_resources") {\n  sources = [ "entry/src/main/resources" ]\n  deps = [ ":calendardata_app_profile" ]\n'
            '  hap_profile = "entry/src/main/module.json5"\n}\n# No separately downloaded CalendarData HAP').encode()
        import hashlib
        self.assertEqual(hashlib.sha256(legacy).hexdigest(), source_prepare.LEGACY_BUILD_SHA256)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            target = root / 'applications/standard/calendardata/BUILD.gn'
            target.parent.mkdir(parents=True)
            source_prepare.prepare(root)
            self.assertFalse(target.exists())
            target.write_bytes(legacy)
            for _ in range(2):
                source_prepare.prepare(root)
                self.assertEqual(target.read_bytes(), desired)
            for unknown in (legacy + b'// user edit\n', desired.replace(b'assembleHap', b'assembleCustom')):
                target.write_bytes(unknown)
                with self.assertRaises(ValueError): source_prepare.prepare(root)
                self.assertEqual(target.read_bytes(), unknown)
            target.unlink()
            real = root / 'user.gn'
            real.write_bytes(legacy)
            target.symlink_to(real)
            with self.assertRaises(ValueError): source_prepare.prepare(root)
            self.assertEqual(real.read_bytes(), legacy)

    def test_existing_policy_requires_matching_leaf_not_wildcard(self):
        module, profile, capabilities = policy()
        validate(module, profile, capabilities, SIGNATURE, SIGNATURE)
        for left, right in (('old-prebuilt', SIGNATURE), (SIGNATURE, 'root-cert'), ('*', '*')):
            with self.assertRaises(ValueError): validate(module, profile, capabilities, left, right)
        for value in ([], ['*'], [SIGNATURE, '*'], ['old-prebuilt']):
            broken = copy.deepcopy(capabilities)
            broken['install_list'][0]['app_signature'] = value
            with self.assertRaises(ValueError): validate(module, profile, broken, SIGNATURE, SIGNATURE)
        duplicated = copy.deepcopy(capabilities)
        duplicated['install_list'].append(duplicated['install_list'][0])
        with self.assertRaises(ValueError): validate(module, profile, duplicated, SIGNATURE, SIGNATURE)

    def test_acl_and_system_identity_cannot_expand_or_downgrade(self):
        module, profile, capabilities = policy()
        for key, value in (('bundle-name', 'com.example.fake'), ('apl', 'normal'),
                           ('app-feature', 'hos_normal_app')):
            broken = copy.deepcopy(profile)
            broken['bundle-info'][key] = value
            with self.assertRaises(ValueError): validate(module, broken, capabilities, SIGNATURE, SIGNATURE)
        for value in ([], sorted(ACLS) + ['ohos.permission.MANAGE_CALENDAR'], sorted(ACLS) * 2):
            broken = copy.deepcopy(profile)
            broken['acls']['allowed-acls'] = value
            with self.assertRaises(ValueError): validate(module, broken, capabilities, SIGNATURE, SIGNATURE)
        profile['permissions']['restricted-permissions'] = ['ohos.permission.READ_WHOLE_CALENDAR']
        with self.assertRaises(ValueError): validate(module, profile, capabilities, SIGNATURE, SIGNATURE)

    def test_authorities_and_service_permission_cannot_be_aliased_or_weakened(self):
        module, profile, capabilities = policy()
        for index in (0, 1):
            for key, value in (('uri', 'datashare://fake'), ('readPermission', ''),
                               ('writePermission', ''), ('type', 'service'), ('exported', 1)):
                broken = copy.deepcopy(module)
                broken['extensionAbilities'][index][key] = value
                with self.assertRaises(ValueError): validate(broken, profile, capabilities, SIGNATURE, SIGNATURE)
        for value in ([], ['ohos.permission.READ_CALENDAR']):
            broken = copy.deepcopy(module)
            broken['extensionAbilities'][-1]['permissions'] = value
            with self.assertRaises(ValueError): validate(broken, profile, capabilities, SIGNATURE, SIGNATURE)
        for extra in (module['extensionAbilities'][0], {'name': 'EditorUIExtensionAbility'}):
            broken = copy.deepcopy(module)
            broken['extensionAbilities'].append(extra)
            with self.assertRaises(ValueError): validate(broken, profile, capabilities, SIGNATURE, SIGNATURE)

    def test_platform_pem_uses_application_leaf_not_first_root(self):
        certs = [b'-----BEGIN CERTIFICATE-----\n' + name + b'\n-----END CERTIFICATE-----'
                 for name in (b'fixture-root', b'fixture-intermediate', b'fixture-application')]
        with patch('calendar_provider.certificate_fingerprint', return_value=SIGNATURE) as fingerprint:
            self.assertEqual(platform_leaf_fingerprint(b'\n'.join(certs)), SIGNATURE)
            fingerprint.assert_called_once_with(certs[-1])
        for chain in (b'', certs[0], b'\n'.join(certs + [certs[-1]])):
            with self.assertRaises(ValueError): platform_leaf_fingerprint(chain)

    def test_source_profile_keeps_all_hars_and_is_idempotent(self):
        modules = [{'name': name, 'srcPath': './' + name} for name in sorted(apply.MODULES)]
        original = {'app': {'products': [apply.ORIGINAL_PRODUCT], 'signingConfigs': [
            {'name': 'release', 'material': {'storeFile': 'signature/OpenHarmony.p12',
                                           'profile': 'signature/Calendardata.p7b'}}]}, 'modules': modules}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'build-profile.json5'
            path.write_text(json.dumps(original))
            apply.configure(path)
            once = path.read_bytes()
            configured = json.loads(once)
            self.assertEqual(configured['modules'], modules)
            self.assertEqual(configured['app'], {'products': [apply.PRODUCT]})
            apply.configure(path)
            self.assertEqual(path.read_bytes(), once)
            for broken in (dict(original, modules=modules[:-1]),
                           dict(original, app={'products': [dict(apply.ORIGINAL_PRODUCT, runtimeOS='custom')]})):
                path.write_text(json.dumps(broken))
                with self.assertRaises(ValueError): apply.configure(path)

    def test_source_hap_vendor_and_stale_prebuilt_are_independently_wired(self):
        script = (REPO / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        for component in ('CALENDAR_SOURCE_PROVIDER_COMPONENT_SCRIPT', 'CALENDAR_PREBUILT_COMPONENT_SCRIPT',
                          'CALENDAR_SIGNING_COMPONENT_SCRIPT'):
            self.assertIn('bash "${' + component + '}" --source-root "${OHOS_ROOT}"', script)
        self.assertIn('python3 "${PATCH_ROOT}/lib/calendar_provider.py" --source-root "${OHOS_ROOT}"', script)
        source = (COMPONENT / '0001-build-calendar-provider-from-source.patch').read_text()
        self.assertIn('+  certificate_profile = "signature/Calendardata.p7b"', source)
        self.assertIn('+  part_name = "calendar_data"', source)
        self.assertIn('calendardata_hap', source)
        self.assertIn('+  deps = []', source)
        self.assertNotIn('ohos_resources(', source)
        self.assertNotIn('ohos_js_assets(', source)
        production = (COMPONENT / '0003-avoid-unused-hypium-fetch-in-production-provider.patch').read_text()
        self.assertIn('-    "@ohos/hypium": "1.0.6"', production)
        vendor = (REPO / 'patches/common/vendor/ohemu/virt/calendar_provider/0001-pin-source-provider-platform-signature.patch').read_text()
        self.assertIn('"com.ohos.calendardata"', vendor)
        self.assertEqual(vendor.count('\n+'), 2)  # +++ header and exactly one changed fingerprint

    def test_pristine_crlf_and_profile_formatted_signing_policy_apply_identically(self):
        component = REPO / 'patches/common/vendor/ohemu/virt/calendar_provider'
        for original_signature in (vendor_prepare.OLD, vendor_prepare.NEW):
            for line_ending in ('\n', '\r\n'):
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    path = root / 'vendor/ohemu/virt/preinstall-config/install_list_capability.json'
                    path.parent.mkdir(parents=True)
                    _, _, original = policy()
                    original['install_list'][0]['app_signature'] = [original_signature]
                    original['install_list'].insert(0, {'bundleName': 'com.other', 'app_signature': ['UNCHANGED']})
                    path.write_bytes(json.dumps(original, indent=4).replace('\n', line_ending).encode())
                    for iteration in range(2):
                        subprocess.run(['bash', str(component / 'apply.sh'), '--source-root', str(root)],
                                       capture_output=True, text=True, check=True)
                        fixed = json.loads(path.read_text())
                        self.assertEqual(fixed['install_list'][0], original['install_list'][0])
                        self.assertEqual(fixed['install_list'][1]['app_signature'], [SIGNATURE])
                        if iteration == 0: once = path.read_bytes()
                        else: self.assertEqual(path.read_bytes(), once)

    def test_unknown_or_duplicate_signing_policy_preserves_original_bytes(self):
        _, _, original = policy()
        variants = []
        for signatures in ([], ['*'], [SIGNATURE, '*'], ['unknown']):
            broken = copy.deepcopy(original)
            broken['install_list'][0]['app_signature'] = signatures
            variants.append(json.dumps(broken))
        duplicate = copy.deepcopy(original)
        duplicate['install_list'].append(duplicate['install_list'][0])
        variants.append(json.dumps(duplicate))
        for privilege in (False, 1):
            broken = copy.deepcopy(original)
            broken['install_list'][0]['allowAppUsePrivilegeExtension'] = privilege
            variants.append(json.dumps(broken))
        variants.append('{"install_list": [], "install_list": []}')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'policy.json'
            for value in variants:
                encoded = value.replace('\n', '\r\n').encode()
                path.write_bytes(encoded)
                with self.assertRaises(ValueError): vendor_prepare.prepare(path)
                self.assertEqual(path.read_bytes(), encoded)


if __name__ == '__main__':
    unittest.main()
