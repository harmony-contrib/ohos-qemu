"""Dedicated account/authority guards, not fusion radio or service acceptance."""
import contextlib
import hashlib
import importlib.util
import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[2]
COMPONENT = REPO / 'patches/common/base/startup/init/fusion_accounts'
spec = importlib.util.spec_from_file_location('qemu_fusion_accounts', COMPONENT / 'check.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)
TABLES = {'passwd': b'fusion_host:x:3067:3067:::/bin/false\n', 'group': b'fusion_host:x:3067:\n'}


class FusionAccountTests(unittest.TestCase):
    def test_separate_nonroot_nonlogin_users_no_extra_group_members(self):
        for kind, original in TABLES.items():
            result = guard.repaired(original, kind)
            self.assertTrue(result.startswith(original))
            for name, uid in guard.ACCOUNTS.items():
                row = next(row.split(':') for row in result.decode().splitlines() if row.startswith(name + ':'))
                self.assertEqual(int(row[2]), uid)
                self.assertGreater(uid, 0)
                self.assertLessEqual(uid, 6999)
                if kind == 'passwd':
                    self.assertEqual(int(row[3]), uid)
                    self.assertEqual(row[-1], '/bin/false')
                else:
                    self.assertEqual(row[-1], '')
        self.assertEqual(len(set(guard.ACCOUNTS.values())), 2)

    def test_name_uid_or_primary_gid_collision_rejected(self):
        for row in (b'existing:x:6067:1234:::/bin/false\n', b'existing:x:1234:6068:::/bin/false\n',
                    b'fusion_ranging:x:1234:1234:::/bin/false\n'):
            with self.subTest(row=row), self.assertRaises(ValueError):
                guard.repaired(TABLES['passwd'] + row, 'passwd')
        with self.assertRaises(ValueError):
            guard.repaired(TABLES['group'] + b'existing:x:6068:\n', 'group')
        with self.assertRaises(ValueError):
            guard.repaired(b'unknown:x:1234:\n', 'group')

    def test_patch_twice_and_source_preparation_before_traversal(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            for kind, data in TABLES.items():
                # The actual numbered patch's complete context, not a marker.
                section = (COMPONENT / '0001-register-distinct-fusion-service-accounts.patch').read_text().split(
                    'diff --git a/base/startup/init/services/etc/' + kind + ' ')[1].split('diff --git ')[0]
                lines = section.split('@@', 2)[2].splitlines()[1:]
                file = root / 'base/startup/init/services/etc' / kind
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text('\n'.join(row[1:] for row in lines if row.startswith(' ')) + '\n')
            for _ in range(2):
                subprocess.run(['bash', str(REPO / 'patches/lib/apply_component_dir.sh'), str(COMPONENT),
                                '--source-root', str(root)], check=True, capture_output=True)
            for kind in TABLES:
                text = (root / 'base/startup/init/services/etc' / kind).read_text()
                self.assertEqual(text.count('fusion_ranging:x:6067:'), 1)
                self.assertEqual(text.count('partner_device_agent:x:6068:'), 1)
        builder = (REPO / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        self.assertLess(builder.index('bash "${FUSION_ACCOUNTS_COMPONENT_SCRIPT}"'),
                        builder.index('  write_source_preparation_metadata'))

    def test_full_table_unknown_edit_and_symlink_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            init = root / 'base/startup/init'
            fusion = root / 'foundation/communication/fusion_connectivity'
            hashes = {}
            for relative in guard.CONFIGS:
                file = fusion / relative
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(b'unchanged authority fixture')
                hashes[relative] = hashlib.sha256(file.read_bytes()).hexdigest()
            for kind, original in TABLES.items():
                file = init / 'services/etc' / kind
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(original)
            def git(command, **kwargs):
                if command[-2:] == ['rev-parse', 'HEAD']:
                    return (guard.INIT_REVISION if Path(command[2]) == init else guard.FUSION_REVISION) + '\n'
                return TABLES[command[-1].split('/')[-1]]
            def invoke():
                with patch.object(sys, 'argv', ['check.py', '--source-root', str(root)]), \
                     patch.object(guard, 'CONFIGS', hashes), \
                     patch.object(guard.subprocess, 'check_output', side_effect=git), contextlib.redirect_stdout(io.StringIO()):
                    guard.main()
            invoke()
            target = init / 'services/etc/passwd'
            target.write_bytes(TABLES['passwd'] + b'unknown user edit')
            with self.assertRaises(SystemExit): invoke()
            self.assertTrue(target.read_bytes().endswith(b'unknown user edit'))
            target.unlink()
            outside = root / 'outside-passwd'
            outside.write_bytes(TABLES['passwd'])
            target.symlink_to(outside)
            with self.assertRaises(SystemExit): invoke()
            self.assertEqual(outside.read_bytes(), TABLES['passwd'])


if __name__ == '__main__':
    unittest.main()
