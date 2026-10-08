"""Fail-closed shared naming repair fixtures, not product graph or guest proof."""
import hashlib
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from test_access_token_kernel import patch_sections, write_preimages
from check_idl_common_type_outputs import fragment

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/build/idl_common_type_outputs'
PATCH = COMPONENT / '0001-use-actual-common-type-header-name.patch'


class IdlCommonTypeOutputsTests(unittest.TestCase):
    def test_patch_only_changes_common_header_naming_not_interface_or_cpp_outputs(self):
        sections = patch_sections(PATCH)
        self.assertEqual(set(sections), {'build/config/components/idl_tool/idl.gni'})
        hunks = next(iter(sections.values()))
        self.assertEqual(len(hunks), 2)
        self.assertEqual([line for line in hunks[0][1] if line not in hunks[0][2]],
                         ['    init_with_i = false', '      init_with_i = true'])
        self.assertEqual([line for line in hunks[1][2] if line not in hunks[1][1]],
                         ['    # Common types already retain the initial I in their normalized name.',
                          '    sources_all += [ "${target_gen_dir}/" + out_full_name + ".h" ]'])
        self.assertEqual(hunks[1][1][-3:], hunks[1][2][-3:])

    def test_guard_rejects_unknown_sources_and_preserves_them(self):
        spec = importlib.util.spec_from_file_location('idl_contract', COMPONENT / 'verify_source.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / 'build/config/components/idl_tool/idl.gni'
            path.parent.mkdir(parents=True)
            path.write_bytes(b'unknown user changes')
            before = path.read_bytes()
            with self.assertRaises(ValueError):
                module.validate(root)
            result = subprocess.run(['bash', COMPONENT / 'apply.sh', '--source-root', root], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(path.read_bytes(), before)
            self.assertFalse((root / '.ohos-qemu-patches').exists())

    def test_marker_free_exact_state_idempotence(self):
        # Plumbing fixture hashes do not substitute for the real-source check.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            write_preimages(root, PATCH)
            path = root / 'build/config/components/idl_tool/idl.gni'
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            subprocess.run(['git', '-C', root, 'apply', PATCH], check=True, capture_output=True)
            after = hashlib.sha256(path.read_bytes()).hexdigest()
            subprocess.run(['git', '-C', root, 'apply', '-R', PATCH], check=True, capture_output=True)
            fixture = root / 'recipe'
            shutil.copytree(COMPONENT, fixture / COMPONENT.relative_to(ROOT))
            shutil.copytree(ROOT / 'patches/lib', fixture / 'patches/lib')
            verify = fixture / COMPONENT.relative_to(ROOT) / 'verify_source.py'
            text = verify.read_text().replace('a4787050abbcf6e8fe2b84c5de0a373fa8eb2c544872cc5b2b216ddd76e476dc', before)
            verify.write_text(text.replace('8246760b8cc70805fdbd0ff31fd8b85f854f2673d957d0b76b83d18edb14784f', after))
            argv = ['bash', fixture / COMPONENT.relative_to(ROOT) / 'apply.sh', '--source-root', root]
            for attempt in range(3):
                subprocess.run(argv, check=True, capture_output=True)
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), after)
                for marker in (root / '.ohos-qemu-patches').glob('*.applied'):
                    marker.unlink()

    def test_pretraversal_plan_and_actual_fragment_checker_are_wired(self):
        builder = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        invocation = 'bash "${IDL_COMMON_TYPE_OUTPUTS_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}"'
        self.assertEqual(builder.count(invocation), 1)
        plan = builder.split('apply_qemu_capability_patch_plan() {', 1)[1].split('\nmain() {', 1)[0]
        self.assertLess(plan.index(invocation), plan.index('apply_armv7a_product_component'))
        with self.assertRaises(ValueError):
            fragment('  # idl name transform\nunexpected\n  # sources\n'
                     '  # common sources\nunexpected\n  action("$target_name") {')


if __name__ == '__main__':
    unittest.main()
