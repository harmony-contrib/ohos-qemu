#!/usr/bin/env python3
"""Bind the six installed Mesa libraries to the current private LLVM recipe.

This checks build provenance and image bytes. It never proves guest behavior.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

from ext_image_entries import dump_unique_file
from qemu_mesa_llvm_artifacts import PRODUCTS, digest, expected_identity, validate
from verify_alsa_config_image import debugfs_path

REPO = Path(__file__).resolve().parents[1]
LIBRARIES = (
    "libEGL.so.1.0.0", "libgbm.so.1.0.0", "libGLESv1_CM.so.1.1.0",
    "libGLESv2.so.2.0.0", "libglapi.so.0.0.0", "kms_swrast_dri.so",
)
REPORTS = ("build.json", "llvm-manifest.json", "libraries.json")
BASE_BUILDERS = {
    "armv7a_virt": "22116ddc5d03bb440596e02c1336541761614c790b4a12bca67ce63eb5d10169",
    "arm64_virt": "03e45a069e5aa14d4b710478971771d174fc4e7bd367a22376b1051cf210ed11",
    "x86_64_virt": "03e45a069e5aa14d4b710478971771d174fc4e7bd367a22376b1051cf210ed11",
}


def regular(path: Path) -> Path:
    if path.is_symlink() or not path.is_file():
        raise ValueError("regular Mesa evidence file required: " + str(path))
    return path


def elf_record(path: Path, product: str) -> dict:
    with regular(path).open("rb") as stream:
        header = stream.read(64)
    elf_class = 1 if product == "armv7a_virt" else 2
    machine = PRODUCTS[product][1]
    if (len(header) != 64 or header[:7] != b"\x7fELF" + bytes((elf_class, 1, 1)) or
            struct.unpack_from("<HH", header, 16) != (3, machine)):
        raise ValueError("wrong actual Mesa shared-library ABI: " + path.name)
    return {"sha256": digest(path), "size": path.stat().st_size,
            "elf_machine": machine}


def check_build(build: dict, manifest: dict, manifest_sha: str, product: str) -> None:
    identity = expected_identity()
    if (manifest.get("schema_version") != 1 or
            manifest.get("component") != "QEMU Mesa private LLVM 10.0.0" or
            manifest.get("product") != product or manifest.get("arch") != PRODUCTS[product][0] or
            manifest.get("runtime_gate_passed") is not False or
            any(manifest.get(key) != value for key, value in identity.items()) or
            manifest.get("archive", {}).get("machines") != [PRODUCTS[product][1]] or
            type(manifest.get("archive", {}).get("objects")) is not int or
            manifest["archive"]["objects"] <= 0):
        raise ValueError("Mesa LLVM manifest differs from the current product/source recipe")
    expected_options = {"llvm": "enabled", "draw-use-llvm": True,
                        "shared-llvm": "disabled", "cpp_std": "c++17"}
    inputs = build.get("build_inputs", {})
    consumer = REPO / "patches/common/third_party/mesa3d/llvm_backend/files/build_qemu_mesa_llvm.py"
    mapping = REPO / "patches/common/third_party/mesa3d/kms_mapping_synchronization/files/apply_mesa_kms_mapping.py"
    build_id = REPO / "patches/common/third_party/mesa3d/build_id_boundaries"
    build_id_inputs = {name: digest(build_id / name) for name in (
        "apply_mesa_build_id.py",
        "0001-bound-ELF-note-payloads-before-reading-or-advancing.patch",
    )}
    if (build.get("schema_version") != 1 or build.get("product") != product or
            build.get("dependency") != identity["recipe_sha256"] or
            build.get("runtime_gate_passed") is not False or
            build.get("actual_options") != expected_options or
            build.get("llvm_archive_sha256") != manifest["files"]["lib/libllvm.a"]["sha256"] or
            inputs.get("product") != product or inputs.get("builder") != digest(consumer) or
            inputs.get("base_builder") != BASE_BUILDERS[product] or
            inputs.get("build_id_backport") != build_id_inputs or
            inputs.get("mapping") != digest(mapping) or inputs.get("llvm_manifest") != manifest_sha):
        raise ValueError("Mesa consumer proof differs from the current build/dependency")


def check_inventory(inventory: dict, build: dict, product: str) -> None:
    if set(inventory) != set(LIBRARIES):
        raise ValueError("all six Mesa output libraries must be recorded")
    for name, entry in inventory.items():
        sha = entry.get("sha256")
        if (not isinstance(sha, str) or len(sha) != 64 or
                any(c not in "0123456789abcdef" for c in sha) or
                type(entry.get("size")) is not int or entry["size"] < 64 or
                entry.get("elf_machine") != PRODUCTS[product][1]):
            raise ValueError("invalid Mesa output inventory: " + name)
    if inventory["kms_swrast_dri.so"]["sha256"] != build.get("driver_sha256"):
        raise ValueError("Mesa DRI driver differs from its actual build proof")


def verify_image(image: Path, inventory: dict, product: str) -> dict:
    abi = "lib" if product == "armv7a_virt" else "lib64"
    records = {}
    with tempfile.TemporaryDirectory(prefix="qemu-mesa-llvm-image-") as directory:
        for name in LIBRARIES:
            destination = Path(directory) / name
            destination.mkdir()
            candidates = tuple(f"{prefix}/{abi}/{name}" for prefix in ("", "/system"))
            library, inode = dump_unique_file(image, candidates, destination, debugfs_path())
            observed = elf_record(library, product)
            if observed != inventory[name]:
                raise ValueError("installed Mesa bytes differ from the checked build: " + name)
            records[name] = {**observed, **inode}
    return records


def write_source_provenance(image: Path, source_build: Path, dependency: Path,
                            product: str, destination: Path) -> dict:
    manifest_path = regular(dependency / "manifest.json")
    manifest = validate(dependency, product)
    proof = regular(source_build / "mesa-llvm-build-provenance.json")
    build = json.loads(proof.read_text())
    check_build(build, manifest, digest(manifest_path), product)
    inventory = {name: elf_record(source_build / name, product) for name in LIBRARIES}
    check_inventory(inventory, build, product)
    result = verify_image(image, inventory, product)
    destination.mkdir(exist_ok=False)
    shutil.copyfile(proof, destination / "build.json")
    shutil.copyfile(manifest_path, destination / "llvm-manifest.json")
    (destination / "libraries.json").write_text(json.dumps(inventory, indent=2) + "\n")
    provenance = {"schema_version": 1, "product": product,
                  "files": {name: digest(destination / name) for name in REPORTS},
                  "runtime_gate_passed": False}
    (destination / "provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
    # Read the written evidence back, including source file stability checks.
    if (digest(proof) != provenance["files"]["build.json"] or
            digest(manifest_path) != provenance["files"]["llvm-manifest.json"]):
        raise ValueError("Mesa source evidence changed during packaging")
    load_packaged_provenance(destination, product)
    return result


def load_packaged_provenance(directory: Path, product: str) -> dict:
    record = json.loads(regular(directory / "provenance.json").read_text())
    if (record.get("schema_version") != 1 or record.get("product") != product or
            record.get("runtime_gate_passed") is not False or
            set(record.get("files", {})) != set(REPORTS)):
        raise ValueError("invalid packaged Mesa source provenance")
    for name in REPORTS:
        if digest(regular(directory / name)) != record["files"][name]:
            raise ValueError("changed packaged Mesa source evidence: " + name)
    build = json.loads((directory / "build.json").read_text())
    manifest = json.loads((directory / "llvm-manifest.json").read_text())
    check_build(build, manifest, record["files"]["llvm-manifest.json"], product)
    inventory = json.loads((directory / "libraries.json").read_text())
    check_inventory(inventory, build, product)
    return inventory


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system-image", type=Path, required=True)
    parser.add_argument("--product", choices=PRODUCTS, required=True)
    parser.add_argument("--source-build", type=Path)
    parser.add_argument("--dependency", type=Path)
    parser.add_argument("--write-provenance", type=Path)
    parser.add_argument("--packaged-provenance", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    creating = bool(args.source_build and args.dependency and args.write_provenance)
    if (creating == bool(args.packaged_provenance) or
            not creating and any((args.source_build, args.dependency, args.write_provenance))):
        parser.error("use source-build/dependency/write-provenance together, or packaged-provenance")
    result = {"status": "fail", "product": args.product,
              "scope": "offline current Mesa/LLVM source provenance and six image libraries ONLY",
              "first_artifact_behavior_gate_passed": False, "runtime_behavior_tested": False,
              "failures": []}
    try:
        before = args.system_image.stat()
        result["system_image_sha256"] = digest(args.system_image)
        if creating:
            result["libraries"] = write_source_provenance(
                args.system_image, args.source_build, args.dependency,
                args.product, args.write_provenance)
        else:
            inventory = load_packaged_provenance(args.packaged_provenance, args.product)
            result["libraries"] = verify_image(args.system_image, inventory, args.product)
        after = args.system_image.stat()
        if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
            raise ValueError("system image changed during Mesa verification")
        result["status"] = "pass"
    except (OSError, ValueError, KeyError, TypeError, struct.error, subprocess.SubprocessError) as error:
        result["failures"].append(str(error))
    if args.output:
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: result[key] for key in ("status", "product", "failures")}))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
