"""SDK runtime build mapping fixtures, not runtime/QEMU acceptance."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from build_m144_sdk_bti_runtimes import member_source, REVISION


class SdkBtiRuntimeTests(unittest.TestCase):
    def test_existing_sdk_sources_and_outline_atomic_specialization(self):
        self.assertEqual(member_source('Unwind-EHABI.cpp.o', True), ('libunwind/src/Unwind-EHABI.cpp', []))
        self.assertEqual(member_source('emutls.c.o', False), ('compiler-rt/lib/builtins/emutls.c', []))
        self.assertEqual(member_source('outline_atomic_cas16_4.S.o', False),
                         ('compiler-rt/lib/builtins/aarch64/lse.S', ['-DL_cas', '-DSIZE=16', '-DMODEL=4']))
        self.assertEqual(member_source('outline_atomic_ldadd8_1.S.o', False),
                         ('compiler-rt/lib/builtins/aarch64/lse.S', ['-DL_ldadd', '-DSIZE=8', '-DMODEL=1']))

    def test_unsafe_or_unknown_member_not_accepted(self):
        for name in ('../emutls.c.o', '/emutls.c.o', 'a\\b.c.o', 'emutls.c', 'a.c.o;touch',
                     'outline_atomic_swp16_4.S.o'):
            with self.assertRaises(ValueError):
                member_source(name, False)

    def test_security_checks_and_same_sdk_source_commit_are_preserved(self):
        code = (ROOT / 'scripts/build_m144_sdk_bti_runtimes.py').read_text()
        self.assertIn('-mbranch-protection=pac-ret+b-key+bti', code)
        self.assertIn("'aarch64 feature: BTI'", code)
        self.assertIn('new_c != old_c', code)
        self.assertIn('not unwind and new_symbols != old_symbols', code)
        self.assertIn('llvm/lib/clang/15.0.4/lib/aarch64-linux-ohos/libclang_rt.builtins.a', code)
        self.assertIn(REVISION, (ROOT / 'scripts/prepare_m144_tool_sources.py').read_text())
        self.assertNotIn('force-bti', code)


if __name__ == '__main__':
    unittest.main()
