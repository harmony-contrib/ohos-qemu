"""Portable Calendar business host checks; no SDK/IPC/signing/native/guest proof.

Run with Node's stripTypeScriptTypes support. Product source is produced by the
real installer from existing exact fixtures, never copied into new fixtures.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest import mock

import test_batch_system_calendar375_composition as composition_tests

ROOT = Path(__file__).resolve().parents[2]
PROJECT = 'applications/standard/calendardata'
COMPONENT = ROOT / 'patches/common' / PROJECT / 'main_ui'
FIXTURE = ROOT / 'ci/capability-audit/fixtures/batch_system/calendar_business'
SCENARIOS = (
    'read_permission_and_real_query', 'read_denied_cancel_wrong_result', 'default_calendar',
    'create_explicit_confirmed', 'write_denied_cancel_no_mutation',
    'invalid_form_never_requests_write', 'edit_preserves_fields_and_timezone',
    'complex_events_read_only', 'delete_confirmation_rechecks_real_event',
    'delete_changed_event_fails_closed', 'delete_missing_or_recurring_fails_closed',
    'delete_changed_public_location', 'delete_changed_public_attendee',
    'delete_changed_public_identifier', 'delete_changed_public_reminderTime',
    'delete_all_public_nested_changes', 'delete_incomparable_types_refresh',
    'delete_instance_projection_and_order', 'delete_displayed_snapshot_frozen_before_permission',
    'delete_lifecycle_permission_cleanup',
    'exit_during_permission_no_write', 'destroy_during_permission_no_write',
    'background_during_prewrite_read', 'destroy_after_submission_does_not_cancel_provider',
    'duplicate_submission_blocked', 'api_denied_after_grant_is_error',
    'write_success_read_failure_is_not_empty_success', 'unsupported_read_visible',
    'stale_read_never_replaces_newer_selection', 'DST_days_use_local_midnight',
    'invalid_backend_data_fails_closed', 'out_of_range_date_no_query',
)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def snapshot(project):
    return {str(path.relative_to(project)): path.read_bytes()
            for path in project.rglob('*') if path.is_file()}


class CalendarBusinessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        temporary = tempfile.TemporaryDirectory(prefix='calendar-business-fixtures-')
        cls.addClassCleanup(temporary.cleanup)
        cls.templates = Path(temporary.name)
        helper = composition_tests.Calendar375CompositionTests('runTest')
        try:
            case = helper.viewer_case()
            result = case.run_component('filter_async_lifetime')
            if result.returncode:
                raise AssertionError(result.stdout + result.stderr)
            shutil.copytree(case.root, cls.templates / 'original')
            case.prepare()
            shutil.copytree(case.root, cls.templates / 'final')
        finally:
            helper.doCleanups()
        cls.verifier = load('business_main_verify', COMPONENT / 'verify_source.py')
        cls.installer = load('business_main_apply', COMPONENT / 'apply.py')
        cls.expected = snapshot(cls.templates / 'final' / PROJECT)

    def source(self):
        temporary = tempfile.TemporaryDirectory(prefix='calendar-business-state-')
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name) / 'source'
        shutil.copytree(self.templates / 'original', root)
        return root

    def prefix(self, root, count):
        for patch in sorted(COMPONENT.glob('[0-9][0-9][0-9][0-9]-*.patch'))[:count]:
            result = subprocess.run(['git', '-C', str(root), 'apply', str(patch)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def node(self, fixture, *arguments):
        result = subprocess.run(
            ['node', '--unhandled-rejections=strict', str(FIXTURE / fixture), *map(str, arguments)],
            capture_output=True, text=True, timeout=20,
            env={**os.environ, 'TZ': 'America/New_York', 'LC_ALL': 'C', 'LC_CTYPE': 'C', 'LANG': 'C'})
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('PASS host-only', result.stdout)

    def test_actual_business_controller_public_api_and_lifecycle(self):
        for scenario in SCENARIOS:
            with self.subTest(scenario=scenario):
                self.node('controller.cjs', self.templates / 'final' / PROJECT, scenario)

    def test_actual_page_and_window_lifecycle_bodies(self):
        self.node('page_lifecycle.cjs', self.templates / 'final' / PROJECT)

    def test_complete_E_and_F_prefixes_upgrade_to_the_same_business_final(self):
        for name, count in (('prefix1', 1), ('prefix2', 2), ('prefix3', 3)):
            with self.subTest(prefix=name):
                root = self.source()
                self.prefix(root, count)
                self.assertEqual(self.verifier.source_state(root), name)
                with self.assertRaisesRegex(ValueError, 'complete'):
                    self.verifier.validate(root, require_patched=True)
                self.installer.apply(root)
                self.assertEqual(snapshot(root / PROJECT), self.expected)
                self.assertEqual(self.verifier.source_state(root), 'final')

    def test_partial_business_controller_is_rejected_without_writes(self):
        root = self.source()
        self.prefix(root, 2)
        target = root / PROJECT / 'entry/src/main/ets/calendar/CalendarBusinessController.ets'
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((self.templates / 'final' / PROJECT / target.relative_to(root / PROJECT)).read_bytes())
        before = snapshot(root / PROJECT)
        with self.assertRaisesRegex(ValueError, 'unknown or mixed'):
            self.installer.apply(root)
        self.assertEqual(snapshot(root / PROJECT), before)

    def test_manifest_drift_is_rejected_without_editing_the_repository(self):
        root = self.source()
        self.prefix(root, 2)
        manifest = COMPONENT / 'source_states.json'
        raw = manifest.read_bytes()
        original_read = Path.read_bytes
        before = snapshot(root / PROJECT)

        def drift(path):
            return raw + b' ' if path == manifest else original_read(path)

        with mock.patch.object(Path, 'read_bytes', drift):
            with self.assertRaisesRegex(ValueError, 'manifest drift'):
                self.installer.apply(root)
        self.assertEqual(snapshot(root / PROJECT), before)

    def test_failure_after_new_controller_publication_restores_F_prefix(self):
        root = self.source()
        self.prefix(root, 2)
        before = snapshot(root / PROJECT)
        count = 0

        def publish_then_fail(path, data, mode):
            nonlocal count
            count += 1
            self.installer.replace(path, data, mode)
            if count == len(self.verifier.FILES):
                raise OSError('failure after final new controller publication')

        with self.assertRaisesRegex(OSError, 'new controller publication'):
            self.installer.apply(root, publish=publish_then_fail)
        self.assertEqual(snapshot(root / PROJECT), before)
        self.assertFalse((root / PROJECT / 'entry/src/main/ets/calendar/CalendarBusinessController.ets').exists())
        self.assertEqual(self.verifier.source_state(root), 'prefix2')

    def test_failure_after_complete_business_prefix_restores_old_controller(self):
        root = self.source()
        self.prefix(root, 3)
        before = snapshot(root / PROJECT)
        self.assertEqual(self.verifier.source_state(root), 'prefix3')
        count = 0

        def publish_then_fail(path, data, mode):
            nonlocal count
            count += 1
            self.installer.replace(path, data, mode)
            if count == len(self.verifier.FILES):
                raise OSError('failure after old business controller replacement')

        with self.assertRaisesRegex(OSError, 'old business controller replacement'):
            self.installer.apply(root, publish=publish_then_fail)
        self.assertEqual(snapshot(root / PROJECT), before)
        self.assertEqual(self.verifier.source_state(root), 'prefix3')

    def test_business_mode_requires_reminder_and_native_guards_before_crypto(self):
        provider = load('business_calendar_provider', ROOT / 'patches/lib/calendar_provider.py')
        for reminder, native, message in ((False, True, 'reminder'), (True, False, 'native')):
            with self.subTest(reminder=reminder, native=native):
                with mock.patch.object(provider.subprocess, 'run', side_effect=AssertionError('crypto must not run')):
                    with self.assertRaisesRegex(ValueError, message):
                        provider.verify(Path('unused-host-input'), True, reminder, native, True)


if __name__ == '__main__':
    unittest.main()
