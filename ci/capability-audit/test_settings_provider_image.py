"""Actual HAP boundary checks; these fixtures do not prove runtime usability."""
import importlib.util
import hashlib
import copy
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import warnings
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('settings_image', ROOT / 'scripts/verify_settings_provider_image.py')
provider = importlib.util.module_from_spec(spec)
spec.loader.exec_module(provider)


class SettingsImageBoundary(unittest.TestCase):
    def test_compiled_wallpaper_permission_must_match_actual_source(self):
        grants = [{'name': 'ohos.permission.SET_WALLPAPER'}]
        source = {'requestPermissions': grants}
        self.module['module']['requestPermissions'] = copy.deepcopy(grants)
        self.write();provider.inspect_hap(self.hap, source)
        for changed in ([], grants + grants, grants + [{'name': 'ohos.permission.READ_CONTACTS'}]):
            self.module['module']['requestPermissions'] = changed;self.write()
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                provider.inspect_hap(self.hap, source)

    def select_fixture(self):
        self.module['module']['abilities'] = [dict(provider.SELECT_ABILITY)]
        self.module['module']['requestPermissions'] = [{'name': 'ohos.permission.SET_WALLPAPER'}]
        self.entries[provider.SELECT_PAGES] = json.dumps({'src': ['pages/Main', 'pages/ChoosePicker']}).encode()
        return copy.deepcopy(self.module['module'])

    def test_compiled_private_select_provider_and_page(self):
        source = self.select_fixture(); self.write()
        result = provider.inspect_hap(self.hap, source)
        self.assertEqual(result['select_provider']['page'], 'pages/ChoosePicker')
        self.assertIs(result['select_provider']['exported'], False)

    def test_select_provider_cannot_be_missing_duplicate_or_exported(self):
        source = self.select_fixture(); original = copy.deepcopy(self.module)
        for change in ('missing', 'duplicate', 'exported', 'numeric_exported', 'launch', 'entry', 'mission', 'permission', 'skill'):
            self.module = copy.deepcopy(original)
            rows = self.module['module']['abilities']
            if change == 'missing': rows.clear()
            elif change == 'duplicate': rows.append(copy.deepcopy(rows[0]))
            elif change == 'exported': rows[0]['exported'] = True
            elif change == 'numeric_exported': rows[0]['exported'] = 0
            elif change == 'launch': rows[0]['launchType'] = 'singleton'
            elif change == 'entry': rows[0]['srcEntry'] = './ets/Other.ets'
            elif change == 'mission': rows[0]['removeMissionAfterTerminate'] = False
            elif change == 'permission': rows[0]['permissions'] = ['ohos.permission.READ_CONTACTS']
            else: rows[0]['skills'] = [{'actions': ['ohos.want.action.select']}]
            self.write()
            with self.subTest(change=change), self.assertRaises(ValueError): provider.inspect_hap(self.hap, source)

    def test_select_source_and_compiled_profile_are_both_required(self):
        source = self.select_fixture()
        for change in ('missing', 'duplicate', 'exported'):
            changed = copy.deepcopy(source)
            if change == 'missing': changed['abilities'].clear()
            elif change == 'duplicate': changed['abilities'].append(copy.deepcopy(changed['abilities'][0]))
            else: changed['abilities'][0]['exported'] = True
            self.write()
            with self.subTest(change=change), self.assertRaises(ValueError): provider.inspect_hap(self.hap, changed)

    def test_select_page_missing_duplicate_invalid_or_wrong_type_rejected(self):
        source = self.select_fixture()
        for data in (None, b'{}', b'{"src":[]}', b'{"src":["pages/ChoosePicker","pages/ChoosePicker"]}',
                     b'{"src":"pages/ChoosePicker"}', b'{"src":["pages/ChoosePicker",1]}',
                     b'{"src":["pages/ChoosePicker"],"src":[]}', b'[]', b'not-json'):
            if data is None: self.entries.pop(provider.SELECT_PAGES, None)
            else: self.entries[provider.SELECT_PAGES] = data
            self.write()
            with self.subTest(data=data), self.assertRaises(ValueError): provider.inspect_hap(self.hap, source)

    def test_profile_cannot_promote_APL_or_expand_existing_policy(self):
        original = {'bundle-info': {'bundle-name': 'com.ohos.settings', 'apl': 'system_basic',
                    'app-feature': 'hos_system_app', 'distribution-certificate': 'old'},
                    'validity': {'not-before': 100, 'not-after': 200}, 'type': 'release',
                    'app-distribution-type': 'os_integration', 'acls': {'allowed-acls': ['unchanged']},
                    'permissions': {'restricted-permissions': []}}
        actual = copy.deepcopy(original)
        actual['bundle-info']['distribution-certificate'] = 'fixture-cert'
        actual['validity']['not-after'] = 2208988800
        with patch.object(provider.subprocess, 'check_output', return_value=b'fixture-DER'), \
                patch.object(provider, 'SIGNATURE', hashlib.sha256(b'fixture-DER').hexdigest().upper()):
            provider.profile_invariants(original, actual)
            for kind in ('apl', 'acl', 'permission', 'expiry', 'distribution', 'identity'):
                changed = copy.deepcopy(actual)
                if kind == 'apl': changed['bundle-info']['apl'] = 'system_core'
                elif kind == 'acl': changed['acls']['allowed-acls'].append('extra')
                elif kind == 'permission': changed['permissions']['restricted-permissions'].append('extra')
                elif kind == 'expiry': changed['validity']['not-after'] += 1
                elif kind == 'distribution': changed['app-distribution-type'] = 'enterprise'
                else: changed['bundle-info']['bundle-name'] = 'other.app'
                with self.assertRaises(ValueError): provider.profile_invariants(original, changed)

    def test_service_permissions_and_external_session_are_not_relaxed(self):
        original = copy.deepcopy(self.module)
        for name, key, value in (('SettingsExtService', 'permissions', []),
                                 ('IgnoreRepeatClickExtService', 'permissions', []),
                                 ('ExternalCommonUIExtensionAbility', 'extensionProcessMode', 'bundle'),
                                 ('ExternalCommonUIExtensionAbility', 'exported', False),
                                 ('SharePickerExtensionAbility', 'srcEntry', './ets/Unrelated.ets'),
                                 ('SharePickerExtensionAbility', 'extensionProcessMode', 'bundle'),
                                 ('SharePickerExtensionAbility', 'exported', False),
                                 ('SharePickerExtensionAbility', 'permissions', ['ohos.permission.READ_CONTACTS'])):
            self.module = copy.deepcopy(original)
            next(row for row in self.module['module']['extensionAbilities'] if row['name'] == name)[key] = value
            self.write()
            with self.assertRaises(ValueError): provider.inspect_hap(self.hap)

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='settings-image-test-')
        self.addCleanup(self.temporary.cleanup)
        self.hap = Path(self.temporary.name) / 'Settings.hap'
        self.module = {'app': {'bundleName': 'com.ohos.settings'}, 'module': {
            'name': 'phone', 'type': 'entry', 'deviceTypes': ['default', 'tablet'],
            'extensionAbilities': [{'name': name, 'type': kind} for name, kind in provider.EXTENSIONS.items()]}}
        for entry in self.module['module']['extensionAbilities']:
            if entry['name'] in ('SettingsExtService', 'IgnoreRepeatClickExtService'):
                entry['permissions'] = ['ohos.permission.ACCESS_SYSTEM_SETTINGS']
            if entry['name'] == 'ExternalCommonUIExtensionAbility':
                entry.update(exported=True, extensionProcessMode='instance')
            if entry['name'] == 'SharePickerExtensionAbility':
                entry.update(srcEntry='./ets/Setting/SharePicker/SharePickerExtension.ets', exported=True,
                             extensionProcessMode='instance')
        self.entries = {'ets/modules.abc': b'actual-fixture-bytecode', 'resources.index': b'resources'}
        for abi, elf_class, machine in provider.ABIS.values():
            raw = bytearray(64)
            raw[:7] = b'\x7fELF' + bytes((elf_class, 1, 1))
            struct.pack_into('<HH', raw, 16, 3, machine)
            for name in ('libnative.so', 'libc++_shared.so'):
                self.entries['libs/' + abi + '/' + name] = bytes(raw)

    def write(self, metadata=None):
        with zipfile.ZipFile(self.hap, 'w') as archive:
            archive.writestr('module.json', metadata or json.dumps(self.module))
            for name, data in self.entries.items():
                archive.writestr(name, data)

    def test_complete_three_abi_provider(self):
        self.write()
        evidence = provider.inspect_hap(self.hap)
        self.assertEqual(len(evidence['native_libraries']), 6)
        self.assertEqual(evidence['extensions'], provider.EXTENSIONS)

    def test_missing_source_extension_and_wrong_type(self):
        original = json.loads(json.dumps(self.module))
        for change in ('missing', 'wrong'):
            with self.subTest(change=change):
                self.module = json.loads(json.dumps(original))
                if change == 'missing':
                    self.module['module']['extensionAbilities'].pop()
                else:
                    self.module['module']['extensionAbilities'][-1]['type'] = 'service'
                self.write()
                with self.assertRaises(ValueError):
                    provider.inspect_hap(self.hap)

    def test_duplicate_extensions_and_metadata(self):
        self.module['module']['extensionAbilities'].append(self.module['module']['extensionAbilities'][0])
        self.write()
        with self.assertRaises(ValueError):
            provider.inspect_hap(self.hap)
        self.write('{"app":{},"app":{},"module":{}}')
        with self.assertRaises(ValueError):
            provider.inspect_hap(self.hap)

    def test_wrong_machine_or_missing_abi(self):
        member = 'libs/armeabi-v7a/libnative.so'
        self.entries[member] = self.entries['libs/arm64-v8a/libnative.so']
        self.write()
        with self.assertRaises(ValueError):
            provider.inspect_hap(self.hap)
        del self.entries[member]
        self.write()
        with self.assertRaises(KeyError):
            provider.inspect_hap(self.hap)

    def test_duplicate_and_escaping_zip_members(self):
        self.entries['../escaped'] = b'bad'
        self.write()
        with self.assertRaises(ValueError):
            provider.inspect_hap(self.hap)
        del self.entries['../escaped']
        self.write()
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            with zipfile.ZipFile(self.hap, 'a') as archive:
                archive.writestr('module.json', '{}')
        with self.assertRaises(ValueError):
            provider.inspect_hap(self.hap)

    def test_empty_bytecode_is_not_a_provider(self):
        self.entries['ets/modules.abc'] = b''
        self.write()
        with self.assertRaises(ValueError):
            provider.inspect_hap(self.hap)

    def test_packaging_requires_actual_image_for_both_profiles(self):
        recipe = (ROOT / 'scripts/package_standard_qemu.sh').read_text()
        self.assertEqual(recipe.count('"${SCRIPT_DIR}/verify_settings_provider_image.py"'), 1)
        section = recipe[recipe.index('python3 "${SCRIPT_DIR}/verify_arkweb_core_image.py"'):
                         recipe.index('  write_full_device_profile_evidence', recipe.index('python3 "${SCRIPT_DIR}/verify_arkweb_core_image.py"'))]
        self.assertIn('--system-image "${IMAGES_OUT}/system.img"', section)
        self.assertIn('--source-root "${SOURCE_ROOT}" --output "${PACKAGE_DIR}/settings-provider-evidence.json"', section)

    def signature_fixture(self, leaf=provider.SIGNATURE, profile=b'exact source profile', markers=True):
        source = Path(self.temporary.name) / 'source'
        original = source / 'applications/standard/settings/signature/settings.p7b'
        original.parent.mkdir(parents=True, exist_ok=True)
        original.write_bytes(b'exact source profile')
        scratch = Path(self.temporary.name) / 'signature'
        scratch.mkdir(exist_ok=True)
        (scratch / 'app-chain.cer').write_bytes(b'chain')
        (scratch / 'embedded-profile.p7b').write_bytes(profile)
        stdout = 'certificate #0 +++++\nSHA256: ' + ':'.join(leaf[i:i+2] for i in range(0, len(leaf), 2)) + '\ncertificate #1 +++++\n'
        if markers:
            stdout += '\nverify codesign success\nDigest verify result: true\nverify permission sign success\nverify-app success\n'
        result = subprocess.CompletedProcess([], 0, stdout, '')
        return source, scratch, result

    def test_signature_output_format_and_exact_profile(self):
        source, scratch, result = self.signature_fixture()
        real_sha = provider.file_sha256
        with patch.object(provider, 'subprocess') as process, patch.object(provider, 'file_sha256',
                side_effect=lambda p: provider.SIGNER_JAR_SHA if p.name == 'hap-sign-tool.jar' else real_sha(p)):
            process.run.return_value = result
            self.assertEqual(provider.verify_signature(self.hap, source, scratch)['application_signer_sha256'],
                             provider.SIGNATURE)

    def test_success_exit_without_digest_permission_proof_rejected(self):
        source, scratch, result = self.signature_fixture(markers=False)
        with patch.object(provider, 'subprocess') as process, patch.object(provider, 'file_sha256', return_value=provider.SIGNER_JAR_SHA):
            process.run.return_value = result
            with self.assertRaises(ValueError):
                provider.verify_signature(self.hap, source, scratch)

    def test_wrong_leaf_and_substituted_profile_rejected(self):
        for leaf, profile in (('A' * 64, b'exact source profile'), (provider.SIGNATURE, b'wrong profile')):
            with self.subTest(leaf=leaf):
                source, scratch, result = self.signature_fixture(leaf, profile)
                with patch.object(provider, 'subprocess') as process, patch.object(provider, 'file_sha256', return_value=provider.SIGNER_JAR_SHA):
                    process.run.return_value = result
                    with self.assertRaises(ValueError):
                        provider.verify_signature(self.hap, source, scratch)

    def policy_fixture(self):
        source = Path(self.temporary.name).resolve() / 'policy-source'
        directory = source / 'vendor/ohemu/virt/preinstall-config'
        directory.mkdir(parents=True)
        capability = {'install_list': [{'bundleName': 'com.ohos.settings', 'app_signature': [provider.SIGNATURE],
            'allowAppUsePrivilegeExtension': True}]}
        grants = [{'bundleName': 'com.ohos.settings', 'app_signature': [provider.SIGNATURE],
            'permissions': [{'name': 'ohos.permission.' + name, 'userCancellable': False} for name in
                ('GET_INSTALLED_BUNDLE_LIST',)]}]
        (directory / 'install_list_capability.json').write_text(json.dumps(capability))
        (directory / 'install_list_permissions.json').write_text(json.dumps(grants))
        return source, directory, grants

    def test_source_checks_both_capability_and_existing_permission_signer(self):
        source, directory, grants = self.policy_fixture()
        result = provider.verify_preinstall_policies(source)
        self.assertEqual(set(result), {'install_list_capability.json', 'install_list_permissions.json'})
        grants[0]['app_signature'] = ['EB5DBE52EE8DD7206DDE612E7484E88CE264E74958704D0712BFA774C87F4DA1']
        (directory / 'install_list_permissions.json').write_text(json.dumps(grants))
        with self.assertRaises(ValueError): provider.verify_preinstall_policies(source)

    def test_image_cannot_retain_old_grant_signer_when_source_is_fixed(self):
        source, directory, grants = self.policy_fixture()
        scratch = Path(self.temporary.name).resolve() / 'policy-image'
        scratch.mkdir()
        def extracted(image, candidates, destination, executable):
            name = Path(candidates[0]).name
            contents = (directory / name).read_text()
            if name == 'install_list_permissions.json':
                contents = contents.replace(provider.SIGNATURE, 'EB5DBE52EE8DD7206DDE612E7484E88CE264E74958704D0712BFA774C87F4DA1')
            target = destination / 'actual-file'
            target.write_text(contents)
            return target, {'image_path': candidates[0], 'image_inode': 5}
        with patch.object(provider, 'dump_unique_file', side_effect=extracted), \
                patch.object(provider, 'debugfs_path', return_value='/host-fixture/debugfs'):
            with self.assertRaises(ValueError):
                provider.verify_preinstall_policies(source, Path('/host-fixture/system.img'), scratch)


if __name__ == '__main__':
    unittest.main()
