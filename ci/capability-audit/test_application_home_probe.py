"""Named UI/policy fixtures, not guest unlock or package acceptance."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from run_application_home_probe import BUNDLE, DESKTOP, LOCK, LOCK_HOME, SCOPE, prepare, system_screen
from verify_first_artifact_gate import checksum, verified_payload

BOOT = '12345678-1234-1234-1234-123456789abc'


def node(identifier, *, bundle='', **attributes):
    return {'attributes': {'id': identifier, 'bundleName': bundle, 'visible': 'true', 'enabled': 'true',
                           'bounds': '[0,37][1280,800]', **attributes}, 'children': []}


def layout(locked):
    tree = node('', bundle=BUNDLE, bounds='[0,0][1280,800]')
    tree['children'] = [node(LOCK), node(LOCK_HOME)] if locked else [node(DESKTOP)]
    return tree


class Clock:
    def __init__(self):
        self.now = 0

    def __call__(self):
        return self.now

    def sleep(self, value):
        self.now += value


class UiFixture:
    def __init__(self, root, locked=True):
        self.root, self.locked, self.calls = root, locked, []
        self.override = 10000 if locked else None
        self.after_override = None
        self.persist_lock = False
        self.credentials_after = False
        self.changed_boot = False
        self.changed_service = False
        self.swiped = False
        self.sequence = 0

    def shell(self, script, label):
        self.calls.append(script)
        if script == 'cat /proc/sys/kernel/random/boot_id':
            return 'changed' if self.changed_boot and label.endswith('after') else BOOT
        if script == 'pidof render_service; pidof foundation':
            return '999\n584' if self.changed_service and label.endswith('after') else '593\n584'
        if script == 'hidumper -s 3301 -a "-a"':
            override = self.after_override if self.swiped else self.override
            return 'ScreenOffTime: Timeout=9000000ms' + ('  OverrideTimeout=' + str(override) + 'ms' if override else '')
        if script.startswith('uitest uiInput swipe '):
            self.swiped = True
            if not self.persist_lock:
                self.locked = False
            return ''
        raise AssertionError('unexpected setup action: ' + script)

    def layout(self, *, label):
        self.sequence += 1
        tree = layout(self.locked)
        if self.credentials_after and self.swiped:
            tree['children'] = [node('PINInput')]
        path = self.root / (str(self.sequence) + '-fixture-layout.json')
        path.write_text(json.dumps(tree))
        return tree, path

    def screenshot(self, *, label):
        path = self.root / 'fixture-not-real-home.png'
        path.write_bytes(b'named unit screenshot fixture, not a device PNG')
        return path


class ApplicationHomeProbeTests(unittest.TestCase):
    def fixture(self, locked=True):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        ui, clock = UiFixture(root, locked), Clock()
        report = {'scope': SCOPE, 'status': 'fail', 'boot_id': BOOT, 'archive_sha256': 'a' * 64,
                  'privileged_unlock': False, 'power_override_cleared': False, 'failures': []}
        return root, ui, clock, report

    def test_one_real_node_based_swipe_and_system_own_policy_restore(self):
        root, ui, clock, report = self.fixture()
        prepare(ui, report, clock=clock, sleep=clock.sleep)
        self.assertEqual(report['swipe_count'], 1)
        self.assertEqual(report['after_screen'], 'home')
        self.assertEqual(report['policy_after'], {'base_ms': 9000000, 'override_ms': None})
        self.assertEqual([s for s in ui.calls if s.startswith('uitest')], ['uitest uiInput swipe 640 685 640 189'])
        path = root / 'fixture-evidence.json'
        path.write_text(json.dumps(report))
        verified_payload('application-home', path, {'sha256': 'a' * 64}, {'boot_id': BOOT})

    def test_already_home_requires_no_gesture(self):
        _, ui, clock, report = self.fixture(False)
        prepare(ui, report, clock=clock, sleep=clock.sleep)
        self.assertEqual(report['swipe_count'], 0)
        self.assertFalse(any(s.startswith('uitest') for s in ui.calls))

    def test_unknown_other_clients_override_rejected_before_any_gesture(self):
        for locked, override in ((False, 10000), (True, 99), (True, 86400000)):
            _, ui, clock, report = self.fixture(locked)
            ui.override = override
            with self.assertRaisesRegex(ValueError, 'unknown existing power override'):
                prepare(ui, report, clock=clock, sleep=clock.sleep)
            self.assertFalse(any(s.startswith('uitest') or 'power-shell' in s for s in ui.calls))

    def test_remaining_lock_and_credentials_never_trigger_privileged_fallback(self):
        for field in ('persist_lock', 'credentials_after'):
            _, ui, clock, report = self.fixture()
            setattr(ui, field, True)
            with self.assertRaises(ValueError):
                prepare(ui, report, clock=clock, sleep=clock.sleep)
            self.assertEqual(sum(s.startswith('uitest') for s in ui.calls), 1)
            self.assertTrue(all('power-shell' not in s and 'unlock' not in s for s in ui.calls))

    def test_service_restart_kernel_change_and_unrestored_override_fail(self):
        for field, value in (('changed_boot', True), ('changed_service', True), ('after_override', 10000)):
            _, ui, clock, report = self.fixture()
            setattr(ui, field, value)
            with self.assertRaises(ValueError):
                prepare(ui, report, clock=clock, sleep=clock.sleep)
            self.assertEqual(report['status'], 'fail')

    def test_unknown_app_duplicate_disabled_wrong_bundle_and_offscreen_rejected(self):
        variants = []
        for field, value in (('bundleName', 'wrong'), ('visible', 'false'), ('enabled', 'false'),
                             ('bounds', '[0,37][1281,800]')):
            tree = layout(False)
            target = tree if field == 'bundleName' else tree['children'][0]
            target['attributes'][field] = value
            variants.append(tree)
        duplicate = layout(False)
        duplicate['children'].append(node(DESKTOP))
        variants += [duplicate, node('PINInput', bundle=BUNDLE), node('app', bundle='ordinary.app')]
        for tree in variants:
            with self.assertRaises(ValueError):
                system_screen(tree)

    def test_inner_gate_rejects_wrong_boot_other_override_or_changed_raw_layout(self):
        root, ui, clock, report = self.fixture()
        prepare(ui, report, clock=clock, sleep=clock.sleep)
        path = root / 'fixture-evidence.json'
        for change in (lambda d: d.update(boot_id='other'), lambda d: d.update(swipe_count=0),
                       lambda d: d.update(privileged_unlock=True),
                       lambda d: d['policy_before'].update(override_ms=99),
                       lambda d: d['policy_after'].update(override_ms=10000)):
            modified = deepcopy(report)
            change(modified)
            path.write_text(json.dumps(modified))
            with self.assertRaises(ValueError):
                verified_payload('application-home', path, {'sha256': 'a' * 64}, {'boot_id': BOOT})
        Path(report['after_layout']).write_text(json.dumps(layout(True)))
        report['after_layout_sha256'] = checksum(Path(report['after_layout']))
        path.write_text(json.dumps(report))
        with self.assertRaises(ValueError):
            verified_payload('application-home', path, {'sha256': 'a' * 64}, {'boot_id': BOOT})


if __name__ == '__main__':
    unittest.main()
