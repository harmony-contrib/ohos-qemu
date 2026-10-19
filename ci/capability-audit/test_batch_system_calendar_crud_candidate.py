"""Exact source composition/rollback and real delivered ETS on host, not guest proof."""
import base64
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/applications/standard/calendardata/calendar_main'
MANIFEST = json.loads((COMPONENT / 'manifest.json').read_text())


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CalendarMainTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='calendar-main-host-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()
        self.project = self.root / MANIFEST['project']
        for relative, record in MANIFEST['fixture'].items():
            data = gzip.decompress(base64.b64decode(
                (COMPONENT / 'tests/predecessor' / record['file']).read_bytes()))
            self.assertEqual(hashlib.sha256(data).hexdigest(), record['sha256'])
            target = self.project / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        self.verifier = load('calendar_main_verify', COMPONENT / 'verify_source.py')

    def apply(self):
        return subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(self.root)],
                              capture_output=True, text=True, timeout=10,
                              env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})

    def prepare(self):
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def source_bytes(self):
        return {str(path.relative_to(self.project)): path.read_bytes()
                for path in self.project.rglob('*') if path.is_file()}

    def test_exact_installed_predecessor_idempotence(self):
        self.assertFalse(self.verifier.validate(self.root))
        self.prepare()
        self.assertTrue(self.verifier.validate(self.root, require_patched=True))
        before = self.source_bytes()
        self.prepare()
        self.assertEqual(self.source_bytes(), before)
        for name, record in MANIFEST['files'].items():
            self.assertEqual(hashlib.sha256((self.project / name).read_bytes()).hexdigest(), record['after_sha256'])

    def test_fixed_original_main_is_empty_and_reminder_targets_another_bundle(self):
        page = (self.project / 'entry/src/main/ets/pages/index.ets').read_text()
        self.assertRegex(page, r'build\(\)\s*\{\s*\}')
        ability = (self.project / 'entry/src/main/ets/MainAbility/MainAbility.ets').read_text()
        self.assertNotIn('onNewWant', ability)
        self.assertNotIn('want.uri', ability)
        app = json.loads((self.project / 'AppScope/app.json5').read_text())['app']
        self.assertEqual(app['bundleName'], 'com.ohos.calendardata')
        reminder = (self.project / 'datamanager/src/main/ets/processor/reminders/ReminderAgentHelper.ets').read_text()
        self.assertIn("const CALENDAR_BUNDLE_NAME = 'com.ohos.calendar';", reminder)

    def test_unknown_partial_and_old_editor_dependency_preserved(self):
        target = self.project / 'entry/src/main/module.json5'
        target.write_bytes(target.read_bytes() + b'\n')
        before = self.source_bytes()
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertEqual(self.source_bytes(), before)
        # Restore the exact predecessor; a single successor target must fail.
        record = MANIFEST['fixture']['entry/src/main/module.json5']
        target.write_bytes(gzip.decompress(base64.b64decode(
            (COMPONENT / 'tests/predecessor' / record['file']).read_bytes())))
        target = self.project / 'entry/src/main/ets/pages/index.ets'
        target.write_bytes((COMPONENT / 'files/entry/src/main/ets/pages/index.ets').read_bytes())
        before = self.source_bytes()
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertEqual(self.source_bytes(), before)

    def test_dispatch_pair_and_existing_editor_guarded(self):
        for relative in ('calendarmanager/napi/src/calendar_manager_napi.cpp',
                         'entry/src/main/ets/editor/EventEditorController.ets'):
            with self.subTest(relative=relative):
                target = self.project / relative
                original = target.read_bytes()
                target.write_bytes(original + b'// unrecognized predecessor\n')
                before = self.source_bytes()
                self.assertNotEqual(self.apply().returncode, 0)
                self.assertEqual(self.source_bytes(), before)
                target.write_bytes(original)

    def test_symlink_rejected_without_touching_outside(self):
        target = self.project / 'entry/src/main/ets/MainAbility/MainAbility.ets'
        outside = self.root / 'outside.ets'
        outside.write_bytes(target.read_bytes())
        target.unlink()
        target.symlink_to(outside)
        before = outside.read_bytes()
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertTrue(target.is_symlink())
        self.assertEqual(outside.read_bytes(), before)

    def test_failed_middle_commit_rolls_back_all_six_targets(self):
        previous = sys.modules.get('verify_source')
        sys.modules['verify_source'] = self.verifier
        try:
            installer = load('calendar_main_installer', COMPONENT / 'apply.py')
        finally:
            if previous is None:
                del sys.modules['verify_source']
            else:
                sys.modules['verify_source'] = previous
        before = self.source_bytes()
        calls = []

        def fail_after_new_file(source, target):
            calls.append(str(target))
            if len(calls) == 5:
                raise OSError('injected failed rename')
            os.replace(source, target)

        with self.assertRaisesRegex(OSError, 'injected failed rename'):
            installer.apply(self.root, replace=fail_after_new_file)
        self.assertEqual(self.source_bytes(), before)
        self.assertFalse(self.verifier.validate(self.root))
        self.assertFalse((self.project / 'entry/src/main/ets/calendar').exists())
        self.prepare()

    def test_original_permissions_provider_editor_and_bundle_preserved(self):
        before = json.loads((self.project / 'entry/src/main/module.json5').read_text())
        old_app = (self.project / 'AppScope/app.json5').read_bytes()
        self.prepare()
        after = json.loads((self.project / 'entry/src/main/module.json5').read_text())
        self.assertEqual((self.project / 'AppScope/app.json5').read_bytes(), old_app)
        skills = after['module']['abilities'][0].pop('skills')
        self.assertEqual(skills[1]['uris'], [{'scheme': 'calendar', 'host': 'com.ohos.calendardata'},
                                           {'scheme': 'calendar', 'host': 'com.ohos.calendar'}])
        self.assertEqual(after['module']['abilities'][0]['launchType'], 'standard')
        for entry in after['module']['requestPermissions']:
            if entry['name'] in ('ohos.permission.READ_WHOLE_CALENDAR', 'ohos.permission.WRITE_WHOLE_CALENDAR'):
                self.assertEqual(entry['usedScene']['abilities'].pop(), 'MainAbility')
        self.assertEqual(after, before)
        text = (self.project / 'datamanager/src/main/ets/processor/reminders/ReminderAgentHelper.ets').read_text()
        self.assertIn("const CALENDAR_BUNDLE_NAME = 'com.ohos.calendardata';", text)
        self.assertEqual(text.count('pkgName: CALENDAR_BUNDLE_NAME'), 2)
        self.assertIn('calendar://com.ohos.calendardata?event_id=', text)

    def test_actual_delivered_route_controller_and_ability_functions(self):
        self.prepare()
        scenarios = ('routes', 'real_reads_and_permissions', 'default_calendar', 'deep_link_current_calendar',
                     'malformed_uri_no_backend', 'cancel_no_mutation', 'create_explicit_and_duplicate',
                     'edit_preserves_fields', 'invalid_and_complex_write_rejected',
                     'invalid_backend_data_fails_closed',
                     'write_failure_and_delete_confirmation', 'background_before_read_and_before_write',
                     'destroy_during_submitted_write', 'new_want_stale_read', 'new_want_during_write',
                     'new_want_during_prewrite_read', 'restart_and_isolated_abilities',
                     'ability_lifecycle_and_old_window_callback', 'ability_initialization_error_is_visible')
        for scenario in scenarios:
            with self.subTest(scenario=scenario):
                result = subprocess.run(['node', '--unhandled-rejections=strict',
                                         str(COMPONENT / 'tests/controller.cjs'), str(self.project), scenario],
                                        capture_output=True, text=True, timeout=10,
                                        env={**os.environ, 'TZ': 'UTC'})
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(result.stdout.strip(), 'PASS ' + scenario)


if __name__ == '__main__':
    unittest.main()
