"""Pinned stack integrity and source boundaries, never guest permission proof."""
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
COMPONENT = REPO / 'patches/2in1/base/busmanager/serial_manager'
sys.path.insert(0, str(COMPONENT))
SPEC = importlib.util.spec_from_file_location('serial_stack', COMPONENT / 'apply_stack.py')
STACK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(STACK)


class SerialStackTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='serial-stack-unit-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repository = self.root / 'upstream'
        self.repository.mkdir()
        subprocess.run(['git', 'init', '-q', str(self.repository)], check=True)
        (self.repository / 'input.txt').write_text('fixed\n')
        subprocess.run(['git', '-C', str(self.repository), 'add', 'input.txt'], check=True)
        subprocess.run(['git', '-C', str(self.repository), '-c', 'user.name=Serial fixture',
                        '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture'], check=True)
        self.revision = subprocess.check_output(['git', '-C', str(self.repository), 'rev-parse', 'HEAD'], text=True).strip()
        self.previous_revision = STACK.REVISION
        STACK.REVISION = self.revision
        self.addCleanup(setattr, STACK, 'REVISION', self.previous_revision)
        self.component = self.root / 'patches'
        self.component.mkdir()
        relative = str(STACK.DESTINATION / 'input.txt')
        for index, before, after in ((1, 'fixed', 'first'), (2, 'first', 'final')):
            (self.component / ('000{}-fixture.patch'.format(index))).write_text(
                'diff --git a/{0} b/{0}\n--- a/{0}\n+++ b/{0}\n@@ -1 +1 @@\n-{1}\n+{2}\n'.format(
                    relative, before, after))
        self.source = self.root / 'source'
        target = self.source / STACK.DESTINATION
        target.mkdir(parents=True)
        self.input = target / 'input.txt'
        self.input.write_text('fixed\n')

    def test_apply_and_repeat_overlapping_stack(self):
        STACK.apply_stack(self.source, self.repository, self.component)
        self.assertEqual(self.input.read_text(), 'final\n')
        STACK.apply_stack(self.source, self.repository, self.component)
        self.assertEqual(self.input.read_text(), 'final\n')

    def test_complete_only_remaining_prefix(self):
        self.input.write_text('first\n')
        STACK.apply_stack(self.source, self.repository, self.component)
        self.assertEqual(self.input.read_text(), 'final\n')

    def test_stale_marker_cannot_hide_foreign_change(self):
        self.input.write_text('foreign user bytes\n')
        marker = self.source / '.ohos-qemu-patches'
        marker.mkdir()
        (marker / 'stale.applied').write_text('already applied\n')
        with self.assertRaisesRegex(ValueError, 'refusing all writes'):
            STACK.apply_stack(self.source, self.repository, self.component)
        self.assertEqual(self.input.read_text(), 'foreign user bytes\n')

    def test_reject_component_escape(self):
        outside = self.component / '0003-outside.patch'
        outside.write_text('diff --git a/other/input.txt b/other/input.txt\n')
        with self.assertRaisesRegex(ValueError, 'inside its fixed component'):
            STACK.apply_stack(self.source, self.repository, self.component)
        self.assertEqual(self.input.read_text(), 'fixed\n')

    def test_refuse_linked_stack_lock_without_touching_external_file(self):
        outside = self.root / 'outside.txt'
        outside.write_text('preserve external data\n')
        (self.input.parent / '.ohos-qemu-stack.lock').symlink_to(outside)
        with self.assertRaisesRegex(ValueError, 'lock must not escape'):
            STACK.apply_stack(self.source, self.repository, self.component)
        self.assertEqual(outside.read_text(), 'preserve external data\n')
        self.assertEqual(self.input.read_text(), 'fixed\n')


class GrantSourceBoundaryTest(unittest.TestCase):
    def test_real_grant_and_wait_share_captured_connection_state(self):
        patch = (COMPONENT / '0002-complete-only-the-verified-captured-grant.patch').read_text()
        self.assertIn('return pendingConnection_->AcceptAuthorization', patch)
        self.assertIn('std::lock_guard<std::mutex> guard(remoteMutex_)', patch)
        self.assertIn('!SerialRightManager::GetInstance().AddDeviceRight(deviceId_', patch)
        self.assertIn('std::chrono::steady_clock::now() >= deadline_', patch)
        self.assertIn('userId_ != userId', patch)
        self.assertIn('GrantCompletesWithoutParentDisconnect', patch)
        self.assertIn('TimedOutCapturedConnectionCannotGrant', patch)
        self.assertIn('DisconnectedCapturedConnectionCannotGrant', patch)
        self.assertIn('ImmutableConnectionRejectsRetargetedPendingTuple', patch)
        self.assertNotIn('interfaces/innerkits/ISerialServer.idl', patch)
        self.assertNotIn('SetSelfTokenID', patch)


if __name__ == '__main__':
    unittest.main()
