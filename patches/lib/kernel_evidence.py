"""Check delivered kernel evidence; this is provenance, not behavior proof."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import re

ROOTS = (
    "kernel/linux/linux-6.6", "kernel/linux/common_modules", "device/qemu/common/virt_full/kernel",
    "drivers/hdf_core", "third_party/bounds_checking_function", "third_party/FreeBSD/sys/dev/evdev",
    "vendor/ohemu/virt/hdf_config/khdf", "kernel/linux/linux-5.10/scripts/ohos-check-dir.sh",
)
MODULES = {"rtw89_core.ko", "rtw89_pci.ko", "rtw89_8852a.ko", "rtw89_8852ae.ko", "mt7601u.ko",
           "mac80211_hwsim.ko", "virt_wifi.ko", "libarc4.ko", "mac80211.ko", "cfg80211.ko",
           "iwlwifi.ko", "iwlmvm.ko"}
ARCHES = {"arm64": ("arm64", "Image"), "armv7a": ("arm", "zImage"), "x86_64": ("x86_64", "bzImage")}


def sha(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def valid_sha(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def verify(package, arch):
    if arch not in ARCHES:
        raise ValueError("unsupported packaged kernel architecture")
    cpu, image_name = ARCHES[arch]
    inputs_path = package / "kernel-source-inputs.json"
    certificate = json.loads((package / "kernel-inputs.json").read_text())
    inputs = json.loads(inputs_path.read_text())
    files = inputs.get("files")
    if (inputs.get("schema_version") != 1 or inputs.get("kind") != "qemu_linux_6_6_prepared_kernel_inputs" or
            inputs.get("roots") != list(ROOTS) or not isinstance(files, dict) or not files or
            type(inputs.get("file_count")) is not int or inputs["file_count"] != len(files)):
        raise ValueError("missing/malformed prepared kernel input inventory")
    for name, item in files.items():
        path = PurePosixPath(name)
        if (path.is_absolute() or ".." in path.parts or not isinstance(item, dict) or
                not any(name == root or name.startswith(root + "/") for root in ROOTS)):
            raise ValueError("unsafe/out-of-scope kernel input")
        if "symlink" in item:
            if (set(item) - {"symlink", "target_sha256"} or not isinstance(item["symlink"], str) or
                    ("target_sha256" in item and not valid_sha(item["target_sha256"]))):
                raise ValueError("invalid kernel symlink evidence")
        elif (set(item) != {"sha256", "mode"} or not valid_sha(item["sha256"]) or
              type(item["mode"]) is not int or not 0 <= item["mode"] <= 0o777):
            raise ValueError("invalid kernel source file evidence")
    tree_sha = hashlib.sha256(json.dumps(files, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if tree_sha != inputs.get("source_tree_sha256"):
        raise ValueError("kernel source inventory hash mismatch")
    modules = certificate.get("modules_sha256", {})
    image = package / "images" / image_name
    if (certificate.get("schema_version") != 1 or certificate.get("kind") != "qemu_linux_6_6_built_kernel_evidence" or
            certificate.get("kernel_arch") != cpu or certificate.get("image_name") != image_name or
            certificate.get("source_tree_sha256") != tree_sha or
            certificate.get("inputs_metadata_sha256") != sha(inputs_path) or
            set(modules) != MODULES or any(not valid_sha(value) for value in modules.values()) or
            not image.is_file() or image.stat().st_size == 0 or certificate.get("image_sha256") != sha(image)):
        raise ValueError("stale, wrong-architecture or mismatched delivered kernel evidence")
    return {"schema_version": 1, "scope": "static_kernel_provenance_only_not_runtime_validation",
            "guest_arch": arch, "source_tree_sha256": tree_sha, "image_sha256": certificate["image_sha256"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", type=Path, required=True)
    parser.add_argument("--guest-arch", choices=tuple(ARCHES), required=True)
    args = parser.parse_args()
    result = verify(args.package, args.guest_arch)
    print(f"PASS: packaged kernel provenance {result['image_sha256']}; runtime gate still required")
