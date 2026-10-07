"""Offline image-checker fixtures, never real DSP/QEMU behavior acceptance."""
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / 'scripts'))
from verify_audio_suite_dsp_image import ALL_NODES, EXPORTS, LIBRARY, ROUTES, verify_image, verify_xml
from verify_audio_suite_dsp_image import (ARM_UNWIND_RUNTIME, ARM_UNWIND_EXPORTS, SANITIZER,
                                         SANITIZER_EXPORTS, dynamic_contract, expected_dependencies)
from test_avc_backend_artifacts import fixture_elf


def config():
    root = ET.Element('audioSuiteCapabilities')
    nodes = ET.SubElement(root, 'nodeCapability')
    for name in sorted(ALL_NODES):
        ET.SubElement(nodes, 'nodeType', name=name, soName=LIBRARY if name in ROUTES else 'original_unimplemented.so',
                      soPath='/system/lib64/', frameLen='480', general='yes')
    return root


class DspImageTests(unittest.TestCase):
    def test_real_security_dependency_contract_rejects_missing_extra_and_bad_soname(self):
        for arch in ('arm', 'arm64', 'x86_64'):
            dependencies = expected_dependencies({'arm': 40, 'arm64': 183, 'x86_64': 62}[arch])
            good = fixture_elf(arch, symbols=EXPORTS | {'__cfi_check'}, needed=dependencies, soname=LIBRARY)
            self.assertEqual(dynamic_contract(good), dependencies)
            for dependencies in (['libc.so'], ['libc.so', SANITIZER, 'libc.so.6'],
                                 ['libc.so', SANITIZER, SANITIZER]):
                with self.subTest(arch=arch, dependencies=dependencies), self.assertRaises(ValueError):
                    dynamic_contract(fixture_elf(arch, needed=dependencies, soname=LIBRARY))
            with self.assertRaises(ValueError):
                dynamic_contract(fixture_elf(arch, needed=['libc.so', SANITIZER], soname='unknown.so'))

    def test_image_security_runtime_closure_and_missing_CFI_are_not_optional(self):
        for arch, machine in (('arm', 40), ('arm64', 183), ('x86_64', 62)):
            abi = 'lib' if machine == 40 else 'lib64'
            failures = [None, 'cfi', 'sanitizer-missing', 'sanitizer-export', 'sanitizer-machine', 'math-export']
            if machine == 40: failures += ['unwind-missing', 'unwind-export', 'unwind-machine']
            for failure in failures:
                symbols = EXPORTS if failure == 'cfi' else EXPORTS | {'__cfi_check'}
                files = {
                    f'/{abi}/{LIBRARY}': fixture_elf(arch, symbols=symbols, needed=expected_dependencies(machine), soname=LIBRARY),
                    f'/{abi}/libc.so': fixture_elf(arch, symbols={'cos', 'pow', 'sin', 'tanh'} | (
                        set() if failure == 'math-export' else {'__cfi_fail_report'})),
                    f'/{abi}/platformsdk/{SANITIZER}': fixture_elf(
                        'arm64' if failure == 'sanitizer-machine' and arch != 'arm64' else (
                            'arm' if failure == 'sanitizer-machine' else arch),
                        symbols=SANITIZER_EXPORTS - ({'__ubsan_handle_mul_overflow_minimal_abort'} if failure == 'sanitizer-export' else set())),
                    '/etc/audio/audio_suite_capabilities.xml': ET.tostring(config()),
                }
                if machine == 40 and failure != 'unwind-missing':
                    files[f'/{abi}/{ARM_UNWIND_RUNTIME}'] = fixture_elf(
                        'arm64' if failure == 'unwind-machine' else arch,
                        symbols=ARM_UNWIND_EXPORTS - ({'__aeabi_unwind_cpp_pr0'} if failure == 'unwind-export' else set()))
                if failure == 'sanitizer-missing': del files[f'/{abi}/platformsdk/{SANITIZER}']
                def dump(command, **kwargs):
                    source, target = command[2].removeprefix('dump ').split(' ', 1)
                    if source in files: Path(target).write_bytes(files[source])
                with self.subTest(arch=arch, failure=failure), patch('verify_audio_suite_dsp_image.subprocess.run', side_effect=dump):
                    if failure:
                        with self.assertRaises(ValueError): verify_image(Path('/fixture/system.img'), machine, 'debugfs-fixture')
                    else:
                        observed = verify_image(Path('/fixture/system.img'), machine, 'debugfs-fixture')
                        self.assertEqual(set(observed['security_math_runtimes']), set(expected_dependencies(machine)))

    def test_only_three_routes_and_exact_upstream_node_names(self):
        self.assertEqual(set(verify_xml(ET.tostring(config()))), ROUTES)
        for operation in ('delete', 'duplicate', 'wrong-name', 'wrong-lib', 'wrong-frame', 'fake-AI'):
            root = config()
            nodes = root.find('nodeCapability')
            eq = next(node for node in nodes if node.get('name') == 'EQUALIZER')
            if operation == 'delete': nodes.remove(eq)
            if operation == 'duplicate': ET.SubElement(nodes, 'nodeType', **eq.attrib)
            if operation == 'wrong-name': next(node for node in nodes if node.get('name') == 'NOISE_REDUCTION').set('name', 'invented')
            if operation == 'wrong-lib': eq.set('soName', 'libimedia_sws.z.so')
            if operation == 'wrong-frame': eq.set('frameLen', '960')
            if operation == 'fake-AI': next(node for node in nodes if node.get('name') == 'NOISE_REDUCTION').set('soName', LIBRARY)
            with self.subTest(operation=operation), self.assertRaises(ValueError): verify_xml(ET.tostring(root))

    def test_missing_image_dump_even_with_zero_exit_fails_all_ABIs(self):
        for machine in (40, 183, 62):
            with self.subTest(machine=machine), patch('verify_audio_suite_dsp_image.subprocess.run') as run:
                with self.assertRaisesRegex(ValueError, 'lacks real native-ABI'):
                    verify_image(Path('/fixture/system.img'), machine, 'debugfs-fixture')
                self.assertEqual(run.call_count, 2)

    def test_export_contract_matches_current_version_script(self):
        component = REPO / 'patches/common/foundation/multimedia/audio_framework/audio_suite_dsp/files'
        map_text = (component / 'qemu_audio_suite_dsp.map').read_text()
        observed = {line.strip().rstrip(';') for line in map_text.splitlines() if line.strip().startswith('iMedia_')}
        self.assertEqual(observed, EXPORTS)
        self.assertEqual(len(EXPORTS), 19)
        self.assertTrue({f'iMedia_{kind}_GetSPECS' for kind in ('Eq', 'Surround', 'Env')} <= EXPORTS)

    def test_full_phone_package_checker_is_mandatory_not_runtime_or_outside_profile_claim(self):
        script = (REPO / 'scripts/verify_device_type_package.sh').read_text()
        block = script.split('VENDOR_IMG="${PACKAGE}/images/vendor.img"')[1].split('VIBRATOR_FOUND=')[0]
        self.assertIn('if [ "${REQUIRE_FULL_DEVICE}" = "phone" ]; then', block)
        self.assertIn('verify_audio_suite_dsp_image.py', block)
        self.assertIn('FAIL=1', block)
        self.assertIn('offline only, not PCM behavior', block)
        checker = (REPO / 'scripts/verify_audio_suite_dsp_image.py').read_text()
        self.assertIn("'first_artifact_behavior_gate_passed': False", checker)


if __name__ == '__main__': unittest.main()
