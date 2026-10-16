#!/usr/bin/env python3
"""Execute extracted real provider methods; no HAP/runtime acceptance claim."""
import base64
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / 'ci/capability-audit/fixtures/batch_apps/provider_lifecycle'


class Lifecycle(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='apps-lifecycle-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        for fixture in [FIX.parent / 'contacts_theme/inspection.json', FIX / 'inspection.json']:
            for relative, record in json.loads(fixture.read_text())['files'].items():
                raw = gzip.decompress(base64.b64decode(record['gzip_base64']))
                self.assertEqual(hashlib.sha256(raw).hexdigest(), record['sha256'])
                target = self.root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(raw)

    def apply(self, project, component):
        return subprocess.run(['bash', str(ROOT / 'patches/common/applications/standard' / project / component / 'apply.sh'),
                               '--source-root', str(self.root)], capture_output=True, text=True)

    def prepare(self):
        for project, component in [('contacts', 'source_provider'), ('theme', 'source_provider'),
                                   ('contacts', 'picker_session_lifecycle'), ('theme', 'renderer_lifecycle')]:
            result = self.apply(project, component)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_exact_source_metadata_and_business_stacks_replay_twice(self):
        for _ in range(3):
            self.prepare()
        for name in ('contacts_theme', 'provider_lifecycle'):
            for relative, expected in json.loads((FIX.parent / name / 'candidate-hashes.json').read_text()).items():
                self.assertEqual(hashlib.sha256((self.root / relative).read_bytes()).hexdigest(), expected)
        metadata = json.loads((FIX.parent / 'contacts_theme/inspection.json').read_text())['files']
        for relative, record in metadata.items():
            if relative.endswith(('module.json5', '.p7b', 'oh-package.json5')):
                # Only Theme's newly added OHPM files are changed, not these originals.
                self.assertEqual(hashlib.sha256((self.root / relative).read_bytes()).hexdigest(), record['sha256'])

    def test_partial_and_drift_business_state_preserves_every_input(self):
        self.prepare()
        relative = 'applications/standard/contacts/entry/src/main/ets/uiExtentionAbility/PickerSession.ets'
        target = self.root / relative
        target.write_bytes(target.read_bytes() + b'// unknown\n')
        before = {p: (self.root / p).read_bytes() for p in json.loads((FIX / 'candidate-hashes.json').read_text())}
        self.assertNotEqual(self.apply('contacts', 'picker_session_lifecycle').returncode, 0)
        self.assertEqual(before, {p: (self.root / p).read_bytes() for p in before})

    def test_real_extracted_request_worker_query_extension_and_renderer_methods(self):
        self.prepare()
        result = subprocess.run(['node', '--unhandled-rejections=strict', str(FIX / 'lifecycles.cjs'), str(self.root)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('actual source scenarios passed', result.stdout)


if __name__ == '__main__':
    unittest.main()
