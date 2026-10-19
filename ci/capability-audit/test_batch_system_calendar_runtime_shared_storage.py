"""Calendar entry/storage and exact original/E/F/business upgrade regressions.

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
ABILITY = 'entry/src/main/ets/MainAbility/MainAbility.ets'
MODULE = 'entry/src/main/module.json5'
READER = 'entry/src/main/ets/reminder/CalendarReminderReader.ets'
PRODUCER = 'datamanager/src/main/ets/processor/reminders/ReminderAgentHelper.ets'
BUSINESS = 'entry/src/main/ets/calendar/CalendarBusinessController.ets'
OLD_PATCH_SHA = '7aa0725a75f07799dd11fed600eac67069f836ffd2976c42c93a577dd53648a7'
SHARED_PATCH_SHA = 'a6fc3306e278a053983f875c855e7628c632b085c1ee2f25b8e1beb1653b6906'
HISTORICAL_F_FIXTURE_SHA = '82d79ffa3c51ce504e36421c58fa3cf173dca2ed392c8dee8f80ba29502440d9'
E_PAGE_SHA = 'ab1e7f11adb58e9b07d49a05d57901d3319d84cea6fb5b63180e268b1c4a3b98'
BUSINESS_POSTIMAGES = {
    MODULE: '5c6cd28e95b3ff48d97157b263ff49b87a8eeb1fda44487b403145d43b0a3874',
    ABILITY: 'ada4728994501933eda37db97b7d75cf5c989394db6e39b3ebbe3c40f5db328b',
    PAGE: 'fa7dff6f63d47401de32869f69d95c23ba4040dac0951156c1072474e9240709',
    BUSINESS: '6f449f25261bbbdf9fa4c63a1a1151720528095dd8226d8fd614062239682dfb',
}


class CalendarSharedStorageTests(unittest.TestCase):
    def fixture(self):
        case = existing.CalendarMainTests()
        case.setUp()
        self.addCleanup(case.doCleanups)
        return case

    def verifier(self):
        return existing.load(COMPONENT / 'verify_source.py', 'calendar_shared_storage_guard')

    def states(self):
        # Keep the old original -> F fixture as historical evidence. Business
        # goldens extend it; replacing that fixture would erase the F regression.
        path = ROOT / 'ci/capability-audit/fixtures/batch_system/calendar_main/main-component-hashes.json'
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), HISTORICAL_F_FIXTURE_SHA)
        rows = json.loads(path.read_text())
        self.assertEqual({row[0] for row in rows}, {MODULE, ABILITY, PAGE, READER, PRODUCER})
        original = {name: before for name, before, after in rows}
        shared = {name: after for name, before, after in rows}
        original[BUSINESS] = None
        shared[BUSINESS] = None
        legacy = dict(shared)
        legacy[PAGE] = E_PAGE_SHA
        final = dict(shared)
        final.update(BUSINESS_POSTIMAGES)
        business = dict(final)
        business[BUSINESS] = 'e0cc534fc0f8a90eca0e2ff87a48bd5e8ea23f86729bff4a361aae77cde49619'
        return {'original': original, 'prefix1': legacy, 'prefix2': shared, 'prefix3': business, 'final': final}

    def assert_state(self, case, state):
        guard = self.verifier()
        self.assertEqual(guard.source_state(case.root), state)
        expected = self.states()[state]
        actual = {name: hashlib.sha256((case.project / name).read_bytes()).hexdigest()
                  if (case.project / name).exists() else None for name in expected}
        self.assertEqual(actual, expected)
        self.assertEqual(guard.validate(case.root), state == 'final')
        if state == 'final':
            self.assertTrue(guard.validate(case.root, require_patched=True))
        else:
            with self.assertRaises(ValueError):
                guard.validate(case.root, require_patched=True)

    def apply_patch(self, case, filename, sha):
        patch = COMPONENT / filename
        self.assertEqual(hashlib.sha256(patch.read_bytes()).hexdigest(), sha)
        for flags in (['--check'], []):
            result = subprocess.run(['git', '-C', str(case.root), 'apply', *flags, str(patch)],
                                    capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def legacy(self, case):
        self.apply_patch(case, '0001-route-real-calendar-reminders-to-source-provider.patch', OLD_PATCH_SHA)

    def shared_only(self, case):
        self.apply_patch(case, '0002-bind-viewer-to-ability-local-storage.patch', SHARED_PATCH_SHA)

    def assert_transition(self, before, after, modified, created=()):
        self.assertEqual({name for name in before.keys() & after.keys() if before[name] != after[name]}, modified)
        self.assertEqual(after.keys() - before.keys(), set(created))
        self.assertEqual(before.keys() - after.keys(), set())

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
        case = self.fixture()
        self.assert_state(case, 'original')
        before = case.snapshot()
        result = case.run_component('main_ui')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_state(case, 'final')
        self.assert_transition(before, case.snapshot(), {MODULE, ABILITY, PAGE, PRODUCER}, {READER, BUSINESS})
        self.assertIn('@Entry({ useSharedStorage: true })', (case.project / PAGE).read_text())
        snapshot = case.snapshot()
        self.assertEqual(case.run_component('main_ui').returncode, 0)
        self.assertEqual(snapshot, case.snapshot())

    def test_complete_E_is_only_prefix_and_upgrades_without_reapplying_patch1(self):
        case = self.fixture()
        self.legacy(case)
        self.assert_state(case, 'prefix1')
        legacy = case.snapshot()
        # Preserve the original F repair as its own exact transition: 0002
        # changes only PAGE, with no business source or WRITE scene added.
        self.shared_only(case)
        self.assert_state(case, 'prefix2')
        shared = case.snapshot()
        self.assert_transition(legacy, shared, {PAGE})
        self.assertEqual(legacy[PAGE].replace(b'@Entry\n', b'@Entry({ useSharedStorage: true })\n'), shared[PAGE])
        result = case.run_component('main_ui')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assert_state(case, 'final')
        self.assert_transition(shared, case.snapshot(), {MODULE, ABILITY, PAGE}, {BUSINESS})

    def test_mixed_original_and_E_is_rejected_without_publication(self):
        case = self.fixture()
        original = case.snapshot()
        self.legacy(case)
        (case.project / MODULE).write_bytes(original[MODULE])
        before = case.snapshot()
        self.assertNotEqual(case.run_component('main_ui').returncode, 0)
        self.assertEqual(before, case.snapshot())

    def test_complete_E_replays_parents_before_product_order_upgrade(self):
        for state in ('prefix1', 'prefix2', 'prefix3'):
            with self.subTest(predecessor=state):
                case = self.fixture()
                self.legacy(case)
                if state in ('prefix2', 'prefix3'):
                    self.shared_only(case)
                if state == 'prefix3':
                    self.apply_patch(case, '0003-integrate-calendar-browsing-and-explicit-user-crud.patch',
                                     'fc3fc82a57ed29c25e7364291968d4afb96d6ea8dbe513673f2a77c0df78e971')
                self.assert_state(case, state)
                before = case.snapshot()
                for name in ('event_editor', 'editor_callback_dispatch'):
                    result = case.run_component(name)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertEqual(before, case.snapshot())
                # Direct E and direct F upgrades must reach the identical final.
                # Reapplying patch1 would fail; the exact installer chooses its suffix.
                result = case.run_component('main_ui')
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assert_state(case, 'final')
                if state == 'prefix3':
                    self.assert_transition(before, case.snapshot(), {BUSINESS})
                else:
                    self.assert_transition(before, case.snapshot(), {MODULE, ABILITY, PAGE}, {BUSINESS})
                final = case.snapshot()
                for name in ('event_editor', 'editor_callback_dispatch', 'main_ui'):
                    result = case.run_component(name)
                    self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                    self.assertEqual(final, case.snapshot())

    def test_parent_replay_rejects_foreign_viewer_native_or_identity_without_writes(self):
        for state in ('prefix1', 'prefix2', 'prefix3', 'final'):
            case = self.fixture()
            self.legacy(case)
            if state in ('prefix2', 'prefix3'):
                self.shared_only(case)
            if state == 'prefix3':
                self.apply_patch(case, '0003-integrate-calendar-browsing-and-explicit-user-crud.patch',
                                 'fc3fc82a57ed29c25e7364291968d4afb96d6ea8dbe513673f2a77c0df78e971')
            elif state == 'final':
                self.assertEqual(case.run_component('main_ui').returncode, 0)
            self.assert_state(case, state)
            for name in (PAGE, MODULE, 'calendarmanager/napi/src/calendar_manager_napi.cpp', 'AppScope/app.json5'):
                with self.subTest(state=state, file=name):
                    target = case.project / name
                    original = target.read_bytes()
                    target.write_bytes(original + b'\n// foreign edit\n')
                    before = case.snapshot()
                    self.assertNotEqual(case.run_component('event_editor').returncode, 0)
                    self.assertEqual(before, case.snapshot())
                    target.write_bytes(original)

    def test_unknown_E_page_is_rejected_without_publication(self):
        for state in ('prefix1', 'prefix2', 'prefix3', 'final'):
            with self.subTest(state=state):
                case = self.fixture()
                self.legacy(case)
                if state in ('prefix2', 'prefix3'):
                    self.shared_only(case)
                if state == 'prefix3':
                    self.apply_patch(case, '0003-integrate-calendar-browsing-and-explicit-user-crud.patch',
                                     'fc3fc82a57ed29c25e7364291968d4afb96d6ea8dbe513673f2a77c0df78e971')
                elif state == 'final':
                    self.assertEqual(case.run_component('main_ui').returncode, 0)
                self.assert_state(case, state)
                page = case.project / PAGE
                page.write_bytes(page.read_bytes() + b'\n// foreign edit\n')
                before = case.snapshot()
                self.assertNotEqual(case.run_component('main_ui').returncode, 0)
                self.assertEqual(before, case.snapshot())

    def test_source_manifest_and_fixture_pin_complete_states_and_patch_bytes(self):
        guard = self.verifier()
        path = COMPONENT / 'source_states.json'
        data = json.loads(path.read_text())
        self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), guard.MANIFEST_SHA256)
        self.assertEqual(data['states'], self.states())
        self.assertEqual(data['states']['original'], {n: before for n, before, after in guard.FILES})
        self.assertEqual(data['states']['final'], {n: after for n, before, after in guard.FILES})
        self.assertEqual({name for name in data['states']['prefix1']
                          if data['states']['prefix1'][name] != data['states']['prefix2'][name]}, {PAGE})
        self.assertEqual({name for name in data['states']['prefix2']
                          if data['states']['prefix2'][name] != data['states']['final'][name]},
                         {MODULE, ABILITY, PAGE, BUSINESS})
        self.assertEqual({name for name in data['states']['prefix3']
                          if data['states']['prefix3'][name] != data['states']['final'][name]}, {BUSINESS})
        self.assertEqual(data['patches_sha256'], {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in sorted(COMPONENT.glob('[0-9][0-9][0-9][0-9]-*.patch'))})
        for name, sha in data['actual_E_prefix_source']['files'].items():
            self.assertEqual(data['states']['prefix1'][name], sha)


if __name__ == '__main__':
    unittest.main()
