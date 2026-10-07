#!/usr/bin/env python3
import copy
import json
import unittest
from verify_permission_results import ABSENT, INVALID, OVERLONG_NAME, verify

RUN_ID = "a" * 32


def fixture(device):
    source = {"definePermissions": [
        {"name": "ohos.permission.GENERAL", "grantMode": "user_grant", "availableLevel": "normal", "availableType": "NORMAL"},
        {"name": "ohos.permission.PC_ONLY", "grantMode": "system_grant", "availableLevel": "system_core",
         "availableType": "SYSTEM", "deviceTypes": ["2in1"], "provisionEnable": True},
    ]}
    rows = [{"kind": "run", "runId": RUN_ID}]
    for i, definition in enumerate(source["definePermissions"]):
        allowed = i == 0 or device == "2in1"
        row = {"kind": "definition", "permissionName": definition["name"], "result": 0 if allowed else ABSENT}
        if allowed:
            row.update(grantMode=i, availableLevel=1 if i == 0 else 3, availableType=i,
                       provisionEnable=i == 1, distributedSceneEnable=False, isKernelEffect=False, hasValue=False)
        rows.append(row)
    rows.extend([
        {"kind": "absent", "permissionName": "ohos.permission.QEMU_CAPABILITY_AUDIT_DOES_NOT_EXIST", "result": ABSENT},
        {"kind": "unknown-format", "permissionName": "invalid!", "result": ABSENT},
        {"kind": "invalid", "permissionName": OVERLONG_NAME, "result": INVALID},
        {"kind": "empty", "permissionName": "", "result": INVALID},
        {"kind": "complete", "runId": RUN_ID, "sourcePermissionCount": 2},
    ])
    return source, rows


def encode(rows):
    return "\n".join(json.dumps(row) for row in rows) + "\n"


class PermissionResultTests(unittest.TestCase):
    def test_both_profiles_and_boundaries(self):
        for device in ("phone", "2in1"):
            source, rows = fixture(device)
            result = verify(source, encode(rows), device, RUN_ID, 0)
            self.assertEqual(result["enabled_count"], 1 if device == "phone" else 2)
            self.assertEqual(result["boundary_count"], 4)

    def test_partial_duplicate_reordered_stale_and_exit_failure(self):
        source, rows = fixture("2in1")
        for broken in ([], rows[:-1], rows[1:], rows + rows,
                       [rows[0], rows[2], rows[1], *rows[3:]]):
            with self.assertRaises(ValueError):
                verify(source, encode(broken), "2in1", RUN_ID, 0)
        for run_id, exit_code in (("b" * 32, 0), (RUN_ID, 1), (RUN_ID, False), ("bad-id", 0)):
            with self.assertRaises(ValueError):
                verify(source, encode(rows), "2in1", run_id, exit_code)

    def test_wrong_profile_missing_rights_privilege_relaxation_and_bad_types(self):
        source, rows = fixture("2in1")
        with self.assertRaises(ValueError):
            verify(source, encode(rows), "phone", RUN_ID, 0)
        for key, value in (("result", ABSENT), ("availableLevel", 1), ("grantMode", 0),
                           ("provisionEnable", 1), ("result", False)):
            bad = copy.deepcopy(rows)
            bad[2][key] = value
            with self.assertRaises(ValueError):
                verify(source, encode(bad), "2in1", RUN_ID, 0)

    def test_boundaries_do_not_accept_arbitrary_errors_or_false_success(self):
        source, rows = fixture("phone")
        for index in (1, 2, 3, 4, 5, 6):
            for result in (201, 202, -1, 12100012):
                bad = copy.deepcopy(rows)
                bad[index]["result"] = result
                with self.assertRaises(ValueError):
                    verify(source, encode(bad), "phone", RUN_ID, 0)


if __name__ == "__main__":
    unittest.main()
