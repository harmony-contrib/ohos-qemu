"""NOTICE input access and exact patch guards, not package license acceptance."""
import ast
import importlib.util
import os
from pathlib import Path
import stat
import subprocess
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
COMPONENT = REPO / 'patches/common/build/notice/readonly_input'
spec = importlib.util.spec_from_file_location('qemu_notice_readonly', COMPONENT / 'check.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)

# Fixed 7.0 build collector's helper, Apache-2.0 / Huawei Device Co., Ltd.
ORIGINAL = '''def write_notice_to_output(notice_file, output):
    with os.fdopen(os.open(notice_file, os.O_RDWR | os.O_CREAT, stat.S_IWUSR | stat.S_IRUSR),
                   'r', encoding='utf-8', errors='ignore') as notice_data_flow:
        license_content = notice_data_flow.read()
    with os.fdopen(os.open(output, os.O_RDWR | os.O_CREAT, stat.S_IWUSR | stat.S_IRUSR),
                   'r', encoding='utf-8', errors='ignore') as output_data_flow:
        output_file_content = output_data_flow.read()
    if license_content not in output_file_content:
        with os.fdopen(os.open(output, os.O_RDWR | os.O_CREAT | os.O_TRUNC, stat.S_IWUSR | stat.S_IRUSR),
                       'a', encoding='utf-8') as testfwk_info_file:
            testfwk_info_file.write(f"{license_content}\\n")
            testfwk_info_file.close()
'''.encode()


class NoticeReadonlyTests(unittest.TestCase):
    def function(self):
        namespace = {'os': os, 'stat': stat}
        exec(compile(ast.parse(guard.repaired(ORIGINAL)), '<patched actual NOTICE helper fixture>', 'exec'), namespace)
        return namespace['write_notice_to_output']

    def test_input_is_readonly_and_complete_content_deduplicates(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / 'COPYRIGHT', Path(directory) / 'notice.txt'
            source.write_text('license copyright\n条款\n')
            output.write_text('')
            source.chmod(0o444)
            calls, original_open = [], os.open
            def opened(path, flags, *args):
                if Path(path) == source:
                    calls.append(flags)
                    self.assertEqual(flags, os.O_RDONLY)
                return original_open(path, flags, *args)
            with patch('os.open', side_effect=opened):
                self.function()(str(source), str(output))
                first = output.read_bytes()
                self.function()(str(source), str(output))
            self.assertEqual(calls, [os.O_RDONLY, os.O_RDONLY])
            self.assertEqual(source.read_text(), 'license copyright\n条款\n')
            self.assertEqual(first, output.read_bytes())
            self.assertIn(source.read_bytes(), first)

    def test_missing_input_is_not_created_or_converted_into_empty_license(self):
        with tempfile.TemporaryDirectory() as directory:
            source, output = Path(directory) / 'missing', Path(directory) / 'notice.txt'
            output.write_text('preserve existing output')
            with self.assertRaises(FileNotFoundError):
                self.function()(str(source), str(output))
            self.assertFalse(source.exists())
            self.assertEqual(output.read_text(), 'preserve existing output')

    def test_unknown_or_duplicate_input_structure_rejected(self):
        for original in (ORIGINAL.replace(guard.OLD, b'unknown'), ORIGINAL * 2,
                         ORIGINAL + guard.NEW):
            with self.subTest(original=original), self.assertRaises(ValueError):
                guard.repaired(original)

    def test_numbered_patch_applies_and_repeats_without_altering_output_logic(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / 'build' / guard.FILE
            target.parent.mkdir(parents=True)
            target.write_bytes(ORIGINAL)
            for _ in range(2):
                subprocess.run(['bash', str(REPO / 'patches/lib/apply_component_dir.sh'),
                                str(COMPONENT), '--source-root', str(root)], check=True, capture_output=True)
            self.assertEqual(target.read_bytes(), guard.repaired(ORIGINAL))
        builder = (REPO / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        self.assertLess(builder.index('bash "${NOTICE_READONLY_INPUT_COMPONENT_SCRIPT}"'),
                        builder.index('  write_source_preparation_metadata'))


if __name__ == '__main__':
    unittest.main()
