#!/usr/bin/env python3
"""Regression tests for product-scoped exclusions and protected contracts."""
from __future__ import annotations

import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "patches/lib"))
from device_contract import (QEMU_REQUIRED_SYSCAPS, RETIRED_DOCUMENTED_SYSCAPS,
                             SYSCAP_REGISTRY, active_official_requirements,
                             retired_declaration_evidence, apply_contract_overrides, contract_overlay)

FIREWALL = "SystemCapability.Communication.NetManager.NetFirewall"
VPE = "SystemCapability.Multimedia.VideoProcessingEngine"
AUDIO_SUITE = "SystemCapability.Multimedia.Audio.SuiteEngine"
CAMERA = "SystemCapability.Multimedia.Camera.Core"
OWNER = ("communication", "netmanager_ext")


class DeviceContractTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        sdk = self.root / "interface/sdk-js/api/device-define"
        sdk.mkdir(parents=True)
        (sdk / "default.json").write_text(json.dumps({"SysCaps": []}))
        (sdk / "2in1.json").write_text(json.dumps({"SysCaps": [FIREWALL]}))
        doc = self.root / "docs/zh-cn/application-dev/reference/phone-syscap-list.md"
        doc.parent.mkdir(parents=True)
        doc.write_text(f"# Phone\n\n- {AUDIO_SUITE}\n")
        self.profile = {"subsystems": [
            {"subsystem": "communication", "components": [{
                "component": "netmanager_ext", "features": [
                    "netmanager_ext_feature_net_firewall = true", "keep_other_feature = true"
                ], "syscap": ["SystemCapability.Communication.NetManager.Ethernet = true"]
            }]},
            {"subsystem": "multimedia", "components": [
                {"component": "media_foundation", "features": []},
                {"component": "audio_framework", "features": ["board_audio_feature = true"]},
                {"component": "camera_framework", "features": ["board_camera_feature = true"],
                 "syscap": [CAMERA + " = true"]},
            ]},
        ]}

    def test_phone_exclusion_is_idempotent_and_preserves_shared_component(self):
        exclusions = {FIREWALL: (*OWNER, "unsupported")}
        features = {OWNER: {"netmanager_ext_feature_net_firewall": False}}
        apply_contract_overrides(self.root, self.profile, "phone", exclusions, features)
        once = copy.deepcopy(self.profile)
        apply_contract_overrides(self.root, self.profile, "phone", exclusions, features)
        self.assertEqual(once, self.profile)
        component = self.profile["subsystems"][0]["components"][0]
        self.assertIn(f"{FIREWALL} = false", component["syscap"])
        self.assertIn("SystemCapability.Communication.NetManager.Ethernet = true", component["syscap"])
        self.assertEqual(component["features"], [
            "keep_other_feature = true", "netmanager_ext_feature_net_firewall = false"
        ])

    def test_2in1_firewall_cannot_be_excluded(self):
        original = copy.deepcopy(self.profile)
        with self.assertRaisesRegex(ValueError, "cannot exclude official"):
            apply_contract_overrides(self.root, self.profile, "2in1", {FIREWALL: (*OWNER, "bad")}, {})
        self.assertEqual(original, self.profile)

    def test_requested_capabilities_are_protected_outside_sdk_profile(self):
        # The synthetic 2in1 SDK contains only firewall. All of the explicitly
        # requested capabilities are absent, but still cannot be dropped.
        for cap in sorted(QEMU_REQUIRED_SYSCAPS):
            with self.subTest(cap=cap):
                original = copy.deepcopy(self.profile)
                with self.assertRaisesRegex(ValueError, "cannot exclude explicitly requested"):
                    apply_contract_overrides(self.root, self.profile, "2in1", {cap: (*OWNER, "bad")}, {})
                self.assertEqual(original, self.profile)

    def test_contract_metadata_records_requested_capabilities(self):
        result = apply_contract_overrides(self.root, self.profile, "2in1", {}, {})
        self.assertEqual(result["explicit_qemu_requirements"], sorted(QEMU_REQUIRED_SYSCAPS))

    def test_documented_phone_minimum_is_protected(self):
        with self.assertRaisesRegex(ValueError, "cannot exclude official"):
            apply_contract_overrides(self.root, self.profile, "phone", {AUDIO_SUITE: (*OWNER, "bad")}, {})

    def test_documented_phone_cloudsync_cannot_be_narrowed(self):
        for cap in ("SystemCapability.DistributedDataManager.CloudSync.Client",
                    "SystemCapability.FileManagement.DistributedFileService.CloudSyncManager"):
            with self.subTest(cap=cap):
                with self.assertRaisesRegex(ValueError, "cannot exclude official"):
                    apply_contract_overrides(self.root, self.profile, "phone", {cap: (*OWNER, "bad")}, {})

    def test_required_phone_camera_cannot_be_narrowed(self):
        original = copy.deepcopy(self.profile)
        with self.assertRaisesRegex(ValueError, "cannot exclude official"):
            apply_contract_overrides(self.root, self.profile, "phone",
                                     {CAMERA: ("multimedia", "camera_framework", "bad")}, {})
        self.assertEqual(self.profile, original)

    def test_2in1_camera_declaration_only_narrowing_is_idempotent_and_sdk_protected(self):
        exclusions = {CAMERA: ("multimedia", "camera_framework", "no QEMU VDI")}
        result = apply_contract_overrides(self.root, self.profile, "2in1", exclusions, {})
        once = copy.deepcopy(self.profile)
        apply_contract_overrides(self.root, self.profile, "2in1", exclusions, {})
        self.assertEqual(once, self.profile)
        self.assertEqual(result["excluded_unsupported_syscaps"][CAMERA]["part"], "multimedia:camera_framework")
        component = self.profile["subsystems"][1]["components"][2]
        self.assertEqual(component["syscap"], [CAMERA + " = false"])
        self.assertEqual(component["features"], ["board_camera_feature = true"])
        self.assertIn(FIREWALL, result["required_official_syscaps"])
        # If a future pinned SDK makes camera official, the same code must fail
        # rather than continuing to ship a narrowed official capability.
        (self.root / "interface/sdk-js/api/device-define/2in1.json").write_text(
            json.dumps({"SysCaps": [FIREWALL, CAMERA]}))
        with self.assertRaisesRegex(ValueError, "cannot exclude official"):
            apply_contract_overrides(self.root, self.profile, "2in1", exclusions, {})

    def test_2in1_keeps_firewall_while_excluding_only_vpe(self):
        result = apply_contract_overrides(
            self.root, self.profile, "2in1", {VPE: ("multimedia", "media_foundation", "unsupported")},
            {OWNER: {"netmanager_ext_feature_net_firewall": True}},
        )
        self.assertEqual(list(result["excluded_unsupported_syscaps"]), [VPE])
        self.assertNotIn(f"{FIREWALL} = false", self.profile["subsystems"][0]["components"][0]["syscap"])

    def test_missing_docs_checkout_still_protects_documented_contract(self):
        (self.root / "docs/zh-cn/application-dev/reference/phone-syscap-list.md").unlink()
        with self.assertRaisesRegex(ValueError, "cannot exclude official"):
            apply_contract_overrides(self.root, self.profile, "phone", {AUDIO_SUITE: (*OWNER, "bad")}, {})

    def test_missing_sdk_contract_evidence_fails_closed(self):
        (self.root / "interface/sdk-js/api/device-define/default.json").unlink()
        with self.assertRaises(FileNotFoundError):
            apply_contract_overrides(self.root, self.profile, "phone", {}, {})

    def test_missing_owner_does_not_silently_ignore_exclusion(self):
        with self.assertRaisesRegex(ValueError, "owners missing"):
            apply_contract_overrides(self.root, self.profile, "phone", {VPE: ("wrong", "part", "bad")}, {})

    def test_last_board_inherit_cannot_clear_contract_settings(self):
        metadata = apply_contract_overrides(
            self.root, self.profile, "phone", {FIREWALL: (*OWNER, "unsupported")},
            {OWNER: {"netmanager_ext_feature_net_firewall": False}},
        )
        (self.root / "phone.json").write_text(json.dumps(self.profile))
        board = {"subsystems": [{"subsystem": OWNER[0], "components": [{
            "component": OWNER[1], "features": ["board_specific_feature = true"],
            "syscap": ["SystemCapability.Communication.NetManager.Ethernet = true"],
        }]}]}
        (self.root / "board.json").write_text(json.dumps(board))
        overlay = contract_overlay(self.root, {"inherit": ["phone.json", "board.json"]}, metadata)
        component = overlay["subsystems"][0]["components"][0]
        self.assertIn("board_specific_feature = true", component["features"])
        self.assertIn("netmanager_ext_feature_net_firewall = false", component["features"])
        self.assertIn(f"{FIREWALL} = false", component["syscap"])
        self.assertIn("SystemCapability.Communication.NetManager.Ethernet = true", component["syscap"])

    def test_product_local_shadow_fails_closed(self):
        metadata = apply_contract_overrides(self.root, self.profile, "phone", {FIREWALL: (*OWNER, "unsupported")}, {})
        with self.assertRaisesRegex(ValueError, "shadow contract"):
            contract_overlay(self.root, self.profile, metadata)

    def test_positive_audio_feature_survives_late_board_override(self):
        owner = ('multimedia', 'audio_framework')
        feature = 'audio_framework_feature_audiosuite_support'
        metadata = apply_contract_overrides(self.root, self.profile, 'phone', {}, {owner: {feature: True}})
        board = {'subsystems': [{'subsystem': owner[0], 'components': [{
            'component': owner[1], 'features': [feature + ' = false', 'board_audio_feature = true'],
        }]}]}
        (self.root / 'board.json').write_text(json.dumps(board))
        overlay = contract_overlay(self.root, {'inherit': ['board.json']}, metadata)
        component = overlay['subsystems'][0]['components'][0]
        self.assertEqual(component['features'], ['board_audio_feature = true', feature + ' = true'])

    def test_sceneboard_unified_renderer_survives_late_board_in_both_profiles(self):
        owner = ('graphic', 'graphic_2d')
        feature = 'graphic_2d_feature_rs_enable_uni_render'
        self.profile['subsystems'].append({'subsystem': owner[0], 'components': [{
            'component': owner[1], 'features': ['graphic_2d_feature_enable_opengl = true'],
        }]})
        for device in ('phone', '2in1'):
            with self.subTest(device=device):
                profile = copy.deepcopy(self.profile)
                metadata = apply_contract_overrides(self.root, profile, device, {}, {owner: {feature: True}})
                board = {'subsystems': [{'subsystem': owner[0], 'components': [{
                    'component': owner[1], 'features': [feature + ' = false',
                        'graphic_2d_feature_enable_opengl = true', 'graphic_2d_feature_enable_vulkan = false'],
                }]}]}
                (self.root / 'board.json').write_text(json.dumps(board))
                overlay = contract_overlay(self.root, {'inherit': ['board.json']}, metadata)
                self.assertEqual(overlay['subsystems'][0]['components'][0]['features'], [
                    'graphic_2d_feature_enable_opengl = true', 'graphic_2d_feature_enable_vulkan = false',
                    feature + ' = true',
                ])

    def test_required_audio_syscap_enable_survives_board_inherit(self):
        owner = ('multimedia', 'audio_framework')
        metadata = apply_contract_overrides(self.root, self.profile, 'phone', {}, {},
                                            {AUDIO_SUITE: (*owner, 'upstream engine enabled')})
        board = {'subsystems': [{'subsystem': owner[0], 'components': [{
            'component': owner[1], 'syscap': [AUDIO_SUITE + ' = false', 'SystemCapability.Multimedia.Audio.Core = true'],
        }]}]}
        (self.root / 'board.json').write_text(json.dumps(board))
        overlay = contract_overlay(self.root, {'inherit': ['board.json']}, metadata)
        self.assertEqual(overlay['subsystems'][0]['components'][0]['syscap'],
                         ['SystemCapability.Multimedia.Audio.Core = true', AUDIO_SUITE + ' = true'])

    def test_cannot_add_arbitrary_syscap_to_hide_missing_implementation(self):
        with self.assertRaisesRegex(ValueError, 'unrequested capabilities'):
            apply_contract_overrides(self.root, self.profile, 'phone', {}, {},
                                     {'SystemCapability.Unrequested.Extra': (*OWNER, 'bad')})

    def test_abandoned_names_need_registry_and_no_active_sdk_reference(self):
        cap = next(iter(RETIRED_DOCUMENTED_SYSCAPS))
        self.assertEqual(retired_declaration_evidence(self.root, {cap}, set()), {})
        registry = self.root / SYSCAP_REGISTRY
        registry.parent.mkdir(parents=True)
        registry.write_text('{"' + cap + '", TEST}, // abandoned\n')
        evidence = retired_declaration_evidence(self.root, {cap}, set())
        self.assertEqual(set(evidence), {cap})
        self.assertFalse(evidence[cap]["behavior_validated"])
        self.assertEqual(active_official_requirements({"required_official_syscaps": [cap],
                                                      "retired_documented_syscap_names": evidence}), set())
        self.assertEqual(retired_declaration_evidence(self.root, {cap}, {cap}), {})
        (self.root / "interface/sdk-js/api/active.d.ts").write_text("/** @syscap " + cap + " */")
        self.assertEqual(retired_declaration_evidence(self.root, {cap}, set()), {})

    def test_retirement_cannot_exempt_requested_or_arbitrary_capability(self):
        for cap in (*QEMU_REQUIRED_SYSCAPS, "SystemCapability.Unrequested.Extra"):
            with self.subTest(cap=cap), self.assertRaises(ValueError):
                active_official_requirements({"required_official_syscaps": [cap],
                                              "retired_documented_syscap_names": {cap: {}}})

    def test_malformed_retirement_evidence_fails_closed(self):
        cap = next(iter(RETIRED_DOCUMENTED_SYSCAPS))
        registry = self.root / SYSCAP_REGISTRY
        registry.parent.mkdir(parents=True)
        registry.write_text('{"' + cap + '", TEST}, // abandoned\n')
        original = retired_declaration_evidence(self.root, {cap}, set())
        for key in original[cap]:
            evidence = copy.deepcopy(original)
            del evidence[cap][key]
            with self.subTest(key=key), self.assertRaises(ValueError):
                active_official_requirements({"required_official_syscaps": [cap],
                                              "retired_documented_syscap_names": evidence})


if __name__ == "__main__":
    unittest.main()
