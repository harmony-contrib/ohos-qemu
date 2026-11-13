import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from snapshot_publication import snapshot


class SnapshotTest(unittest.TestCase):
    def fixture(self, directory):
        root = directory / 'root'
        workspace = directory / 'workspace'
        manifest = workspace / 'manifest'

        def write(path, value):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(value) + '\n')
            return path

        branch = 'OpenHarmony-7.0-Release-qemu'
        revision = 'a' * 40
        upstream = 'b' * 40
        catalog = write(directory / 'catalog.json', dict(repositories=[dict(name='build',
            auto_sync=True, inputs=[dict(revision=upstream)])]))
        write(workspace / 'repository-creation.jsonl', dict(name='build', status='created'))
        write(workspace / 'baseline-publication.jsonl',
              dict(name='build', status='published', remote_revision=upstream))
        export = workspace / 'exports/build'
        write(export / 'export.json', dict(name='build'))
        (export / 'tracked.patch').write_bytes(b'fixture patch\n')
        fingerprint = hashlib.sha256((export / 'export.json').read_bytes() +
                                     (export / 'tracked.patch').read_bytes()).hexdigest()
        write(workspace / 'source-publication.jsonl', dict(name='build', status='published',
            qemu_commit=revision, parent=upstream, export_sha256=fingerprint))
        write(workspace / 'reviewed-publication-selection.json', dict(phases=[dict(
            exports='exports', journal='source-publication.jsonl', repositories=['build'])]))
        payload = root / '.qemu/component-inputs/patches/example.patch'
        payload.parent.mkdir(parents=True)
        payload.write_bytes(b'component input\n')
        payload.chmod(0o644)
        root.joinpath('patches').symlink_to('.qemu/component-inputs/patches')
        index = write(manifest / 'adaptations.json', dict(repositories={'build': []},
            materializer=dict(repository='build'), files=[dict(path='patches/example.patch',
            mode='100644', sha256=hashlib.sha256(payload.read_bytes()).hexdigest())]))
        index_hash = hashlib.sha256(index.read_bytes()).hexdigest()
        write(workspace / 'remote-state-latest.json', dict(repositories=[dict(name='build',
            qemu_revision=revision, default_branch=branch, matches_expected=True)]))
        write(workspace / 'component-payload-verification.json', dict(complete=True,
            index_sha256=index_hash, repositories=[dict(repository='build', status='verified',
            qemu_commit=revision, expected_files=1, verified_files=1)]))
        write(workspace / 'mirror-sync/repositories.json', dict(repositories=[
            dict(name='build', enabled=True)]))
        write(manifest / 'migration-evidence/mirror-sync/build-sync-123.json',
            dict(repository='openharmony-qemu/build', remote_refs_verified=True,
                 results={'created': 1}))
        cutover = write(workspace / 'backup/cutover.json', dict(index_sha256=index_hash,
            original_files_preserved=True, original_backup=str(workspace / 'backup')))
        return root, workspace, manifest, catalog, cutover

    def test_complete_requires_current_remote_and_payload_heads(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, workspace, manifest, catalog, cutover = self.fixture(Path(temporary))
            status = snapshot(workspace, catalog, root, True, cutover)
            self.assertTrue(all(status['completion_gates'].values()))
            self.assertFalse(status['build_validated'])
            self.assertFalse(status['runtime_validated'])
            previous = (manifest / 'components.lock.json').read_bytes()
            journal = workspace / 'source-publication.jsonl'
            row = json.loads(journal.read_text())
            row.update(parent=row['qemu_commit'], qemu_commit='c' * 40)
            with journal.open('a') as stream:
                stream.write(json.dumps(row) + '\n')
            with self.assertRaisesRegex(ValueError, 'remote_branches_and_defaults, component_payloads'):
                snapshot(workspace, catalog, root, True, cutover)
            self.assertEqual((manifest / 'components.lock.json').read_bytes(), previous)

    def test_changed_export_or_missing_mirror_cannot_be_complete(self):
        with tempfile.TemporaryDirectory() as temporary:
            root, workspace, manifest, catalog, cutover = self.fixture(Path(temporary))
            (workspace / 'exports/build/tracked.patch').write_bytes(b'changed after publication\n')
            mirror = manifest / 'migration-evidence/mirror-sync/build-sync-123.json'
            mirror.unlink()
            status = snapshot(workspace, catalog, root)
            self.assertEqual(status['publication_phases'][0]['pending'], ['build'])
            self.assertEqual(status['mirrors_awaiting_verification'], ['build'])
            self.assertFalse(json.loads((manifest / 'components.lock.json').read_text())['complete'])
            with self.assertRaisesRegex(ValueError, 'reviewed_publications'):
                snapshot(workspace, catalog, root, True, cutover)


if __name__ == '__main__':
    unittest.main()
