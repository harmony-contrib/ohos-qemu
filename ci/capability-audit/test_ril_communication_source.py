"""Fixed complete CRLF source, repeatability and preservation at the RIL boundary."""
import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('ril_source', ROOT / 'scripts/prepare_ril_communication_callback.py')
M = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(M)


class RilSourceTests(unittest.TestCase):
    def test_real_complete_source_retains_bytes_and_is_repeatable(self):
        raw = (Path(__file__).parent / 'fixtures/ril_communication/IRilCallback.idl').read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), M.BEFORE_SHA)
        self.assertIn(b'\r\n', raw)
        final = M.transform(raw)
        self.assertEqual(final.replace(M.APPEND.encode().replace(b'\n', b'\r\n'), b''), raw)
        self.assertEqual(final, M.transform(final))
        self.assertNotIn(b'\n', final.replace(b'\r\n', b''))
        for broken in (raw + b'// unrelated edit', final.replace(b'boolean is5A', b'int is5A')):
            with self.assertRaises(ValueError):
                M.transform(broken)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / M.TARGET
            path.parent.mkdir(parents=True)
            path.write_bytes(raw)
            M.apply(root)
            M.apply(root)
            self.assertEqual(path.read_bytes(), final)
            path.write_bytes(raw + b'// edit')
            with self.assertRaises(ValueError):
                M.apply(root)
            self.assertEqual(path.read_bytes(), raw + b'// edit')


if __name__ == '__main__':
    unittest.main()
