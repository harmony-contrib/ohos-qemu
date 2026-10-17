"""Host-only counterexamples. Mocks never establish Java/CMS/image/runtime success."""
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'patches/lib'))
sys.path.insert(0, str(ROOT / 'scripts'))
import privacycenter_provider as provider
import verify_privacycenter_provider_image as image


class StagingTransaction(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='privacycenter-host-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.source = self.root / 'source'; self.assets = self.root / 'assets'
        self.source.mkdir(); self.assets.mkdir()
        self.old, self.new = b'explicit host original model', b'explicit host canonical model'
        self.hap = self.write(provider.TARGET, self.old)
        self.asset = self.assets / provider.FILENAME; self.asset.write_bytes(self.new)
        self.install = self.write(provider.POLICY_DIR + '/install_list.json', b'{"install_list": [{"app_dir":"/system/app/Other","removable":true}]}\n')
        self.capability = self.write(provider.POLICY_DIR + '/install_list_capability.json', b'{"install_list":[]}\n')
        self.grants = self.write(provider.POLICY_DIR + '/install_list_permissions.json', b'[]\n')
        self.uninstall = self.write(provider.POLICY_DIR + '/uninstall_list.json', b'{"uninstall_list":[],"recover_list":[]}\n')
        for device in ('phone', '2in1'):
            self.write(f'vendor/ohemu/virt/virt_{device}_full.meta.json', b'{"existing":"preserved"}\n')
        self.meta = self.source / 'vendor/ohemu/virt/virt_phone_full.meta.json'
        self.write(provider.JAR, b'host mock JAR NOT executable')
        for name, value in [('ORIGINAL_SHA', provider.digest(self.old)), ('CANONICAL_SHA', provider.digest(self.new)),
                            ('JAR_SHA', provider.digest(b'host mock JAR NOT executable'))]:
            item = patch.object(provider, name, value); item.start(); self.addCleanup(item.stop)
        item = patch.object(provider, 'inspect_payload', side_effect=self.mock_payload)
        item.start(); self.addCleanup(item.stop)
        item = patch.object(provider, 'verify_signature', return_value={'scope': 'host mock NOT cryptographic evidence'})
        self.crypto = item.start(); self.addCleanup(item.stop)
        self.revision = 'a' * 40

    def write(self, name, data):
        path = self.source / name; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data); path.chmod(0o640)
        return path

    def mock_payload(self, data, inventory, *, canonical=True):
        expected = self.new if canonical else self.old
        provider.require(data == expected, 'host model exact HAP mismatch')
        return {'scope': 'host payload model only'}

    def apply(self, device='phone'):
        return provider.apply(self.source, self.assets, device, self.revision)

    def contents(self):
        return {str(path.relative_to(self.source)): (path.read_bytes(), stat.S_IMODE(path.stat().st_mode))
                for path in self.source.rglob('*') if path.is_file()}

    def test_pristine_transaction_phone_2in1_and_exact_idempotence(self):
        before = self.contents(); result = self.apply()
        self.assertEqual(3, len(result['changed']))
        self.assertEqual(self.new, self.hap.read_bytes())
        self.assertEqual([provider.ENTRY], [r for r in provider.load(self.install.read_bytes())['install_list'] if r['app_dir'] == provider.ENTRY['app_dir']])
        for path in (self.capability, self.grants, self.uninstall):
            self.assertEqual(before[str(path.relative_to(self.source))], (path.read_bytes(), stat.S_IMODE(path.stat().st_mode)))
        identity = {p: (p.stat().st_ino, p.stat().st_mtime_ns) for p in (self.hap, self.install, self.meta)}
        self.assertEqual([], self.apply()['changed'])
        self.assertEqual(identity, {p: (p.stat().st_ino, p.stat().st_mtime_ns) for p in identity})
        self.assertEqual(1, len(self.apply('2in1')['changed']))
        self.assertFalse(result['provider_runtime_validated'])
        self.assertFalse(result['first_artifact_behavior_gate_passed'])

    def test_unknown_source_or_asset_fails_without_writes(self):
        for path in (self.hap, self.asset):
            old = path.read_bytes(); path.write_bytes(b'unknown edited HAP')
            before = self.contents()
            with self.assertRaises(ValueError): self.apply()
            self.assertEqual(before, self.contents()); path.write_bytes(old)

    def test_conflicting_duplicate_or_boolean_alias_scan_entries_rejected(self):
        for entries in ([dict(provider.ENTRY, removable=True)], [provider.ENTRY, provider.ENTRY],
                        [dict(provider.ENTRY, removable=0)], [dict(provider.ENTRY, extra=True)],
                        [dict(provider.ENTRY, app_dir=provider.ENTRY['app_dir'] + '/')]):
            self.install.write_text(json.dumps({'install_list': entries})); before = self.contents()
            with self.subTest(entries=entries), self.assertRaises(ValueError): self.apply()
            self.assertEqual(before, self.contents())

    def test_existing_capability_grant_veto_or_recover_mentions_are_never_changed(self):
        for path, value in ((self.capability, {'install_list': [{'bundleName': provider.BUNDLE, 'allowAppUsePrivilegeExtension': False}]}),
                            (self.grants, [{'bundleName': provider.BUNDLE, 'permissions': []}]),
                            (self.uninstall, {'uninstall_list': [provider.ENTRY['app_dir']], 'recover_list': []}),
                            (self.uninstall, {'uninstall_list': [], 'recover_list': [provider.ENTRY['app_dir']]})):
            original = path.read_bytes(); path.write_text(json.dumps(value)); before = self.contents()
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, 'existing PrivacyCenter policy'):
                self.apply()
            self.assertEqual(before, self.contents()); path.write_bytes(original)

    def test_signature_failure_precedes_all_source_writes(self):
        self.crypto.side_effect = ValueError('actual verification failed')
        before = self.contents()
        with self.assertRaisesRegex(ValueError, 'actual verification failed'): self.apply()
        self.assertEqual(before, self.contents())

    def test_late_failure_rolls_back_every_written_byte_and_mode(self):
        before = self.contents(); real_replace = provider.replace
        def replace(path, data, snapshot, written):
            if path == self.meta: raise OSError('host injected third-write failure')
            return real_replace(path, data, snapshot, written)
        with patch.object(provider, 'replace', side_effect=replace), self.assertRaises(OSError): self.apply()
        self.assertEqual(before, self.contents())
        self.assertEqual([], list(self.source.rglob('.privacycenter-provider-*')))

    def test_failure_after_rename_still_tracks_and_rolls_back_that_write(self):
        before = self.contents(); real_rename = os.replace; injected = False
        def rename(source, target):
            nonlocal injected
            real_rename(source, target)
            if target == self.install and not injected:
                injected = True; raise OSError('error after successful rename')
        with patch.object(provider.os, 'replace', side_effect=rename), self.assertRaises(OSError): self.apply()
        self.assertEqual(before, self.contents())

    def test_preflight_chmod_hardlink_and_symlink_changes_are_preserved(self):
        original = self.hap.read_bytes()
        for kind in ('chmod', 'hardlink', 'symlink'):
            self.hap.unlink(); self.hap.write_bytes(original); self.hap.chmod(0o640)
            external = self.root / ('external-' + kind)
            def change(*args, **kwargs):
                if kind == 'chmod': self.hap.chmod(0o600)
                elif kind == 'hardlink': os.link(self.hap, external)
                else:
                    external.write_bytes(original); self.hap.unlink(); self.hap.symlink_to(external)
                return {'scope': 'host mock'}
            self.crypto.side_effect = change
            with self.subTest(kind=kind), self.assertRaises(ValueError): self.apply()
            if kind == 'chmod': self.assertEqual(0o600, stat.S_IMODE(self.hap.stat().st_mode))
            elif kind == 'hardlink': self.assertEqual(2, self.hap.stat().st_nlink)
            else: self.assertTrue(self.hap.is_symlink())
            self.assertNotIn(provider.BUNDLE.encode(), self.install.read_bytes())
            if external.exists(): external.unlink()

    def test_other_pending_file_external_edit_survives_rollback(self):
        old_hap = self.hap.read_bytes(); real_replace = provider.replace
        external = b'{"install_list":[],"external":"preserve"}\n'
        def replace(path, data, snapshot, written):
            real_replace(path, data, snapshot, written)
            if path == self.hap and data == self.new: self.install.write_bytes(external)
        with patch.object(provider, 'replace', side_effect=replace), self.assertRaises(ValueError): self.apply()
        self.assertEqual(old_hap, self.hap.read_bytes())
        self.assertEqual(external, self.install.read_bytes())

    def test_new_policy_file_and_protected_policy_edit_after_preflight_rejected(self):
        for kind in ('new-file', 'protected-edit'):
            def change(*args, **kwargs):
                if kind == 'new-file': self.write(provider.POLICY_DIR + '/new-deny.json', b'{}')
                else: self.uninstall.write_bytes(b'{"uninstall_list":["external"],"recover_list":[]}')
                return {'scope': 'host mock'}
            self.crypto.side_effect = change
            with self.subTest(kind=kind), self.assertRaises(ValueError): self.apply()
            self.assertEqual(self.old, self.hap.read_bytes())
            (self.uninstall.parent / 'new-deny.json').unlink(missing_ok=True)

    def test_same_transaction_written_file_external_edit_is_not_overwritten_on_rollback(self):
        real_replace = provider.replace
        external = b'external edit after this transaction wrote HAP'
        def replace(path, data, snapshot, written):
            real_replace(path, data, snapshot, written)
            if path == self.hap and data == self.new: self.hap.write_bytes(external)
        with patch.object(provider, 'replace', side_effect=replace), self.assertRaisesRegex(ValueError, 'rollback conflicts'):
            self.apply()
        self.assertEqual(external, self.hap.read_bytes())
        self.assertNotIn(provider.BUNDLE.encode(), self.install.read_bytes())

    def test_fifo_parent_alias_and_duplicate_json_policies_rejected_before_writes(self):
        fifo = self.uninstall.parent / 'unexpected-input'
        os.mkfifo(fifo)
        with self.assertRaises(ValueError): self.apply()
        fifo.unlink()
        original = self.install.read_bytes()
        self.install.write_bytes(b'{"install_list":[],"install_list":[]}')
        with self.assertRaisesRegex(ValueError, 'duplicate'): self.apply()
        self.install.write_bytes(original)
        alias = self.root / 'source-alias'; alias.symlink_to(self.source, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'canonical'): provider.apply(alias, self.assets, 'phone', self.revision)
        self.assertEqual(self.old, self.hap.read_bytes())

    def test_unrecognized_metadata_or_partial_installed_state_preserved(self):
        for value in ({'privacycenter_provider': {'claimed': True}},
                      {'privacycenter_provider': provider.metadata('phone', self.revision)}):
            self.meta.write_text(json.dumps(value)); before = self.contents()
            with self.assertRaises(ValueError): self.apply()
            self.assertEqual(before, self.contents())


class CryptographicParser(unittest.TestCase):
    def setUp(self):
        self.public = provider.fixtures()
        temp = tempfile.TemporaryDirectory(prefix='privacycenter-parser-'); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve(); jar = self.root / 'fake.jar'; jar.write_bytes(b'host mock only')
        self.jar = provider.Snapshot.read(jar)
        item = patch.object(provider, 'JAR_SHA', provider.digest(self.jar.data)); item.start(); self.addCleanup(item.stop)
        item = patch.object(provider, 'inspect_payload', return_value={'scope': 'host protocol model NOT payload evidence'})
        item.start(); self.addCleanup(item.stop)
        self.change = None

    def mocked_command(self, argv, label, commands):
        # Protocol/output-shape model only. Root separately executes real Java/CMS.
        commands.append({'label': label, 'argv': list(map(str, argv)), 'scope': 'host mock NOT crypto evidence'})
        if label == 'verify-app':
            Path(argv[argv.index('-outCertChain') + 1]).write_bytes(self.public['canonical-app-chain.cer'].data)
            Path(argv[argv.index('-outProfile') + 1]).write_bytes(self.public['canonical-profile.p7b'].data)
            text = self.public['canonical-verify-app.stdout'].data.decode()
            if self.change == 'leaf': text = text.replace('8E:93:86:3F', '00:00:00:00')
            if self.change and self.change.startswith('marker:'): text = text.replace(self.change[7:], 'missing-check')
            return text, ''
        original = label.startswith('original')
        value = provider.load(self.public['original-profile.json' if original else 'canonical-profile.json'].data)
        if label.endswith('verify-profile'):
            report = {'verifiedPassed': True, 'message': 'OK', 'content': value}
            if self.change == 'jar-report': report['verifiedPassed'] = False
            Path(argv[argv.index('-outFile') + 1]).write_text(json.dumps(report))
            return 'verify-profile success', ''
        self.assertIn('-nointern', argv); self.assertIn('-noverify', argv)
        self.assertEqual('profile-release-leaf.pem', Path(argv[argv.index('-certfile') + 1]).name)
        if self.change == 'cms-policy': value['bundle-info']['apl'] = 'system_core'
        if self.change == 'cms-original' and original: value['validity']['not-after'] += 1
        Path(argv[argv.index('-out') + 1]).write_text(json.dumps(value))
        return '', 'CMS Verification successful'

    def verify(self):
        with patch.object(provider, 'command', side_effect=self.mocked_command):
            return provider.verify_signature(b'host HAP model', self.jar, self.public)

    def test_actual_public_fixture_policy_and_five_verification_protocols(self):
        proof = self.verify()
        self.assertEqual(5, len(proof['commands']))
        self.assertEqual({'not-before': 1594865258, 'not-after': 1689473258}, proof['legacy_validity_preserved_NOT_runtime_acceptance'])
        policy = provider.load(self.public['canonical-profile.json'].data)
        self.assertEqual('normal', policy['bundle-info']['apl'])
        self.assertNotIn('AllowAppUsePrivilegeExtension', policy['app-privilege-capabilities'])

    def test_missing_marker_wrong_leaf_jar_report_or_either_CMS_content_rejected(self):
        for change in ('leaf', 'jar-report', 'cms-policy', 'cms-original',
                       *('marker:' + value for value in ('verify codesign success', 'Digest verify result: true',
                                                        'verify permission sign success', 'verify-app success'))):
            self.change = change
            with self.subTest(change=change), self.assertRaises(ValueError): self.verify()

    def test_fixture_change_is_rejected_even_when_its_json_is_valid(self):
        copied = self.root / 'public'; copied.mkdir()
        for name, row in self.public.items(): (copied / name).write_bytes(row.data)
        original = provider.load((copied / 'original-profile.json').read_bytes())
        original['validity']['not-after'] += 1
        (copied / 'original-profile.json').write_text(json.dumps(original))
        with patch.object(provider, 'PUBLIC', copied), self.assertRaisesRegex(ValueError, 'fixed PrivacyCenter public fixture'):
            provider.fixtures()

    def test_nonzero_command_and_timeout_keep_raw_failure_evidence(self):
        commands = []
        completed = subprocess.CompletedProcess(['host-only'], 1, b'verify-app success\n', b'real failure model')
        with patch.object(provider.subprocess, 'run', return_value=completed), self.assertRaises(ValueError):
            provider.command(['host-only-NOT-executed'], 'host-command', commands)
        self.assertEqual(1, commands[0]['exit_code'])
        self.assertEqual('real failure model', commands[0]['stderr'])
        error = subprocess.TimeoutExpired(['host-only'], 60, output=b'partial', stderr=b'timed out')
        with patch.object(provider.subprocess, 'run', side_effect=error), self.assertRaises(subprocess.TimeoutExpired):
            provider.command(['host-only-NOT-executed'], 'host-timeout', commands)
        self.assertTrue(commands[1]['timed_out'])
        self.assertEqual('partial', commands[1]['stdout'])


class PayloadAndImage(unittest.TestCase):
    def payload(self, files, *, duplicate=False, symlink=False):
        data = io.BytesIO()
        with zipfile.ZipFile(data, 'w') as archive:
            for name, body in files.items():
                if symlink and name == 'resources.index':
                    entry = zipfile.ZipInfo(name); entry.external_attr = (stat.S_IFLNK | 0o644) << 16
                    archive.writestr(entry, body)
                else: archive.writestr(name, body)
            if duplicate: archive.writestr('resources.index', b'extra')
        value = data.getvalue(); inventory = {n: {'bytes': len(b), 'sha256': provider.digest(b)} for n, b in files.items()}
        with patch.object(provider, 'CANONICAL_SHA', provider.digest(value)), patch.object(provider, 'HAP_BYTES', len(value)):
            return provider.inspect_payload(value, inventory)

    def test_inventory_code_bytes_unsafe_members_and_compiled_identity(self):
        files = {'module.json': json.dumps({'app': {'bundleName': provider.BUNDLE},
            'module': {'name': 'entry', 'deviceTypes': ['default', '2in1']}}).encode(),
            'ets/modules.abc': b'host ABC model', 'resources.index': b'host resources model'}
        self.assertTrue(self.payload(files)['payload_unchanged'])
        for duplicate, symlink in ((True, False), (False, True)):
            with self.subTest(duplicate=duplicate, symlink=symlink), self.assertRaises(ValueError):
                self.payload(files, duplicate=duplicate, symlink=symlink)
        for name in ('../outside', '/absolute', 'a//b', 'a/./b', 'a\\b'):
            with self.subTest(name=name), self.assertRaises(ValueError): self.payload(dict(files, **{name: b'unsafe'}))
        bad = copy.deepcopy(files); bad['module.json'] = bad['module.json'].replace(provider.BUNDLE.encode(), b'foreign')
        with self.assertRaises(ValueError): self.payload(bad)

    def test_changed_abc_or_added_member_cannot_borrow_original_inventory(self):
        original = {'module.json': b'{}', 'ets/modules.abc': b'original ABC', 'resources.index': b'original resource'}
        inventory = {n: {'bytes': len(b), 'sha256': provider.digest(b)} for n, b in original.items()}
        for mode in ('changed-abc', 'added-member'):
            files = dict(original)
            if mode == 'changed-abc': files['ets/modules.abc'] = b'changed! ABC'
            else: files['unexpected'] = b'new'
            stream = io.BytesIO()
            with zipfile.ZipFile(stream, 'w') as archive:
                for name, body in files.items(): archive.writestr(name, body)
            data = stream.getvalue()
            with patch.object(provider, 'CANONICAL_SHA', provider.digest(data)), patch.object(provider, 'HAP_BYTES', len(data)), \
                    self.subTest(mode=mode), self.assertRaises(ValueError):
                provider.inspect_payload(data, inventory)

    @staticmethod
    def stat_text(inode=123, kind='regular', size=3):
        return f'Inode: {inode}   Type: {kind}    Mode:  0644   Flags: 0x0\nUser: 0   Group: 0   Project: 0   Size: {size}\nLinks: 1   Blockcount: 8\n'

    def test_debugfs_exit0_does_not_prove_absence_or_regular_file(self):
        path = '/system/app/provider.hap'
        self.assertIsNone(image.parse_stat('', 'debugfs 1.47.4\n' + path + ': File not found by ext2_lookup \n', path))
        self.assertEqual(123, image.parse_stat(self.stat_text(), 'debugfs 1.47.4\n', path)['inode'])
        for out, err in (('', ''), (self.stat_text(kind='symlink'), ''),
                         (self.stat_text() + self.stat_text(), ''),
                         (self.stat_text() + 'Inode: malformed later record\n', ''),
                         (self.stat_text(), 'debugfs 1.47.4\nI/O error'),
                         (self.stat_text().replace('Links: 1', 'Links: 2'), '')):
            with self.subTest(out=out, err=err), self.assertRaises(ValueError): image.parse_stat(out, err, path)

    def test_two_paths_require_actual_same_inode_bytes_and_safe_alias(self):
        candidates = ('/app/provider.hap', '/system/app/provider.hap')
        for mode in ('same', 'one-absent', 'different-inode', 'different-bytes', 'symlink', 'both-absent'):
            with tempfile.TemporaryDirectory() as temp:
                def command(argv, label, commands):
                    request = argv[2]; index = 0 if candidates[0] in request.split() else 1
                    if request.startswith('stat '):
                        if mode == 'both-absent' or mode == 'one-absent' and index == 0:
                            return '', 'debugfs 1.47.4\n' + candidates[index] + ': File not found by ext2_lookup\n'
                        return self.stat_text(inode=124 if mode == 'different-inode' and index else 123,
                                              kind='symlink' if mode == 'symlink' and index else 'regular'), 'debugfs 1.47.4\n'
                    Path(request.split()[-1]).write_bytes(b'bad' if mode == 'different-bytes' and index else b'abc')
                    return '', 'debugfs 1.47.4\n'
                with patch.object(provider, 'command', side_effect=command):
                    if mode in ('same', 'one-absent'):
                        _, value = image.dump_unique_file(Path('host-image'), candidates, Path(temp).resolve(), 'host-debugfs', [])
                        self.assertEqual(123, value['stat']['inode'])
                        self.assertEqual(2 if mode == 'same' else 1, len(value['image_path_aliases']))
                    else:
                        with self.subTest(mode=mode), self.assertRaises(ValueError):
                            image.dump_unique_file(Path('host-image'), candidates, Path(temp).resolve(), 'host-debugfs', [])


if __name__ == '__main__': unittest.main()
