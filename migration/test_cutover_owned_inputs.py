import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class CutoverTest(unittest.TestCase):
    def test_changed_files_are_preserved_and_success_retains_originals(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            environment = dict(os.environ, GIT_AUTHOR_NAME='Migration test',
                GIT_AUTHOR_EMAIL='test@example.invalid', GIT_COMMITTER_NAME='Migration test',
                GIT_COMMITTER_EMAIL='test@example.invalid')
            subprocess.run(['git', 'init', '-b', 'codex/ohos7-integrated-development', str(root)],
                           check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            entries = []
            for relative in ('patches/input.patch', 'scripts/input.py'):
                content = (relative + '\n').encode()
                for base in (root, root / '.qemu/component-inputs'):
                    target = base / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(content)
                    target.chmod(0o644)
                entries.append(dict(path=relative, mode='100644', sha256=hashlib.sha256(content).hexdigest()))
            subprocess.run(['git', '-C', str(root), 'add', 'patches', 'scripts'], check=True)
            subprocess.run(['git', '-C', str(root), '-c', 'commit.gpgsign=false', 'commit', '-m', 'fixture'],
                           env=environment, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            (root / 'patches/untracked-evidence.txt').write_text('preserve me\n')
            index = root / 'index.json'
            index.write_text(json.dumps(dict(files=entries)))
            verification = root / 'verified.json'
            verification.write_text(json.dumps(dict(complete=True,
                index_sha256=hashlib.sha256(index.read_bytes()).hexdigest())))
            command = [sys.executable, str(Path(__file__).with_name('cutover_owned_inputs.py')),
                       '--root', str(root), '--index', str(index), '--verification', str(verification)]
            helper = root / 'scripts/input.py'
            helper.write_text('unreviewed change\n')
            failed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertNotEqual(failed.returncode, 0)
            self.assertFalse((root / 'patches').is_symlink())
            self.assertEqual(helper.read_text(), 'unreviewed change\n')
            helper.write_text('scripts/input.py\n')
            completed = subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            receipt = json.loads(completed.stdout)
            self.assertTrue((root / 'patches').is_symlink())
            self.assertTrue(helper.is_symlink())
            self.assertEqual(helper.read_text(), 'scripts/input.py\n')
            backup = Path(receipt['original_backup'])
            self.assertEqual((backup / 'patches/untracked-evidence.txt').read_text(), 'preserve me\n')
            self.assertEqual((backup / 'scripts/input.py').read_text(), 'scripts/input.py\n')


if __name__ == '__main__':
    unittest.main()
