"""Exact formatting/unknown-edit fixtures, not full native/HAP acceptance."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from test_access_token_kernel import patch_sections, write_preimages

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / 'patches/common/web/arkweb/m144_adapter_header_format'
PATCH = next(COMPONENT.glob('*.patch'))
spec = importlib.util.spec_from_file_location('adapter_header_format_check', COMPONENT / 'check.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class AdapterHeaderFormatTests(unittest.TestCase):
    def fixture(self, root):
        write_preimages(root, PATCH)
        original = {}
        for name in checker.HEADERS:
            path = root / 'deps_code/webview/ohos_interface/include/ohos_adapter' / name
            body = path.read_bytes().removesuffix(b'\n')
            path.write_bytes(body)
            original[name] = body
        def git(arguments, **keywords):
            if arguments[-1] == 'HEAD':
                return checker.REVISION + '\n'
            return original[arguments[-1].split('/')[-1]]
        return original, git

    def test_exact_pristine_then_added_lf_and_repeat(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original, git = self.fixture(root)
            with patch.object(checker.subprocess, 'check_output', side_effect=git):
                checker.check(root, before=True)
                with self.assertRaises(ValueError):
                    checker.check(root)
                subprocess.run(['git', '-C', str(root), 'apply', str(PATCH)], check=True, capture_output=True)
                for _ in range(2):
                    checker.check(root, before=True)
                    checker.check(root)
                for name, body in original.items():
                    self.assertEqual((root / 'deps_code/webview/ohos_interface/include/ohos_adapter' / name).read_bytes(),
                                     body + b'\n')

    def test_unknown_full_content_and_aliased_headers_are_rejected_before_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _, git = self.fixture(root)
            path = root / 'deps_code/webview/ohos_interface/include/ohos_adapter' / checker.HEADERS[0]
            with patch.object(checker.subprocess, 'check_output', side_effect=git):
                path.write_bytes(path.read_bytes() + b'\n// user change\n')
                edited = path.read_bytes()
                with self.assertRaises(ValueError):
                    checker.check(root, before=True)
                self.assertEqual(path.read_bytes(), edited)
                moved = root / 'preserved.h'
                path.rename(moved)
                path.symlink_to(moved)
                with self.assertRaises(ValueError):
                    checker.check(root, before=True)

    def test_moving_wrong_source_revision_rejected(self):
        with patch.object(checker.subprocess, 'check_output', return_value='master\n'), self.assertRaises(ValueError):
            checker.check(Path('/fixture'), True)

    def test_only_fourteen_source_final_newlines_change(self):
        sections = patch_sections(PATCH)
        self.assertEqual(set(sections), {'deps_code/webview/ohos_interface/include/ohos_adapter/' + name
                                        for name in checker.HEADERS})
        for hunks in sections.values():
            self.assertEqual(len(hunks), 1)
            _, old, new = hunks[0]
            self.assertEqual(old, new)
        self.assertEqual(PATCH.read_text().count('\\ No newline at end of file'), 14)
        script = (COMPONENT / 'apply.sh').read_text()
        self.assertLess(script.index('check.py" --source-root "${SOURCE_ROOT}" --before'),
                        script.index('apply_component_dir.sh'))
        self.assertNotIn('third_party/ohos_ndk/includes', PATCH.read_text())


if __name__ == '__main__':
    unittest.main()
