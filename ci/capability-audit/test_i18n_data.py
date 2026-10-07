#!/usr/bin/env python3
"""Init assembly and verifier regressions, not guest API validation."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from verify_i18n_data import NAMES, verify

ROOT = Path(__file__).resolve().parents[2]
COMPONENT = ROOT / "patches/common/base/global/i18n/builtin_data"
RUN = 'a' * 32


def results():
    values = [["28800000", "-18000000", "-14400000"], ["500", "400", "Shanghai", "Asia/Shanghai"],
              ["true", "false", "+12025550123"], ["China"], ["2026"],
              ["201", "number", "en-Latn-US", "en-Latn-US"],
              ["401", "number", "en-Latn-US", "en-Latn-US"],
              ["401", "number", "en-Latn-US", "en-Latn-US"]]
    return [dict(name=name, values=value, pass_=True, runId=RUN) for name, value in zip(NAMES, values)]


def render(rows):
    return "\n".join(json.dumps({("pass" if key == "pass_" else key): value for key, value in row.items()})
                     for row in rows)


class I18nTests(unittest.TestCase):
    def test_valid_fixture_is_only_verifier_coverage(self):
        self.assertEqual(len(verify(render(results()), RUN)), 8)

    def test_missing_duplicate_and_malformed_results_fail(self):
        rows = results()
        for broken in ([], rows[:5], rows * 2, list(reversed(rows))):
            with self.assertRaises(ValueError):
                verify(render(broken), RUN)
        for index in range(len(rows)):
            for field, value in (("pass_", False), ("pass_", 1), ("values", None), ("values", [None])):
                broken = copy.deepcopy(rows)
                broken[index][field] = value
                with self.subTest(index=index, field=field), self.assertRaises(ValueError):
                    verify(render(broken), RUN)

    def test_data_and_permissions_must_match_even_with_pass_true(self):
        for index, value in ((0, ["0", "-18000000", "-14400000"]), (1, ["500", "0", "", ""]),
                             (2, ["true", "true", "+12025550123"]), (3, [""]), (4, ["1970"]),
                             (5, ["0", "number", "en-US", "en-US"]),
                             (5, ["202", "string", "en-US", "en-US"]),
                             (5, ["201", "number", "en-US", "zh-CN"]),
                             (6, ["401", "string", "en-US", "en-US"]),
                             (7, ["202", "number", "en-US", "en-US"])):
            rows = results()
            rows[index]["values"] = value
            with self.subTest(index=index, value=value), self.assertRaises(ValueError):
                verify(render(rows), RUN)

    def test_stale_or_mixed_run_challenges_fail(self):
        for run in ('b' * 32, '', 'bad-id', None):
            with self.assertRaises(ValueError): verify(render(results()), run)
        for index in range(len(NAMES)):
            rows = results()
            rows[index]['runId'] = 'b' * 32
            with self.assertRaises(ValueError): verify(render(rows), RUN)

    def test_cli_retains_failed_observations_and_does_not_claim_full_gate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive, log, output = root / 'archive', root / 'log', root / 'result.json'
            archive.write_bytes(b'host fixture, not guest evidence')
            rows = results()
            rows[5]['pass_'] = False
            log.write_text(render(rows))
            completed = subprocess.run([sys.executable, str(ROOT / 'ci/capability-audit/verify_i18n_data.py'),
                                        '--archive', str(archive), '--results', str(log), '--run-id', RUN,
                                        '--output', str(output)], capture_output=True, text=True)
            report = json.loads(output.read_text())
            self.assertEqual(completed.returncode, 1)
            self.assertEqual(report['status'], 'fail')
            self.assertEqual(len(report['observations']), 8)
            self.assertEqual(len(report['results_sha256']), 64)
            self.assertFalse(report['first_artifact_behavior_gate_passed'])

    def test_init_patch_preserves_icu_mount_and_service(self):
        vendor = [f"exec /system/bin/hmos_cust_{name}_mount" for name in ("timezone", "libphonenumber", "taboo")]
        directories = [f"mkdir /data/service/el1/public/i18n/{name}/ {mode} i18n i18n"
                       for name, mode in (("taboo", "0755"), ("global", "0777"), ("icu", "0755"))]
        config = {"jobs": [{"name": "boot", "cmds": directories + vendor + ["exec /system/bin/icu72_dat_mount"]}],
                  "services": [{"name": "i18n_service", "uid": "i18n", "gid": ["i18n", "shell"],
                                "permission": ["ohos.permission.UPDATE_CONFIGURATION"],
                                "path": ["/system/bin/sa_main", "/system/profile/i18n_service.json"]}]}
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / "base/global/i18n/services/etc/init/i18n_service.cfg"
            path.parent.mkdir(parents=True)
            path.write_text(json.dumps(config, indent=4) + "\n")
            command = ["bash", str(COMPONENT / "apply.sh"), "--source-root", str(root)]
            subprocess.run(command, check=True, capture_output=True)
            patched = json.loads(path.read_text())
            expected = copy.deepcopy(config)
            expected["jobs"][0]["cmds"] = directories + ["exec /system/bin/icu72_dat_mount"]
            self.assertEqual(patched, expected)
            subprocess.run(["git", "-C", str(root), "apply", "--check", "--reverse",
                            str(next(COMPONENT.glob("*.patch")))], check=True)
            subprocess.run(command, check=True, capture_output=True)
            self.assertEqual(json.loads(path.read_text()), expected)


if __name__ == "__main__":
    unittest.main()
