#!/usr/bin/env python3
"""A PC profile must not compile the phone permission table or relax APLs."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "patches/lib"))
from permission_profile import INTERNAL_NAMES, INTERNAL_POLICY, target_platform, validate


def fixture(device):
    source = {"definePermissions": [
        {"name": "ohos.permission.PC_ONLY", "grantMode": "system_grant",
         "availableLevel": "system_basic", "availableType": "SYSTEM", "deviceTypes": ["2in1"]},
        {"name": "ohos.permission.PHONE_ONLY", "grantMode": "user_grant",
         "availableLevel": "normal", "availableType": "NORMAL", "deviceTypes": ["phone"]},
        {"name": "ohos.permission.GENERAL", "grantMode": "system_grant",
         "availableLevel": "system_core", "availableType": "SERVICE"},
    ]}
    names = [r["name"] for r in source["definePermissions"]] + sorted(INTERNAL_NAMES)
    header = "\n".join(f'const static char PERMISSION_NAME_{i}[] = "{name}";' for i, name in enumerate(names))
    header += "\nstatic PermissionBriefDef g_permList[] = {\n"
    for i in range(len(names)):
        if names[i] in INTERNAL_NAMES:
            header += f"{{\n.permissionName = PERMISSION_NAME_{i},\n"
            header += ",\n".join(f".{k} = {v}" for k, v in INTERNAL_POLICY[names[i]].items())
            header += "\n},\n"
            continue
        is_enabled = i >= 2 or (i == 0 and device == "2in1") or (i == 1 and device == "phone")
        header += (f"{{\n.permissionName = PERMISSION_NAME_{i},\n"
                   f".grantMode = {'USER_GRANT' if i == 1 else 'SYSTEM_GRANT'},\n"
                   f".availableLevel = {('APL_SYSTEM_BASIC', 'APL_NORMAL', 'APL_SYSTEM_CORE')[min(i, 2)]},\n"
                   f".availableType = {('SYSTEM', 'NORMAL', 'SERVICE')[min(i, 2)]},\n"
                   ".provisionEnable = false,\n.distributedSceneEnable = false,\n"
                   ".isKernelEffect = false,\n.hasValue = false,\n"
                   f".isEnable = {'true' if is_enabled else 'false'}\n}},\n")
    return source, header + "};\n"


class PermissionProfileTests(unittest.TestCase):
    def test_platform_mapping_and_both_generated_tables(self):
        self.assertEqual(target_platform("2in1"), "pc")
        self.assertEqual(target_platform("phone"), "phone")
        for device in ("phone", "2in1"):
            result = validate(*fixture(device), device)
            self.assertFalse(result["runtime_validated"])
            self.assertEqual(len(result["enabled_permissions"]), 2)
            self.assertEqual(len(result["disabled_permissions"]), 1)

    def test_wrong_platform_table_fails(self):
        for device, wrong in (("phone", "2in1"), ("2in1", "phone")):
            with self.assertRaises(ValueError):
                validate(*fixture(wrong), device)
        with self.assertRaises(ValueError):
            target_platform("default")

    def test_privilege_and_missing_or_duplicate_rows_fail(self):
        source, header = fixture("2in1")
        for broken in (
                header.replace("APL_SYSTEM_BASIC", "APL_NORMAL"),
                header.replace(".provisionEnable = false", ".provisionEnable = true", 1),
                header.replace(".isEnable = true", ".isEnable = true,\n.isEnable = true", 1),
                header.replace(".grantMode = MANUAL_SETTINGS", ".grantMode = SYSTEM_GRANT"),
                header.replace("PERMISSION_NAME_0,", "PERMISSION_NAME_9999,", 1),
                header.replace('const static char PERMISSION_NAME_0[]', 'const static char PERMISSION_NAME_1[]'),
                header.replace("static PermissionBriefDef g_permList[]", "static PermissionBriefDef other[]")):
            with self.subTest(broken=broken):
                with self.assertRaises(ValueError):
                    validate(source, broken, "2in1")

    def test_invalid_source_and_general_permission_boundaries(self):
        source, header = fixture("phone")
        for mutation in ({"deviceTypes": []}, {"deviceTypes": "phone"}, {"hasValue": 1}):
            bad = copy.deepcopy(source)
            bad["definePermissions"][0].update(mutation)
            with self.assertRaises(ValueError):
                validate(bad, header, "phone")
        source["definePermissions"].append(copy.deepcopy(source["definePermissions"][0]))
        with self.assertRaises(ValueError):
            validate(source, header, "phone")


if __name__ == "__main__":
    unittest.main()
