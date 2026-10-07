import json
import unittest
from verify_vibrator_hdi_results import CASES, verify

RUN = "abcde12345" * 3 + "ab"


def valid(arch="arm64"):
    return [{"kind": "run", "run_id": RUN, "arch": arch, "uid": 0, "euid": 0},
            *[{"kind": "case", "name": name, "pass": True} for name in CASES],
            {"kind": "complete", "run_id": RUN}]


def log(rows):
    return "\n".join(json.dumps(row) for row in rows)


class VibratorHdiResultsTests(unittest.TestCase):
    def test_all_architectures_complete(self):
        for arch in ("arm64", "armv7a", "x86_64"):
            self.assertEqual(verify(log(valid(arch)), arch, RUN, 0)["case_count"], 14)

    def test_failed_partial_stale_wrong_role_and_synthetic_success_rejected(self):
        variants = [valid()[:-1], valid()[1:], valid() + [valid()[-1]], list(reversed(valid()))]
        for index in range(1, len(CASES) + 1):
            for value in (False, 1, "true"):
                rows = valid(); rows[index]["pass"] = value; variants.append(rows)
        for key, value in (("run_id", "0" * 32), ("uid", 10001), ("euid", False), ("arch", "armv7a")):
            rows = valid(); rows[0][key] = value; variants.append(rows)
        for rows in variants:
            with self.assertRaises(ValueError):
                verify(log(rows), "arm64", RUN, 0)

    def test_actual_exit_required(self):
        for exit_code in (1, -1, False, None):
            with self.assertRaises(ValueError):
                verify(log(valid()), "arm64", RUN, exit_code)


if __name__ == "__main__":
    unittest.main()
