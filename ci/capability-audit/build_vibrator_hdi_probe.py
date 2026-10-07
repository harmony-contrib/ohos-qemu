#!/usr/bin/env python3
"""Build a root HDI runtime probe with real system ABI/headers (not NDK ABI)."""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--arch", choices=("arm64", "armv7a", "x86_64"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.source_root.resolve()
    product = {"arm64": "arm64_virt", "armv7a": "armv7a_virt", "x86_64": "x86_64_virt"}[args.arch]
    cwd = root / "out" / product
    commands = subprocess.run([str(root / "prebuilts/build-tools/linux-x86/bin/ninja"), "-w", "dupbuild=warn",
        "-C", str(cwd), "-t", "commands",
        "obj/vendor/ohemu/virt/hals/vibrator/libhdi_product_vibrator_impl/qemu_virtual_vibrator.o"],
        check=True, capture_output=True, text=True)
    command = shlex.split(commands.stdout.splitlines()[-1])
    if Path(command[0]).name == "ccache":
        command.pop(0)
    if Path(command[0]).name != "clang++":
        raise ValueError("expected one actual system compiler command")
    for flag in ("-MF", "-o", "-c"):
        index = command.index(flag)
        del command[index:index + 2]
    command.remove("-MMD")
    probe = Path(__file__).resolve().parent / "probes/vibrator_hdi.cpp"
    libraries = [cwd / "hdf/drivers_interface_vibrator/libvibrator_proxy_2.0.z.so",
                 cwd / "commonlibrary/c_utils/libutils.z.so"]
    for library in libraries:
        if not library.is_file():
            raise ValueError(f"build the actual {product} proxy/runtime before this probe: {library}")
    args.output.mkdir(parents=True, exist_ok=True)
    binary = args.output.resolve() / "vibrator_hdi"
    command += [str(probe), *map(str, libraries), "-Wl,--allow-shlib-undefined", "-o", str(binary)]
    subprocess.run(command, cwd=cwd, check=True)
    evidence = {"arch": args.arch, "scope": "compile_only_not_guest",
                "source_sha256": hashlib.sha256(probe.read_bytes()).hexdigest(),
                "probe_sha256": hashlib.sha256(binary.read_bytes()).hexdigest(), "command": command,
                "libraries": {str(path): hashlib.sha256(path.read_bytes()).hexdigest() for path in libraries}}
    (args.output / "build.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
