#!/usr/bin/env python3
import unittest
from verify_device_contract import verify, FIREWALL, VPE, QEMU_REQUIRED_SYSCAPS

CORE = "SystemCapability.Global.I18n"
CORE_CAPS = {"components": [{"syscap": [CORE, *sorted(QEMU_REQUIRED_SYSCAPS)]}]}
REQUESTED_PARAMS = ''.join(f'const.{cap}=true\n' for cap in sorted(QEMU_REQUIRED_SYSCAPS))
CORE_PARAMS = REQUESTED_PARAMS + f"const.{CORE}=true\n"

class VerifyDeviceContractTests(unittest.TestCase):
    def profile(self, device):
        return {"device_type": device, "qemu_adaptations": {"excluded_unsupported_syscaps": {
            cap: {"reason": "unsupported"} for cap in ({VPE, FIREWALL} if device == "phone" else {VPE})
        }, "explicit_qemu_requirements": sorted(QEMU_REQUIRED_SYSCAPS),
            "required_official_syscaps": [CORE]}}

    def test_phone_excluded_absent_passes(self):
        result = verify("phone", CORE_CAPS, CORE_PARAMS, self.profile("phone"))
        self.assertEqual(result["status"], "pass")
        self.assertTrue(result["declaration_consistency_only"])

    def test_phone_stale_true_parameter_is_rejected(self):
        for params in (f"const.{FIREWALL}=true", f"[const.{FIREWALL}]: [true]"):
            with self.subTest(params=params):
                self.assertEqual(verify("phone", CORE_CAPS, CORE_PARAMS + params, self.profile("phone"))["status"], "fail")

    def test_stale_syscap_json_is_rejected(self):
        self.assertEqual(verify("phone", {"components": [{"syscap": [VPE]}]}, "", self.profile("phone"))["status"], "fail")

    def test_2in1_requires_positive_firewall_declaration_and_parameter(self):
        caps = {"components": [{"syscap": [CORE, FIREWALL, *sorted(QEMU_REQUIRED_SYSCAPS)]}]}
        self.assertEqual(verify("2in1", caps, CORE_PARAMS + f"const.{FIREWALL}=true", self.profile("2in1"))["status"], "pass")
        self.assertEqual(verify("2in1", caps, CORE_PARAMS + f"const.{FIREWALL}=false", self.profile("2in1"))["status"], "fail")

    def test_missing_package_policy_cannot_pass(self):
        self.assertEqual(verify("phone", {"components": []}, "", {})["status"], "fail")

    def test_empty_or_unrecognized_evidence_cannot_pass(self):
        self.assertEqual(verify("phone", {"components": []}, CORE_PARAMS, self.profile("phone"))["status"], "fail")
        self.assertEqual(verify("phone", CORE_CAPS, "file not found", self.profile("phone"))["status"], "fail")

    def test_additional_package_exclusions_are_checked(self):
        extra = "SystemCapability.DistributedDataManager.CloudSync.Client"
        profile = self.profile("phone")
        profile["qemu_adaptations"]["excluded_unsupported_syscaps"][extra] = {"reason": "no provider"}
        self.assertEqual(verify("phone", CORE_CAPS, CORE_PARAMS, profile)["status"], "pass")
        self.assertEqual(verify("phone", CORE_CAPS, CORE_PARAMS + f"const.{extra}=true", profile)["status"], "fail")
        caps = {"components": [{"syscap": [CORE, extra]}]}
        self.assertEqual(verify("phone", caps, CORE_PARAMS + f"const.{extra}=true", profile)["status"], "fail")

    def test_requested_capability_cannot_be_excluded_by_package_policy(self):
        profile = self.profile("phone")
        profile["qemu_adaptations"]["explicit_qemu_requirements"] = [VPE]
        self.assertEqual(verify("phone", CORE_CAPS, CORE_PARAMS, profile)["status"], "fail")

    def test_retained_declarations_and_parameters_must_agree(self):
        self.assertEqual(verify("phone", CORE_CAPS, f"const.{CORE}=false", self.profile("phone"))["status"], "fail")
        self.assertEqual(verify("phone", CORE_CAPS, CORE_PARAMS + "const.SystemCapability.Stale=true", self.profile("phone"))["status"], "fail")

    def test_missing_requested_policy_cannot_bypass_positive_capability_check(self):
        profile = self.profile('phone')
        del profile['qemu_adaptations']['explicit_qemu_requirements']
        self.assertEqual(verify('phone', CORE_CAPS, CORE_PARAMS, profile)['status'], 'fail')

    def test_missing_requested_capability_is_rejected_even_when_consistently_absent(self):
        for cap in sorted(QEMU_REQUIRED_SYSCAPS):
            with self.subTest(cap=cap):
                caps = {'components': [{'syscap': [CORE, *sorted(QEMU_REQUIRED_SYSCAPS - {cap})]}]}
                params = CORE_PARAMS.replace(f'const.{cap}=true\n', '')
                result = verify('phone', caps, params, self.profile('phone'))
                self.assertEqual(result['status'], 'fail')
                self.assertIn(f'required SysCap missing: {cap}', result['failures'])

    def test_official_requirement_cannot_disappear_from_both_evidence_files(self):
        caps = {'components': [{'syscap': sorted(QEMU_REQUIRED_SYSCAPS)}]}
        result = verify('phone', caps, REQUESTED_PARAMS, self.profile('phone'))
        self.assertEqual(result['status'], 'fail')
        self.assertIn(f'required SysCap missing: {CORE}', result['failures'])

    def test_official_requirement_evidence_is_mandatory(self):
        for value in (None, [], 'not a list', [True]):
            with self.subTest(value=value):
                profile = self.profile('phone')
                profile['qemu_adaptations']['required_official_syscaps'] = value
                self.assertEqual(verify('phone', CORE_CAPS, CORE_PARAMS, profile)['status'], 'fail')

    def test_positive_syscap_override_is_also_required(self):
        profile = self.profile('phone')
        profile['qemu_adaptations']['enabled_required_syscaps'] = {'SystemCapability.Extra.Required': {}}
        self.assertEqual(verify('phone', CORE_CAPS, CORE_PARAMS, profile)['status'], 'fail')


if __name__ == "__main__":
    unittest.main()
