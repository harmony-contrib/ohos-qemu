"""Partial failure preservation contracts; no actual app/audio result is implied."""
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest

from run_normal_hap_probe import APP_FILES, preserve_microphone_failure


class MicrophoneFailurePreservationTests(unittest.TestCase):
    def test_only_current_nonce_regular_owned_bounded_files_are_received(self):
        for mutation in ('good', 'foreign', 'duplicate', 'wrong-owner', 'oversize', 'truncated', 'different-boot'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                name = 'audio-capture-' + 'a' * 32 + '-permission.json'
                remote = APP_FILES + name
                line = remote + '|20010001 600 2'
                if mutation == 'foreign': line = line.replace('a' * 32, 'b' * 32)
                if mutation == 'wrong-owner': line = line.replace('20010001', '0')
                if mutation == 'oversize': line = remote + '|20010001 600 16777217'
                rows = ['BEGIN', line, 'END']
                if mutation == 'duplicate': rows.insert(1, line)
                if mutation == 'truncated': rows.pop()
                def actual(script, label):
                    return ('other-boot' if mutation == 'different-boot' else 'owned-boot') if label == 'MIC-partial-boot' else '\n'.join(rows)
                received = []
                def command(argv, label): received.append(argv); Path(argv[-1]).write_bytes(b'{}')
                runtime = SimpleNamespace(output=Path(directory), args=SimpleNamespace(hdc='owned-hdc', target='owned-target'),
                                          actual_shell=actual, command=command)
                report = dict(run_id='a' * 32, persona='audio-capture', boot_id='owned-boot', ordinary_uid=20010001,
                              ordinary_result_directory=APP_FILES)
                if mutation == 'good':
                    result = preserve_microphone_failure(runtime, report)
                    self.assertEqual(len(result['files']), 1)
                    self.assertEqual(result['files'][0]['bytes'], 2)
                    self.assertIn('NOT_behavior_pass', result['scope'])
                else:
                    with self.assertRaises(ValueError): preserve_microphone_failure(runtime, report)
                    # Invalid complete inventory must not begin any transfer.
                    self.assertEqual(received, [])


if __name__ == '__main__': unittest.main()
