"""Execute the real profile-gated builder hook; not Serial runtime acceptance."""
import importlib.util
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT / 'scripts/build_standard_qemu_in_docker.sh'
HOOK = BUILDER.read_text().split('apply_qemu_serial_components() {', 1)[1].split(
    '\n}\n\napply_armv7a_product_component()', 1)[0]
COMPONENTS = ('METADATA', 'MANAGER', 'DIALOG', 'DEVICES', 'USB_ENDPOINT')


class SerialBuilderWiringTests(unittest.TestCase):
    def invoke(self, device='2in1', profile='1', missing=False, failure=None):
        with tempfile.TemporaryDirectory() as temporary:
            work = Path(temporary)
            cache, source, logs = work / 'cache', work / 'source', work / 'logs'
            source.mkdir()
            logs.mkdir()
            if not missing:
                cache.mkdir()
            seen = work / 'seen'
            env = dict(os.environ, DEVICE_TYPE=device, QEMU_2IN1_PROFILE_COMPONENT=profile,
                       QEMU_SERIAL_SOURCE_REPO=str(cache), OHOS_ROOT=str(source),
                       CACHE_ROOT=str(work), FIXTURE_SEEN=str(seen))
            for name in COMPONENTS:
                script = work / (name + '.sh')
                script.write_text('#!/bin/bash\nset -euo pipefail\n'
                    'printf "%s" "' + name + '" >> "$FIXTURE_SEEN"\n'
                    'printf " <%s>" "$@" >> "$FIXTURE_SEEN"\n'
                    'printf "\\n" >> "$FIXTURE_SEEN"\n' +
                    ('exit 23\n' if failure == name else ''))
                env['SERIAL_' + name + '_COMPONENT_SCRIPT'] = str(script)
            wrapper = 'set -euo pipefail\napply_qemu_serial_components() {' + HOOK + '\n}\napply_qemu_serial_components\n'
            result = subprocess.run(['bash', '-c', wrapper], env=env, capture_output=True, text=True)
            return result, seen.read_text().splitlines() if seen.exists() else []

    def test_real_hook_executes_five_components_in_order_with_exact_arguments(self):
        result, calls = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual([line.split()[0] for line in calls], list(COMPONENTS))
        for name, line in zip(COMPONENTS, calls):
            self.assertIn('<--source-root>', line)
            self.assertNotIn('<--product>', line)
            self.assertEqual('<--source-repo>' in line, name == 'MANAGER')

    def test_phone_or_disabled_full_profile_never_imports_or_applies_serial(self):
        for device, profile in (('phone', '1'), ('2in1', '0')):
            with self.subTest(device=device, profile=profile):
                result, calls = self.invoke(device, profile, missing=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(calls, [])

    def test_missing_fixed_cache_fails_before_any_component(self):
        result, calls = self.invoke(missing=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('c05fbbf156230982aa576373da6ee04378b09ca0', result.stderr)
        self.assertEqual(calls, [])

    def test_each_real_hook_pipeline_failure_stops_later_components(self):
        for index, name in enumerate(COMPONENTS):
            with self.subTest(component=name):
                result, calls = self.invoke(failure=name)
                self.assertEqual(result.returncode, 23)
                self.assertEqual([line.split()[0] for line in calls], list(COMPONENTS[:index + 1]))

    def test_preparation_calls_serial_before_profile_and_build_traversal(self):
        source = BUILDER.read_text()
        prepare = source[source.index('\n  apply_armv7a_product_component\n'):]
        self.assertLess(prepare.index('\n  apply_qemu_serial_components\n'),
                        prepare.index('\n  configure_qemu_device_profile\n'))
        self.assertLess(prepare.index('\n  apply_qemu_serial_components\n'),
                        prepare.index('\n  write_source_preparation_metadata\n'))
        host = (ROOT / 'scripts/run_2in1_full_build_docker.sh').read_text()
        self.assertIn('dst=${QEMU_SERIAL_SOURCE_REPO},readonly', host)
        self.assertIn('-e QEMU_SERIAL_SOURCE_REPO="${QEMU_SERIAL_SOURCE_REPO}"', host)
        self.assertNotIn('git fetch', host[host.index('SERIAL_CACHE_MOUNT_ARGS=()'):host.index('mkdir -p "${PACKAGE_ROOT}"')])

    def test_profile_requires_all_three_real_parts_idempotently(self):
        path = ROOT / 'patches/2in1/product_profile/apply.py'
        spec = importlib.util.spec_from_file_location('serial_profile_fixture', path)
        profile = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(profile)
        expected = {'busmanager:serial_manager', 'hdf:drivers_interface_serial', 'hdf:drivers_peripheral_serial'}
        self.assertTrue(expected.issubset(profile.REQUIRED_2IN1_PARTS))
        document = {'subsystems': []}
        for _ in range(2):
            for part in sorted(expected):
                profile.add_component(document, *part.split(':'))
        self.assertEqual(len(profile.component_map(document)), 3)


if __name__ == '__main__':
    unittest.main()
