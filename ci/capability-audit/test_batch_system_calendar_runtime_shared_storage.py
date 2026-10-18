"""Calendar entry/storage integration and exact whole-state upgrade counterexamples.

Host component checks only. Actual ArkUI, SDK HAP and new-package behavior remain
required; this module does not simulate notification delivery or UI success.
"""
import hashlib
import json
from pathlib import Path
import subprocess
import unittest

import test_batch_system_calendar_main as existing

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/applications/standard/calendardata/main_ui'
QA = ROOT / 'ci/capability-audit/fixtures/batch_system/calendar_runtime'
PAGE = 'entry/src/main/ets/pages/index.ets'
OLD_PATCH_SHA = '7aa0725a75f07799dd11fed600eac67069f836ffd2976c42c93a577dd53648a7'


class CalendarSharedStorageTests(unittest.TestCase):
    def fixture(self):
        case = existing.CalendarMainTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        return case

    def verifier(self):
        return existing.load(COMPONENT / 'verify_source.py', 'calendar_shared_storage_guard')

    def legacy(self, case):
        patch = COMPONENT / '0001-route-real-calendar-reminders-to-source-provider.patch'
        self.assertEqual(hashlib.sha256(patch.read_bytes()).hexdigest(), OLD_PATCH_SHA)
        result = subprocess.run(['git', '-C', str(case.root), 'apply', str(patch)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_QA_page_selects_ability_storage_without_global_singleton(self):
        page = (QA / 'Index.ets').read_text()
        ability = (QA / 'EntryAbility.ets').read_text()
        self.assertIn('@Entry({ useSharedStorage: true })', page)
        self.assertIn("@LocalStorageLink('calendarRequest')", page)
        self.assertEqual(ability.count('new LocalStorage()'), 1)
        self.assertIn('  private storage: LocalStorage = new LocalStorage();', ability)
        self.assertIn("stage.loadContent('pages/Index', this.storage)", ability)
        self.assertIn('onCreate(want: Want): void { this.request(want); }', ability)
        self.assertIn('onNewWant(want: Want): void { this.request(want); }', ability)
        self.assertNotIn('new LocalStorage', page)

    def test_original_upgrades_to_new_final_and_replay_preserves_bytes(self):
        case = self.fixture(); guard = self.verifier()
        self.assertEqual(guard.source_state(case.root), 'original')
        result = case.run_component('main_ui')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(guard.source_state(case.root), 'final')
        self.assertTrue(guard.validate(case.root, require_patched=True))
        self.assertIn('@Entry({ useSharedStorage: true })', (case.project / PAGE).read_text())
        snapshot = case.snapshot()
        self.assertEqual(case.run_component('main_ui').returncode, 0)
        self.assertEqual(snapshot, case.snapshot())

    def test_complete_E_is_only_prefix_and_upgrades_without_reapplying_patch1(self):
        case = self.fixture(); self.legacy(case); guard = self.verifier()
        self.assertEqual(guard.source_state(case.root), 'prefix1')
        self.assertFalse(guard.validate(case.root))
        with self.assertRaises(ValueError): guard.validate(case.root, require_patched=True)
        before = case.snapshot()
        result = case.run_component('main_ui')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(guard.validate(case.root, require_patched=True))
        after = case.snapshot()
        self.assertEqual({name for name in before if before[name] != after[name]}, {PAGE})

    def test_mixed_original_and_E_is_rejected_without_publication(self):
        case = self.fixture(); original = case.snapshot(); self.legacy(case)
        name = 'entry/src/main/module.json5'
        (case.project / name).write_bytes(original[name])
        before = case.snapshot()
        self.assertNotEqual(case.run_component('main_ui').returncode, 0)
        self.assertEqual(before, case.snapshot())

    def test_complete_E_replays_parents_before_product_order_upgrade(self):
        case = self.fixture(); self.legacy(case); guard = self.verifier()
        self.assertEqual(guard.source_state(case.root), 'prefix1')
        before = case.snapshot()
        for name in ('event_editor', 'editor_callback_dispatch'):
            result = case.run_component(name)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(before, case.snapshot())
        result = case.run_component('main_ui')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(guard.validate(case.root, require_patched=True))
        self.assertEqual({name for name, data in before.items()
                          if data != case.snapshot()[name]}, {PAGE})

    def test_parent_replay_rejects_foreign_viewer_native_or_identity_without_writes(self):
        case = self.fixture(); self.legacy(case)
        for name in (PAGE, 'entry/src/main/module.json5',
                     'calendarmanager/napi/src/calendar_manager_napi.cpp', 'AppScope/app.json5'):
            with self.subTest(file=name):
                target = case.project / name; original = target.read_bytes()
                target.write_bytes(original + b'\n// foreign edit\n')
                before = case.snapshot()
                self.assertNotEqual(case.run_component('event_editor').returncode, 0)
                self.assertEqual(before, case.snapshot())
                target.write_bytes(original)

    def test_unknown_E_page_is_rejected_without_publication(self):
        case = self.fixture(); self.legacy(case)
        page = case.project / PAGE; page.write_bytes(page.read_bytes() + b'\n// foreign edit\n')
        before = case.snapshot()
        self.assertNotEqual(case.run_component('main_ui').returncode, 0)
        self.assertEqual(before, case.snapshot())

    def test_source_manifest_and_fixture_pin_complete_states_and_patch_bytes(self):
        guard = self.verifier(); data = json.loads((COMPONENT / 'source_states.json').read_text())
        self.assertEqual(data['states']['original'], {n: before for n, before, after in guard.FILES})
        self.assertEqual(data['states']['prefix1'], {n: after for n, before, after in guard.PREVIOUS_FILES})
        self.assertEqual(data['states']['final'], {n: after for n, before, after in guard.FILES})
        self.assertNotEqual(data['states']['prefix1'][PAGE], data['states']['final'][PAGE])
        self.assertEqual(data['patches_sha256'], {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in sorted(COMPONENT.glob('[0-9][0-9][0-9][0-9]-*.patch'))})
        fixture = ROOT / 'ci/capability-audit/fixtures/batch_system/calendar_main/main-component-hashes.json'
        self.assertEqual(json.loads(fixture.read_text()), [list(row) for row in guard.FILES])


if __name__ == '__main__':
    unittest.main()
