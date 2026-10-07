#!/usr/bin/env python3
"""Build a read-only permission registry probe from the current source innerkit."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--arch", choices=("arm64", "armv7a", "x86_64"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    target, product, innerkit = {
        "arm64": ("aarch64-linux-ohos", "arm64_virt", "ohos-arm64"),
        "armv7a": ("arm-linux-ohos", "armv7a_virt", "ohos-arm"),
        "x86_64": ("x86_64-linux-ohos", "x86_64_virt", "ohos-x86_64"),
    }[args.arch]
    root = args.source_root
    # Innerkits use libc++'s system __h ABI, not the public NDK __n1 ABI.
    # Compile with the actual system toolchain/sysroot instead of changing the
    # ABI namespace or passing a hand-written PermissionDef across a DSO.
    compiler = root / "prebuilts/clang/ohos/linux-x86_64/llvm"
    sysroot = root / "out" / product / "obj/third_party/musl"
    includes = root / "base/security/access_token/interfaces/innerkits/accesstoken/include"
    library = root / "out" / product / "security/access_token/libaccesstoken_sdk.z.so"
    if not library.is_file():
        raise SystemExit(f"compile the {product} AccessToken SDK before building this probe")
    args.output.mkdir(parents=True, exist_ok=True)
    probe = Path(__file__).parent / "probes/permission_registry.cpp"
    command = [str(compiler / "bin/clang++"), f"--target={target}", f"--sysroot={sysroot}",
               "-std=c++17", "-O2", "-g", "-Wall", "-Wextra", "-Werror", "-fno-exceptions", "-fno-rtti",
               f"-I{includes}", f"-I{root / 'out' / product / 'innerkits' / innerkit / 'c_utils/utils/include'}",
               str(probe), str(library), f"-L{compiler / 'lib' / target}",
               "-Wl,--allow-shlib-undefined", "-o", str(args.output / "permission_registry")]
    if args.arch == "armv7a":
        command[1:1] = ["-march=armv7-a", "-mfloat-abi=softfp", "-mfpu=neon"]
    subprocess.run(command, check=True)
    source = root / "base/security/access_token/services/accesstokenmanager/permission_definitions.json"
    names = sorted(row["name"] for row in json.loads(source.read_text())["definePermissions"])
    if len(names) != len(set(names)):
        raise SystemExit("duplicate source permission names")
    (args.output / "permission-names.txt").write_text("\n".join(names) + "\n")
    (args.output / "permission-definitions.json").write_bytes(source.read_bytes())
    evidence = {"arch": args.arch, "source_definitions_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "compiled_sdk_sha256": hashlib.sha256(library.read_bytes()).hexdigest(),
                "probe_sha256": hashlib.sha256((args.output / "permission_registry").read_bytes()).hexdigest(),
                "source_permission_count": len(names), "command": command, "runtime_validated": False}
    (args.output / "build.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
