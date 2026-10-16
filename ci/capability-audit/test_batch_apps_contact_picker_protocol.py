#!/usr/bin/env python3
"""Small source-state and real public-JS checks; native sanitizer runs separately."""
import base64
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
FIX = ROOT / 'ci/capability-audit/fixtures/batch_apps/contact_picker_protocol'
PROJECT = 'applications/standard/contacts_data'
COMPONENT = ROOT / 'patches/common' / PROJECT / 'picker_result_protocol'


def prepare(root):
    for relative, record in json.loads((FIX / 'inspection.json').read_text())['files'].items():
        raw = gzip.decompress(base64.b64decode(record['gzip_base64']))
        assert hashlib.sha256(raw).hexdigest() == record['sha256']
        path = root / PROJECT / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)


def apply(root):
    return subprocess.run(['bash', str(COMPONENT / 'apply.sh'), '--source-root', str(root)],
                          capture_output=True, text=True)


class CallerProtocol(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='contacts-caller-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        prepare(self.root)

    def test_exact_component_replay_and_unchanged_build(self):
        for _ in range(3):
            result = apply(self.root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        hashes = json.loads((FIX / 'candidate-hashes.json').read_text())
        for relative, digest in hashes.items():
            self.assertEqual(hashlib.sha256((self.root / relative).read_bytes()).hexdigest(), digest)
        actual = (self.root / PROJECT / 'contacts/src/contacts_napi_utils.cpp').read_text()
        start = actual.index('namespace {\nstruct SelectionRequest {')
        end = actual.index('\nModalUICallback::ModalUICallback(', start)
        self.assertEqual(actual[start:end].strip(), (FIX / 'selection_native.cpp.txt').read_text().strip())
        record = json.loads((FIX / 'inspection.json').read_text())['files']['contacts/BUILD.gn']
        self.assertEqual(hashlib.sha256((self.root / PROJECT / 'contacts/BUILD.gn').read_bytes()).hexdigest(), record['sha256'])

    def test_drift_or_partial_state_fails_before_other_inputs_mutate(self):
        self.assertEqual(apply(self.root).returncode, 0)
        target = self.root / PROJECT / 'contacts/include/contact_picker_protocol.h'
        target.write_text(target.read_text() + '// unknown source\n')
        targets = json.loads((FIX / 'candidate-hashes.json').read_text())
        before = {name: (self.root / name).read_bytes() for name in targets}
        self.assertNotEqual(apply(self.root).returncode, 0)
        self.assertEqual(before, {name: (self.root / name).read_bytes() for name in targets})

    def test_actual_public_js_overloads_and_error_propagation(self):
        self.assertEqual(apply(self.root).returncode, 0)
        result = subprocess.run(['node', '--unhandled-rejections=strict', str(FIX / 'caller_test.cjs'),
                                 str(self.root / PROJECT / 'contacts/src/contact.js')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('86 actual public JS wrapper scenarios passed', result.stdout)


if __name__ == '__main__':
    unittest.main()
