"""Compiler/link driver argument contracts only, not actual guest evidence."""
from pathlib import Path
import unittest

from build_rs_object_probe import compiler_arguments, linker_arguments


class BuildRSObjectProbeTests(unittest.TestCase):
    def test_real_abi_lto_toolchain_choices_kept_without_compile_only_warning_flags(self):
        original = ['clang++', '--target=arm-linux-ohos', '--sysroot=obj/third_party/musl',
                    '-march=armv7-a', '-mfloat-abi=softfp', '-mfpu=neon',
                    '-stdlib=libc++', '-flto=thin', '-fuse-ld=lld', '-B', '/actual/bin',
                    '-Werror', '-fno-ident', '-fno-exceptions', '-MMD', '-MF', 'old.d',
                    '-I/private/actual/include', '-c', 'old.cpp', '-o', 'old.o']
        self.assertEqual(linker_arguments(original), original[1:11])
        self.assertEqual(original[-4:], ['-c', 'old.cpp', '-o', 'old.o'])

    def test_compile_keeps_actual_includes_macros_and_replaces_only_owned_outputs_and_source(self):
        original = ['ccache', '/actual/clang++', '-DROSEN_OHOS', '-I/actual',
                    '-MMD', '-MF', 'old.d', '-c', 'old.cpp', '-o', 'old.o']
        changed = compiler_arguments(original, Path('/owned/probe.cpp'), Path('/owned/probe.o'))
        self.assertEqual(changed, ['/actual/clang++', '-DROSEN_OHOS', '-I/actual',
                                  '-MMD', '-MF', '/owned/probe.d', '-c', '/owned/probe.cpp',
                                  '-o', '/owned/probe.o'])
        self.assertEqual(original[0], 'ccache')
        with self.assertRaises(ValueError):
            compiler_arguments(['host-g++'], Path('x'), Path('y'))


if __name__ == '__main__':
    unittest.main()
