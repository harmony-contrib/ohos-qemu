"""Actual patch lifecycle under host doubles; no real pixel/permission claim."""
import hashlib
import importlib.util
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

from test_access_token_kernel import compile_run, patch_sections

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/foundation/barrierfree/accessibility/screen_blink'
PATCH = COMPONENT / '0001-connect-public-blink-controls-to-owned-screen-worker.patch'
PROJECT = 'foundation/barrierfree/accessibility'


def baseline(path):
    spec = importlib.util.spec_from_file_location('blink_test_baseline', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ScreenBlinkTests(unittest.TestCase):
    def test_actual_worker_lifecycle_ownership_failure_and_late_timeout_cancellation(self):
        sections = patch_sections(PATCH)
        actual = ''
        for relative in ('services/aams/include/accessibility_blink_controller.h',
                         'services/aams/src/accessibility_blink_controller.cpp'):
            hunks = sections[PROJECT + '/' + relative]
            self.assertEqual(len(hunks), 1)
            self.assertEqual(hunks[0][1], [])
            actual += '\n'.join(hunks[0][2]) + '\n'
        actual = re.sub(r'^#include "[^"\n]+"\n', '', actual, flags=re.M)
        fixture = (Path(__file__).with_name('screen_blink_backend_fixture.cpp')).read_text()
        compile_run(fixture.replace('// __ACTUAL_HEADER_AND_IMPLEMENTATION__', actual), language='c++')

    def test_component_atomic_exact_replay_and_unknown_or_partial_rejection(self):
        original_baseline = baseline(COMPONENT / 'verify_source.py')
        sections = patch_sections(PATCH)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            originals = {}
            for relative, old_sha, new_sha in original_baseline.FILES:
                if old_sha is None:
                    continue
                lines = []
                key = PROJECT + '/' + relative
                for line, before, after in sections[key]:
                    self.assertLess(len(lines), line)
                    lines += ['// fixture filler ' + str(i) for i in range(len(lines), line - 1)]
                    lines += before
                value = ('\n'.join(lines) + '\n').encode()
                section = next(s for s in PATCH.read_text().split('diff --git ')[1:] if '+++ b/' + key + '\n' in s)
                if '\\ No newline at end of file' in section:
                    value = value.rstrip(b'\n')
                target = root / key
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(value)
                originals[relative] = value
            subprocess.run(['git', '-C', str(root), 'apply', str(PATCH)], check=True, capture_output=True)
            repaired = {relative: (root / PROJECT / relative).read_bytes()
                        for relative, _, _ in original_baseline.FILES}
            component = root / 'recipe' / COMPONENT.relative_to(ROOT)
            shutil.copytree(COMPONENT, component)
            shutil.copytree(ROOT / 'patches/lib', root / 'recipe/patches/lib')
            verifier = component / 'verify_source.py'
            value = verifier.read_text()
            for relative, old_sha, new_sha in original_baseline.FILES:
                if old_sha is not None:
                    value = value.replace(old_sha, hashlib.sha256(originals[relative]).hexdigest())
                value = value.replace(new_sha, hashlib.sha256(repaired[relative]).hexdigest())
            verifier.write_text(value)
            for relative, old_sha, _ in original_baseline.FILES:
                target = root / PROJECT / relative
                if old_sha is None:
                    target.unlink()
                else:
                    target.write_bytes(originals[relative])
            command = ['bash', str(component / 'apply.sh'), '--source-root', str(root)]
            for _ in range(2):
                subprocess.run(command, check=True, capture_output=True)
            self.assertEqual({relative: (root / PROJECT / relative).read_bytes() for relative in repaired}, repaired)
            predecessor = component.parent / 'api26_blink_enums'
            shutil.copytree(COMPONENT.parent / 'api26_blink_enums', predecessor)
            native = 'interfaces/kits/napi/accessibility_config/src/native_module.cpp'
            final_sha = next(new for name, _, new in original_baseline.FILES if name == native)
            previous_validator = predecessor / 'verify_source.py'
            previous_validator.write_text(previous_validator.read_text().replace(
                final_sha, hashlib.sha256(repaired[native]).hexdigest()))
            replay = ['bash', str(predecessor / 'apply.sh'), '--source-root', str(root)]
            subprocess.run(replay, check=True, capture_output=True)
            target = root / PROJECT / 'services/aams/src/accessibility_blink_controller.cpp'
            target.write_bytes(target.read_bytes() + b'// unrelated edit\n')
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertNotEqual(subprocess.run(replay, capture_output=True).returncode, 0)
            target.unlink()
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertNotEqual(subprocess.run(replay, capture_output=True).returncode, 0)

    def test_identity_is_server_supplied_and_checks_precede_backend(self):
        changes = '\n'.join(line[1:] for line in PATCH.read_text().splitlines()
                            if line.startswith('+') and not line.startswith('+++'))
        service = changes[changes.index('ErrCode AccessibleAbilityManagerService::ControlBlinking'):]
        self.assertLess(service.index('IsSystemApp()'), service.index('CheckPermission('))
        self.assertLess(service.index('CheckPermission('), service.index('IPCSkeleton::GetCallingPid()'))
        self.assertLess(service.index('IPCSkeleton::GetCallingPid()'), service.index('blink->Control('))
        self.assertIn('void ControlBlinking([in] boolean start, [in] int mode, [in] int scenario, [out] int blinkResult);', changes)
        for forbidden in ('SetSkipCheckInMultiInstance', 'ResetCallingIdentity', 'SetCallingIdentity', 'chmod(', 'setuid('):
            self.assertNotIn(forbidden, changes)
        plan = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        self.assertEqual(plan.count('bash "${ACCESSIBILITY_SCREEN_BLINK_SCRIPT}" --source-root'), 1)


if __name__ == '__main__':
    unittest.main()
