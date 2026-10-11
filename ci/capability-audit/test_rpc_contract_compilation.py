"""RPC source-generation fixtures are not real compiler or guest results."""
import unittest

from build_rpc_contract_probe import CASES, module, page

NONCE = '0123456789abcdef0123456789abcdef'


class RpcContractCompilationTests(unittest.TestCase):
    def test_ordinary_profile_has_no_permission_or_privilege_request(self):
        self.assertEqual(module('normal')['module']['requestPermissions'], [])
        with self.assertRaises(ValueError): module('system')

    def test_exact_distinct_type_and_value_cases_without_runtime_shims(self):
        for case in CASES:
            source = page(NONCE, case)
            with self.subTest(case=case):
                self.assertNotIn('__RPC_', source)
                self.assertIn('const object: rpc.IRemoteObject = new rpc.RemoteObject(', source)
                self.assertNotIn('Object.setPrototypeOf', source)
                self.assertNotIn('Object.defineProperty', source)
                self.assertNotIn('as unknown', source)
        self.assertIn('object.getDescriptor()', page(NONCE, 'typed-object'))
        self.assertIn('object instanceof rpc.IRemoteObject', page(NONCE, 'instance-check'))
        self.assertIn('class AuditAbstract extends rpc.IRemoteObject', page(NONCE, 'abstract-subclass'))
        self.assertIn('new rpc.IRemoteObject()', page(NONCE, 'abstract-new'))

    def test_foreign_nonce_and_unknown_case_rejected(self):
        for nonce, case in ((None, 'typed-object'), ('old', 'typed-object'), (NONCE, 'unknown')):
            with self.subTest(nonce=nonce, case=case), self.assertRaises(ValueError): page(nonce, case)


if __name__ == '__main__': unittest.main()
