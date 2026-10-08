"""IDL action confinement fixtures; no compiler or generated-header claim."""
from pathlib import Path
import unittest

from prepare_enum_generated_headers import OUTPUT_NAMES, PROJECT, validate_action


def action(root, product):
    cwd = Path(root) / 'out' / product
    return ['/usr/bin/env', '../../build/config/components/idl_tool/idl.py',
        '--src-idl', str(Path(root) / PROJECT / 'INetworkVpnService.idl'),
        '--dst-path', str(cwd / 'gen' / PROJECT), '--idl-tool-path', str(cwd / 'clang_x64/ability/idl_tool'),
        '--dst-file', ','.join(str(cwd / 'gen' / PROJECT / name) for name in OUTPUT_NAMES), '--language', 'cpp']


class GeneratedEnumHeaderTests(unittest.TestCase):
    def test_only_known_volume_aliases_and_exact_output_names_are_relocated(self):
        for root in ('/openharmony', '/Volumes/PSSD/qemu/openharmony'):
            for product in ('armv7a_virt', 'x86_64_virt'):
                original = action(root, product)
                actual, outputs, cached = validate_action(original, product)
                self.assertEqual(cached, root)
                self.assertEqual(actual[actual.index('--src-idl') + 1], original[original.index('--src-idl') + 1])
                self.assertEqual([path.name for path in outputs], list(OUTPUT_NAMES))
                self.assertTrue(all(path.parent == Path('/openharmony/out') / product / 'gen' / PROJECT for path in outputs))
                self.assertEqual(original, action(root, product))

    def test_extra_duplicate_missing_flags_and_wrong_program_are_rejected(self):
        argv = action('/openharmony', 'armv7a_virt')
        variants = [argv + ['--src-idl', '/other.idl'], argv[:-2], argv + ['&&'],
                    ['bash', '-c', *argv[2:]]]
        duplicate = argv[:]; duplicate[6] = '--src-idl'; variants.append(duplicate)
        for variant in variants:
            with self.assertRaises(ValueError): validate_action(variant, 'armv7a_virt')

    def test_wrong_sources_cross_product_outputs_traversal_or_other_file_are_rejected(self):
        for flag, value in (('--src-idl', '/other/' + PROJECT + '/INetworkVpnService.idl'),
                ('--src-idl', '/openharmony/' + PROJECT + '/different.idl'),
                ('--dst-path', '/openharmony/out/x86_64_virt/gen/' + PROJECT),
                ('--dst-file', '/openharmony/out/armv7a_virt/gen/' + PROJECT + '/../outside'),
                ('--idl-tool-path', '/openharmony/out/x86_64_virt/clang_x64/ability/idl_tool'),
                ('--language', 'rust')):
            argv = action('/openharmony', 'armv7a_virt'); argv[argv.index(flag) + 1] = value
            with self.assertRaises(ValueError): validate_action(argv, 'armv7a_virt')
        with self.assertRaises(ValueError): validate_action(action('/openharmony', 'armv7a_virt'), 'arm64_virt')


if __name__ == '__main__':
    unittest.main()
