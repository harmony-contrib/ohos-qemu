"""Execute patched fixed-release service code with host-only backend doubles."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / 'ci/capability-audit/fixtures/batch_apps/accessibility_service'
COMPONENT = ROOT / 'patches/common/applications/standard/settings/accessibility_service_completion'
RELATIVE = ('applications/standard/settings/product/phone/src/main/ets/Setting/Accessibility/'
            'service/IgnoreRepeatClickService.ets')


def executable_source(source):
    """Erase type syntax only; retain the entire actual service class and methods."""
    source = re.sub(r'^import .*?;\n', '', source, flags=re.MULTILINE)
    source = source.replace('export default class', 'class')
    source = re.sub(r'\bprivate ', '', source)
    source = re.sub(r': (?:Promise<void>|Want|number|string|boolean|void)(?=\s*[,)=;{])', '', source)
    return source


class AccessibilityServiceCompletionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='batch-apps-a11y-service-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.target = self.root / RELATIVE
        self.target.parent.mkdir(parents=True)
        self.original = (FIXTURE / 'IgnoreRepeatClickService.before.ets').read_bytes()
        self.target.write_bytes(self.original)

    def apply(self):
        return subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(self.root)],
                              capture_output=True, text=True)

    def exercise(self, scenario):
        js = self.root / 'service.js'
        js.write_text(executable_source(self.target.read_text()))
        return subprocess.run(['node', '--unhandled-rejections=strict', str(FIXTURE / 'exercise.cjs'),
                               str(js), scenario], capture_output=True, text=True)

    def test_fixture_provenance_and_exact_patch_idempotence(self):
        provenance = json.loads((FIXTURE / 'provenance.json').read_text())
        self.assertEqual(hashlib.sha256(self.original).hexdigest(), provenance['sha256'])
        self.assertEqual(self.apply().returncode, 0)
        patched = self.target.read_bytes()
        self.assertEqual(hashlib.sha256(patched).hexdigest(), provenance['patched_sha256'])
        self.assertEqual(self.apply().returncode, 0)
        self.assertEqual(patched, self.target.read_bytes())

    def test_baseline_reproduces_premature_cache_and_event_success(self):
        result = self.exercise('pending_success')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('cache must not anticipate backend completion', result.stderr)

    def test_patch_drift_and_symlink_fail_before_writing(self):
        edited = self.original.replace(b'config.ignoreRepeatClick.set(false)', b'config.ignoreRepeatClick.set(true)')
        self.target.write_bytes(edited)
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertEqual(self.target.read_bytes(), edited)
        saved = self.target.with_suffix('.saved')
        self.target.rename(saved)
        self.target.symlink_to(saved)
        self.assertNotEqual(self.apply().returncode, 0)
        self.assertEqual(saved.read_bytes(), edited)

    def test_real_service_body_success_failures_queue_reentry_and_lifetime(self):
        result = self.apply()
        self.assertEqual(result.returncode, 0, result.stderr)
        for scenario in ('pending_success', 'animation_success', 'async_rejection', 'sync_throw',
                         'queued', 'reentrant', 'failure_then_queued', 'notification_actions',
                         'notification_failure', 'unknown_action', 'destroy_before_dispatch',
                         'destroy_queued_success', 'destroy_queued_rejection', 'recreate_epoch'):
            with self.subTest(scenario=scenario):
                result = self.exercise(scenario)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                self.assertEqual(result.stdout.strip(), 'PASS ' + scenario)


if __name__ == '__main__':
    unittest.main()
