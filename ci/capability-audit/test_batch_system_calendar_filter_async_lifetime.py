"""Frozen production patch/rollback + executable ownership schedules; no compiler."""
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
COMPONENT = ROOT / 'patches/common/applications/standard/calendardata/filter_async_lifetime'
MANIFEST = json.loads((COMPONENT / 'manifest.json').read_text())
CALENDAR = 'calendarmanager/napi/src/calendar_napi.cpp'
QUEUE = 'calendarmanager/napi/src/napi_queue.cpp'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MODEL = load('calendar_filter_ownership_model', COMPONENT / 'tests/ownership_model.py')


class CalendarFilterAsyncTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='calendar-filter-async-host-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.project = self.root / MANIFEST['project']
        for relative, record in MANIFEST['fixture'].items():
            data = gzip.decompress(base64.b64decode((COMPONENT / 'tests/predecessor' / record['file']).read_bytes()))
            self.assertEqual(hashlib.sha256(data).hexdigest(), record['sha256'])
            path = self.project / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        self.before = {name: (self.project / name).read_text() for name in (CALENDAR, QUEUE)}
        self.verify = load('calendar_filter_verify', COMPONENT / 'verify_source.py')
        self.after = {name: self.verify.read_payload(name).decode() for name in (CALENDAR, QUEUE)}
        self.old = MODEL.SourcePolicy(self.before[CALENDAR], self.before[QUEUE], repaired=False)
        self.new = MODEL.SourcePolicy(self.after[CALENDAR], self.after[QUEUE], repaired=True)

    def run_apply(self):
        return subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(self.root)],
                              capture_output=True, text=True, timeout=10,
                              env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})

    def snapshot(self):
        return {str(path.relative_to(self.project)): path.read_bytes()
                for path in self.project.rglob('*') if path.is_file()}

    def request(self, *, bad=None, callback=False, filter=True):
        engine = MODEL.Engine()
        native = MODEL.Native()
        wrapper = MODEL.Wrapper(native)
        request = MODEL.Request(self.new, engine, wrapper if filter else None, callback=callback, bad=bad)
        return engine, native, wrapper, request

    def test_original_cpp_schedule_exposes_gc_use_after_finalize(self):
        engine = MODEL.Engine()
        native = MODEL.Native()
        wrapper = MODEL.Wrapper(native)
        request = MODEL.Request(self.old, engine, wrapper)
        request.submit()
        wrapper.gc()
        self.assertFalse(wrapper.alive)
        with self.assertRaisesRegex(ReferenceError, 'EventFilterNapi used after JS finalization'):
            request.execute()
        self.assertEqual(native.destroyed, 1)
        request.complete(cancelled=True)

    def test_original_queue_failure_drops_unsettled_promise(self):
        request = MODEL.Request(self.old, MODEL.Engine())
        request.submit(failure='queue')
        self.assertEqual(request.promise, 'pending_returned_undefined')
        self.assertEqual(request.deliveries, [])

    def test_native_snapshot_outlives_wrapper_and_releases_once(self):
        engine, native, wrapper, request = self.request()
        request.submit()
        wrapper.gc()
        self.assertFalse(wrapper.alive)
        self.assertEqual(native.owners, 1)
        request.execute()
        self.assertEqual(request.executed, 1)
        request.complete()
        self.assertEqual(request.promise, 'resolved')
        self.assertEqual(request.owner_releases, 1)
        self.assertEqual(request.js_reference_releases, 1)
        self.assertEqual(native.destroyed, 1)
        self.assertFalse(engine.hooks)

    def test_no_filter_bad_unwrap_null_native_and_invalid_keys(self):
        for bad in ('unwrap_failure', 'null_wrapper', 'null_native', 'wrong_receiver', 'null_calendar', 'invalid_keys'):
            with self.subTest(bad=bad):
                engine, native, wrapper, request = self.request(bad=bad)
                request.submit()
                wrapper.gc()
                request.execute()
                request.complete()
                self.assertEqual(request.executed, 0)
                self.assertEqual(request.promise, 'rejected')
                self.assertEqual(len(request.deliveries), 1)
                self.assertEqual(native.destroyed, 1)
                self.assertFalse(engine.hooks)
        engine, native, wrapper, request = self.request(filter=False)
        request.submit()
        request.execute()
        request.complete()
        self.assertEqual(request.executed, 1)
        self.assertEqual(request.owner_releases, 0)

    def test_create_queue_cancel_output_failures_for_callback_and_promise(self):
        for callback in (False, True):
            for failure in ('hook', 'resource', 'work', 'queue', 'cancel', 'output'):
                with self.subTest(callback=callback, failure=failure):
                    engine, native, wrapper, request = self.request(callback=callback)
                    if failure in ('cancel', 'output'):
                        request.submit()
                        wrapper.gc()
                        if failure == 'output':
                            request.execute()
                        request.complete(cancelled=failure == 'cancel', output_error=failure == 'output')
                    else:
                        request.submit(failure=failure)
                        wrapper.gc()
                    self.assertEqual(len(request.deliveries), 1)
                    self.assertNotEqual(request.deliveries[0], 'ok')
                    self.assertNotEqual(request.deliveries[0], 'error_code_0')
                    self.assertEqual(request.owner_releases, 1)
                    self.assertEqual(request.js_reference_releases, 1)
                    self.assertEqual(native.destroyed, 1)
                    self.assertFalse(engine.hooks)
                    if not callback:
                        self.assertEqual(request.promise, 'rejected')

    def test_unretained_callback_or_uncreatable_promise_throws_synchronously(self):
        for failure in ('promise', 'self_ref', 'callback_ref'):
            with self.subTest(failure=failure):
                engine, native, wrapper, request = self.request(bad=failure if failure != 'promise' else None)
                request.submit(failure=failure)
                wrapper.gc()
                self.assertEqual(request.promise, 'sync_throw')
                self.assertEqual(request.deliveries, [])
                self.assertEqual(native.destroyed, 1)
                self.assertFalse(engine.hooks)

    def test_environment_exit_and_null_complete_never_call_napi_after_exit(self):
        for schedule in ('before_worker', 'after_worker', 'null_complete', 'callback_reentry'):
            with self.subTest(schedule=schedule):
                engine, native, wrapper, request = self.request(callback=True)
                request.submit()
                wrapper.gc(force=True)
                if schedule == 'before_worker':
                    engine.destroy()
                    request.execute()
                    self.assertEqual(request.executed, 0)
                else:
                    request.execute()
                if schedule == 'after_worker':
                    engine.destroy()
                if schedule == 'callback_reentry':
                    request.complete(reentrant=engine.destroy)
                else:
                    request.complete(null_env=schedule == 'null_complete')
                if schedule == 'null_complete':
                    self.assertEqual(len(engine.hooks), 1)
                    # Token is independent from the already released request.
                    engine.destroy()
                self.assertEqual(request.owner_releases, 1)
                self.assertEqual(native.destroyed, 1)
                self.assertEqual(request.js_reference_releases, 0)
                self.assertFalse(engine.hooks)

    def test_failed_hook_removal_does_not_retain_or_dereference_async_context(self):
        engine, native, wrapper, request = self.request()
        request.submit(unregister_failure=True)
        wrapper.gc()
        request.execute()
        request.complete()
        self.assertTrue(request.done)
        self.assertEqual(native.destroyed, 1)
        self.assertEqual(len(engine.hooks), 1)
        self.assertEqual(request.js_reference_releases, 1)
        engine.destroy()
        self.assertFalse(engine.hooks)

    def test_shared_filter_two_requests_cancel_one_then_complete_other(self):
        engine = MODEL.Engine()
        native = MODEL.Native()
        wrapper = MODEL.Wrapper(native)
        requests = [MODEL.Request(self.new, engine, wrapper) for _ in range(2)]
        for request in requests:
            request.submit()
        wrapper.gc()
        self.assertEqual(native.owners, 2)
        requests[0].complete(cancelled=True)
        self.assertEqual(native.owners, 1)
        requests[1].execute()
        requests[1].complete()
        self.assertEqual(native.destroyed, 1)
        self.assertFalse(engine.hooks)

    def test_actual_patch_matches_two_full_postimages_and_installer_replays(self):
        patch = COMPONENT / '0001-retain-native-filter-through-async-completion.patch'
        for arguments in (['--check'], []):
            result = subprocess.run(['git', '-C', str(self.root), 'apply', '--unidiff-zero', *arguments, str(patch)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(self.verify.validate(self.root, require_patched=True))
        self.assertEqual(self.run_apply().returncode, 0)

    def test_installer_unknown_mixed_and_dependency_drift_rejected(self):
        target = self.project / CALENDAR
        original = target.read_bytes()
        target.write_text(self.after[CALENDAR])
        before = self.snapshot()
        self.assertNotEqual(self.run_apply().returncode, 0)
        self.assertEqual(self.snapshot(), before)
        target.write_bytes(original + b'// unknown\n')
        before = self.snapshot()
        self.assertNotEqual(self.run_apply().returncode, 0)
        self.assertEqual(self.snapshot(), before)
        target.write_bytes(original)
        header = self.project / 'calendarmanager/napi/include/napi_queue.h'
        header.write_bytes(header.read_bytes() + b'\n')
        before = self.snapshot()
        self.assertNotEqual(self.run_apply().returncode, 0)
        self.assertEqual(self.snapshot(), before)

    def test_failed_second_commit_restores_both_originals(self):
        previous = sys.modules.get('verify_source')
        sys.modules['verify_source'] = self.verify
        try:
            installer = load('calendar_filter_installer', COMPONENT / 'apply.py')
        finally:
            if previous is None:
                del sys.modules['verify_source']
            else:
                sys.modules['verify_source'] = previous
        before = self.snapshot()
        count = 0

        def fail_second(source, target):
            nonlocal count
            count += 1
            if count == 2:
                raise OSError('second rename failed')
            os.replace(source, target)

        with self.assertRaisesRegex(OSError, 'second rename failed'):
            installer.apply(self.root, replace=fail_second)
        self.assertEqual(self.snapshot(), before)
        self.assertFalse(self.verify.validate(self.root))
        result = self.run_apply()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(self.verify.validate(self.root, require_patched=True))

    def test_all_existing_queue_callers_return_the_queue_result_directly(self):
        sources = [self.after[CALENDAR],
                   (self.project / 'calendarmanager/napi/src/calendar_manager_napi.cpp').read_text()]
        callers = []
        import re
        for source in sources:
            for declaration in re.findall(r'napi_value (?:CalendarNapi|CalendarManagerNapi)::\w+\([^\n]+\)', source):
                body = MODEL.block(source, declaration)
                if 'NapiQueue::AsyncWork(' in body:
                    self.assertIn('return NapiQueue::AsyncWork(', body)
                    callers.append(declaration.split('::')[1].split('(')[0])
        self.assertEqual(len(callers), 13)
        self.assertIn('GetEvents', callers)
        self.assertIn('CreateCalendar', callers)


if __name__ == '__main__':
    unittest.main()
