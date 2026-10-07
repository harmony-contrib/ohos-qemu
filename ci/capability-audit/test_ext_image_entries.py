"""Read-only extraction unit fixtures; no actual image/runtime acceptance."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from ext_image_entries import dump_unique_file


class ExtImageEntryTests(unittest.TestCase):
    def extract(self, inodes):
        with tempfile.TemporaryDirectory() as directory:
            def run(argv, **kwargs):
                request = argv[2]
                if request.startswith("stat "):
                    inode = inodes.pop(0)
                    output = f"Inode: {inode}   Type: regular    Mode:  0644\n" if inode else ""
                    return subprocess.CompletedProcess(argv, 0, stdout=output, stderr="")
                Path(request.split(" ")[-1]).write_bytes(b"synthetic extracted fixture")
                return subprocess.CompletedProcess(argv, 0, stdout=b"", stderr=b"")
            with patch("ext_image_entries.subprocess.run", side_effect=run):
                _, identity = dump_unique_file(Path("fixture.img"), ("/app/a", "/system/app/a"), directory, "debugfs")
                return identity

    def test_two_paths_to_same_inode_are_one_file(self):
        self.assertEqual(self.extract([2207, 2207])["image_path_aliases"], ["/app/a", "/system/app/a"])

    def test_different_regular_files_rejected_even_if_identical(self):
        with self.assertRaisesRegex(ValueError, "unambiguous"):
            self.extract([2207, 2208])

    def test_missing_entry_zero_exit_is_not_pass(self):
        with self.assertRaisesRegex(ValueError, "unambiguous"):
            self.extract([None, None])

    def test_one_existing_candidate(self):
        self.assertEqual(self.extract([None, 2207])["image_path"], "/system/app/a")


if __name__ == "__main__":
    unittest.main()
