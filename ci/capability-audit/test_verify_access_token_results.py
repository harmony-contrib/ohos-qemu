#!/usr/bin/env python3
import copy
import unittest
from verify_access_token_results import NORMAL_CASES, PRIVILEGED_CASES, verify

RUN = "a" * 32


def results(arch="arm64", mode="privileged", device_denied=False):
    names = PRIVILEGED_CASES if mode == "privileged" else NORMAL_CASES
    if device_denied:
        names = ("normal_uid_device_access_denied",)
    return [{"kind": "run", "run_id": RUN, "mode": mode, "uid": 0 if mode == "privileged" else 20010001,
             "arch": arch, "pointer_bits": 32 if arch == "armv7a" else 64}] + [
                 {"kind": "case", "run_id": RUN, "name": name, "pass": True} for name in names] + [
                     {"kind": "complete", "run_id": RUN}]


class VerifyAccessTokenTests(unittest.TestCase):
    def test_architectures_and_authorization_roles(self):
        for arch in ("arm64", "armv7a", "x86_64"):
            for mode in ("privileged", "unprivileged"):
                result = verify(results(arch, mode), arch, mode, RUN, 0)
                self.assertFalse(result["enhanced_spm_implemented"])
                self.assertFalse(result["device_access_denied"])
        self.assertTrue(verify(results(mode="unprivileged", device_denied=True),
                               "arm64", "unprivileged", RUN, 0)["device_access_denied"])

    def test_rejects_partial_stale_repeated_and_wrong_abi(self):
        full = results()
        bad = [[], full[:-1], full[:1] + full[2:], full[:-1] + [full[1], full[-1]], results("x86_64")]
        for key, value in (("pointer_bits", 32), ("uid", 3020), ("mode", "unprivileged")):
            row = copy.deepcopy(full)
            row[0][key] = value
            bad.append(row)
        for row in bad:
            with self.subTest(row=row), self.assertRaises(ValueError):
                verify(row, "arm64", "privileged", RUN, 0)
        for run_id, code in (("b" * 32, 0), (RUN, 1), (RUN, False)):
            with self.assertRaises(ValueError):
                verify(full, "arm64", "privileged", run_id, code)

    def test_failed_case_and_non_boolean_success_are_rejected(self):
        for value in (False, 1, "true", None):
            row = results()
            row[3]["pass"] = value
            with self.assertRaises(ValueError):
                verify(row, "arm64", "privileged", RUN, 0)

    def test_unprivileged_mode_cannot_be_run_by_atm_or_root(self):
        for uid in (0, 3020):
            row = results(mode="unprivileged")
            row[0]["uid"] = uid
            with self.assertRaises(ValueError):
                verify(row, "arm64", "unprivileged", RUN, 0)


if __name__ == "__main__":
    unittest.main()
