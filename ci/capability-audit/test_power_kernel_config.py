"""Power patch/config fixtures only; no guest sleep or wake claims."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from check_power_kernel_config import REQUIRED, resolved_config
from test_access_token_kernel import patch_sections

ROOT = Path(__file__).resolve().parents[2]
COMPONENTS = ('common/device/qemu/power_wakelocks',
              'common/kernel/linux/linux_6_6/qemu_power_button',
              'common/kernel/linux/linux_6_6/qemu_virtio_gpu_s2idle')


class PowerKernelTests(unittest.TestCase):
    def test_real_dependencies_limits_and_duplicate_rejection(self):
        text = '\n'.join(key + '=' + value for key, value in REQUIRED.items()) + '\n# CONFIG_PM_AUTOSLEEP is not set\n'
        self.assertEqual(resolved_config(text)['CONFIG_PM_WAKELOCKS'], 'y')
        for key in REQUIRED:
            with self.assertRaises(ValueError):
                resolved_config(text.replace(key + '=' + REQUIRED[key], '# ' + key + ' is not set'))
        for wrong in (text + 'CONFIG_PM_WAKELOCKS=y\n', text.replace('LIMIT=100', 'LIMIT=0'),
                      text.replace('# CONFIG_PM_AUTOSLEEP is not set', 'CONFIG_PM_AUTOSLEEP=y')):
            with self.assertRaises(ValueError):
                resolved_config(wrong)

    def test_components_are_idempotent_and_actual_patch_is_reversible(self):
        for name in COMPONENTS:
            component = ROOT / 'patches' / name
            patch = next(component.glob('0001-*.patch'))
            with tempfile.TemporaryDirectory() as directory:
                root = Path(directory).resolve()
                for relative, hunks in patch_sections(patch).items():
                    lines = ['# isolated fixture\n'] * max(start + len(old) for start, old, _ in hunks)
                    for start, old, _ in hunks:
                        lines[start - 1:start - 1 + len(old)] = [line + '\n' for line in old]
                    path = root / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text(''.join(lines))
                argv = ['bash', str(component / 'apply.sh'), '--source-root', str(root)]
                subprocess.run(argv, check=True, capture_output=True)
                subprocess.run(argv, check=True, capture_output=True)
                subprocess.run(['git', '-C', str(root), 'apply', '--reverse', '--check', str(patch)],
                               check=True, capture_output=True)

    def test_wakeup_scope_does_not_extend_to_other_boards_or_keys(self):
        component = ROOT / 'patches' / COMPONENTS[1]
        text = next(component.glob('0001-*.patch')).read_text()
        for required in ('is_of_node(child)', 'of_machine_is_compatible("linux,dummy-virt")',
                         'of_node_name_eq(to_of_node(child), "poweroff")',
                         'button->type == EV_KEY && button->code == KEY_POWER'):
            self.assertIn(required, text)
        self.assertNotIn('pm_system_wakeup(', text)
        self.assertNotIn('IRQF_NO_SUSPEND', text)

    def test_both_components_precede_kernel_input_inventory_and_traversal(self):
        builder = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        for name in ('QEMU_POWER_WAKELOCKS_COMPONENT_SCRIPT', 'QEMU_POWER_BUTTON_COMPONENT_SCRIPT',
                     'QEMU_VIRTIO_GPU_S2IDLE_COMPONENT_SCRIPT'):
            self.assertLess(builder.index('bash "${' + name + '}"'), builder.index('  configure_qemu_device_profile\n'))
        self.assertIn('kernel_input_evidence.py', builder)

    def test_gpu_quirk_only_preserves_qemu_s2idle_with_no_driver_pm(self):
        text = next((ROOT / 'patches' / COMPONENTS[2]).glob('0001-*.patch')).read_text()
        for guard in ('pm_suspend_target_state != PM_SUSPEND_TO_IDLE',
                      'vdev->id.device != VIRTIO_ID_GPU',
                      'of_machine_is_compatible("linux,dummy-virt")',
                      'strcmp(vendor, "QEMU")', '!drv->freeze && !drv->restore'):
            self.assertIn(guard, text)
        for callback in ('freeze', 'poweroff'):
            self.assertIn('.' + callback + ' = virtio_pci_freeze', text)
        for callback in ('thaw', 'restore'):
            self.assertIn('.' + callback + ' = virtio_pci_restore', text)
        self.assertNotIn('VIRTIO_GPU_CMD_STATUS_FREEZING', text)


if __name__ == '__main__':
    unittest.main()
