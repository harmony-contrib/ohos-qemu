import gzip
import hashlib
from pathlib import Path
import tempfile
import unittest

from collect_sync_evidence import verify_conflict_issues, write_chunk


class ConversionArchiveTest(unittest.TestCase):
    def test_conflict_requires_matching_open_issue_in_the_central_repository(self):
        repository = 'openharmony-qemu/source'
        ref = 'refs/heads/renovate/dependency'
        report = dict(repository=repository, results=[dict(ref=ref, old='old', new='new',
                                                          status='conflict', issue=2)])
        marker = hashlib.sha256((repository + '\n' + ref).encode()).hexdigest()
        issue = dict(html_url='https://github.com/openharmony-qemu/mirror-sync/issues/2',
            state='open', body='\n'.join(['<!-- mirror-conflict:' + marker + ' -->',
                'Repository: https://github.com/' + repository, 'Ref: `' + ref + '`',
                'Destination: `old`', 'Incoming: `new`']))
        rows = verify_conflict_issues(report, lambda number: issue)
        self.assertTrue(rows[0]['issue_verified'])
        self.assertEqual(rows[0]['old'], 'old')
        for changed in (dict(issue, state='closed'),
                        dict(issue, body=issue['body'].replace('Destination: `old`', 'Destination: `different`')),
                        dict(issue, html_url='https://github.com/other/repository/issues/2')):
            with self.assertRaisesRegex(ValueError, 'does not describe'):
                verify_conflict_issues(report, lambda number: changed)

    def test_repeated_archival_preserves_exact_bytes_and_rejects_replacement(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            original = [b'old,new\n', b'original-sha,hosted-sha\n']
            record = write_chunk(directory, original, 0)
            path = directory / record['file']
            encoded = path.read_bytes()
            self.assertEqual(gzip.decompress(encoded), b''.join(original))
            self.assertEqual(record['sha256'], hashlib.sha256(b''.join(original)).hexdigest())
            self.assertEqual(write_chunk(directory, original, 0), record)
            self.assertEqual(path.read_bytes(), encoded)
            with self.assertRaisesRegex(ValueError, 'preserving existing evidence'):
                write_chunk(directory, [b'different history\n'], 0)
            self.assertEqual(path.read_bytes(), encoded)


if __name__ == '__main__':
    unittest.main()
