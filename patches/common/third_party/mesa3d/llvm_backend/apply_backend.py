#!/usr/bin/env python3
"""Stage checked LLVM dependencies and compose with the existing Mesa backports."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile

COMPONENT = Path(__file__).resolve().parent
SCRIPTS = COMPONENT.parents[4] / "scripts"
sys.path.insert(0, str(SCRIPTS))
from qemu_mesa_llvm_artifacts import PRODUCTS, digest, expected_identity, validate

GN_FILES = {
    "device/qemu/common/virt_full/hardware/gpu/BUILD.gn":
        "b56b266c535d01bbb36c184bee26339a35af63221fcd93630ba9ee8212242af0",
    "third_party/mesa3d/ohos/BUILD.gn":
        "4e5e0f2ea4a4608c43b5559088cb1c11ad2b015e8e5e6739d7f8f1c1f4049b6c",
}
PROJECTS = {"device/qemu": "b017aee8e2dfc97e45aeb508facc1527c3d06f4b",
            "third_party/mesa3d": "952a438c56ce20610d88f0c4d8c673485aefeff7"}
HOOK_RECORD = "third_party/mesa3d/qemu_llvm_recipe_hooks.json"
SOURCE_SCRIPT = "third_party/mesa3d/build_qemu_mesa_llvm.py"
BUILD_ID_FILES = (
    "apply_mesa_build_id.py",
    "0001-bound-ELF-note-payloads-before-reading-or-advancing.patch",
)
UNCHECKED = object()


def checked_path(root: Path, name: str) -> Path:
    path = root / name
    for parent in (path, *path.parents):
        if parent == root:
            break
        if parent.is_symlink():
            raise ValueError("symlink in managed Mesa LLVM source paths")
    return path


def transform(name: str, content: bytes, recipe: str, build_id_backport: bool = True) -> bytes:
    if not re.fullmatch("[a-f0-9]{64}", recipe):
        raise ValueError("invalid LLVM recipe identity")
    if hashlib.sha256(content).hexdigest() != GN_FILES[name]:
        raise ValueError("unexpected base Mesa GN inputs")
    text = content.decode()
    if name.startswith("device/"):
        old = '  script = "build_qemu_mesa.py"\n'
        indent = "    "
        variable = "$qemu_llvm_product"
        base = "//device/qemu/common/virt_full/hardware/gpu/build_qemu_mesa.py"
        target = 'action("qemu_mesa_build") {\n'
        text = text.replace(target,
            'qemu_llvm_product = "arm64_virt"\n'
            'if (target_cpu == "x86_64") {\n'
            '  qemu_llvm_product = "x86_64_virt"\n}\n\n' + target, 1)
        text = text.replace('    "$qemu_mesa_libs_dir/libEGL.so.1.0.0",',
            '    "$qemu_mesa_libs_dir/mesa-llvm-build-provenance.json",\n'
            '    "$qemu_mesa_libs_dir/libEGL.so.1.0.0",', 1)
    else:
        old = '    script = "//device/qemu/arm_virt/linux_full_armv7a/build_armv7a_mesa.py"\n'
        indent = "      "
        variable = "armv7a_virt"
        base = "//device/qemu/arm_virt/linux_full_armv7a/build_armv7a_mesa.py"
        text = text.replace("  outputs = []\n", "  outputs = []\n"
            '  if (product_name == "armv7a_virt") {\n'
            '    outputs += [ "$mesa3d_libs_dir/mesa-llvm-build-provenance.json" ]\n'
            "  }\n", 1)
    if text.count(old) != 1:
        raise ValueError("Mesa action script contract changed")
    text = text.replace(old, old[:len(old)-len(old.lstrip())] +
                        'script = "//' + SOURCE_SCRIPT + '"\n', 1)
    anchor = indent[:-2] + "inputs = [\n"
    if text.count(anchor) != 1:
        raise ValueError("Mesa action dependency contract changed")
    extras = [base, "//" + SOURCE_SCRIPT,
              "//third_party/mesa3d/qemu_mesa_llvm_artifacts.py",
              "//third_party/mesa3d/qemu_llvm_build_identity.json",
              f"//third_party/mesa3d/qemu_llvm/{recipe}/{variable}/manifest.json",
              f"//third_party/mesa3d/qemu_llvm/{recipe}/{variable}/lib/libllvm.a"]
    if build_id_backport:
        extras += ["//third_party/mesa3d/qemu_build_id/" + name for name in BUILD_ID_FILES]
    text = text.replace(anchor, anchor + "".join(indent + '"' + item + '",\n'
                                               for item in extras), 1)
    return text.encode()


def atomic_write(path: Path, content: bytes, expected=UNCHECKED, mode: int | None = None) -> None:
    if mode is None:
        mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(content)
        os.fchmod(stream.fileno(), mode)
    try:
        if expected is not UNCHECKED:
            actual = path.read_bytes() if path.exists() else None
            if actual != expected:
                raise ValueError("Mesa source changed before publication; preserving caller changes")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def restore_plan(root: Path) -> tuple[dict, list[tuple[Path, bytes]]]:
    record_path = checked_path(root, HOOK_RECORD)
    if not record_path.exists():
        return {}, []
    record = json.loads(record_path.read_text())
    changes = []
    for name, item in record["hooks"].items():
        if name not in GN_FILES:
            raise ValueError("unknown managed GN hook path")
        original = base64.b64decode(item["base"], validate=True)
        repaired = transform(name, original, record["identity"]["recipe_sha256"],
                             record.get("build_id_backport", False))
        current = checked_path(root, name)
        if current.read_bytes() not in (original, repaired):
            raise ValueError("modified Mesa GN hook; preserving user changes")
        if current.read_bytes() == repaired:
            changes.append((current, original))
    return record, changes


def apply(root: Path, artifacts: Path, products: list[str]) -> None:
    identity = expected_identity(SCRIPTS)
    previous, restorations = restore_plan(root)
    for project, revision in PROJECTS.items():
        if (root / project / ".git").exists():
            actual = subprocess.check_output(
                ["git", "-C", str(root / project), "rev-parse", "HEAD"], text=True).strip()
            if actual != revision:
                raise ValueError("pinned OpenHarmony 7.0 Mesa/QEMU projects required")
    # Validate every selected dependency before publishing any source changes.
    for product in products:
        validate(artifacts / product, product, identity)
    planned = {}
    restored = {str(path.relative_to(root)): data for path, data in restorations}
    for name, expected in GN_FILES.items():
        path = checked_path(root, name)
        original = restored.get(name, path.read_bytes())
        # An ungenerated ARM product has no QEMU action in the official GN.
        if name.startswith("third_party/") and "armv7a_virt" not in products:
            if hashlib.sha256(original).hexdigest() != expected:
                continue
        planned[name] = (original, transform(name, original, identity["recipe_sha256"]))
    payloads = {
        SOURCE_SCRIPT: (COMPONENT / "files/build_qemu_mesa_llvm.py").read_bytes(),
        "third_party/mesa3d/qemu_mesa_llvm_artifacts.py":
            (SCRIPTS / "qemu_mesa_llvm_artifacts.py").read_bytes(),
        "third_party/mesa3d/qemu_llvm_build_identity.json":
            (json.dumps(identity, indent=2) + "\n").encode(),
    }
    payloads.update({"third_party/mesa3d/qemu_build_id/" + name:
                     (COMPONENT.parent / "build_id_boundaries" / name).read_bytes()
                     for name in BUILD_ID_FILES})
    snapshots = {name: checked_path(root, name).read_bytes() for name in planned}
    for name, content in payloads.items():
        path = checked_path(root, name)
        snapshots[name] = path.read_bytes() if path.exists() else None
        if path.exists() and path.read_bytes() != content:
            if previous.get("payloads", {}).get(name) != digest(path):
                raise ValueError("unknown LLVM backend helper; preserving user changes")
    mesa = checked_path(root, "third_party/mesa3d")
    for product in products:
        destination = mesa / "qemu_llvm" / identity["recipe_sha256"] / product
        checked_path(root, str(destination.relative_to(root)))
        if destination.exists():
            validate(destination, product, identity)
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=destination.parent) as temp:
            stage = Path(temp) / product
            stage.mkdir()
            source = artifacts / product
            shutil.copytree(source / "include", stage / "include")
            shutil.copytree(source / "lib", stage / "lib")
            shutil.copyfile(source / "manifest.json", stage / "manifest.json")
            validate(stage, product, identity)
            os.replace(stage, destination)
    # Recheck every source sibling after dependency copying and before publishing.
    for name, before in snapshots.items():
        path = checked_path(root, name)
        if (path.read_bytes() if path.exists() else None) != before:
            raise ValueError("Mesa source changed while staging LLVM; preserving caller changes")
    for name, content in payloads.items():
        # GN executes its action script directly through /usr/bin/env. A new
        # file otherwise receives 0644, and a previously staged 0644 helper
        # retains that broken mode on every replay.
        atomic_write(checked_path(root, name), content, snapshots[name],
                     mode=0o755 if name == SOURCE_SCRIPT else None)
    for name, (original, repaired) in planned.items():
        atomic_write(checked_path(root, name), repaired, snapshots[name])
    record = {
        "schema_version": 1, "identity": identity, "build_id_backport": True,
        "payloads": {name: hashlib.sha256(data).hexdigest() for name, data in payloads.items()},
        "hooks": {name: {"base": base64.b64encode(original).decode(),
                         "patched_sha256": hashlib.sha256(repaired).hexdigest()}
                  for name, (original, repaired) in planned.items()},
    }
    atomic_write(checked_path(root, HOOK_RECORD), (json.dumps(record, indent=2) + "\n").encode())
    print("staged fixed LLVM dependencies and QEMU-only Mesa GN actions")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--products", nargs="+", choices=PRODUCTS)
    parser.add_argument("--restore-hooks", action="store_true")
    args = parser.parse_args()
    root = args.source_root.resolve()
    if args.restore_hooks:
        record, changes = restore_plan(root)
        for path, data in changes:
            repaired = transform(path.relative_to(root).as_posix(), data,
                                 record["identity"]["recipe_sha256"],
                                 record.get("build_id_backport", False))
            atomic_write(path, data, repaired)
        print("restored exact Mesa base hooks before parent component installers")
    else:
        if not args.artifact_root or not args.products:
            parser.error("--artifact-root and --products are required")
        apply(root, args.artifact_root.resolve(), args.products)


if __name__ == "__main__":
    main()
