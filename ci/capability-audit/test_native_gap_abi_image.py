"""Final-image ABI policy/contract fixtures, not runtime behavior evidence."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from verify_native_gap_abi_image import canonical_library, contracts, declared_syscaps, required_contracts


class NativeGapAbiImageTests(unittest.TestCase):
    def test_documentation_alias_only_not_an_implementation_alias(self):
        self.assertEqual(canonical_library('location_ndk.so'), 'liblocation_ndk.so')
        self.assertEqual(canonical_library('libhuks_external_crypto.z.so'), 'libhuks_external_crypto.so')

    def test_fixed_ndk_manifest_and_all_original_symbols_required(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'lib.ndk.json').write_text(json.dumps([{'name': 'OH_Test'}]))
            (root / 'test.h').write_text('/** @syscap SystemCapability.Test @library libtest.so */\nint OH_Test(void);')
            ledger = root / 'ledger.json'
            row = {'library': 'libtest.so', 'syscap': 'SystemCapability.Test',
                   'missing_symbols': ['OH_Test'], 'public_function_count': 1}
            ledger.write_text(json.dumps({'devices': {'phone': {'native_abi_gaps': [row]}}}))
            with patch('verify_native_gap_abi_image.LEDGER', ledger):
                actual = contracts(root, 'phone')
                self.assertEqual(actual[0]['functions'], ['OH_Test'])
                self.assertEqual(set(actual[0]['source_inputs_sha256']), {'test.h', 'lib.ndk.json'})
                row['public_function_count'] = 2
                ledger.write_text(json.dumps({'devices': {'phone': {'native_abi_gaps': [row]}}}))
                with self.assertRaises(ValueError):
                    contracts(root, 'phone')

    def test_official_requested_and_actual_declared_capabilities_never_optional(self):
        policy = {'required_official_syscaps': ['SystemCapability.Required'],
                  'explicit_qemu_requirements': ['SystemCapability.Requested'],
                  'enabled_required_syscaps': {}, 'excluded_unsupported_syscaps': {}}
        rows = [{'syscap': name} for name in ('SystemCapability.Required', 'SystemCapability.Requested',
                                             'SystemCapability.Declared', 'SystemCapability.Optional')]
        declared = {row['syscap'] for row in rows[:3]}
        actual = required_contracts(rows, {'qemu_adaptations': policy}, declared)
        self.assertEqual([row['needs_library'] for row in actual], [True, True, True, False])
        for name in ('SystemCapability.Required', 'SystemCapability.Requested'):
            with self.assertRaises(ValueError):
                required_contracts(rows, {'qemu_adaptations': policy}, declared - {name})
            changed = dict(policy, excluded_unsupported_syscaps={name: {}})
            with self.assertRaises(ValueError):
                required_contracts(rows, {'qemu_adaptations': changed}, declared)
        changed = dict(policy, excluded_unsupported_syscaps={'SystemCapability.Declared': {}})
        with self.assertRaises(ValueError):
            required_contracts(rows, {'qemu_adaptations': changed}, declared)

    def test_final_syscap_document_must_be_actual_and_nonempty(self):
        self.assertEqual(declared_syscaps({'components': [{'syscap': ['SystemCapability.Test']}]}),
                         {'SystemCapability.Test'})
        for value in ({}, {'components': [{'syscap': ['invented']}]}):
            with self.assertRaises(ValueError):
                declared_syscaps(value)


if __name__ == '__main__':
    unittest.main()
