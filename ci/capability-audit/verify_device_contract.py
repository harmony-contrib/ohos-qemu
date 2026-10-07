#!/usr/bin/env python3
"""Check shipped/booted SysCaps and parameters against explicit package policy.

This is a declaration-consistency check, not proof that retained APIs work.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "patches/lib"))
from device_contract import QEMU_REQUIRED_SYSCAPS, active_official_requirements

FIREWALL = "SystemCapability.Communication.NetManager.NetFirewall"
VPE = "SystemCapability.Multimedia.VideoProcessingEngine"


def verify(device: str, syscap: dict, parameters: str, profile: dict) -> dict:
    failures = []
    declared = {cap for component in syscap["components"] for cap in component.get("syscap", [])}
    if not declared:
        failures.append("SysCap evidence is empty")
    required_exclusions = {VPE} | ({FIREWALL} if device == "phone" else set())
    policy = profile.get("qemu_adaptations", profile)
    if profile.get("device_type", device) != device:
        failures.append("package device_type does not match the requested device")
    recorded = policy.get("excluded_unsupported_syscaps", {})
    if not isinstance(recorded, dict):
        failures.append("package exclusions must be a SysCap map")
        recorded = {}
    if not required_exclusions.issubset(recorded):
        failures.append("package policy does not record every required exclusion")
    # Validate the whole package policy, not just the original two families.
    excluded = required_exclusions | set(recorded)
    recorded_requirements = policy.get("explicit_qemu_requirements")
    if not isinstance(recorded_requirements, list) or any(not isinstance(cap, str) for cap in recorded_requirements):
        failures.append("package requested capability policy is missing or invalid")
        recorded_requirements = []
    if not QEMU_REQUIRED_SYSCAPS.issubset(recorded_requirements):
        failures.append("package policy omits explicitly requested QEMU capabilities")
    official_requirements = policy.get("required_official_syscaps")
    if (not isinstance(official_requirements, list) or not official_requirements or
            any(not isinstance(cap, str) for cap in official_requirements)):
        failures.append("package official device requirements are missing or invalid")
        official_requirements = []
    enabled = policy.get("enabled_required_syscaps", {})
    if not isinstance(enabled, dict):
        failures.append("package enabled SysCap policy must be a map")
        enabled = {}
    try:
        active_official = active_official_requirements({**policy, "required_official_syscaps": official_requirements})
    except (ValueError, TypeError) as exc:
        failures.append(str(exc))
        active_official = set(official_requirements)
    required_caps = QEMU_REQUIRED_SYSCAPS | set(recorded_requirements) | active_official | set(enabled)
    forbidden = excluded.intersection(required_caps)
    if forbidden:
        failures.append("package excludes explicitly requested capabilities: " + ", ".join(sorted(forbidden)))
    actual = {}
    for line in parameters.splitlines():
        # Accept both syscap.para assignments and `param get` bracketed output.
        match = re.search(r"\[?(const\.SystemCapability\.[A-Za-z0-9_.]+)\]?\s*[:=]\s*\[?(true|false)\]?", line)
        if match:
            key, value = match.groups()
            value = value == "true"
            if key in actual and actual[key] is not value:
                failures.append(f"contradictory parameter values: {key}")
            actual[key] = value
    if not actual:
        failures.append("SysCap parameter evidence is empty or unrecognized")
    for cap in sorted(required_caps):
        if cap not in declared:
            failures.append(f"required SysCap missing: {cap}")
        if actual.get(f"const.{cap}") is not True:
            failures.append(f"required SysCap parameter is not true: {cap}")
    for cap in sorted(declared):
        if actual.get(f"const.{cap}") is not True:
            failures.append(f"declared SysCap parameter is not true: {cap}")
    for key, value in sorted(actual.items()):
        if value and key.removeprefix("const.") not in declared:
            failures.append(f"true SysCap parameter absent from SysCap JSON: {key}")
    for cap in sorted(excluded):
        if cap in declared:
            failures.append(f"excluded SysCap still declared: {cap}")
        if actual.get(f"const.{cap}") is True:
            failures.append(f"excluded SysCap parameter still true: {cap}")
    if device == "2in1":
        if FIREWALL not in declared:
            failures.append("required 2in1 NetFirewall SysCap missing")
        if actual.get(f"const.{FIREWALL}") is not True:
            failures.append("required 2in1 NetFirewall parameter is not true")
    return {
        "device": device,
        "status": "pass" if not failures else "fail",
        "declaration_consistency_only": True,
        "excluded_syscaps": sorted(excluded),
        "required_syscaps": sorted(required_caps),
        "retired_documented_syscap_names": policy.get("retired_documented_syscap_names", {}),
        "failures": failures,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", choices=("phone", "2in1"), required=True)
    parser.add_argument("--syscap", type=Path, required=True)
    parser.add_argument("--parameters", type=Path, required=True)
    parser.add_argument("--profile", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = verify(args.device, json.loads(args.syscap.read_text()),
                    args.parameters.read_text(), json.loads(args.profile.read_text()))
    text = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
