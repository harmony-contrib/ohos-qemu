#!/usr/bin/env python3
"""Verify the fixed-source LLVM dependency without claiming guest validation."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath

PRODUCTS = {
    "armv7a_virt": ("arm", 40),
    "arm64_virt": ("arm64", 183),
    "x86_64_virt": ("x86_64", 62),
}
RECIPE_FILES = (
    "build_qemu_mesa_llvm.py",
    "build_qemu_mesa_llvm_in_docker.sh",
    "m144_release_source_lock.json",
    "openharmony_7_0_release_source_lock.json",
)


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for data in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(data)
    return h.hexdigest()


def expected_identity(script_dir: Path | None = None) -> dict:
    directory = script_dir or Path(__file__).resolve().parent
    hashes = {name: digest(directory / name) for name in RECIPE_FILES}
    lock = json.loads((directory / "m144_release_source_lock.json").read_text())
    sources = [p for p in lock["projects"] if p["path"] == "src/third_party/swiftshader"]
    if len(sources) != 1 or lock["chromium_milestone"] != 144:
        raise ValueError("the fixed M144 SwiftShader source lock is required")
    return {
        "recipe_sha256": hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest(),
        "source_lock_sha256": hashes["m144_release_source_lock.json"],
        "openharmony_source_lock_sha256": hashes["openharmony_7_0_release_source_lock.json"],
        "swiftshader_revision": sources[0]["revision"],
    }


def archive_machines(path: Path) -> dict:
    """Inspect every object in a regular GNU/LLVM ar archive."""
    machines: set[int] = set()
    objects = 0
    with path.open("rb") as stream:
        if stream.read(8) != b"!<arch>\n":
            raise ValueError("a materialized LLVM archive is required")
        while True:
            header = stream.read(60)
            if not header:
                break
            if len(header) != 60 or header[58:] != b"\x60\n":
                raise ValueError("invalid LLVM archive member header")
            try:
                size = int(header[48:58].decode("ascii").strip())
            except (ValueError, UnicodeError) as error:
                raise ValueError("invalid LLVM archive member size") from error
            if size < 0:
                raise ValueError("negative LLVM archive member size")
            name = header[:16].decode("ascii").strip()
            start = stream.tell()
            if name not in ("/", "//", "/SYM64/"):
                data = stream.read(min(size, 64))
                if len(data) < 20 or data[:4] != b"\x7fELF" or data[5] != 1:
                    raise ValueError("every LLVM member must be a little-endian ELF object")
                if int.from_bytes(data[16:18], "little") != 1:
                    raise ValueError("LLVM archive contains a non-relocatable ELF")
                machines.add(int.from_bytes(data[18:20], "little"))
                objects += 1
            stream.seek(start + size + (size & 1))
            if stream.tell() > path.stat().st_size:
                raise ValueError("truncated LLVM archive member")
    if not objects:
        raise ValueError("LLVM archive has no objects")
    return {"machines": sorted(machines), "objects": objects}


def inventory(root: Path) -> dict:
    if any(path.is_symlink() for path in (root / "include").rglob("*")):
        raise ValueError("LLVM consumer headers cannot contain symlinks")
    if {path.name for path in (root / "lib").iterdir()} != {"libllvm.a"}:
        raise ValueError("unrecorded LLVM library files")
    files = [root / "lib/libllvm.a"]
    files += sorted(path for path in (root / "include").rglob("*") if path.is_file())
    result = {}
    for path in files:
        parents = path.relative_to(root).parents
        if (path.is_symlink() or not path.is_file() or
                any((root / parent).is_symlink() for parent in parents)):
            raise ValueError(f"materialized LLVM artifact file required: {path}")
        result[path.relative_to(root).as_posix()] = {
            "sha256": digest(path), "size": path.stat().st_size,
        }
    return result


def write_manifest(root: Path, product: str, source_identity: dict,
                   builder_evidence: dict) -> dict:
    identity = expected_identity()
    if (source_identity["swiftshader_revision"] != identity["swiftshader_revision"] or
            source_identity["m144_source_lock_sha256"] != identity["source_lock_sha256"] or
            builder_evidence["artifact_identity"] != identity):
        raise ValueError("built LLVM does not match the fixed source")
    manifest = {
        "schema_version": 1,
        "component": "QEMU Mesa private LLVM 10.0.0",
        "product": product, "arch": PRODUCTS[product][0],
        **identity,
        "llvm_git_tree": source_identity["llvm_git_tree"],
        "builder_sha256": builder_evidence["builder_sha256"],
        "compiler_sha256": builder_evidence["compiler_sha256"],
        "sysroot": builder_evidence["sysroot"],
        "unwind_registration": builder_evidence["unwind_registration"],
        "archive": archive_machines(root / "lib/libllvm.a"),
        "files": inventory(root),
        "runtime_gate_passed": False,
    }
    (root / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return manifest


def validate(root: Path, product: str, identity: dict | None = None) -> dict:
    root = root.resolve()
    expected = identity or expected_identity()
    manifest = json.loads((root / "manifest.json").read_text())
    if (manifest.get("schema_version") != 1 or
            manifest.get("component") != "QEMU Mesa private LLVM 10.0.0" or
            manifest.get("product") != product or manifest.get("arch") != PRODUCTS[product][0]):
        raise ValueError("LLVM artifact component, product or architecture mismatch")
    if manifest.get("runtime_gate_passed") is not False:
        raise ValueError("a dependency manifest cannot claim packaged runtime validation")
    for name, value in expected.items():
        if manifest.get(name) != value:
            raise ValueError(f"LLVM artifact identity mismatch: {name}")
    files = manifest["files"]
    required = {
        "lib/libllvm.a", "include/llvm-c/Core.h", "include/llvm-c/ExecutionEngine.h",
        "include/llvm/IR/IRBuilder.h", "include/llvm/ExecutionEngine/MCJIT.h",
        "include/llvm/Config/llvm-config.h", "include/llvm/Config/config.h",
    }
    if not required <= set(files):
        raise ValueError("LLVM artifact is missing its complete consumer headers")
    for name, entry in files.items():
        relative = PurePosixPath(name)
        if (relative.is_absolute() or ".." in relative.parts or
                relative.as_posix() != name or
                not (name == "lib/libllvm.a" or name.startswith("include/"))):
            raise ValueError("invalid LLVM artifact file path")
        path = root / name
        if (path.is_symlink() or
                any((root / parent).is_symlink() for parent in relative.parents) or
                not path.is_file() or path.stat().st_size != entry["size"] or
                digest(path) != entry["sha256"]):
            raise ValueError(f"LLVM artifact content mismatch: {name}")
    if inventory(root) != files:
        raise ValueError("LLVM artifact contains unrecorded consumer files")
    objects = archive_machines(root / "lib/libllvm.a")
    if objects != manifest["archive"] or objects["machines"] != [PRODUCTS[product][1]]:
        raise ValueError("LLVM archive contains objects for the wrong architecture")
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path)
    parser.add_argument("--product", choices=PRODUCTS)
    parser.add_argument("--recipe-hash", action="store_true")
    args = parser.parse_args()
    if args.recipe_hash:
        print(expected_identity()["recipe_sha256"])
        return
    if args.artifact_root is None or args.product is None:
        parser.error("--artifact-root and --product are required")
    result = validate(args.artifact_root, args.product)
    print(json.dumps({"status": "verified_dependency_only", "product": args.product,
                      "recipe_sha256": result["recipe_sha256"]}))


if __name__ == "__main__":
    main()
