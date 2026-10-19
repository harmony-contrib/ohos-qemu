"""Calendar exact source composition and publication faults; no native execution."""
import base64
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest
from unittest import mock

import test_batch_system_calendar_main as viewer_tests
import test_batch_system_calendar_filter_async_lifetime as filter_tests


ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/applications/standard/calendardata/filter_async_lifetime'
MANIFEST = json.loads((COMPONENT / 'manifest.json').read_text())


class Calendar375CompositionTests(unittest.TestCase):
    def filter_case(self):
        case = filter_tests.CalendarFilterAsyncTests('runTest')
        case.setUp()
        self.addCleanup(case.doCleanups)
        return case

    def installer(self, case):
        previous = sys.modules.get('verify_source')
        sys.modules['verify_source'] = case.verify
        try:
            return filter_tests.load('calendar375_installer', COMPONENT / 'apply.py')
        finally:
            if previous is None:
                sys.modules.pop('verify_source', None)
            else:
                sys.modules['verify_source'] = previous

    def test_replace_then_raise_rolls_back_first_and_second_publication(self):
        for fail_at in (1, 2):
            with self.subTest(fail_at=fail_at):
                case = self.filter_case()
                installer = self.installer(case)
                before = case.snapshot()
                calls = []

                def publish_then_fail(source, target):
                    os.replace(source, target)
                    calls.append(target)
                    if len(calls) == fail_at:
                        raise OSError('failure after actual publication')

                with self.assertRaisesRegex(OSError, 'after actual publication'):
                    installer.apply(case.root, replace=publish_then_fail)
                self.assertEqual(case.snapshot(), before)
                self.assertEqual(case.verify.source_state(case.root), 'original')
                self.assertEqual(case.run_apply().returncode, 0)

    def test_unknown_edit_after_publication_is_preserved_with_exact_backup(self):
        case = self.filter_case()
        installer = self.installer(case)
        target = case.project / filter_tests.CALENDAR
        original = target.read_bytes()

        def foreign_edit(source, destination):
            os.replace(source, destination)
            destination.write_bytes(b'concurrent owner bytes\n')
            raise OSError('publication interrupted by foreign edit')

        with self.assertRaisesRegex(RuntimeError, 'preserved unknown target and backups'):
            installer.apply(case.root, replace=foreign_edit)
        self.assertEqual(target.read_bytes(), b'concurrent owner bytes\n')
        transactions = list((case.root / '.ohos-qemu-patches').glob('calendar-filter-async-lifetime-*'))
        self.assertEqual(len(transactions), 1)
        self.assertEqual((transactions[0] / '0.before').read_bytes(), original)
        before = case.snapshot()
        self.assertNotEqual(case.run_apply().returncode, 0)
        self.assertEqual(case.snapshot(), before)

    def test_failed_backup_restoration_retains_transaction_for_root_recovery(self):
        case = self.filter_case()
        installer = self.installer(case)
        original = (case.project / filter_tests.CALENDAR).read_bytes()
        actual_replace = os.replace

        def publish_then_fail(source, target):
            actual_replace(source, target)
            raise OSError('published then interrupted')

        with mock.patch.object(installer.os, 'replace', side_effect=OSError('restore filesystem error')):
            with self.assertRaisesRegex(RuntimeError, 'backups at'):
                installer.apply(case.root, replace=publish_then_fail)
        transactions = list((case.root / '.ohos-qemu-patches').glob('calendar-filter-async-lifetime-*'))
        self.assertEqual(len(transactions), 1)
        self.assertEqual((transactions[0] / '0.before').read_bytes(), original)
        self.assertEqual((case.project / filter_tests.CALENDAR).read_text(), case.after[filter_tests.CALENDAR])

    def install_previous(self, case):
        for index, (name, expected) in enumerate(MANIFEST['previous_complete_candidate'].items()):
            source = COMPONENT / 'tests/previous_candidate' / (str(index) + '-' + Path(name).name + '.gz.b64')
            raw = gzip.decompress(base64.b64decode(source.read_bytes(), validate=True))
            self.assertEqual(hashlib.sha256(raw).hexdigest(), expected)
            (case.project / name).write_bytes(raw)

    def test_only_complete_previous_candidate_upgrades_and_final_replays(self):
        case = self.filter_case()
        self.install_previous(case)
        self.assertEqual(case.verify.source_state(case.root), 'previous_candidate')
        self.assertFalse(case.verify.validate(case.root))
        with self.assertRaisesRegex(ValueError, 'complete final'):
            case.verify.validate(case.root, require_patched=True)
        self.assertEqual(case.run_apply().returncode, 0)
        self.assertTrue(case.verify.validate(case.root, require_patched=True))
        final = case.snapshot()
        self.assertEqual(case.run_apply().returncode, 0)
        self.assertEqual(case.snapshot(), final)

    def test_previous_final_mixture_and_old_dependency_drift_fail_closed(self):
        case = self.filter_case()
        self.install_previous(case)
        (case.project / filter_tests.CALENDAR).write_text(case.after[filter_tests.CALENDAR])
        before = case.snapshot()
        self.assertNotEqual(case.run_apply().returncode, 0)
        self.assertEqual(case.snapshot(), before)
        self.install_previous(case)
        header = case.project / 'calendarmanager/napi/include/calendar_manager_napi.h'
        header.write_bytes(header.read_bytes() + b'// foreign dependency\n')
        before = case.snapshot()
        self.assertNotEqual(case.run_apply().returncode, 0)
        self.assertEqual(case.snapshot(), before)

    def viewer_case(self):
        case = viewer_tests.CalendarMainTests('runTest')
        case.setUp()
        self.addCleanup(case.doCleanups)
        # Supply the exact source-provider inputs, then re-run the existing
        # full predecessor stack. No product source/out or compiler is used.
        fixture = ROOT / 'ci/capability-audit/fixtures/batch_apps/calendar_dispatch/source-provider-pristine.json'
        for relative, row in json.loads(fixture.read_text())['files'].items():
            case.write(relative, gzip.decompress(base64.b64decode(row['gzip_base64'])), row['sha256'])
        for name in ('source_provider', 'event_editor', 'editor_callback_dispatch'):
            result = case.run_component(name)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for relative, row in MANIFEST['fixture'].items():
            target = case.project / relative
            raw = gzip.decompress(base64.b64decode((COMPONENT / 'tests/predecessor' / row['file']).read_bytes()))
            if target.exists():
                self.assertEqual(hashlib.sha256(target.read_bytes()).hexdigest(), row['sha256'])
            else:
                case.write(relative, raw, row['sha256'])
        return case

    def test_complete_source_editor_dispatch_filter_viewer_owner_both_orders_and_replays(self):
        for filter_first in (True, False):
            with self.subTest(filter_first=filter_first):
                case = self.viewer_case()
                if filter_first:
                    result = case.run_component('filter_async_lifetime')
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    # Native ownership repair alone cannot enable a MainAbility write scene.
                    baseline = json.loads((case.project / 'entry/src/main/module.json5').read_text())['module']
                    write = next(p for p in baseline['requestPermissions']
                                 if p['name'] == 'ohos.permission.WRITE_WHOLE_CALENDAR')
                    self.assertNotIn('MainAbility', write['usedScene']['abilities'])
                case.prepare()
                result = case.run_component('filter_async_lifetime')
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                final = case.snapshot()
                for component in ('source_provider', 'event_editor', 'editor_callback_dispatch',
                                  'main_ui', 'calendar_owner', 'filter_async_lifetime'):
                    result = case.run_component(component)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(case.snapshot(), final)
                verifier = filter_tests.load('calendar375_filter_verify', COMPONENT / 'verify_source.py')
                self.assertEqual(verifier.source_state(case.root), 'final')
                # The reviewed business UI successor alone adds the MainAbility
                # WRITE scene; it retains per-Ability shared storage and the viewer.
                module = json.loads((case.project / 'entry/src/main/module.json5').read_text())['module']
                for permission in module['requestPermissions']:
                    if permission['name'] in ('ohos.permission.READ_WHOLE_CALENDAR',
                                              'ohos.permission.WRITE_WHOLE_CALENDAR'):
                        self.assertEqual(permission['usedScene']['abilities'].count('MainAbility'), 1)
                        self.assertEqual(permission['usedScene']['when'], 'inuse')
                page = (case.project / 'entry/src/main/ets/pages/index.ets').read_text()
                self.assertIn('@Entry({ useSharedStorage: true })', page)

    def test_getevents_type_failures_cannot_reuse_a_previous_successful_type(self):
        case = self.filter_case()
        old = case.before[filter_tests.CALENDAR]
        new = case.after[filter_tests.CALENDAR]
        start = 'struct GetEventsContext'
        before = old[old.index(start):old.index('\nstruct InstancesContext')]
        after = new[new.index(start):new.index('\nstruct InstancesContext')]
        # Source-constrained failure schedule: typeof may fail without updating
        # its out-parameter. The old second check reuses the first object's
        # type; the successor must propagate status before any conversion.
        for index, label in ((0, 'event filter'), (1, 'event keys')):
            unchecked = 'napi_typeof(env, argv[' + str(index) + '], &type);'
            checked = 'ctxt->status = ' + unchecked
            self.assertIn(unchecked, before)
            self.assertNotIn(checked, before)
            at = after.index(checked)
            guard = 'CHECK_STATUS_RETURN_VOID(ctxt, PARAMETER_INVALID, "cannot inspect ' + label + ' type")'
            self.assertIn(guard, after[at:at + 220])
        queue = case.after[filter_tests.QUEUE]
        at = queue.index('status = napi_typeof(env, argv[index], &type);')
        self.assertIn('CHECK_STATUS_RETURN_VOID(this, INTERNAL_ERROR, "cannot inspect async callback type")',
                      queue[at:at + 230])


if __name__ == '__main__':
    unittest.main()
