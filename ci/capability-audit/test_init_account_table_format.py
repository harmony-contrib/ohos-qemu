"""Exact account composition boundaries, not cloud/guest acceptance."""
import importlib.util
import contextlib
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('init_account_tables', ROOT / 'patches/lib/init_account_tables.py')
tables = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tables)
COMPONENT = ROOT / 'patches/common/base/startup/init/account_table_format'
spec = importlib.util.spec_from_file_location('account_format_check', COMPONENT / 'check.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class AccountFormatTests(unittest.TestCase):
    def test_exact_missing_field_only_and_all_other_bytes_preserved(self):
        original = b'root:x:0:0:::/bin/false\n' + tables.CLOUD_ORIGINAL + b'\nlast:x:99:99:::/bin/false\n'
        repaired = tables.repair_cloud(original)
        self.assertEqual(repaired.replace(tables.CLOUD_REPAIRED, tables.CLOUD_ORIGINAL), original)
        self.assertEqual(repaired.count(b'cloud_disk_service:'), 1)
        tables.validate(b'root:x:0:\ncloud_disk_service:x:6161:\n', 'group')

    def test_missing_duplicate_alias_bad_format_authority_fail(self):
        for data in (b'', tables.CLOUD_ORIGINAL + b'\n' + tables.CLOUD_ORIGINAL,
                     tables.CLOUD_ORIGINAL + b'\n' + tables.CLOUD_REPAIRED,
                     tables.CLOUD_ORIGINAL + b'\nalias:x:6161:6161:::/bin/false',
                     tables.CLOUD_ORIGINAL + b'\nbroken:x:99:99::/bin/false'):
            with self.subTest(data=data), self.assertRaises(ValueError): tables.repair_cloud(data)
        for data in (tables.CLOUD_REPAIRED.replace(b':6161:6161:', b':6161:0:'),
                     tables.CLOUD_REPAIRED.replace(b'/bin/false', b'/bin/sh'),
                     tables.CLOUD_REPAIRED + b'\ncloud_disk_service:x:2:2:::/bin/false'):
            with self.subTest(data=data), self.assertRaises(ValueError): tables.validate(data, 'passwd')
        for data in (b'cloud_disk_service:x:6161:root', b'cloud_disk_service:x:6161:\nalias:x:6161:'):
            with self.assertRaises(ValueError): tables.validate(data, 'group')

    def test_actual_numbered_patch_repeats_and_precedes_traversal(self):
        patch = next(COMPONENT.glob('0001-*.patch')).read_text()
        context = patch.split('@@', 2)[2].splitlines()[1:]
        original = '\n'.join(row[1:] for row in context if row.startswith((' ', '-'))) + '\n'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            file = root / 'base/startup/init/services/etc/passwd'
            file.parent.mkdir(parents=True)
            file.write_text(original)
            for _ in range(2):
                subprocess.run(['bash', str(ROOT / 'patches/lib/apply_component_dir.sh'), str(COMPONENT),
                                '--source-root', str(root)], check=True, capture_output=True)
            self.assertEqual(file.read_bytes(), tables.repair_cloud(original.encode()))
        text = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        start = text.index('bash "${ACCOUNT_TABLE_FORMAT_COMPONENT_SCRIPT}"')
        self.assertGreater(start, text.index('bash "${FUSION_ACCOUNTS_COMPONENT_SCRIPT}"'))
        self.assertLess(start, text.index('  write_source_preparation_metadata'))

    def test_complete_known_compositions_unknown_edits_and_symlinks(self):
        originals = {'passwd': b'fusion_host:x:3067:3067:::/bin/false\n' + tables.CLOUD_ORIGINAL + b'\n',
                     'group': b'fusion_host:x:3067:\ncloud_disk_service:x:6161:\n'}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            init = root / 'base/startup/init'
            (init / 'services/etc').mkdir(parents=True)
            def git(argv, **kwargs):
                return guard.fusion.INIT_REVISION + '\n' if argv[-2:] == ['rev-parse', 'HEAD'] else originals[argv[-1].split('/')[-1]]
            def invoke(patched=False):
                with patch('sys.argv', ['check', '--source-root', str(root)] + (['--require-patched'] if patched else [])), \
                        patch.object(guard.subprocess, 'check_output', side_effect=git), contextlib.redirect_stdout(io.StringIO()):
                    guard.main()
            for fused in (False, True):
                for formatted in (False, True):
                    for kind, original in originals.items():
                        value = guard.fusion.repaired(original, kind) if fused else original
                        if formatted and kind == 'passwd': value = tables.repair_cloud(value)
                        (init / 'services/etc' / kind).write_bytes(value)
                    invoke()
                    if formatted: invoke(True)
                    else:
                        with self.assertRaises(SystemExit): invoke(True)
            target = init / 'services/etc/passwd'
            original = target.read_bytes()
            target.write_bytes(original + b'unknown edit')
            with self.assertRaises(SystemExit): invoke()
            self.assertEqual(target.read_bytes(), original + b'unknown edit')
            target.unlink()
            outside = root / 'outside-passwd'; outside.write_bytes(original)
            target.symlink_to(outside)
            with self.assertRaises(SystemExit): invoke()
            self.assertEqual(outside.read_bytes(), original)


if __name__ == '__main__': unittest.main()
