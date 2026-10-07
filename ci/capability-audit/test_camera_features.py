"""Camera selection/inheritance tests; not device or public API acceptance."""
import copy
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'patches/lib'))
from camera_features import validate

BOARD = REPO / 'patches/common/vendor/ohemu/camera_profile'
HAL = REPO / 'patches/common/drivers/peripheral/camera/usb_backend'


def load(path):
    spec = importlib.util.spec_from_file_location('camera_test_' + path.parent.name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CameraFeatureTests(unittest.TestCase):
    def test_generated_pipeline_patch_has_explicit_product_gen_sources_and_is_reversible(self):
        module = load(HAL / 'check.py')
        patch = HAL / '0002-generate-usb-pipeline-config-in-product-out.patch'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            originals = {}
            for section in patch.read_text().split('diff --git ')[1:]:
                name = section.split('+++ b/')[1].splitlines()[0]
                hunks = list(re.finditer(r'^@@ -(\d+),(\d+) \+\d+,\d+ @@\n(.*?)(?=^@@|\Z)', section, re.M | re.S))
                lines = ['# patch-context fixture only\n'] * max(int(h[1]) + int(h[2]) for h in hunks)
                for hunk in hunks:
                    old = [line[1:] + '\n' for line in hunk[3].splitlines() if line.startswith((' ', '-'))]
                    self.assertEqual(len(old), int(hunk[2]))
                    start = int(hunk[1]) - 1
                    lines[start:start + len(old)] = old
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(''.join(lines))
                originals[path] = path.read_bytes()
            # Match the production component helper's git apply, not macOS
            # BSD patch's deletion-hunk matching semantics.
            command = ['git', '-C', str(root), 'apply', '--whitespace=nowarn', str(patch)]
            result = subprocess.run(command, cwd=root, capture_output=True, text=True)
            rejects = ''.join(path.read_text() for path in root.rglob('*.rej'))
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr + rejects)
            for path, original in originals.items():
                transform = module.generated_config if path.parent.name == 'camera_config' else module.generated_pipeline
                repaired = path.read_bytes()
                self.assertEqual(repaired, transform(original))
                if path.parent.name == 'camera_config':
                    self.assertNotIn(b'"touch"', repaired)
                    self.assertNotIn(b'action("copy_source")', repaired)
                else:
                    self.assertIn(b'"$camera_config_gen_dir/config.c"', repaired)
                    self.assertIn(b'"$camera_config_gen_dir/params.c"', repaired)
                    self.assertNotIn(b'get_target_outputs(', repaired)
                    self.assertIn(b'"$camera_path_usb/camera_config:generate_source"', repaired)
            subprocess.run(command + ['--reverse'], cwd=root, check=True, capture_output=True)
            self.assertTrue(all(path.read_bytes() == original for path, original in originals.items()))

    def test_missing_emulator_defines_fix_preserves_existing_lists(self):
        module = load(HAL / 'check.py')
        original = b'  if (!is_emulator) {\n    defines = []\n  }\n'
        self.assertEqual(module.adapter_defines(original),
                         b'  if (!is_emulator || !defined(defines)) {\n    defines = []\n  }\n')
        for emulator in (False, True):
            for defined in (False, True):
                initialize = not emulator or not defined
                self.assertEqual(initialize, not (emulator and defined))
        with self.assertRaises(ValueError): module.adapter_defines(b'unknown user edit')

    def test_phone_requires_exact_real_vdi_config_and_no_express_protocol(self):
        features = {
            'drivers_peripheral_camera_feature_usb': True,
            'drivers_peripheral_camera_use_commom_usb_camera_host_config': True,
            'drivers_peripheral_camera_qemu_vivid_capture': True,
            'drivers_peripheral_camera_v4l2_emulator': False,
        }
        validate(features, 'phone')
        for key, expected in features.items():
            for wrong in (not expected, None, str(expected).lower(), int(expected)):
                with self.subTest(key=key, wrong=wrong), self.assertRaises(ValueError):
                    validate({**features, key: wrong}, 'phone')
            with self.assertRaises(ValueError):
                validate({k: v for k, v in features.items() if k != key}, 'phone')
        validate({}, '2in1')
        with self.assertRaises(ValueError): validate(features, 'tablet')

    def test_board_migration_is_optional_arm32_idempotent_and_preserves_neighbors(self):
        module = load(BOARD / 'check.py')
        neighbor = {'component': 'drivers_devhost', 'features': ['preserve = true']}
        for arm32 in (False, True):
            with self.subTest(arm32=arm32), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                products = ['qemu_arm64_linux_full', 'qemu_x86_64_linux_full']
                if arm32: products += ['qemu_armv7a_linux_full']
                paths = []
                for product in products + ['virt']:
                    path = root / 'vendor/ohemu' / product / ('virt_common.json' if product == 'virt' else 'config.json')
                    path.parent.mkdir(parents=True)
                    part = module.BOARD if product == 'virt' else module.LOCAL
                    path.write_text(json.dumps({'subsystems': [{'subsystem': 'hdf', 'components': [neighbor, part, neighbor]}]}, indent=2) + '\n')
                    paths.append(path)
                command = ['bash', str(BOARD / 'apply.sh'), '--source-root', str(root)]
                subprocess.run(command, check=True, capture_output=True)
                once = [p.read_bytes() for p in paths]
                subprocess.run(command, check=True, capture_output=True)
                self.assertEqual(once, [p.read_bytes() for p in paths])
                module.validate(root, patched=True)
                for path in paths:
                    parts = json.loads(path.read_text())['subsystems'][0]['components']
                    self.assertEqual([p for p in parts if p['component'] != module.PART], [neighbor, neighbor])

    def test_unknown_board_edit_or_symlink_is_rejected_before_mutation(self):
        module = load(BOARD / 'check.py')
        for broken in ('unknown', 'duplicate', 'symlink'):
            with self.subTest(broken=broken), tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                paths = []
                for product in ('qemu_arm64_linux_full', 'qemu_x86_64_linux_full', 'virt'):
                    path = root / 'vendor/ohemu' / product / ('virt_common.json' if product == 'virt' else 'config.json')
                    path.parent.mkdir(parents=True)
                    part = copy.deepcopy(module.BOARD if product == 'virt' else module.LOCAL)
                    path.write_text(json.dumps({'subsystems': [{'subsystem': 'hdf', 'components': [part]}]}, indent=2) + '\n')
                    paths.append(path)
                original = json.loads(paths[0].read_text())
                if broken == 'unknown': original['subsystems'][0]['components'][0]['features'].append('preserve_user_edit = true')
                elif broken == 'duplicate': original['subsystems'][0]['components'].append(module.LOCAL)
                else:
                    renamed = paths[0].with_suffix('.owned')
                    paths[0].rename(renamed)
                    paths[0].symlink_to(renamed)
                if broken != 'symlink': paths[0].write_text(json.dumps(original))
                before = [p.read_bytes() for p in paths]
                run = subprocess.run(['bash', str(BOARD / 'apply.sh'), '--source-root', str(root)], capture_output=True)
                self.assertNotEqual(run.returncode, 0)
                self.assertEqual(before, [p.read_bytes() for p in paths])

    def test_x86_portable_hal_change_is_exact_and_reversible(self):
        module = load(HAL / 'check.py')
        original = ('  group("camera_hal") {\n    ' + module.OLD.decode() + '\n      deps = []\n  }\n'
                    + '  group("camera_hal_unittest") {\n    ' + module.OLD.decode() + '\n      deps = []\n  }\n').encode()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'drivers/peripheral/camera/BUILD.gn'
            path.parent.mkdir(parents=True)
            path.write_bytes(original)
            patch = HAL / '0001-build-real-usb-camera-on-x86-64.patch'
            command = ['patch', '--batch', '--fuzz=0', '-p1', '-i', str(patch)]
            subprocess.run(command, cwd=root, check=True, capture_output=True)
            self.assertEqual(path.read_bytes(), module.repaired(original))
            subprocess.run(command + ['-R'], cwd=root, check=True, capture_output=True)
            self.assertEqual(path.read_bytes(), original)
        with self.assertRaises(ValueError): module.repaired(original.replace(module.OLD, b'unknown', 1))

    def test_current_builder_applies_before_profile_and_validates_current_preload(self):
        script = (REPO / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        applied = script.index('bash "${QEMU_CAMERA_PROFILE_COMPONENT_SCRIPT}" --source-root')
        self.assertLess(applied, script.index('  configure_qemu_device_profile', applied))
        self.assertIn('python3 "${PATCH_ROOT}/lib/camera_features.py"', script)
        profile = (REPO / 'patches/phone/product_profile/apply.py').read_text()
        self.assertIn('"drivers_peripheral_camera_feature_usb": True', profile)
        self.assertIn('"drivers_peripheral_camera_use_commom_usb_camera_host_config": True', profile)
        self.assertIn('"drivers_peripheral_camera_v4l2_emulator": False', profile)


if __name__ == '__main__':
    unittest.main()
