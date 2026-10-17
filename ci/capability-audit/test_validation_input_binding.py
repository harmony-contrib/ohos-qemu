"""Synthetic input provenance boundaries, never guest acceptance evidence."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

from validation_input_binding import tree_digest, verify_update


class ValidationBindingTests(unittest.TestCase):
    def setUp(self):
        self.original = {'patches/product.patch': 'a' * 64, 'scripts/build.sh': 'b' * 64,
                         'docs/capability-audit/native-arkts11-gap-ledger.json': 'c' * 64,
                         'ci/capability-audit/run_luminance_probe.py': 'd' * 64}
        self.current = dict(self.original, **{'ci/capability-audit/run_luminance_probe.py': 'e' * 64})
        self.inputs = dict(files_sha256=self.original, tree_sha256=tree_digest(self.original))

    def receipt(self, current):
        return dict(schema_version=1, archive_sha256='f' * 64, build_tree_sha256=tree_digest(self.original),
                    validation_tree_sha256=tree_digest(current), changed_test_files=sorted(
                        key for key in self.original.keys() | current.keys() if self.original.get(key) != current.get(key)))

    def verify(self, current, receipt=None, inputs=None):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'binding.json'
            path.write_text(json.dumps(self.receipt(current) if receipt is None else receipt))
            return verify_update(self.inputs if inputs is None else inputs, current, 'f' * 64, path)

    def test_explicit_exact_test_update_is_bound_to_both_trees(self):
        result = self.verify(self.current)
        self.assertEqual(result['validation_tree_sha256'], tree_digest(self.current))
        self.assertEqual(result['changed_test_files'], ['ci/capability-audit/run_luminance_probe.py'])

    def test_production_ledger_unknown_and_deleted_inputs_never_allowed(self):
        for name in (*list(self.original)[:3], 'ci/capability-audit/unreviewed_builder.py'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.verify(dict(self.current, **{name: '9' * 64}))
        current = dict(self.current)
        del current['ci/capability-audit/run_luminance_probe.py']
        with self.assertRaises(ValueError): self.verify(current)

    def test_receipt_cannot_hide_changes_or_replace_archive_or_trees(self):
        receipt = self.receipt(self.current)
        for field, value in (('archive_sha256', '0' * 64), ('build_tree_sha256', '0' * 64),
                             ('validation_tree_sha256', '0' * 64), ('changed_test_files', []),
                             ('schema_version', True)):
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.verify(self.current, dict(receipt, **{field: value}))
        broken = copy.deepcopy(self.inputs)
        broken['tree_sha256'] = '0' * 64
        with self.assertRaises(ValueError): self.verify(self.current, inputs=broken)
        with self.assertRaises(ValueError): self.verify(self.original)

    def test_dedicated_QA_updates_require_exact_receipt_and_never_admit_production(self):
        from validation_input_binding import DEDICATED_QA_TEST_ONLY
        self.assertEqual(len(DEDICATED_QA_TEST_ONLY), 16)
        self.assertTrue(all(name.startswith('ci/capability-audit/') for name in DEDICATED_QA_TEST_ONLY))
        current = dict(self.current)
        current.update({name: '9'*64 for name in DEDICATED_QA_TEST_ONLY})
        self.assertEqual(self.verify(current)['changed_test_files'], self.receipt(current)['changed_test_files'])
        for name in ('scripts/build_standard_qemu_in_docker.sh',
                     'scripts/verify_first_artifact_gate.py',
                     'patches/common/device/qemu/external_gnss/files/qemu_gnss_protocol.h',
                     'docs/capability-audit/native-arkts11-gap-ledger.json',
                     'ci/capability-audit/unreviewed_runtime.py'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                self.verify(dict(current, **{name: '8'*64}))
        receipt = self.receipt(current); receipt['changed_test_files'].pop()
        with self.assertRaises(ValueError): self.verify(current, receipt)

    def test_symlink_or_missing_receipt_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            target, link = Path(directory) / 'target', Path(directory) / 'link'
            target.write_text(json.dumps(self.receipt(self.current)))
            link.symlink_to(target)
            for path in (link, Path(directory) / 'missing'):
                with self.assertRaises(ValueError):
                    verify_update(self.inputs, self.current, 'f' * 64, path)


if __name__ == '__main__':
    unittest.main()
