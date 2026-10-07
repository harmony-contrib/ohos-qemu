from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
import prepare_m144_release_cache as cache
import prepare_m144_release_sources as sources


class ReleaseSourceTests(unittest.TestCase):
    def setUp(self):
        self.lock = json.loads((ROOT / "scripts/m144_release_source_lock.json").read_text())

    def load(self, data):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "lock.json"
            path.write_text(json.dumps(data))
            return cache.load_lock(path)

    def test_actual_complete_release_lock_and_ohos_quic(self):
        data = self.load(self.lock)
        self.assertEqual(len(data["projects"]), 156)
        quic = next(p for p in data["projects"] if p["name"] == "chromium_quiche")
        self.assertEqual(quic["revision"], "dd5f831424b2b60023028f7081634022e0cc7535")
        self.assertNotEqual(quic["revision"], "901d0a7b4dbb141f2ad4eb8e1f00eb87f945044e")

    def test_incomplete_master_wrong_remote_and_unsafe_paths_rejected(self):
        for change in (lambda d: d["projects"].pop(),
                       lambda d: d.update(release="master"),
                       lambda d: d["projects"][0].update(revision="master"),
                       lambda d: d["projects"][0].update(path="../other"),
                       lambda d: d["projects"][0].update(path="."),
                       lambda d: d["projects"][0].update(upstream_url="https://example.invalid/source.git"),
                       lambda d: d["projects"][0].update(release_ref="refs/heads/master")):
            data = deepcopy(self.lock)
            change(data)
            with self.assertRaises(ValueError):
                self.load(data)

    def test_unknown_workspace_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory) / "work"
            work.mkdir()
            sentinel = work / "keep"
            sentinel.write_text("user source")
            with self.assertRaises(ValueError):
                sources.materialize(work, Path(directory) / "cache", self.lock)
            self.assertEqual(sentinel.read_text(), "user source")
            self.assertFalse((work / ".m144-release-source-owner.json").exists())

    def test_different_lock_workspace_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            marker = work / ".m144-release-source-owner.json"
            marker.write_text('{"source_lock_identity":"different"}')
            with self.assertRaises(ValueError):
                sources.materialize(work, work / "cache", self.lock)
            self.assertEqual(json.loads(marker.read_text())["source_lock_identity"], "different")

    def test_fetch_requests_only_exact_commit_and_mirror_then_upstream(self):
        project = self.lock["projects"][0]
        calls = []
        def fake_git(target, *args, **kwargs):
            calls.append(args)
            if args[0] == "cat-file":
                return subprocess.CompletedProcess(args, 1, "", "missing")
            if args == ("rev-parse", "--is-bare-repository"):
                return subprocess.CompletedProcess(args, 0, "true\n", "")
            if args[0] == "fetch" and project["mirror_url"] in args:
                return subprocess.CompletedProcess(args, 128, "", "missing mirror commit")
            stdout = project["revision"] + "\n" if args[0] == "rev-parse" else ""
            return subprocess.CompletedProcess(args, 0, stdout, "")
        with tempfile.TemporaryDirectory() as directory, patch.object(cache, "git", fake_git):
            result = cache.fetch(project, Path(directory))
        fetches = [args for args in calls if args[0] == "fetch" and args[3].startswith("https://")]
        self.assertEqual(len(fetches), 2)
        self.assertIn(project["mirror_url"], fetches[0])
        self.assertIn(project["upstream_url"], fetches[1])
        self.assertTrue(all(args[-1] == project["revision"] + ":refs/ohos7/" + project["revision"] for args in fetches))
        self.assertEqual(result["status"], "fetched_exact_commit")


if __name__ == "__main__":
    unittest.main()
