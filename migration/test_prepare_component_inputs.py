import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ComponentInputsTest(unittest.TestCase):
    def test_locked_local_repositories_reconstruct_inputs_and_reject_tampering(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            upstream = directory / 'upstream'
            component = upstream / 'build.git'
            manifest = directory / 'manifest'
            environment = dict(os.environ, GIT_AUTHOR_NAME='Migration test',
                GIT_AUTHOR_EMAIL='test@example.invalid', GIT_COMMITTER_NAME='Migration test',
                GIT_COMMITTER_EMAIL='test@example.invalid', GIT_CONFIG_COUNT='1',
                GIT_CONFIG_KEY_0='url.' + upstream.as_uri() + '/.insteadOf',
                GIT_CONFIG_VALUE_0='https://github.com/openharmony-qemu/')

            def git(repository, *args):
                return subprocess.check_output(['git', '-C', str(repository), *args],
                    env=environment, stderr=subprocess.PIPE)

            for repository in (component, manifest):
                repository.mkdir(parents=True)
                git(repository, 'init', '-b', 'OpenHarmony-7.0-Release-qemu')
            content = b'component-owned source preparation input\n'
            relative = '.qemu/adaptations/patches/example.patch'
            payload = component / relative
            payload.parent.mkdir(parents=True)
            payload.write_bytes(content)
            utility = component / '.qemu/materialize_adaptations.py'
            utility.write_bytes((ROOT / 'migration/materialize_component_recipes.py').read_bytes())
            utility.chmod(0o755)
            git(component, 'add', '.')
            git(component, '-c', 'commit.gpgsign=false', 'commit', '-m', 'fixture component')
            revision = git(component, 'rev-parse', 'HEAD').decode().strip()
            index = dict(schema_version=1, baseline_branch='OpenHarmony-7.0-Release-qemu',
                repositories={'build': [{'tree': 'ohos', 'path': 'build', 'revision': revision}]},
                materializer=dict(repository='build', path='.qemu/materialize_adaptations.py',
                                  sha256=hashlib.sha256(utility.read_bytes()).hexdigest()),
                files=[dict(path='patches/example.patch', mode='100644',
                    sha256=hashlib.sha256(content).hexdigest(), parts=[dict(repository='build',
                    path=relative, sha256=hashlib.sha256(content).hexdigest())])])
            index_path = manifest / 'adaptations.json'
            index_path.write_text(json.dumps(index))
            lock = dict(complete=True, adaptations_sha256=hashlib.sha256(index_path.read_bytes()).hexdigest(),
                        repositories=[dict(name='build', qemu_revision=revision)])
            (manifest / 'components.lock.json').write_text(json.dumps(lock))
            git(manifest, 'add', '.')
            git(manifest, '-c', 'commit.gpgsign=false', 'commit', '-m', 'fixture manifest')
            arguments = [sys.executable, str(ROOT / 'scripts/prepare_component_inputs.py'),
                '--manifest', str(manifest), '--cache', str(directory / 'cache')]
            output = directory / 'materialized'
            subprocess.run(arguments + ['--output', str(output)], env=environment,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
            self.assertEqual((output / 'patches/example.patch').read_bytes(), content)
            receipt = json.loads((output / '.component-inputs.json').read_text())
            self.assertFalse(receipt['build_validated'])
            self.assertFalse(receipt['runtime_validated'])
            # Existing generated inputs are never overwritten.
            result = subprocess.run(arguments + ['--output', str(output)], env=environment,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((output / 'patches/example.patch').read_bytes(), content)
            # A modified manifest must fail before another tree is materialized.
            index_path.write_text(json.dumps(index) + '\n')
            rejected = directory / 'rejected'
            result = subprocess.run(arguments + ['--output', str(rejected)], env=environment,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(rejected.exists())


if __name__ == '__main__':
    unittest.main()
