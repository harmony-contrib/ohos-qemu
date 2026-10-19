"""Hostile synthetic inputs only; no image extraction, crypto, SDK or guest pass."""
import copy
import importlib.util
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock
import warnings
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import verify_number_identity_image as guard
from preinstall_selection import entry


class NumberIdentityImageTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.module = json.loads((ROOT / 'ci/capability-audit/fixtures/batch_system/number_identity_image/source-module.json').read_text())

    def hap(self, change=None, duplicate=False, payload=None):
        value = {'app': {'bundleName': guard.BUNDLE, 'debug': False}, 'module': copy.deepcopy(self.module)}
        if change:
            change(value)
        abc = bytearray(64);abc[:8] = b'PANDA\0\0\0';struct.pack_into('<I', abc, 16, len(abc));struct.pack_into('<I', abc, 8, zlib.adler32(abc[12:]) & 0xffffffff)
        resource = bytearray(144);resource[:7] = b'Restool';struct.pack_into('<II', resource, 128, len(resource), 1)
        members = {'module.json': json.dumps(value).encode(), 'ets/modules.abc': abc, 'resources.index': resource}
        if payload:
            members.update(payload)
        path = self.root / 'synthetic-host-only.hap'
        with warnings.catch_warnings(), zipfile.ZipFile(path, 'w') as archive:
            warnings.simplefilter('ignore', UserWarning)
            for name, data in members.items():
                archive.writestr(name, data)
            if duplicate:
                archive.writestr('module.json', json.dumps(value))
        return path

    def test_expected_native_module_is_bounded_host_structure_only(self):
        result = guard.inspect_hap(self.hap(), self.module)
        self.assertEqual(result['bundle'], 'com.ohos.numberidentity')
        self.assertEqual(result['compiled_abc_bytes'], 64)
        self.assertNotIn('provider_runtime_validated', result)
        old = copy.deepcopy(self.module)
        for item in old['extensionAbilities']:
            item.pop('srcLanguage', None)
        with self.assertRaisesRegex(ValueError, 'source module'):
            guard.inspect_hap(self.hap(), old)

    def test_wrong_bundle_URI_permissions_and_boolean_exports_rejected(self):
        changes = [lambda v: v['app'].update(bundleName='com.numberidentity'),
                   lambda v: v['module']['extensionAbilities'][0].update(uri='datashare://evil'),
                   lambda v: v['module']['requestPermissions'].append({'name': 'ohos.permission.SET_TELEPHONY_STATE'}),
                   lambda v: v['module']['extensionAbilities'][0].update(exported=1),
                   lambda v: v['module']['extensionAbilities'][0].pop('srcLanguage'),
                   lambda v: v['module']['extensionAbilities'][0].update(srcLanguage='ets')]
        for change in changes:
            with self.subTest(change=change), self.assertRaises(ValueError):
                guard.inspect_hap(self.hap(change), self.module)

    def test_duplicate_unsafe_and_empty_or_corrupt_compiled_payloads_rejected(self):
        with self.assertRaises(ValueError):
            guard.inspect_hap(self.hap(duplicate=True), self.module)
        for payload in ({'../escape': b'bad'}, {'ets/modules.abc': b'HOST stub'},
                        {'resources.index': b''}, {'resources.index': b'fake' * 40}):
            with self.subTest(payload=list(payload)), self.assertRaises(ValueError):
                guard.inspect_hap(self.hap(payload=payload), self.module)

    def test_wrong_ABI_type_and_header_only_ELF_rejected(self):
        for arch, elf_class, machine, kind in [('arm64', 1, 40, 3), ('arm64', 2, 183, 2),
                                               ('armv7a', 2, 183, 3), ('x86_64', 2, 183, 3),
                                               ('arm64', 2, 183, 3)]:
            data = bytearray(64);data[:7] = b'\x7fELF' + bytes((elf_class, 1, 1));struct.pack_into('<HH', data, 16, kind, machine)
            path = self.root / 'host-header-only.so';path.write_bytes(data)
            with self.subTest(arch=arch, machine=machine, kind=kind), self.assertRaises(ValueError):
                guard.inspect_elf(path, arch, guard.LIBRARIES[0])

    def test_actual_policy_type_and_existing_no_grant_boundary(self):
        source = {'install_list': [{'bundleName': 'other', 'keepAlive': False}]}
        guard.compare_policy('install_list_capability.json', json.dumps(source), json.dumps(source))
        actual = copy.deepcopy(source);actual['install_list'][0]['keepAlive'] = 0
        with self.assertRaises(ValueError):
            guard.compare_policy('install_list_capability.json', json.dumps(source), json.dumps(actual))
        forbidden = json.dumps({'install_list': [{'bundleName': guard.BUNDLE}]})
        for name in ('install_list_capability.json', 'install_list_permissions.json'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                guard.compare_policy(name, forbidden, forbidden)
        with self.assertRaises(ValueError):
            guard.compare_policy('uninstall_list.json', '{"recover_list":[],"recover_list":[]}', '{}')

    def test_install_directory_identity_and_removability_are_typed(self):
        for removable in (False, 0, True):
            data = json.dumps({'install_list': [{'app_dir': '/system/app/' + guard.INSTALL_ID, 'removable': removable}]})
            if removable is False:
                self.assertEqual(entry(data, guard.INSTALL_ID)['removable'], False)
            else:
                with self.assertRaises(ValueError):
                    entry(data, guard.INSTALL_ID)
        with self.assertRaises(ValueError):
            entry(json.dumps({'install_list': [{'app_dir': '/system/app/' + guard.BUNDLE, 'removable': False}]}), guard.INSTALL_ID)

    def test_orchestration_keeps_both_native_guards_signer_and_directory_binding(self):
        source = self.root / 'source';path = source / guard.PROJECT / 'entry/src/main/module.json5';path.parent.mkdir(parents=True);path.write_text(json.dumps({'module': self.module}))
        policies = source / 'vendor/ohemu/virt/preinstall-config';policies.mkdir(parents=True)
        for name in ('install_list.json', 'uninstall_list.json', 'install_list_capability.json', 'install_list_permissions.json'):
            (policies / name).write_text('{"install_list":[]}')
        scratch = self.root / 'scratch';scratch.mkdir();hap = self.hap()
        native, manifest, selection, profile = (mock.Mock() for _ in range(4))
        profile.verify.return_value = {'state': 'authenticated_renewed', 'bundle': guard.BUNDLE}
        def extracted(image, candidates, directory, executable):
            target = directory / 'host-only-file'
            if candidates[0].endswith('.hap'):
                target.write_bytes(hap.read_bytes())
            else:
                target.write_text('{"install_list":[]}')
            return target, {'image_path': candidates[0], 'image_inode': 1}
        with mock.patch.object(guard, 'load_guard', side_effect=[native, manifest, selection, profile]), \
             mock.patch.object(guard, 'verify_selection', return_value={}) as chosen, \
             mock.patch.object(guard, 'verify_signature', return_value={}) as signature, \
             mock.patch.object(guard, 'dump_unique_file', side_effect=extracted), \
             mock.patch.object(guard, 'debugfs_path', return_value='HOST unused'), \
             mock.patch.object(guard, 'inspect_elf', return_value={}), \
             mock.patch.object(guard, 'file_sha256', return_value='HOST ONLY'):
            guard.verify_image(source, Path('unused-image'), 'arm64', scratch)
        native.validate.assert_called_once_with(source, require_patched=True)
        manifest.validate.assert_called_once_with(source, require_patched=True)
        selection.configure.assert_called_once_with(source, require_patched=True)
        chosen.assert_called_once_with(source, guard.INSTALL_ID, Path('unused-image'), scratch, removable=False)
        self.assertEqual(signature.call_args.kwargs, {'profile_relative': guard.PROFILE})

    def test_offline_result_never_claims_runtime_or_whole_library(self):
        output = self.root / 'host-only-result.json'
        with mock.patch.object(guard, 'verify_image', return_value={}):
            self.assertEqual(guard.main(['--system-image', 'unused-image', '--source-root', 'unused-source',
                                        '--arch', 'arm64', '--output', str(output)]), 0)
        value = json.loads(output.read_text())
        for key in ('provider_runtime_validated', 'local_subset_runtime_validated', 'aggregate_provider_supported',
                    'full_number_library_supported', 'first_artifact_behavior_gate_passed'):
            self.assertIs(value[key], False)


if __name__ == '__main__':
    unittest.main()
