import gzip
import hashlib
from pathlib import Path
import tempfile
import unittest

from collect_sync_evidence import write_chunk


class ConversionArchiveTest(unittest.TestCase):
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
