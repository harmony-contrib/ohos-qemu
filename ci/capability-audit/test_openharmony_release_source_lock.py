"""Project-lock/manifest fixtures; the real 519 HEAD check is separate evidence."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import openharmony_release_source_lock as source_lock


class MainReleaseSourceLockTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.document = {'schema_version': 1, 'manifest_branch': 'OpenHarmony-7.0-Release',
            'manifest_revision': source_lock.MANIFEST_REVISION,
            'projects': [{'name': 'project_a', 'path': 'base/a', 'revision': '1' * 40},
                         {'name': 'project_b', 'path': 'third_party/b', 'revision': '2' * 40}]}
        self.lock = self.root / 'lock.json'
        self.source = self.root / 'source'
        for path in ('.repo/manifests', 'base/a', 'third_party/b'):
            (self.source / path).mkdir(parents=True, exist_ok=True)
        self.save(self.document)

    def save(self, document):
        self.lock.write_text(json.dumps(document))

    def test_real_checked_in_graph_has_all_exact_unique_heads(self):
        document = source_lock.load_lock(source_lock.DEFAULT_LOCK)
        self.assertEqual(len(document['projects']), 519)
        self.assertEqual(document['projects'], sorted(document['projects'], key=lambda p: p['path']))
        self.assertIn({'name': 'web_webview', 'path': 'base/web/webview',
            'revision': 'd421b6b549fa3038ad01cf34589b959286137be9'}, document['projects'])

    def test_moving_head_bad_branch_duplicate_and_unsafe_path_rejected(self):
        for change in (lambda d: d.update(manifest_branch='master'),
                       lambda d: d['projects'][0].update(revision='OpenHarmony-7.0-Release'),
                       lambda d: d['projects'].append(d['projects'][0]),
                       lambda d: d['projects'][0].update(path='../elsewhere'),
                       lambda d: d['projects'][0].update(path='base//a'),
                       lambda d: d['projects'][0].update(path='/base/a')):
            document = deepcopy(self.document)
            change(document)
            self.save(document)
            with self.assertRaises(ValueError):
                source_lock.load_lock(self.lock)

    def test_install_is_repeatable_preserves_fetch_hints_and_unknown_edits(self):
        unknown_source = self.source / 'base/a/user.txt'
        unknown_source.write_text('user edit')
        for _ in range(2):
            source_lock.install(self.source, self.document)
        target = self.source / '.repo/local_manifests/ohos-qemu-7.0-source-lock.xml'
        elements = ET.parse(target).findall('extend-project')
        self.assertEqual([e.attrib for e in elements], self.document['projects'])
        self.assertEqual(unknown_source.read_text(), 'user edit')
        target.write_text('foreign manifest edit')
        with self.assertRaises(ValueError):
            source_lock.install(self.source, self.document)
        self.assertEqual(target.read_text(), 'foreign manifest edit')

    def test_manifest_or_project_head_drift_and_aliased_checkout_rejected(self):
        def head(argv, **kwargs):
            relative = Path(argv[2]).relative_to(self.source).as_posix()
            return {'.repo/manifests': source_lock.MANIFEST_REVISION,
                    'base/a': '1' * 40, 'third_party/b': '2' * 40}[relative] + '\n'
        with patch.object(source_lock.subprocess, 'check_output', side_effect=head):
            observed = source_lock.verify(self.source, self.document)
            self.assertEqual(observed, [{**p, 'observed_head': p['revision']} for p in self.document['projects']])
            changed = deepcopy(self.document)
            changed['projects'][0]['revision'] = '3' * 40
            with self.assertRaises(ValueError):
                source_lock.verify(self.source, changed)
            (self.source / 'base/a').rmdir()
            (self.source / 'base/a').symlink_to(self.source / 'third_party/b', target_is_directory=True)
            with self.assertRaises(ValueError):
                source_lock.verify(self.source, self.document)
        with patch.object(source_lock.subprocess, 'check_output', return_value='0' * 40):
            with self.assertRaises(ValueError):
                source_lock.verify(self.source, self.document)

    def test_resolved_graph_wrong_commit_or_extra_project_rejected(self):
        resolved = self.root / 'resolved.xml'
        for projects in ([{**self.document['projects'][0], 'revision': '0' * 40}],
                         [*self.document['projects'], {'name': 'extra', 'path': 'extra', 'revision': '3' * 40}]):
            manifest = ET.Element('manifest')
            for project in projects:
                ET.SubElement(manifest, 'project', **project)
            resolved.write_bytes(ET.tostring(manifest))
            with patch.object(source_lock.subprocess, 'check_output', return_value=source_lock.MANIFEST_REVISION):
                with self.assertRaises(ValueError):
                    source_lock.verify(self.source, self.document, resolved)

    def test_sync_reuse_and_packaging_all_check_main_graph(self):
        builder = (ROOT / 'scripts/build_standard_qemu_in_docker.sh').read_text()
        self.assertEqual(builder.count('openharmony_release_source_lock.py" --source-root "${OHOS_ROOT}" --install'), 2)
        for filename in ('scripts/package_standard_qemu.sh', 'scripts/verify_device_type_package.sh'):
            text = (ROOT / filename).read_text()
            self.assertIn('openharmony-project-heads.json', text)
            self.assertIn('openharmony-project-lock.json', text)


if __name__ == '__main__':
    unittest.main()
