#!/usr/bin/env python3
from __future__ import annotations

import sys
import os
import re
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from snapshot_build_inputs import snapshot, digest_files


class SnapshotTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "repo"
        self.output = self.root / "snapshot"
        self.output.mkdir()
        for directory in ("scripts", "patches"):
            (self.source / directory).mkdir(parents=True)
            (self.source / directory / "input.txt").write_text("before\n")

    def test_later_edit_does_not_change_frozen_inputs(self):
        document = snapshot(self.source, self.output)
        self.assertEqual(document["files_sha256"], digest_files(self.output))
        (self.source / "scripts/input.txt").write_text("after\n")
        self.assertEqual((self.output / "scripts/input.txt").read_text(), "before\n")
        self.assertNotEqual(digest_files(self.source), document["files_sha256"])

    def test_validation_changes_invalidate_cached_package_acceptance(self):
        for directory in ('ci/capability-audit', 'ci/qemu-smoke'):
            (self.source / directory).mkdir(parents=True)
            (self.source / directory / 'caller.py').write_text('before\n')
        document = snapshot(self.source, self.output)
        for directory in ('ci/capability-audit', 'ci/qemu-smoke'):
            relative = directory + '/caller.py'
            self.assertIn(relative, document['files_sha256'])
            (self.source / relative).write_text('after\n')
            self.assertEqual((self.output / relative).read_text(), 'before\n')
        self.assertNotEqual(digest_files(self.source), document['files_sha256'])

    def test_original_gap_contract_is_frozen_without_copying_unrelated_documentation(self):
        name = 'docs/capability-audit/native-arkts11-gap-ledger.json'
        (self.source / name).parent.mkdir(parents=True)
        (self.source / name).write_text('{"original": true}\n')
        (self.source / 'docs/unrelated.md').write_text('unrelated\n')
        document = snapshot(self.source, self.output)
        self.assertIn(name, document['files_sha256'])
        self.assertEqual((self.output / name).read_text(), '{"original": true}\n')
        self.assertFalse((self.output / 'docs/unrelated.md').exists())
        (self.source / name).write_text('{"original": false}\n')
        self.assertNotEqual(digest_files(self.source), document['files_sha256'])

    def test_nonempty_destination_is_not_overwritten(self):
        (self.output / "keep.txt").write_text("keep\n")
        with self.assertRaisesRegex(ValueError, "empty directory"):
            snapshot(self.source, self.output)
        self.assertEqual((self.output / "keep.txt").read_text(), "keep\n")

    def test_destination_under_source_is_rejected(self):
        nested = self.source / "build-inputs"
        nested.mkdir()
        with self.assertRaisesRegex(ValueError, "outside"):
            snapshot(self.source, nested)

    def test_actual_host_launch_tail_survives_edit_and_propagates_docker_status(self):
        launcher = (Path(__file__).resolve().parents[2] / 'scripts/run_2in1_full_build_docker.sh').read_text()
        self.assertIn('\nmain() {\nSCRIPT_DIR=', launcher)
        tail = launcher[launcher.index('# shellcheck disable=SC2086\nset -- ${PRODUCTS}'):]
        self.assertIn('\nexec docker run --rm', tail)
        self.assertTrue(tail.endswith('\n}\n\nmain "$@"\n'))
        # Execute the real Docker argument/exec tail inside the launcher's same
        # parse-before-wait function. This is shell lifetime fixture coverage,
        # not a successful OpenHarmony build or a replaced production Docker.
        for status in (0, 17):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory:
                root = Path(directory)
                script, docker = root / 'launcher.sh', root / 'docker'
                ready, release = root / 'ready', root / 'release'
                script.write_text('#!/bin/bash\nset -euo pipefail\nmain() {\n' + tail)
                docker.write_text('#!' + sys.executable + '\n'
                    'import os, pathlib, time, sys\n'
                    'pathlib.Path(os.environ["FIXTURE_READY"]).write_text("ready")\n'
                    'deadline = time.monotonic() + 10\n'
                    'while not pathlib.Path(os.environ["FIXTURE_RELEASE"]).exists():\n'
                    ' if time.monotonic() >= deadline: sys.exit(99)\n'
                    ' time.sleep(0.01)\n'
                    'sys.exit(int(os.environ["FIXTURE_STATUS"]))\n')
                docker.chmod(0o700)
                env = {**os.environ, **dict.fromkeys(re.findall(r'\$\{([A-Z][A-Z0-9_]*)', tail), 'fixture')}
                env.update(PATH=str(root) + os.pathsep + os.environ['PATH'], LOG_FILE=str(root / 'launch.log'),
                           FIXTURE_READY=str(ready), FIXTURE_RELEASE=str(release), FIXTURE_STATUS=str(status))
                process = subprocess.Popen(['/bin/bash', str(script)], env=env, stdout=subprocess.PIPE,
                                           stderr=subprocess.PIPE, text=True)
                try:
                    deadline = time.monotonic() + 5
                    while not ready.exists() and process.poll() is None and time.monotonic() < deadline:
                        time.sleep(0.01)
                    self.assertTrue(ready.exists(), 'real launch tail did not reach fixture Docker')
                    # Change size/offset and add an invalid command while the
                    # child is blocked, reproducing the R6 live-file hazard.
                    script.write_text('broken-edited-host-entry\n-e MUST_NOT_EXECUTE\n')
                    release.touch()
                    stdout, stderr = process.communicate(timeout=5)
                    self.assertEqual(process.returncode, status, stdout + stderr)
                    self.assertNotIn('MUST_NOT_EXECUTE', stdout + stderr)
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main()
