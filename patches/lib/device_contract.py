"""Apply explicit QEMU profile exclusions without hiding required capabilities.

Use product-level SysCap overrides, not shared bundle.json mutations: two
device profiles may build from the same patched source. Both the SDK profile
and the documented phone minimum are protected against accidental exclusions.
"""

from __future__ import annotations

import json
import re
import copy
import hashlib
from pathlib import Path


# These capabilities are an explicit part of the user's QEMU contract, even
# when the upstream SDK device list omits them. Profile narrowing must never
# turn the requested implementation work into a declaration-only workaround.
QEMU_REQUIRED_SYSCAPS = frozenset({
    "SystemCapability.ArkCompiler.JSVM",
    "SystemCapability.Resourceschedule.QoS.Core",
    "SystemCapability.Sensors.MiscDevice",  # Native/ArkTS vibrator APIs.
    "SystemCapability.Web.Webview.Core",
    "SystemCapability.Graphic.Graphic2D.WebGL",
    "SystemCapability.Graphic.Graphic2D.WebGL2",
    "SystemCapability.Graphic.Vulkan",
})

# These *names*, not their owning services or APIs, are explicitly abandoned
# by the pinned SysCap registry. Do not revive them by inventing true values.
# The original documented list stays protected against profile exclusions.
RETIRED_DOCUMENTED_SYSCAPS = {
    "SystemCapability.FileManagement.File.DistributedFile": "filemanagement:dfs_service",
    "SystemCapability.HiviewDFX.HiDumper": "hiviewdfx:hidumper",
    "SystemCapability.Security.DataTransitManager": "security:dataclassification",
    "SystemCapability.Security.DeviceAuth": "security:device_auth",
    "SystemCapability.Security.DeviceSecurityLevel": "security:device_security_level",
    "SystemCapability.UserIAM.UserAuth.PinAuth": "useriam:pin_auth",
}
SYSCAP_REGISTRY = "developtools/syscap_codec/include/codec_config/syscap_define.h"


def retired_declaration_evidence(root: Path, required: set[str], sdk_required: set[str]) -> dict:
    """Reconcile stale documentation names against actual fixed-source evidence.

    Missing registry evidence is not an exemption. A required SDK declaration
    or any ArkTS API reference also prevents exemption. This function does not
    certify service behavior, remove parts, or authorize excluding any APIs.
    """
    registry = root / SYSCAP_REGISTRY
    if not registry.is_file():
        return {}
    content = registry.read_text()
    candidates = {cap for cap in RETIRED_DOCUMENTED_SYSCAPS.keys() & required - sdk_required
                  if re.search(r'^\s*\{"' + re.escape(cap) + r'",[^\n]*\},\s*// abandoned\s*$',
                               content, re.MULTILINE)}
    if not candidates:
        return {}
    # A stale label used by an existing API cannot be discarded just because
    # the codec comment calls it abandoned.
    for path in (root / "interface/sdk-js/api").rglob("*.ts"):
        # Some pinned SDK comments use non-UTF-8 encodings; identifiers are
        # ASCII. Inspect bytes so undecodable comments cannot hide references.
        text = path.read_bytes()
        candidates.difference_update({cap for cap in candidates if cap.encode("ascii") in text})
        if not candidates:
            return {}
    digest = hashlib.sha256(registry.read_bytes()).hexdigest()
    return {cap: {
        "owning_part": RETIRED_DOCUMENTED_SYSCAPS[cap],
        "registry": SYSCAP_REGISTRY,
        "registry_sha256": digest,
        "registry_status": "abandoned",
        "sdk_device_requirement": False,
        "arkts_api_reference_count": 0,
        "behavior_validated": False,
    } for cap in sorted(candidates)}


def active_official_requirements(policy: dict) -> set[str]:
    """Validate narrow retirement evidence; never exempt requested QEMU APIs."""
    required = set(policy["required_official_syscaps"])
    evidence = policy.get("retired_documented_syscap_names", {})
    if not isinstance(evidence, dict):
        raise ValueError("retired SysCap evidence must be a map")
    for cap, item in evidence.items():
        if (cap not in required or cap not in RETIRED_DOCUMENTED_SYSCAPS or
                cap in QEMU_REQUIRED_SYSCAPS or not isinstance(item, dict) or
                item.get("owning_part") != RETIRED_DOCUMENTED_SYSCAPS[cap] or
                item.get("registry") != SYSCAP_REGISTRY or
                not re.fullmatch(r"[0-9a-f]{64}", item.get("registry_sha256", "")) or
                item.get("registry_status") != "abandoned" or
                item.get("sdk_device_requirement") is not False or
                type(item.get("arkts_api_reference_count")) is not int or
                item.get("arkts_api_reference_count") != 0 or
                item.get("behavior_validated") is not False):
            raise ValueError(f"invalid retired SysCap name evidence: {cap}")
    return required - evidence.keys()


def apply_contract_overrides(
    root: Path,
    profile: dict,
    device: str,
    exclusions: dict[str, tuple[str, str, str]],
    feature_overrides: dict[tuple[str, str], dict[str, bool]],
    required_syscap_enables: dict[str, tuple[str, str, str]] | None = None,
) -> dict:
    required_syscap_enables = required_syscap_enables or {}
    if device not in {"phone", "2in1"}:
        raise ValueError(f"unsupported QEMU contract: {device}")
    sdk_name = "default" if device == "phone" else "2in1"
    sdk_path = root / f"interface/sdk-js/api/device-define/{sdk_name}.json"
    required = set(json.loads(sdk_path.read_text(encoding="utf-8"))["SysCaps"])
    sdk_required = required.copy()
    protected_sources = [str(sdk_path.relative_to(root))]
    if device == "phone":
        snapshot_path = Path(__file__).resolve().parents[1] / "phone/product_profile/official_documented_syscaps.json"
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        required.update(snapshot["SysCaps"])
        protected_sources.append(
            f'{snapshot["source_repository"]}@{snapshot["source_revision"]}:{snapshot["source_path"]}'
        )
        docs_path = root / "docs/zh-cn/application-dev/reference/phone-syscap-list.md"
        # The pinned build intentionally omits the documentation repository.
        # The checked-in audited release contract is mandatory; a local docs
        # tree, when present, may add requirements but never relax them.
        if docs_path.exists():
            text = docs_path.read_text(encoding="utf-8")
            required.update(re.findall(
                r"^-\s+(SystemCapability\.[A-Za-z0-9_.]+)\s*$", text, re.MULTILINE
            ))
            protected_sources.append(str(docs_path.relative_to(root)))
    forbidden = sorted(required.intersection(exclusions))
    if forbidden:
        raise ValueError("cannot exclude official device capabilities: " + ", ".join(forbidden))
    requested = sorted(QEMU_REQUIRED_SYSCAPS.intersection(exclusions))
    if requested:
        raise ValueError("cannot exclude explicitly requested QEMU capabilities: " + ", ".join(requested))
    if set(required_syscap_enables).intersection(exclusions):
        raise ValueError("cannot both enable and exclude a capability")
    outside_contract = sorted(set(required_syscap_enables) - required - QEMU_REQUIRED_SYSCAPS)
    if outside_contract:
        raise ValueError("cannot add unrequested capabilities outside the device contract: " + ", ".join(outside_contract))

    components = {
        (subsystem["subsystem"], component["component"]): component
        for subsystem in profile["subsystems"]
        for component in subsystem["components"]
    }
    # Validate all owners before mutating the generated profile.
    owners = ({value[:2] for value in exclusions.values()} | set(feature_overrides) |
              {value[:2] for value in required_syscap_enables.values()})
    missing = sorted(owners - components.keys())
    if missing:
        raise ValueError(f"contract override owners missing from profile: {missing}")

    for cap, (subsystem, part, _reason) in sorted(exclusions.items()):
        component = components[(subsystem, part)]
        values = [value for value in component.get("syscap", [])
                  if value.split("=", 1)[0].strip() != cap]
        component["syscap"] = values + [f"{cap} = false"]
    for cap, (subsystem, part, _reason) in sorted(required_syscap_enables.items()):
        component = components[(subsystem, part)]
        values = [value for value in component.get("syscap", [])
                  if value.split("=", 1)[0].strip() != cap]
        component["syscap"] = values + [f"{cap} = true"]
    for owner, overrides in sorted(feature_overrides.items()):
        component = components[owner]
        values = [value for value in component.get("features", [])
                  if value.split("=", 1)[0].strip() not in overrides]
        values.extend(f"{key} = {str(value).lower()}" for key, value in sorted(overrides.items()))
        component["features"] = values
    return {
        "official_contract_sources": protected_sources,
        "required_official_syscaps": sorted(required),
        "retired_documented_syscap_names": retired_declaration_evidence(root, required, sdk_required),
        "explicit_qemu_requirements": sorted(QEMU_REQUIRED_SYSCAPS),
        "enabled_required_syscaps": {
            cap: {"part": f"{owner[0]}:{owner[1]}", "reason": owner[2]}
            for cap, owner in sorted(required_syscap_enables.items())
        },
        "excluded_unsupported_syscaps": {
            cap: {"part": f"{owner[0]}:{owner[1]}", "reason": owner[2]}
            for cap, owner in sorted(exclusions.items())
        },
        "contract_feature_overrides": {
            f"{owner[0]}:{owner[1]}": value
            for owner, value in sorted(feature_overrides.items())
        },
    }


def contract_overlay(root: Path, product_config: dict, metadata: dict) -> dict:
    """Preserve final board component settings while applying contract keys.

    hb replaces entire parts between inherits rather than deep-merging their
    features and SysCaps. The narrow contract overlay must therefore come last
    and carry the winning board settings of each affected component with it.
    """
    owners = {tuple(value["part"].split(":"))
              for value in metadata["excluded_unsupported_syscaps"].values()}
    owners.update(tuple(owner.split(":")) for owner in metadata["contract_feature_overrides"])
    owners.update(tuple(value["part"].split(":")) for value in metadata["enabled_required_syscaps"].values())
    components = {}

    def visit(document: dict, stack: tuple[Path, ...] = ()) -> None:
        for relative in document.get("inherit", []):
            path = (root / relative).resolve()
            if not path.is_relative_to(root.resolve()):
                raise ValueError(f"inherit escapes the source root: {relative}")
            if path in stack:
                raise ValueError(f"cyclic product inherit: {relative}")
            visit(json.loads(path.read_text(encoding="utf-8")), (*stack, path))
        for subsystem in document.get("subsystems", []):
            for component in subsystem.get("components", []):
                key = (subsystem["subsystem"], component["component"])
                if key in owners:
                    components[key] = copy.deepcopy(component)

    # The product's own entries override every inherit, including the generated
    # contract overlay. Fail if they would erase it rather than silently ship a
    # false contract. Existing QEMU products have no local entries for owners.
    local = {(s["subsystem"], c["component"]) for s in product_config.get("subsystems", [])
             for c in s.get("components", [])}
    if local & owners:
        raise ValueError(f"product-local components shadow contract overlay: {sorted(local & owners)}")
    visit(product_config)
    if owners - components.keys():
        raise ValueError(f"missing contract components in product: {sorted(owners - components.keys())}")

    def assign(component: dict, field: str, values: dict[str, bool]) -> None:
        existing = [v for v in component.get(field, []) if v.split("=", 1)[0].strip() not in values]
        component[field] = existing + [f"{key} = {str(value).lower()}" for key, value in sorted(values.items())]

    for cap, evidence in metadata["excluded_unsupported_syscaps"].items():
        assign(components[tuple(evidence["part"].split(":"))], "syscap", {cap: False})
    for cap, evidence in metadata["enabled_required_syscaps"].items():
        assign(components[tuple(evidence["part"].split(":"))], "syscap", {cap: True})
    for owner, values in metadata["contract_feature_overrides"].items():
        assign(components[tuple(owner.split(":"))], "features", values)
    subsystems = {}
    for (subsystem, _part), component in sorted(components.items()):
        subsystems.setdefault(subsystem, []).append(component)
    return {"subsystems": [{"subsystem": name, "components": values}
                           for name, values in sorted(subsystems.items())]}
