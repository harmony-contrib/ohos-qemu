"""Host-only exact product controller/NAPI callback execution, not guest proof."""
import base64
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / 'ci/capability-audit/fixtures/batch_apps/calendar_editor'
COMPONENT = ROOT / 'patches/common/applications/standard/calendardata/event_editor'
PROJECT = 'applications/standard/calendardata'


class CalendarEditorTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='batch-apps-calendar-editor-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.project = self.root / PROJECT
        self.meta = json.loads((FIXTURE / 'provenance.json').read_text())
        for relative, record in self.meta['files'].items():
            data = gzip.decompress(base64.b64decode((FIXTURE / record['fixture']).read_bytes()))
            self.assertEqual(hashlib.sha256(data).hexdigest(), record['sha256'])
            target = self.project / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)

    def apply(self):
        return subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(self.root)],
                              capture_output=True, text=True)

    def prepare(self):
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_exact_patch_idempotence_and_drift_rejection(self):
        self.prepare()
        for path, digest in self.meta['patched_sha256'].items():
            self.assertEqual(hashlib.sha256((self.project / path).read_bytes()).hexdigest(), digest)
        self.assertEqual(self.apply().returncode, 0)
        target = self.project / 'entry/src/main/ets/editor/EventEditorController.ets'
        target.write_text(target.read_text() + '\n// unknown edit\n')
        before = target.read_bytes()
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertEqual(target.read_bytes(), before)

    def test_actual_controller_consent_crud_result_errors_and_lifetime(self):
        self.prepare()
        target = self.project / 'entry/src/main/ets/editor/EventEditorController.ets'
        for scenario in ('validation', 'cancel', 'save', 'write_failure', 'read_failure', 'delivery_retry',
                         'invalid_backend_id', 'invalid_edited_fields', 'destroy_before_write',
                         'destroy_during_write', 'isolated_sessions'):
            with self.subTest(scenario=scenario):
                result = subprocess.run(['node', '--unhandled-rejections=strict', str(FIXTURE / 'controller.cjs'),
                                         str(target), scenario], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(result.stdout.strip(), 'PASS ' + scenario)

    def test_actual_napi_callbacks_settle_once_without_stale_js_handles(self):
        self.prepare()
        cpp = (self.project / 'calendarmanager/napi/src/calendar_manager_napi.cpp').read_text()
        header = (self.project / 'calendarmanager/napi/include/calendar_manager_napi.h').read_text()
        context = re.search(r'    struct EditEventContext : public ContextBase \{.*?\n    \};', header, re.S).group()
        functions = cpp[cpp.index('void CalendarManagerNapi::FinishEditor('):cpp.index('napi_value CalendarManagerNapi::New(')]
        code = (FIXTURE / 'napi_harness.cpp').read_text().replace('// INSERT_CONTEXT', context).replace('// INSERT_FUNCTIONS', functions)
        harness = self.root / 'editor.cpp'
        harness.write_text(code)
        binary = self.root / 'editor'
        result = subprocess.run(['c++', '-std=c++20', '-Wall', '-Wextra', '-Werror', str(harness), '-o', str(binary)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        subprocess.run([str(binary)], check=True, capture_output=True, text=True)
        self.assertNotIn('napi_value id', context)

    def test_whole_and_lower_datashare_permission_and_proxy_contracts_preserved(self):
        original = json.loads((self.project / 'entry/src/main/module.json5').read_text())['module']
        self.prepare()
        module = json.loads((self.project / 'entry/src/main/module.json5').read_text())['module']
        editor = module['extensionAbilities'][0]
        self.assertEqual(editor, {'name': 'EditorUIExtensionAbility', 'srcEntry': './ets/EditorUIExtensionAbility.ets',
                                 'type': 'sys/commonUI', 'exported': True, 'extensionProcessMode': 'instance'})
        self.assertEqual(module['extensionAbilities'][1:], original['extensionAbilities'])
        self.assertEqual(module['proxyData'], original['proxyData'])
        before = {p['name']: p for p in original['requestPermissions']}
        after = {p['name']: p for p in module['requestPermissions']}
        self.assertEqual(before.keys(), after.keys())
        for name in ('ohos.permission.READ_WHOLE_CALENDAR', 'ohos.permission.WRITE_WHOLE_CALENDAR'):
            expected = before[name]['usedScene']['abilities'] + ['EditorUIExtensionAbility']
            self.assertEqual(after[name]['usedScene']['abilities'], expected)
        self.assertNotIn('setReceiveDataCallback', (self.project / 'entry/src/main/ets/EditorUIExtensionAbility.ets').read_text())


if __name__ == '__main__':
    unittest.main()
