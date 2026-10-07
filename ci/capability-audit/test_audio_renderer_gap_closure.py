"""Complete challenged Renderer closure fixtures, not actual guest acceptance."""
import json
from pathlib import Path
import tempfile
import unittest

from run_root_probe import digest
from test_verify_audio_stream_results import IDENTITY, RUN, render, rows
from verify_gap_closure import behavior_results


class AudioRendererGapClosureTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.work = self.root / 'audio-stream'
        self.work.mkdir()
        self.raw = self.work / 'results.log'
        self.raw.write_text(render(rows()))
        self.identity = self.work / 'application-identity.json'
        self.identity.write_text(IDENTITY)
        self.result = self.work / 'verified-result.json'
        self.result.write_text(json.dumps({'status': 'pass', 'results': rows(), 'archive_sha256': 'a' * 64}))
        self.document = {'status': 'pass', 'persona': 'audio-stream', 'boot_id': 'fixture',
            'archive_sha256': 'a' * 64, 'run_id': RUN, 'raw_results_sha256': digest(self.raw),
            'ordinary_identity_sha256': digest(self.identity), 'result': str(self.result),
            'result_sha256': digest(self.result)}
        self.path = self.work / 'evidence.json'
        self.save()

    def save(self):
        self.path.write_text(json.dumps(self.document))

    def test_only_actual_renderer_gap_not_capture_haptics_or_all_audio_is_closed(self):
        actual = behavior_results(self.root, 'fixture', 'a' * 64)
        self.assertEqual(set(actual), {'behavior:audio-renderer-data-path-unavailable'})
        self.assertIn('Capturer', next(iter(actual.values()))['not_claimed'])

    def test_old_boot_wrong_archive_tampered_raw_or_identity_never_closes_gap(self):
        self.assertEqual(behavior_results(self.root, 'other-boot', 'a' * 64), {})
        self.assertEqual(behavior_results(self.root, 'fixture', 'b' * 64), {})
        for path in (self.raw, self.identity, self.result):
            original = path.read_text()
            path.write_text(original + 'changed')
            self.assertEqual(behavior_results(self.root, 'fixture', 'a' * 64), {})
            path.write_text(original)

    def test_updated_hash_cannot_hide_missing_PCM_or_privileged_persona(self):
        self.raw.write_text(render(rows()[:-1]))
        self.document['raw_results_sha256'] = digest(self.raw)
        self.save()
        with self.assertRaises(ValueError):
            behavior_results(self.root, 'fixture', 'a' * 64)
        self.raw.write_text(render(rows()))
        self.document['raw_results_sha256'] = digest(self.raw)
        self.identity.write_text(IDENTITY.replace('normal', 'system_basic'))
        self.document['ordinary_identity_sha256'] = digest(self.identity)
        self.save()
        with self.assertRaises(ValueError):
            behavior_results(self.root, 'fixture', 'a' * 64)


if __name__ == '__main__':
    unittest.main()
