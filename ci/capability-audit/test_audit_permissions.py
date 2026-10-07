#!/usr/bin/env python3
import unittest
from audit_permissions import classify, source_support


class PermissionAuditTests(unittest.TestCase):
    def test_pc_only_permission_with_shared_syscap_is_not_missing_on_phone(self):
        source = {"deviceTypes": ["2in1"]}
        row = {"public_api": True}
        caps = ["SystemCapability.Startup.SystemInfo"]
        self.assertFalse(source_support(source, "phone"))
        self.assertTrue(source_support(source, "2in1"))
        self.assertEqual(classify(row, caps, None, source, "phone"),
                         "permission_disabled_by_device_policy_requires_api_boundary_validation")
        self.assertEqual(classify(row, caps, None, source, "2in1"), "missing_official_public_permission")

    def test_general_and_missing_source_permissions_still_require_registration(self):
        for source in (None, {}, {"deviceTypes": ["general"]}, {"deviceTypes": ["phone", "2in1"]}):
            for device in ("phone", "2in1"):
                self.assertEqual(classify({"public_api": False}, ["SystemCapability.A"], None, source, device),
                                 "missing_official_system_permission")

    def test_registration_is_not_replaced_by_source_presence(self):
        self.assertEqual(classify({"public_api": True}, [], None, {}, "phone"),
                         "missing_public_permission_outside_profile")
        self.assertEqual(classify({"public_api": True}, ["SystemCapability.A"], {"permissionName": "A"},
                                 {}, "phone"), "registered")

    def test_invalid_source_policy_fails_closed(self):
        for source in ({"deviceTypes": []}, {"deviceTypes": "phone"}, {"deviceTypes": [1]}):
            with self.assertRaises(ValueError):
                source_support(source, "phone")
        with self.assertRaises(ValueError):
            source_support({}, "tablet")



if __name__ == "__main__":
    unittest.main()
