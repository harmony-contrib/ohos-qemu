"""Chooser candidate host checks. No SDK/native ABI or packaged guest claim."""
import base64
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
COMP = ROOT / 'patches/common/applications/standard/settings/share_picker_choose'
META = json.loads((COMP / 'tests/predecessor.json').read_text())
JSON5 = os.environ.get('BATCH_APPS_JSON5_MODULE',
    '/Volumes/PSSD/qemu/openharmony/prebuilts/tool/command-line-tools/6.x/hvigor/hvigor-ohos-plugin/node_modules/json5')
SPEC = importlib.util.spec_from_file_location('choose_candidate_installer', COMP / 'apply.py')
INSTALL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INSTALL)


def fixture(root):
    for name, row in META['files'].items():
        data = gzip.decompress(base64.b64decode(row['gzip_base64']))
        if hashlib.sha256(data).hexdigest() != row['sha256']:
            raise ValueError('invalid retained actual-source fixture')
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)


def block(source, signature):
    start = source.index(signature)
    begin = source.index('{', start)
    count = 1
    end = begin + 1
    while count:
        count += (source[end] == '{') - (source[end] == '}')
        end += 1
    return source[start:end]


class ChooseSourceTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='share-choose-host-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        fixture(self.root)
        self.value = INSTALL.manifest()

    def apply(self):
        # Transaction fixtures retain all real source bytes and hashes. The
        # project HEAD values are tested separately below; these exported source
        # copies are not forged Git repositories or a product build.
        with mock.patch.object(INSTALL, 'revisions'):
            return INSTALL.apply(self.root)

    def snapshot(self):
        return {p.relative_to(self.root).as_posix(): (p.read_bytes(), p.stat().st_mode & 0o777)
                for p in self.root.rglob('*') if p.is_file() and '.ohos-qemu-patches' not in p.parts}

    def test_manifest_checks_all_targets_from_nested_repository_directory(self):
        previous = Path.cwd()
        try:
            os.chdir(ROOT / 'ci')
            self.assertEqual(set(INSTALL.manifest()['files']), INSTALL.TARGETS)
        finally:
            os.chdir(previous)

    def test_complete_two_project_apply_and_replay_twice(self):
        self.assertEqual(INSTALL.state(self.root, self.value, False), 'before')
        self.assertEqual(self.apply()['status'], 'applied')
        self.assertEqual(INSTALL.state(self.root, self.value, False), 'after')
        after = self.snapshot()
        for _ in range(2):
            self.assertEqual(self.apply()['status'], 'already_applied')
            self.assertEqual(self.snapshot(), after)
        self.assertEqual(set(self.value['files']), INSTALL.TARGETS)
        self.assertEqual(len(self.value['files']), 9)

    def test_unknown_each_target_never_mutates_other_source(self):
        self.apply()
        for name in self.value['files']:
            path = self.root / name
            original = path.read_bytes()
            path.write_bytes(original + b'// unknown edit\n')
            before = self.snapshot()
            with self.assertRaisesRegex(ValueError, 'unknown source'):
                self.apply()
            self.assertEqual(self.snapshot(), before)
            path.write_bytes(original)

    def test_all_predecessor_dependencies_are_required(self):
        self.assertEqual(set(self.value['dependencies']), INSTALL.DEPENDENCIES)
        for name in self.value['dependencies']:
            path = self.root / name
            original = path.read_bytes()
            path.write_bytes(original + b'unknown')
            before = self.snapshot()
            with self.assertRaisesRegex(ValueError, 'predecessor dependency'):
                self.apply()
            self.assertEqual(self.snapshot(), before)
            path.write_bytes(original)

    def test_partial_native_settings_and_missing_payload_rejected(self):
        self.apply()
        for name, row in self.value['files'].items():
            path = self.root / name
            after = path.read_bytes()
            if row['before'] is None:
                path.unlink()
            else:
                path.write_bytes(gzip.decompress(base64.b64decode(META['files'][name]['gzip_base64'])))
            before = self.snapshot()
            with self.assertRaisesRegex(ValueError, 'mixed'):
                self.apply()
            self.assertEqual(self.snapshot(), before)
            path.write_bytes(after)

    def test_source_file_and_project_symlinks_refused(self):
        name = next(iter(self.value['files']))
        path = self.root / name
        data = path.read_bytes()
        outside = self.root / 'external-source'
        outside.write_bytes(data)
        path.unlink()
        path.symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.apply()
        self.assertEqual(outside.read_bytes(), data)
        path.unlink()
        path.write_bytes(data)
        project = self.root / 'applications/standard/settings'
        actual = self.root / 'actual-project'
        project.rename(actual)
        project.symlink_to(actual, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.apply()

    def test_root_and_lock_symlinks_refused(self):
        alias = self.root / 'root-alias'
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'root symlink'):
            INSTALL.apply(alias)
        alias.unlink()
        marker = self.root / '.ohos-qemu-patches'
        marker.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'lock directory'):
            self.apply()

    def test_failure_mid_install_restores_all_bytes_modes_and_absent_new_files(self):
        before = self.snapshot()
        original_write = INSTALL.atomic_write
        calls = 0

        def fail_once(*args):
            nonlocal calls
            calls += 1
            if calls == 5:
                raise OSError('injected publication failure')
            return original_write(*args)

        with mock.patch.object(INSTALL, 'atomic_write', side_effect=fail_once):
            with self.assertRaisesRegex(OSError, 'publication failure'):
                self.apply()
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(INSTALL.state(self.root, self.value, False), 'before')

    def test_failed_rollback_keeps_recoverable_original_bytes(self):
        original_write = INSTALL.atomic_write
        calls = 0

        def fail_after_first(*args):
            nonlocal calls
            calls += 1
            if calls > 1:
                raise OSError('persistent filesystem failure')
            return original_write(*args)

        with mock.patch.object(INSTALL, 'atomic_write', side_effect=fail_after_first):
            with self.assertRaisesRegex(RuntimeError, 'rollback incomplete') as raised:
                self.apply()
        directory = Path(str(raised.exception).split('retained at ', 1)[1].split(';', 1)[0])
        self.addCleanup(shutil.rmtree, directory)
        recovery = json.loads((directory / 'original.json').read_text())
        for name, row in recovery.items():
            if row['existed']:
                self.assertEqual(hashlib.sha256((directory / name).read_bytes()).hexdigest(), row['sha256'])
        with self.assertRaisesRegex(ValueError, 'mixed'):
            INSTALL.state(self.root, self.value, False)

    def test_missing_git_wrong_revision_and_parent_git_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Git metadata'):
            INSTALL.revisions(self.root, self.value)
        for name in INSTALL.PROJECTS:
            (self.root / name / '.git').mkdir()
        valid = []
        for name, revision in INSTALL.PROJECTS.items():
            valid.extend([revision, str(self.root / name)])
        with mock.patch.object(INSTALL.subprocess, 'check_output', side_effect=valid):
            INSTALL.revisions(self.root, self.value)
        for bad in [['0' * 40, str(self.root)], [valid[0], str(self.root)]]:
            with mock.patch.object(INSTALL.subprocess, 'check_output', side_effect=bad):
                with self.assertRaisesRegex(ValueError, 'revision/toplevel'):
                    INSTALL.revisions(self.root, self.value)

    def test_unknown_component_payload_or_patch_is_rejected(self):
        for relative in ['files/ChoosePickerController.ets', '0002-authenticate-native-select-dialog-session.patch']:
            with tempfile.TemporaryDirectory(prefix='share-choose-component-') as temporary:
                copied = Path(temporary) / 'component'
                shutil.copytree(COMP, copied)
                path = copied / relative
                path.write_bytes(path.read_bytes() + b'// drift\n')
                with mock.patch.object(INSTALL, 'COMPONENT', copied):
                    with self.assertRaisesRegex(ValueError, 'unknown'):
                        INSTALL.manifest()

    def test_manifest_cannot_omit_a_required_predecessor(self):
        with tempfile.TemporaryDirectory(prefix='share-choose-component-') as temporary:
            copied = Path(temporary) / 'component'
            shutil.copytree(COMP, copied)
            value = json.loads((copied / 'manifest.json').read_text())
            value['dependencies'].pop(next(iter(value['dependencies'])))
            (copied / 'manifest.json').write_text(json.dumps(value))
            with mock.patch.object(INSTALL, 'COMPONENT', copied):
                with self.assertRaisesRegex(ValueError, 'complete exact predecessor'):
                    INSTALL.manifest()

    def json5(self, data):
        result = subprocess.run(['node', '-e', 'process.stdout.write(JSON.stringify(require(process.argv[1]).parse(require("fs").readFileSync(0,"utf8"))))', JSON5],
                                input=data, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_private_standard_ability_preserves_entire_existing_module_and_pages(self):
        name = 'applications/standard/settings/product/phone/src/main/module.json5'
        pages = 'applications/standard/settings/product/phone/src/main/resources/base/profile/main_pages.json'
        before = self.json5((self.root / name).read_text())
        old_pages = json.loads((self.root / pages).read_text())
        self.apply()
        after = self.json5((self.root / name).read_text())
        added = after['module']['abilities'].pop()
        self.assertEqual(added['name'], 'PickerDialog')
        self.assertEqual(added['launchType'], 'standard')
        self.assertIs(added['exported'], False)
        self.assertTrue(added['removeMissionAfterTerminate'])
        self.assertNotIn('skills', added)
        self.assertEqual(after, before)  # all existing permissions/abilities/extension contract
        expected = dict(old_pages)
        expected['src'] = [*old_pages['src'], 'pages/ChoosePicker']
        self.assertEqual(json.loads((self.root / pages).read_text()), expected)

    def test_official_sdk_imports_and_source_uses_no_fake_result_or_settings_grant(self):
        sdk = Path(os.environ.get('BATCH_APPS_SDK_API', '/Volumes/PSSD/qemu/validation/first-20261005/provider-sdk-26-full/26.0.0/ets/api'))
        for p in (COMP / 'files').glob('*.ets'):
            for name in re.findall(r"from '(@ohos[^']+)'", p.read_text()):
                self.assertTrue((sdk / (name + '.d.ts')).is_file(), name)
        controller = (COMP / 'files/ChoosePickerController.ets').read_text()
        for forbidden in ['.startAbility(', '.startAbilityAsCaller(', '.terminateSelfWithResult(', '.grantUriPermission(', 'AppStorage.']:
            self.assertNotIn(forbidden, controller)
        self.assertIn('dialogSession.sendDialogResult', controller)
        self.assertIn('await this.context.terminateSelf()', controller)

    def test_actual_controller_boundaries(self):
        for case in ['invalid_session', 'opaque_payload', 'enumeration', 'label_failure', 'empty', 'get_failure',
                     'owner_denied', 'unknown_target', 'stale_target', 'sync_start_error', 'async_start_error', 'cancel_loading',
                     'destroy_loading', 'duplicate', 'destroy_start', 'close_retry', 'cancel_after_accept',
                     'cancel_close_retry', 'cancel_error', 'cancel_both_errors', 'isolation', 'destroy_then_cancel']:
            with self.subTest(case=case):
                result = subprocess.run(['node', '--unhandled-rejections=strict', str(COMP / 'tests/controller.cjs'),
                                         str(COMP / 'files/ChoosePickerController.ets'), case], capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('PASS ' + case, result.stdout)

    def test_actual_ability_instances_page_failure_back_and_late_load(self):
        for case in ['invalid', 'load_error', 'destroy_loading', 'isolated', 'ordinary']:
            with self.subTest(case=case):
                result = subprocess.run(['node', '--unhandled-rejections=strict', str(COMP / 'tests/ability.cjs'),
                                         str(COMP / 'files/ChoosePickerAbility.ets'), case], capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertIn('PASS ' + case, result.stdout)

    def test_actual_native_owner_predicate_rejects_known_id_wrong_identity_and_expiry(self):
        self.apply()
        source = (self.root / INSTALL.NATIVE / 'services/abilitymgr/src/dialog_session/dialog_session_manager.cpp').read_text()
        actual = block(source, 'bool DialogSessionManager::IsLegacyPickerOwner(')
        expression = actual[actual.index('return ') + 7:actual.index(';')]
        expression = expression.replace('IPCSkeleton::GetCallingUid()', 'uid').replace('IPCSkeleton::GetCallingTokenID()', 'token')
        expression = expression.replace('IPCSkeleton::GetCallingPid()', 'pid').replace('std::chrono::steady_clock::now()', 'now')
        # This executes the extracted simple predicate with unchanged operators;
        # it does not pretend to execute the surrounding native IPC/locking ABI.
        script = 'const assert=require("node:assert/strict");const check=(owner,attached,uid,token,pid,now)=>(' + expression + ');'
        script += '''const o={uid:20010001,tokenId:77,pid:123,committed:false,expiresAt:100};
        assert.equal(check(o,true,20010001,77,123,99),true);
        for(const args of [[20010002,77,123,99],[20010001,78,123,99],[20010001,77,124,99],[20010001,77,0,99],[20010001,77,123,100],[20010001,77,123,101]])assert.equal(check(o,true,...args),false);
        assert.equal(check({...o,tokenId:0},true,20010001,0,123,99),false);
        assert.equal(check({...o,pid:-1},true,20010001,77,123,99),false);
        assert.equal(check({...o,pid:-1},false,20010001,77,123,99),true);
        assert.equal(check({...o,committed:true},true,20010001,77,123,101),true);
        assert.equal(check({...o,committed:true},true,20010002,77,123,101),false);'''
        result = subprocess.run(['node', '-e', script], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_native_attachment_is_verified_before_ui_and_cleanup_uses_owned_token(self):
        self.apply()
        native = self.root / INSTALL.NATIVE / 'services/abilitymgr'
        ams = (native / 'src/ability_manager_service.cpp').read_text()
        manager = (native / 'src/dialog_session/dialog_session_manager.cpp').read_text()
        attach = block(ams, 'int AbilityManagerService::AttachAbilityThread(')
        self.assertLess(attach.index('JudgeSelfCalled(abilityRecord)'), attach.index('AttachLegacyPickerAbility'))
        self.assertLess(attach.index('AttachLegacyPickerAbility'), attach.index('ret = manager->AttachAbilityThread'))
        binding = block(manager, 'bool DialogSessionManager::AttachLegacyPickerAbility(')
        for token in ['!IsLegacyPickerOwner(*found->second, false)', 'record->GetApplicationInfo().uid',
                      'record->GetApplicationInfo().accessTokenId', 'caller->second->callerToken',
                      'found->second->dialogToken.GetRefPtr() != record->GetToken().GetRefPtr()',
                      'found->second->pid = IPCSkeleton::GetCallingPid()',
                      'found->second->dialogToken = record->GetToken()']:
            self.assertIn(token, binding)
        getter = block(manager, 'sptr<DialogSessionInfo> DialogSessionManager::GetLegacyPickerInfo(')
        self.assertIn('!IsLegacyPickerOwner(*owner->second, true)', getter)
        self.assertIn('owner->second->dialogToken == nullptr', getter)
        self.assertIn('dialog->GetWant().GetStringParam(DIALOG_SESSION_ID) != id', getter)
        self.assertNotIn('pid = IPCSkeleton', getter)
        closer = block(ams, 'void AbilityManagerService::CloseLegacyPickerDialog(')
        for token in ['Token::GetAbilityRecordByToken(token)', 'record->GetWant().GetStringParam(DIALOG_SESSION_ID) != id',
                      '!record->GetApplicationInfo().isSystemApp', 'SHARE_PICKER_DIALOG_BUNDLE_NAME_KEY',
                      'SHARE_PICKER_DIALOG_ABILITY_NAME_KEY', 'missions->TerminateAbility(record,',
                      'std::static_pointer_cast<UIAbilityRecord>(record)']:
            self.assertIn(token, closer)
        for forbidden in ['ResetCallingIdentity', 'KillProcess', 'ForceExit', 'StartAbility(']:
            self.assertNotIn(forbidden, closer)
        release = block(manager, 'void DialogSessionManager::ReleaseLegacyPickerOwner(')
        self.assertIn('CloseLegacyPickerDialog(owner->sessionId, owner->dialogToken)', release)
        create = block(manager, 'std::string DialogSessionManager::CreateLegacyPickerSession(')
        self.assertGreaterEqual(create.count('RemoveDeathRecipient(owner->callerDeath)'), 2)
        clear = block(manager, 'void DialogSessionManager::ClearDialogContext(')
        self.assertLess(clear.index('legacyPickerOwners_.erase'), clear.index('ReleaseLegacyPickerOwner(released)'))

    def installed_predecessor(self):
        # Reconstruct only the pinned old source bytes in this owned scratch.
        # It is a host source fixture, never an installed/product receipt.
        self.apply()
        name = INSTALL.TOKEN_COMPARISON_SOURCE
        path = self.root / name
        source = path.read_text()
        for left, operator in [('found->second->dialogToken', '!='),
                               ('caller->second->callerToken', '=='),
                               ('item.second->dialogToken', '==')]:
            after = left + '.GetRefPtr() ' + operator + ' record->GetToken().GetRefPtr()'
            before = left + ' ' + operator + ' record->GetToken()'
            self.assertEqual(source.count(after), 1)
            source = source.replace(after, before)
        path.write_text(source)
        for target, expected in self.value['installed_predecessor']['files'].items():
            self.assertEqual(hashlib.sha256((self.root / target).read_bytes()).hexdigest(), expected)
        self.assertEqual(INSTALL.state(self.root, self.value, False), 'installed_predecessor')
        return path

    def test_exact_installed_predecessor_upgrades_only_native_token_file_and_replays(self):
        path = self.installed_predecessor()
        others = {name: (INSTALL.capture(self.root, name)) for name in
                  [*self.value['files'], *self.value['dependencies']] if name != INSTALL.TOKEN_COMPARISON_SOURCE}
        self.assertEqual(self.apply()['status'], 'applied')
        INSTALL.unchanged(self.root, others)
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(),
                         self.value['files'][INSTALL.TOKEN_COMPARISON_SOURCE]['after'])
        self.assertEqual(self.apply()['status'], 'already_applied')

    def test_installed_predecessor_partial_token_fix_and_dependency_drift_rejected(self):
        path = self.installed_predecessor()
        original = path.read_bytes()
        path.write_bytes(original.replace(b'caller->second->callerToken == record->GetToken()',
            b'caller->second->callerToken.GetRefPtr() == record->GetToken().GetRefPtr()'))
        partial = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'unknown source bytes'):
            self.apply()
        self.assertEqual(self.snapshot(), partial)
        path.write_bytes(original)
        dependency = self.root / next(iter(self.value['dependencies']))
        dependency.write_bytes(dependency.read_bytes() + b'// external dependency edit\n')
        drift = self.snapshot()
        with self.assertRaisesRegex(ValueError, 'predecessor dependency'):
            self.apply()
        self.assertEqual(self.snapshot(), drift)

    def test_installed_predecessor_post_publication_failure_restores_bytes_and_modes(self):
        self.installed_predecessor()
        before = self.snapshot()
        state = INSTALL.state
        injected = False

        def fail_once(root, value, check_revisions=True):
            nonlocal injected
            result = state(root, value, check_revisions)
            if Path(root) == self.root and result == 'after' and not injected:
                injected = True
                raise OSError('injected upgrade post-publication failure')
            return result

        with mock.patch.object(INSTALL, 'state', side_effect=fail_once):
            with self.assertRaisesRegex(OSError, 'upgrade post-publication'):
                self.apply()
        self.assertTrue(injected)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(INSTALL.state(self.root, self.value, False), 'installed_predecessor')

    def test_installed_predecessor_prepublication_chmod_preserved_without_revert(self):
        path = self.installed_predecessor()
        original = path.read_bytes()
        unchanged = INSTALL.unchanged
        calls = 0
        mode = (path.stat().st_mode & 0o777) ^ 0o100

        def mutate_once(root, expected):
            nonlocal calls
            calls += 1
            if calls == 2:
                path.chmod(mode)
            return unchanged(root, expected)

        with mock.patch.object(INSTALL, 'unchanged', side_effect=mutate_once):
            with self.assertRaisesRegex(ValueError, 'changed during transaction'):
                self.apply()
        self.assertEqual(path.read_bytes(), original)
        self.assertEqual(path.stat().st_mode & 0o777, mode)

    def test_native_cross_type_tokens_compare_only_unwrapped_references(self):
        self.apply()
        manager = (self.root / INSTALL.NATIVE /
                   'services/abilitymgr/src/dialog_session/dialog_session_manager.cpp').read_text()
        binding = block(manager, 'bool DialogSessionManager::AttachLegacyPickerAbility(')
        exited = block(manager, 'void DialogSessionManager::OnLegacyPickerAbilityExit(')
        comparisons = [
            (binding, 'found->second->dialogToken', '!='),
            (exited, 'caller->second->callerToken', '=='),
            (exited, 'item.second->dialogToken', '=='),
        ]
        for body, left, operator in comparisons:
            # Both GetRefPtr calls use the held sptr values. The temporary
            # GetToken() strong reference lasts through the full comparison.
            expected = left + '.GetRefPtr() ' + operator + ' record->GetToken().GetRefPtr()'
            self.assertEqual(body.count(expected), 1)
            self.assertNotIn(left + ' ' + operator + ' record->GetToken()', body)
        self.assertIn('std::lock_guard<ffrt::mutex> guard(dialogSessionRecordLock_);', binding)
        self.assertIn('std::lock_guard<ffrt::mutex> guard(dialogSessionRecordLock_);', exited)
        self.assertIn('found->second->dialogToken = record->GetToken();', binding)
        self.assertIn('CancelLegacyPickerSession(item.first, item.second);', exited)

    def test_native_source_contract_uses_real_request_caller_and_opaque_payload(self):
        self.apply()
        native = self.root / INSTALL.NATIVE / 'services/abilitymgr'
        ams = (native / 'src/ability_manager_service.cpp').read_text()
        manager = (native / 'src/dialog_session/dialog_session_manager.cpp').read_text()
        self.assertIn('constexpr const char* ACTION_CHOOSE = "ohos.want.action.select"', ams)
        self.assertEqual(ams.count('ShowPickerDialog(want, validUserId, callerToken, requestCode)'), 2)
        self.assertIn('ShowPickerDialog(param.want, validUserId, param.callerToken, param.requestCode)', ams)
        choose = block(ams, 'int32_t AbilityManagerService::ShowPickerDialog(')
        for token in ['VerificationAllToken(callerToken)', '!IsAppSelfCalled(caller)', 'request.want = want;', 'request.want.SetAction("")',
                      'request.want.RemoveParam(TOKEN_KEY)', 'request.want.RemoveParam(DIALOG_SESSION_ID)',
                      'request.callerToken = callerToken;', 'request.requestCode = requestCode;',
                      'request.callerAccessTokenId = caller->GetApplicationInfo().accessTokenId',
                      'UpdateCallerInfoFromToken(request.want, callerToken)', 'dialog.SetParam(DIALOG_SESSION_ID, id)',
                      'CancelLegacyPickerSession(id, false)']:
            self.assertIn(token, choose)
        self.assertLess(choose.index('!IsAppSelfCalled(caller)'), choose.index('IN_PROCESS_CALL'))
        self.assertIn('StartAbility(dialog, userId, DEFAULT_INVAL_VALUE)', choose)
        self.assertNotIn('StartAbility(dialog, DEFAULT_INVAL_VALUE, userId)', choose)
        header = (native / 'include/ability_manager_service.h').read_text()
        self.assertIn('const Want &want, int32_t userId = DEFAULT_INVAL_VALUE, int requestCode = DEFAULT_INVAL_VALUE,', header)
        for token in ['dialog.SetUri(', 'dialog.SetFlags(', 'dialog.SetParams(', 'dialog.SetParam(TOKEN_KEY']:
            self.assertNotIn(token, choose)
        caller = block(manager, 'std::shared_ptr<DialogCallerInfo> DialogSessionManager::GetDialogCallerInfo(')
        self.assertIn('!IsLegacyPickerOwner(*owner->second, true)', caller)
        self.assertIn('!owner->second->committed', caller)
        send = block(manager, 'int DialogSessionManager::SendLegacyPickerResult(')
        self.assertLess(send.index('IsLegacyPickerOwner'), send.index('owner->busy = true'))
        self.assertIn('std::none_of(snapshot->second->targetAbilityInfos.begin()', send)
        self.assertIn('Want query = caller->targetWant;\n    query.SetParams(WantParams());', send)
        self.assertLess(send.index('QueryAbilityInfos(query,'), send.index('owner->committed = true'))
        self.assertLess(send.index('owner->committed = true'), send.index('SendDialogResultCommon(selected'))
        self.assertIn('Want selected;\n    selected.SetElement(element);', send)
        self.assertNotIn('selected.SetParams', send)
        common = block(manager, 'int DialogSessionManager::SendDialogResultCommon(')
        self.assertIn('auto targetWant = dialogCallerInfo->targetWant;', common)
        self.assertIn('StartAbilityAsCallerDetails(targetWant, callerToken, callerToken', common)
        self.assertIn('dialogCallerInfo->requestCode', common)
        self.assertIn('dialogCallerInfo->callerAccessTokenId', common)
        cancel = block(manager, 'void DialogSessionManager::CancelLegacyPickerSession(')
        self.assertIn('caller->requestCode != -1', cancel)
        self.assertIn('SendResultByBackToCaller(std::make_shared<AbilityResult>(caller->requestCode, -1, result))', cancel)
        self.assertNotIn('SetResult(', cancel)
        self.assertIn('std::chrono::minutes(10)', manager)
        self.assertIn('legacyPickerOwners_.size() >= 64', manager)
        self.assertEqual(ams.count('OnLegacyPickerAbilityExit(abilityRecord)'), 4)
        create = block(manager, 'std::string DialogSessionManager::CreateLegacyPickerSession(')
        self.assertIn('caller->GetScheduler()', create)
        self.assertIn('!owner->callerScheduler->AddDeathRecipient(owner->callerDeath)', create)
        self.assertIn('current != legacyPickerOwners_.end() && !caller->IsTerminating()', create)
        release = block(manager, 'void DialogSessionManager::ReleaseLegacyPickerOwner(')
        self.assertIn('owner->callerScheduler->RemoveDeathRecipient(owner->callerDeath)', release)
        self.assertIn('owner->timeout.Cancel()', release)


if __name__ == '__main__':
    unittest.main()
