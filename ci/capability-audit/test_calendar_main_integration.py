"""Real component replay and permission-contract counterexamples; host only."""
import base64
import copy
import gzip
import json
from pathlib import Path
import sys
import unittest

import test_batch_apps_calendar_dispatch as dispatch_tests
from test_calendar_provider import policy

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'patches/lib'))
import calendar_provider as provider
COMPONENT = ROOT / 'patches/common/applications/standard/calendardata/calendar_main'
MANIFEST = json.loads((COMPONENT / 'manifest.json').read_text())


class CalendarMainIntegrationTests(unittest.TestCase):
    def prepare(self):
        old = dispatch_tests.CalendarDispatchTests('runTest')
        old.setUp()
        self.addCleanup(old.doCleanups)
        old.prepare_full_stack()
        for relative, row in MANIFEST['fixture'].items():
            target = old.project / relative
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(gzip.decompress(base64.b64decode(
                    (COMPONENT / 'tests/predecessor' / row['file']).read_bytes())))
        result = old.run_component('calendar_main')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return old

    def test_complete_source_editor_dispatch_main_replay_keeps_exact_bytes(self):
        case = self.prepare()
        before = {str(p): p.read_bytes() for p in case.project.rglob('*') if p.is_file()}
        for _ in range(2):
            for component in ('source_provider', 'event_editor', 'editor_callback_dispatch', 'calendar_main'):
                result = case.run_component(component)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(before, {str(p): p.read_bytes() for p in case.project.rglob('*') if p.is_file()})
        provider.validate_main_source(case.root)

    def test_whole_successor_required_before_editor_replay(self):
        case = self.prepare()
        targets = ('entry/src/main/ets/pages/index.ets',
                   'entry/src/main/ets/calendar/CalendarRoute.ets',
                   'datamanager/src/main/ets/processor/reminders/ReminderAgentHelper.ets',
                   'calendarmanager/napi/src/calendar_manager_napi.cpp')
        for relative in targets:
            with self.subTest(relative=relative):
                target = case.project / relative
                original = target.read_bytes()
                target.write_bytes(original + b'// unknown successor\n')
                before = {str(p): p.read_bytes() for p in case.project.rglob('*') if p.is_file()}
                result = case.run_component('event_editor')
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(before, {str(p): p.read_bytes() for p in case.project.rglob('*') if p.is_file()})
                with self.assertRaises(ValueError): provider.validate_main_source(case.root)
                target.write_bytes(original)

    def test_main_permission_scene_cannot_accept_only_module_or_changed_identity(self):
        _, profile, capabilities = policy()
        module = json.loads((COMPONENT / 'files/entry/src/main/module.json5').read_text())['module']
        provider.validate(module, profile, capabilities, provider.SIGNATURE, provider.SIGNATURE,
                          require_editor=True, require_main=True)
        variants = []
        changed = copy.deepcopy(module)
        changed['abilities'][0]['exported'] = 1
        variants.append(changed)
        changed = copy.deepcopy(module)
        changed['abilities'][0]['launchType'] = 'singleton'
        variants.append(changed)
        changed = copy.deepcopy(module)
        changed['abilities'][0]['skills'][1]['uris'][0]['host'] = 'caller-supplied'
        variants.append(changed)
        changed = copy.deepcopy(module)
        changed['requestPermissions'].append({'name': 'ohos.permission.MANAGE_CALENDAR'})
        variants.append(changed)
        for changed in variants:
            with self.subTest(changed=changed):
                with self.assertRaises(ValueError):
                    provider.validate(changed, profile, capabilities, provider.SIGNATURE, provider.SIGNATURE)
        for key, value in (('apl', 'normal'), ('app-feature', 'hos_normal_app')):
            changed = copy.deepcopy(profile)
            changed['bundle-info'][key] = value
            with self.assertRaises(ValueError):
                provider.validate(module, changed, capabilities, provider.SIGNATURE, provider.SIGNATURE)


if __name__ == '__main__':
    unittest.main()
