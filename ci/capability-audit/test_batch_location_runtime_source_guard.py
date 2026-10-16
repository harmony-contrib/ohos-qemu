#!/usr/bin/env python3
"""Exercise strict whole-byte/HEAD guards on bounded synthetic source snapshots.

Only copied fixture manifests/HEADs are substituted. Production full-file hashes
remain pinned and are separately checked against complete fixed source copies.
"""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from batch_location_runtime_fixture import COMPONENT, FIXTURE, PREFIX, ROOT, runtime_sources


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


class RuntimeSourceGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.states = {
            'original': json.loads(FIXTURE.read_text())['files'],
            'prefix_1': runtime_sources(prefix=1),
            'final': runtime_sources(),
        }

    def fixture(self, directory, state='original'):
        root = Path(directory) / 'source'
        project = root / 'base/location/location'
        project.mkdir(parents=True)
        subprocess.run(['git', 'init', '-q', str(project)], check=True)
        subprocess.run(['git', '-C', str(project), '-c', 'user.name=Location fixture', '-c',
                        'user.email=location-fixture@example.invalid', 'commit', '--allow-empty', '-qm', 'Fixture HEAD'], check=True)
        head = subprocess.check_output(['git', '-C', str(project), 'rev-parse', 'HEAD'], text=True).strip()
        component = Path(directory) / 'fixture' / COMPONENT.relative_to(ROOT)
        shutil.copytree(COMPONENT, component)
        shutil.copytree(ROOT / 'patches/lib', Path(directory) / 'fixture/patches/lib')
        manifest = json.loads((component / 'source_states.json').read_text())
        pinned = manifest['revision']
        manifest['revision'] = head
        manifest['states'] = {name: {path: digest(text) for path, text in values.items()}
                              for name, values in self.states.items()}
        (component / 'source_states.json').write_text(json.dumps(manifest))
        verifier = component / 'verify_source.py'
        verifier.write_text(verifier.read_text().replace(pinned, head))
        for name, text in self.states[state].items():
            target = root / (PREFIX + name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(text)
        return root, component

    def apply(self, root, component):
        return subprocess.run(['bash', str(component / 'apply.sh'), '--source-root', str(root)],
                              capture_output=True, text=True)

    def contents(self, root):
        return {name: (root / (PREFIX + name)).read_bytes() for name in self.states['original']}

    def test_all_legal_prefixes_and_idempotence(self):
        for state in self.states:
            with self.subTest(state=state), tempfile.TemporaryDirectory(prefix='batch-location-guard-') as directory:
                root, component = self.fixture(directory, state)
                result = self.apply(root, component)
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                expected = {name: text.encode() for name, text in self.states['final'].items()}
                self.assertEqual(expected, self.contents(root))
                result = self.apply(root, component)
                self.assertEqual(0, result.returncode, result.stdout + result.stderr)
                self.assertEqual(expected, self.contents(root))

    def test_unknown_and_mixed_edits_rejected_before_mutation(self):
        target = 'services/location_locator/locator/source/locator_required_data_manager.cpp'
        for mixed in [False, True]:
            with self.subTest(mixed=mixed), tempfile.TemporaryDirectory(prefix='batch-location-guard-') as directory:
                root, component = self.fixture(directory)
                path = root / (PREFIX + target)
                path.write_text(self.states['final'][target] if mixed else path.read_text() + '\n// unrelated edit\n')
                before = self.contents(root)
                self.assertNotEqual(0, self.apply(root, component).returncode)
                self.assertEqual(before, self.contents(root))
                self.assertFalse((root / '.ohos-qemu-patches').exists())

    def test_symlink_target_and_parent_rejected(self):
        for parent in [False, True]:
            with self.subTest(parent=parent), tempfile.TemporaryDirectory(prefix='batch-location-guard-') as directory:
                root, component = self.fixture(directory)
                target = root / PREFIX / ('services/location_locator/locator/include' if parent else
                                          'services/location_locator/locator/include/locator_ability.h')
                external = Path(directory) / 'outside'
                if parent:
                    shutil.copytree(target, external)
                    shutil.rmtree(target)
                else:
                    shutil.copy2(target, external)
                    target.unlink()
                target.symlink_to(external, target_is_directory=parent)
                before = self.contents(root)
                self.assertNotEqual(0, self.apply(root, component).returncode)
                self.assertEqual(before, self.contents(root))
                self.assertFalse((root / '.ohos-qemu-patches').exists())

    def test_wrong_head_and_changed_patch_rejected(self):
        for patch_change in [False, True]:
            with self.subTest(patch_change=patch_change), tempfile.TemporaryDirectory(prefix='batch-location-guard-') as directory:
                root, component = self.fixture(directory)
                if patch_change:
                    patch = sorted(component.glob('*.patch'))[0]
                    patch.write_text(patch.read_text() + '\n')
                else:
                    project = root / PREFIX
                    subprocess.run(['git', '-C', str(project), '-c', 'user.name=Location fixture', '-c',
                                    'user.email=location-fixture@example.invalid', 'commit', '--allow-empty', '-qm',
                                    'Unexpected HEAD'], check=True)
                before = self.contents(root)
                self.assertNotEqual(0, self.apply(root, component).returncode)
                self.assertEqual(before, self.contents(root))
                self.assertFalse((root / '.ohos-qemu-patches').exists())

    def test_production_revision_and_frozen_targets_are_consistent(self):
        manifest = json.loads((COMPONENT / 'source_states.json').read_text())
        frozen = json.loads((ROOT / 'docs/capability-audit/parallel/location/round2-freeze-inputs.json').read_text())
        self.assertEqual(frozen['revision'], manifest['revision'])
        self.assertEqual(set(PREFIX + path for path in manifest['files']), set(frozen['targets']))
        for path, info in frozen['targets'].items():
            self.assertEqual(info['sha256'], manifest['states']['original'][path.removeprefix(PREFIX)])


if __name__ == '__main__':
    unittest.main()
