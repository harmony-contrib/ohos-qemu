#!/usr/bin/env python3
"""Read-only DAYU200/QEMU source comparison; never builds or edits OHOS inputs.

Generated profiles describe proposed source selection, not runtime capability.
Whole component replacement follows the existing product-profile resolver.
Unassigned feature values are left absent: absence does not mean GN false.
"""
from __future__ import annotations

import argparse
import copy
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def assignments(values: list[str]) -> dict[str, str]:
    result = {}
    for value in values:
        key, separator, rhs = value.partition("=")
        if not separator:
            raise ValueError(f"not an assignment: {value}")
        result[key.strip()] = rhs.strip()
    return result


class Reader:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.inputs = {}

    def read_bytes(self, relative: str) -> bytes:
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError(f"source path escapes root: {relative}")
        data = path.read_bytes()
        self.inputs[relative] = sha(data)
        return data

    def read(self, relative: str) -> str:
        return self.read_bytes(relative).decode("utf-8")

    def resolve(self, relative: str, document=None, stack=()):
        if relative in stack:
            raise ValueError(f"inherit cycle: {stack + (relative,)}")
        document = document if document is not None else json.loads(self.read(relative))
        parts = {}
        for parent in document.get("inherit", []):
            parts.update(self.resolve(parent, stack=stack + (relative,)))
        for subsystem in document.get("subsystems", []):
            for component in subsystem.get("components", []):
                key = subsystem["subsystem"] + ":" + component["component"]
                parts[key] = {"source": relative, "definition": copy.deepcopy(component)}
        return parts


def profile_module(repo: Path, device: str):
    path = repo / "patches" / device / "product_profile/apply.py"
    spec = importlib.util.spec_from_file_location("dayu_compare_" + device, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def proposed_profile(reader: Reader, module, product: str, effective: dict, metadata: dict):
    relative = module.PRODUCT_CONFIGS[product]
    document = json.loads(reader.read(relative))
    parents = [p for p in document["inherit"]
               if not re.fullmatch(r"vendor/ohemu/virt/virt_(phone|2in1)_(full|contract_.*)\.json", p)]
    parents.insert(parents.index(module.RICH_PROFILE) + 1, module.EFFECTIVE_PROFILE)
    parts = {}
    for parent in parents:
        parts.update(reader.resolve(parent, effective if parent == module.EFFECTIVE_PROFILE else None))
    for subsystem in document.get("subsystems", []):
        for component in subsystem.get("components", []):
            key = subsystem["subsystem"] + ":" + component["component"]
            parts[key] = {"source": relative, "definition": copy.deepcopy(component)}
    local = {s["subsystem"] + ":" + c["component"]
             for s in document.get("subsystems", []) for c in s.get("components", [])}
    owners = set(metadata["contract_feature_overrides"])
    owners.update(v["part"] for field in ("excluded_unsupported_syscaps", "enabled_required_syscaps")
                  for v in metadata[field].values())
    if local & owners:
        raise ValueError(f"local parts shadow generated contract: {sorted(local & owners)}")
    for owner in owners:
        parts[owner]["source"] += " + generated contract overlay"
    for owner, features in metadata["contract_feature_overrides"].items():
        old = assignments(parts[owner]["definition"].get("features", []))
        old.update({key: str(value).lower() for key, value in features.items()})
        parts[owner]["definition"]["features"] = [f"{key} = {value}" for key, value in sorted(old.items())]
    for field, value in (("excluded_unsupported_syscaps", "false"), ("enabled_required_syscaps", "true")):
        for capability, evidence in metadata[field].items():
            old = assignments(parts[evidence["part"]]["definition"].get("syscap", []))
            old[capability] = value
            parts[evidence["part"]]["definition"]["syscap"] = [f"{key} = {rhs}" for key, rhs in sorted(old.items())]
    return {"config": relative, "metadata": metadata,
            "parts": dict(sorted(parts.items())), "product_fields": {
                k: v for k, v in document.items() if k not in ("inherit", "subsystems")},
            "evidence_level": "read_only_generated_source_selection_not_hb_or_image_or_runtime"}


def difference(left: dict, right: dict):
    only_left = sorted(left.keys() - right.keys())
    only_right = sorted(right.keys() - left.keys())
    rows = []
    for part in sorted(left.keys() & right.keys()):
        for field in ("features", "syscap"):
            a = assignments(left[part]["definition"].get(field, []))
            b = assignments(right[part]["definition"].get(field, []))
            for key in sorted(a.keys() | b.keys()):
                if a.get(key) != b.get(key):
                    rows.append({"part": part, "field": field, "key": key,
                                 "dayu200": a.get(key), "qemu": b.get(key),
                                 "dayu_source": left[part]["source"],
                                 "qemu_source": right[part]["source"]})
    return {"dayu_only_parts": only_left, "qemu_only_parts": only_right,
            "explicit_assignment_differences": rows,
            "counts": {"dayu_parts": len(left), "qemu_parts": len(right),
                       "dayu_only": len(only_left), "qemu_only": len(only_right),
                       "assignment_differences": len(rows)}}


def file_comparison(reader: Reader, dayu_dir: str, qemu_dir: str):
    def inventory(directory):
        return {str(p.relative_to(reader.root / directory)) for p in (reader.root / directory).rglob("*")
                if p.is_file()}
    a, b = inventory(dayu_dir), inventory(qemu_dir)
    changed = []
    for path in sorted(a & b):
        left = reader.read_bytes(dayu_dir + "/" + path)
        right = reader.read_bytes(qemu_dir + "/" + path)
        if left != right:
            row = {"relative_path": path, "dayu_source": dayu_dir + "/" + path,
                   "qemu_source": qemu_dir + "/" + path,
                   "dayu_sha256": sha(left), "qemu_sha256": sha(right)}
            try:
                if b"\0" in left or b"\0" in right:
                    raise ValueError("binary input")
                row["diff"] = "".join(difflib.unified_diff(
                    left.decode("utf-8").splitlines(True), right.decode("utf-8").splitlines(True),
                    fromfile="dayu200/" + path, tofile="qemu/" + path))
            except (UnicodeError, ValueError):
                row["binary"] = True
            changed.append(row)
    # Hash unmatched files too, so the full inventory can be reproduced.
    for path in sorted(a - b):
        reader.read_bytes(dayu_dir + "/" + path)
    for path in sorted(b - a):
        reader.read_bytes(qemu_dir + "/" + path)
    return {"dayu_dir": dayu_dir, "qemu_dir": qemu_dir, "dayu_only": sorted(a - b),
            "qemu_only": sorted(b - a), "changed": changed,
            "identical": sorted((a & b) - {x["relative_path"] for x in changed})}


def kernel_values(text: str):
    result = {}
    for line in text.splitlines():
        if line.startswith("CONFIG_") and "=" in line:
            key, value = line.split("=", 1)
            result[key] = value
        else:
            match = re.fullmatch(r"# (CONFIG_\w+) is not set", line)
            if match:
                result[match[1]] = "n"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--qemu-repo", type=Path, default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    reader = Reader(args.source_root)
    dayu_path = "vendor/hihope/rk3568/config.json"
    dayu = reader.resolve(dayu_path)
    profiles = {}
    generators = {}
    for device in ("phone", "2in1"):
        module = profile_module(args.qemu_repo, device)
        effective, metadata = module.make_effective_profile(reader.root)
        generators[device] = {"path": str(Path(module.__file__).relative_to(args.qemu_repo)),
                              "sha256": sha(Path(module.__file__).read_bytes()),
                              "effective_profile_sha256": sha(json.dumps(effective, sort_keys=True).encode())}
        for product in module.PRODUCT_CONFIGS:
            profiles[product + "/" + device] = proposed_profile(reader, module, product, effective, metadata)
    revisions = {}
    for project in ("vendor/hihope", "vendor/ohemu", "device/board/hihope", "device/soc/rockchip",
                    "device/qemu", "kernel/linux/config", "productdefine/common"):
        revisions[project] = subprocess.check_output(["git", "-C", str(reader.root / project),
                                                     "rev-parse", "HEAD"], text=True).strip()
    files = [file_comparison(reader, "vendor/hihope/rk3568", "vendor/ohemu/virt")]
    for subdir in ("cfg", "distributedhardware", "updater"):
        files.append(file_comparison(reader, "device/board/hihope/rk3568/" + subdir,
                                     "device/qemu/common/virt_full/" + subdir))
    # DAYU's builder merges type, optional form, architecture, optional product,
    # and base, in that order. This pinned tree has no form/product fragments.
    # Do not substitute the similarly named archived rk3568_standard_defconfig.
    kernel_paths = {"dayu200": ["kernel/linux/config/linux-6.6/type/standard_defconfig",
                               "kernel/linux/config/linux-6.6/rk3568/arch/arm64_defconfig",
                               "kernel/linux/config/linux-6.6/base_defconfig"],
                    "arm64_virt": ["device/qemu/common/virt_full/kernel/arm64_virt_defconfig",
                                   "device/qemu/common/virt_full/kernel/qos.config"],
                    "armv7a_virt": ["device/qemu/common/virt_full/kernel/arm_virt_defconfig",
                                    "device/qemu/common/virt_full/kernel/qos.config"],
                    "x86_64_virt": ["device/qemu/common/virt_full/kernel/x86_64_virt_defconfig",
                                    "device/qemu/common/virt_full/kernel/qos.config"]}
    kernels = {}
    for key, paths in kernel_paths.items():
        values = {}
        for path in paths:
            values.update(kernel_values(reader.read(path)))
        kernels[key] = {"paths_in_merge_order": paths, "values": values,
                        "evidence_level": "explicit_merged_inputs_before_kconfig"}
    kernel_diffs = {key: [{"key": option, "dayu200": kernels["dayu200"]["values"].get(option),
                          "qemu": value["values"].get(option)}
                         for option in sorted(kernels["dayu200"]["values"].keys() | value["values"].keys())
                         if kernels["dayu200"]["values"].get(option) != value["values"].get(option)]
                    for key, value in kernels.items() if key != "dayu200"}
    supporting_paths = [
        "device/board/hihope/rk3568/BUILD.gn", "device/board/hihope/rk3568/device.gni",
        "device/board/hihope/rk3568/kernel/build_kernel.sh",
        "device/board/hihope/rk3568/loader/parameter.txt",
        "device/board/hihope/rk3568/loader/parameter_ab.txt",
        "device/soc/rockchip/rk3568/hardware/BUILD.gn",
        "device/qemu/common/virt_full/BUILD.gn", "device/qemu/common/virt_full/device.gni",
        "device/qemu/common/virt_full/hardware/BUILD.gn",
        "device/qemu/common/virt_full/kernel/build_kernel.sh",
        "device/qemu/common/virt_full/cfg/fstab.virt",
        "device/qemu/common/virt_full/updater/config/fstab.updater",
        "arkcompiler/ets_runtime/js_runtime_config.gni",
        "arkcompiler/runtime_core/static_core/ark_config.gni",
        "base/security/selinux_adapter/selinux.gni",
        "third_party/skia/build_overrides/skia.gni",
        "foundation/arkui/ace_engine/ace_config.gni",
        "foundation/graphic/graphic_2d/graphic_config.gni",
        "foundation/multimedia/image_framework/ide/image_decode_config.gni",
        "foundation/resourceschedule/memmgr/memmgr.gni",
    ]
    supporting_files = {path: reader.read(path) for path in supporting_paths}
    actual_features_path = "out/preloader/arm64_virt/features.json"
    actual_features = json.loads(reader.read(actual_features_path))["features"]
    actual_phone = reader.resolve("vendor/ohemu/qemu_arm64_linux_full/config.json")
    proposed_phone = profiles["arm64_virt/phone"]["parts"]
    mismatches = difference(actual_phone, proposed_phone)
    explicit = {k: v for part in proposed_phone.values()
                for k, v in assignments(part["definition"].get("features", [])).items()}
    def gn_value(value):
        if value in ("true", "false"):
            return value == "true"
        if value.startswith('"') and value.endswith('"'):
            return value[1:-1]
        return value
    feature_mismatches = [{"key": key, "proposed": value, "preloader": actual_features.get(key)}
                          for key, value in sorted(explicit.items())
                          if key not in actual_features or gn_value(value) != actual_features[key]]
    output = {"schema_version": 1, "scope": "source_configuration_comparison_no_dayu_image_or_board_validation",
              "source_root": str(reader.root), "source_revisions": revisions,
              "dayu_product": json.loads(reader.read(dayu_path)), "dayu_resolved_parts": dayu,
              "profile_generators": generators, "qemu_proposed_profiles": profiles,
              "comparisons": {key: difference(dayu, value["parts"]) for key, value in profiles.items()},
              "file_comparisons": files, "kernel_defconfigs": kernels, "kernel_differences": kernel_diffs,
              "supporting_source_files": supporting_files,
              "actual_arm64_phone_source_vs_proposal": mismatches,
              "actual_arm64_phone_preloader": {"path": actual_features_path,
                  "scope": "currently_loaded_source_not_packaged_or_runtime",
                  "checked_explicit_feature_count": len(explicit),
                  "feature_mismatches": feature_mismatches, "features": actual_features},
              "notes": ["All generated profiles are in memory; source/out volumes remain read-only.",
                        "Component selection is not the transitive GN target graph.",
                        "Null means not explicitly assigned here; GN defaults are not evaluated.",
                        "Defconfig differences are not olddefconfig or runtime kernel proof.",
                        "Directory inventories include all regular files, including generated profiles, firmware, and build remnants; file presence alone is not product support.",
                        "DAYU200 source, actual QEMU source and proposed profile selections have different evidence levels."],
              "source_file_sha256": dict(sorted(reader.inputs.items()))}
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
