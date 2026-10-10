"""Backend parser fail-closed fixtures, not runtime evidence."""
from pathlib import Path
import unittest

from verify_thermal_backend import verify

ROOT = Path(__file__).resolve().parents[2]


def added(path):
    return '\n'.join(line[1:] for line in (ROOT / path).read_text().splitlines()
                     if line.startswith('+') and not line.startswith('+++'))


HDI = added('patches/common/drivers/peripheral/thermal/qemu_backend/0002-add-qemu-hdi-config.patch').replace(
    'type="test_battery"', 'type="battery"')
POLICY = added('patches/common/base/powermgr/thermal_manager/qemu_backend/0002-add-qemu-policy.patch')
KERNEL = 'thermal_zone0|battery|2600\n'
SERVICE = 'Type: battery\nTemperature: 2600\n'


class ThermalBackendTests(unittest.TestCase):
    def test_nonzero_equality_is_narrow(self):
        result = verify(HDI, POLICY, KERNEL, SERVICE)
        self.assertEqual(result['kernel_raw_temperature'], 2600)
        self.assertEqual(result['closed'], [])
        self.assertFalse(result['hot_transitions_proven'])

    def test_missing_stale_ambiguous_and_zero_data_rejected(self):
        for kernel, service in (('', SERVICE), (KERNEL, ''), (KERNEL, SERVICE.replace('2600', '0')),
                (KERNEL + KERNEL, SERVICE), (KERNEL, SERVICE + SERVICE),
                (KERNEL.replace('2600', '0'), SERVICE.replace('2600', '0')),
                (KERNEL.replace('battery', 'gpu'), SERVICE),
                (KERNEL, SERVICE + 'Type: gpu\nTemperature: 0\n'),
                (KERNEL, SERVICE + 'Type: gpu\nTemperature: unavailable\n'),
                (KERNEL.replace('2600', '40000'), SERVICE.replace('2600', '40000'))):
            with self.subTest(kernel=kernel, service=service), self.assertRaises(ValueError):
                verify(HDI, POLICY, kernel, service)

    def test_simulation_wrong_sensor_and_changed_thresholds_rejected(self):
        for hdi, policy in ((HDI.replace('sim_tz" value="0', 'sim_tz" value="1'), POLICY),
                (HDI, POLICY.replace('sim_tz" value="0', 'sim_tz" value="1')),
                (HDI.replace('type="battery"', 'type="test_battery"'), POLICY),
                (HDI, POLICY.replace('sensor="battery"', 'sensor="gpu"')),
                (HDI, POLICY.replace('38000', '39000'))):
            with self.assertRaises(ValueError): verify(hdi, policy, KERNEL, SERVICE)


if __name__ == '__main__':
    unittest.main()
