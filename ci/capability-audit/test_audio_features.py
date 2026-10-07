"""Feature/config regression, not a claim of guest audio behavior."""
import copy
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'patches/lib'))
from audio_features import validate

COMPONENT = REPO / 'patches/common/third_party/alsa-lib/config_install'


class AudioFeatureTests(unittest.TestCase):
    def test_both_profiles_require_explicit_true(self):
        features = {'drivers_peripheral_audio_feature_alsa_lib': True, 'alsa_lib_feature_config_enable': True}
        for device in ('phone', '2in1'):
            validate(features, device)
            for key in features:
                for wrong in (False, None, 1, 'true'):
                    broken = copy.deepcopy(features)
                    broken[key] = wrong
                    with self.assertRaises(ValueError): validate(broken, device)
                broken = copy.deepcopy(features)
                del broken[key]
                with self.assertRaises(ValueError): validate(broken, device)
        with self.assertRaises(ValueError): validate(features, 'tablet')

    def test_component_is_complete_idempotent_and_reversible(self):
        patch = (COMPONENT / '0001-install-alsa-config-in-chipset-image.patch').read_text()
        # Reconstruct only a patch-context fixture. This is not the source-tree
        # GN validation (which must run separately with actual pinned inputs).
        hunks = list(re.finditer(r'^@@ -(\d+),3 \+\d+,4 @@\n(.*?)(?=^@@|\Z)', patch, re.M | re.S))
        self.assertEqual(len(hunks), 79)
        lines = ['# fixture only\n'] * (int(hunks[-1][1]) + 3)
        for hunk in hunks:
            context = [line[1:] + '\n' for line in hunk[2].splitlines() if line.startswith(' ')]
            self.assertEqual(len(context), 3)
            offset = int(hunk[1]) - 1
            lines[offset:offset + 3] = context
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'third_party/alsa-lib/src/conf/BUILD.gn'
            source.parent.mkdir(parents=True)
            original = ''.join(lines)
            source.write_text(original)
            command = ['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(root)]
            subprocess.run(command, check=True, capture_output=True)
            once = source.read_bytes()
            self.assertEqual(once.count(b'install_images = [ chipset_base_dir ]'), 79)
            subprocess.run(command, check=True, capture_output=True)
            self.assertEqual(source.read_bytes(), once)
            subprocess.run(['patch', '--batch', '--fuzz=0', '-R', '-p1', '-i',
                            str(COMPONENT / '0001-install-alsa-config-in-chipset-image.patch')],
                           cwd=root, check=True, capture_output=True)
            self.assertEqual(source.read_text(), original)

    def test_build_applies_config_before_current_preload_and_validates_pair(self):
        script = (REPO / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        self.assertIn('bash "${ALSA_CONFIG_INSTALL_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}"', script)
        self.assertIn('python3 "${PATCH_ROOT}/lib/audio_features.py"', script)
        for device in ('phone', '2in1'):
            profile = (REPO / f'patches/{device}/product_profile/apply.py').read_text()
            self.assertIn('add_component(effective, "thirdparty", "alsa-lib")', profile)
            self.assertIn('("thirdparty", "alsa-lib"): {"alsa_lib_feature_config_enable": True}', profile)

    def test_board_migration_preserves_other_local_parts_and_optional_arm32(self):
        component = REPO / 'patches/common/vendor/ohemu/audio_profile'
        for with_arm32 in (False, True):
            with self.subTest(with_arm32=with_arm32), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                vendor = root / 'vendor/ohemu'
                original = {'subsystems': [{'subsystem': 'thirdparty', 'components': [
                    {'component': 'expat', 'features': ['preserve = true']},
                    {'component': 'alsa-lib', 'features': []},
                    {'component': 'alsa-utils', 'features': []}]}]}
                board = {'subsystems': [{'subsystem': 'thirdparty', 'components': [
                    {'component': 'libuv', 'features': ['libuv_use_ffrt = true']}]}]}
                products = ['qemu_arm64_linux_full', 'qemu_x86_64_linux_full']
                if with_arm32: products += ['qemu_armv7a_linux_full']
                paths = [vendor / product / 'config.json' for product in products]
                paths += [vendor / 'virt/virt_common.json']
                for path in paths:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(json.dumps(board if path.name == 'virt_common.json' else original, indent=2) + '\n')
                command = ['bash', str(component / 'apply.sh'), '--source-root', str(root)]
                subprocess.run(command, check=True, capture_output=True)
                once = [path.read_bytes() for path in paths]
                subprocess.run(command, check=True, capture_output=True)
                self.assertEqual(once, [path.read_bytes() for path in paths])
                for path in paths[:-1]:
                    local = json.loads(path.read_text())['subsystems'][0]['components']
                    self.assertEqual(local, [original['subsystems'][0]['components'][index] for index in (0, 2)])
                shared = json.loads(paths[-1].read_text())['subsystems'][0]['components']
                self.assertEqual(shared, [original['subsystems'][0]['components'][1], *board['subsystems'][0]['components']])

    def test_board_migration_rejects_nonempty_user_local_features(self):
        component = REPO / 'patches/common/vendor/ohemu/audio_profile'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for product in ('qemu_arm64_linux_full', 'qemu_x86_64_linux_full'):
                path = root / 'vendor/ohemu' / product / 'config.json'
                path.parent.mkdir(parents=True)
                path.write_text('''{
  "subsystems": [{"subsystem": "thirdparty", "components": [
        {
          "component": "alsa-lib",
          "features": ["keep = true"]
        }
  ]}]
}
''')
            command = ['bash', str(component / 'apply.sh'), '--source-root', str(root)]
            completed = subprocess.run(command, capture_output=True)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn('keep = true', path.read_text())


if __name__ == '__main__':
    unittest.main()
