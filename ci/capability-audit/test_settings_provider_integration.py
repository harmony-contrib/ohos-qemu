"""Certificate-bound Settings privilege and graph tests, not guest acceptance."""
import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
HAP = ROOT / 'patches/common/applications/standard/hap/settings_provider'
POLICY = ROOT / 'patches/common/vendor/ohemu/virt/settings_provider'


def load(path):
    spec = importlib.util.spec_from_file_location('settings_guard_' + path.parent.name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


graph_guard = load(HAP / 'prepare.py')
policy_guard = load(POLICY / 'prepare.py')


class SettingsProviderIntegration(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='settings-provider-policy-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.graph = self.root / 'applications/standard/hap/BUILD.gn'
        self.graph.parent.mkdir(parents=True)
        self.graph.write_text('\n' + graph_guard.BLOCK + '\nohos_prebuilt_etc("note_hap") {\n}\n' +
            '\n'.join('group("group' + str(i) + '") {\n  deps = [\n' +
            '    "//applications/standard/hap:settings_faceauth_hap",\n' +
            '    "//applications/standard/hap:settings_hap",\n' +
            '    "//applications/standard/hap:statusBar_hap",\n  ]\n}' for i in range(2)) +
            '\n# unrelated source = "Launcher_Settings.hap"\n')
        self.cap = self.root / 'vendor/ohemu/virt/preinstall-config/install_list_capability.json'
        self.cap.parent.mkdir(parents=True)
        self.grant = self.cap.with_name('install_list_permissions.json')
        self.caps = {'install_list': [
            {'bundleName': 'com.ohos.mms', 'app_signature': ['untouched'], 'allowCommonEvent': ['sms']},
            {'bundleName': 'com.ohos.settingsdata', 'app_signature': ['untouched']}]}
        self.grants = [{'bundleName': policy_guard.BUNDLE, 'app_signature': [policy_guard.OLD],
                        'permissions': copy.deepcopy(policy_guard.GRANTS)},
                       {'bundleName': 'other', 'permissions': []}]
        self.cap.write_text(json.dumps(self.caps))
        self.grant.write_text(json.dumps(self.grants))

    def apply(self, component):
        return subprocess.run(['bash', str(component / 'apply.sh'), '--source-root', str(self.root)],
                              capture_output=True, text=True)

    def snapshot(self):
        return self.cap.read_bytes(), self.grant.read_bytes()

    def test_graph_removes_only_old_settings_and_is_idempotent(self):
        for _ in range(2):
            result = self.apply(HAP)
            self.assertEqual(result.returncode, 0, result.stderr)
        text = self.graph.read_text()
        self.assertNotIn('"settings_hap"', text)
        self.assertNotIn(':settings_hap"', text)
        self.assertIn('Launcher_Settings.hap', text)
        self.assertEqual(text.count(':settings_faceauth_hap"'), 2)

    def test_unknown_or_partial_graph_preserved(self):
        original = self.graph.read_text()
        for text in (original.replace('app/com.ohos.settings', 'app/edited'),
                     original.replace(graph_guard.ABSOLUTE, '"changed"', 1)):
            self.graph.write_text(text)
            self.assertNotEqual(self.apply(HAP).returncode, 0)
            self.assertEqual(self.graph.read_text(), text)

    def test_exact_authorized_privilege_and_existing_grants_only(self):
        for _ in range(2):
            result = self.apply(POLICY)
            self.assertEqual(result.returncode, 0, result.stderr)
        expected = copy.deepcopy(self.caps)
        expected['install_list'].insert(1, policy_guard.CAPABILITY)
        self.assertEqual(json.loads(self.cap.read_text()), expected)
        grants = copy.deepcopy(self.grants)
        grants[0]['app_signature'] = [policy_guard.NEW]
        self.assertEqual(json.loads(self.grant.read_text()), grants)

    def test_changed_grants_fail_without_normalizing_either_file(self):
        for mutation in ('signer', 'extra', 'cancellable', 'duplicate'):
            value = copy.deepcopy(self.grants)
            if mutation == 'signer': value[0]['app_signature'] = ['*']
            elif mutation == 'extra': value[0]['permissions'].append({'name': 'ohos.permission.CAMERA'})
            elif mutation == 'cancellable': value[0]['permissions'][0]['userCancellable'] = True
            else: value.append(value[0])
            self.grant.write_text(json.dumps(value))
            before = self.snapshot()
            self.assertNotEqual(self.apply(POLICY).returncode, 0)
            self.assertEqual(before, self.snapshot())

    def test_unknown_privilege_or_signer_fail_closed(self):
        for key, value in (('app_signature', ['*']), ('allowAppUsePrivilegeExtension', False),
                           ('allowAppDesktopIconHide', True)):
            caps = copy.deepcopy(self.caps)
            row = copy.deepcopy(policy_guard.CAPABILITY)
            row[key] = value
            caps['install_list'].insert(1, row)
            self.cap.write_text(json.dumps(caps))
            before = self.snapshot()
            self.assertNotEqual(self.apply(POLICY).returncode, 0)
            self.assertEqual(before, self.snapshot())

    def test_symlink_grant_is_rejected_before_policy_mutation(self):
        target = self.grant.with_suffix('.saved')
        self.grant.rename(target)
        self.grant.symlink_to(target)
        before = self.snapshot()
        self.assertNotEqual(self.apply(POLICY).returncode, 0)
        self.assertEqual(before, self.snapshot())

    def test_recipe_prepares_all_pieces_before_traversal(self):
        recipe = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        boundary = recipe.index('  write_source_preparation_metadata\n}')
        for name in ('SOURCE_PROVIDER', 'EXTERNAL_INPUT', 'PREBUILT', 'SIGNING'):
            call = 'bash "${SETTINGS_' + name + '_COMPONENT_SCRIPT}"'
            self.assertEqual(recipe.count(call), 1)
            self.assertLess(recipe.index(call), boundary)
        self.assertLess(recipe.index('/settings/source_provider/prepare_dependencies.py"'), boundary)


if __name__ == '__main__':
    unittest.main()
