"""Compiler relocation confinement, not native compilation evidence."""
from pathlib import Path
import unittest
from compile_public_module_registrations import COMPONENTS, PATCH_ONLY_SOURCES, PLAN, ROOT, relocate
import re


class RegistrationCompilerTests(unittest.TestCase):
    def test_each_component_keeps_its_complete_real_patch_target_set(self):
        self.assertEqual(len(PLAN), len({row[0] for row in PLAN}))
        # Independent overlays can change the same TU; each complete component
        # is applied and compiled separately in its declared stack order.
        self.assertEqual(len(PLAN), len({(row[1], row[2]) for row in PLAN}))
        for component in COMPONENTS:
            paths = (ROOT / 'patches/common' / component).glob('*.patch')
            actual = {name for path in paths for name in re.findall(r'^\+\+\+ b/(.+)$', path.read_text(), re.M)}
            self.assertEqual(actual, {row[2] for row in PLAN if row[1] == component} |
                             set(PATCH_ONLY_SOURCES.get(component, ())))

    def fixture(self):
        root=Path('/readonly/source')
        source='foundation/example/entry.cpp'
        argv=['ccache','../../clang++','--target=aarch64-linux-ohos','-I../../include',
              '-DMODE=1','-c','../../'+source,'-o','obj/example.o','-MF','obj/example.d']
        return argv,root/'out/product',root,source,Path('/private/staged'),Path('/private/a.o'),Path('/private/a.d')

    def test_only_quote_source_object_and_dep_paths_change(self):
        args=self.fixture()
        original,actual=relocate(*args,'aarch64-linux-ohos')
        self.assertEqual(original,args[0][1:])
        self.assertEqual(args[0][0],'ccache')
        self.assertEqual(actual,[original[0],'-iquote','/readonly/source/foundation/example',
            *original[1:5],'/private/staged/foundation/example/entry.cpp','-o','/private/a.o','-MF','/private/a.d'])

    def test_wrong_source_abi_shell_or_duplicate_write_flags_rejected(self):
        for change in ('source','abi','shell','duplicate','compiler'):
            with self.subTest(change=change):
                args=list(self.fixture());argv=args[0]
                if change=='source':argv[argv.index('-c')+1]='../../another.cpp'
                elif change=='abi':argv[2]='--target=x86_64-linux-ohos'
                elif change=='shell':argv+=[';','other-command']
                elif change=='duplicate':argv+=['-o','other.o']
                elif change=='compiler':argv[1]='../../g++'
                with self.assertRaises(ValueError):relocate(*args,'aarch64-linux-ohos')


if __name__=='__main__':
    unittest.main()
