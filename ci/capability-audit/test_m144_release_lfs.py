import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import prepare_m144_release_lfs as lfs


class ReleaseLFSTests(unittest.TestCase):
    def setUp(self):
        self.content = b"actual pinned profile content"
        self.oid = hashlib.sha256(self.content).hexdigest()
        self.pointer = ("version https://git-lfs.github.com/spec/v1\n"
                        f"oid sha256:{self.oid}\nsize {len(self.content)}\n")
        self.data = {"projects": [{"name": "chromium_src", "revision": "1" * 40,
                                  "mirror_url": "https://mirror.invalid/repo.git",
                                  "upstream_url": "https://upstream.invalid/repo.git"}]}

    def fake_git(self, *args, **kwargs):
        return subprocess.CompletedProcess(args, 0, self.pointer, "")

    def fixture(self, root):
        cache = root / "cache"
        obj = cache / "chromium_src.git/lfs/objects" / self.oid[:2] / self.oid[2:4] / self.oid
        obj.parent.mkdir(parents=True)
        obj.write_bytes(self.content)
        target = root / "work/src" / lfs.PGO_PATH
        target.parent.mkdir(parents=True)
        target.write_text(self.pointer)
        return cache, target, obj

    def test_install_real_object_and_verify_idempotently(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(lfs, "git", self.fake_git):
            root = Path(directory)
            cache, target, _ = self.fixture(root)
            self.assertEqual(lfs.install(root / "work", cache, self.data)["status"], "installed_verified_object")
            self.assertEqual(target.read_bytes(), self.content)
            self.assertEqual(lfs.install(root / "work", cache, self.data)["status"], "reused_verified_object")
            self.assertEqual(lfs.verify(root / "work", self.data)["sha256"], self.oid)

    def test_pointer_is_not_a_prepared_build_input(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(lfs, "git", self.fake_git):
            root = Path(directory)
            self.fixture(root)
            with self.assertRaises(ValueError):
                lfs.verify(root / "work", self.data)

    def test_changed_source_and_bad_cached_object_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(lfs, "git", self.fake_git):
            root = Path(directory)
            cache, target, obj = self.fixture(root)
            target.write_text("user changed profile")
            with self.assertRaises(ValueError):
                lfs.install(root / "work", cache, self.data)
            self.assertEqual(target.read_text(), "user changed profile")
            obj.write_bytes(b"wrong cached profile")
            with self.assertRaises(ValueError):
                lfs.prepare_cache(cache, self.data, fetch=False)

    def test_invalid_and_zero_size_pointers_rejected(self):
        for content in (self.pointer.replace(self.oid, "master"),
                        self.pointer.replace(f"size {len(self.content)}", "size 0"), "not a pointer"):
            with self.assertRaises(ValueError):
                lfs.pointer_record(content)

    def test_prepare_is_before_native_and_no_sdk_lfs_traversal(self):
        frontend = (ROOT / "scripts/run_m144_release_build_docker.sh").read_text()
        self.assertLess(frontend.index("prepare_m144_release_lfs.py"), frontend.index("docker run"))
        self.assertNotIn("--all", (ROOT / "scripts/prepare_m144_release_lfs.py").read_text())


if __name__ == "__main__":
    unittest.main()
