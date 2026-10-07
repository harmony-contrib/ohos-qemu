#!/usr/bin/env python3
"""Compile the candidate VDI with real product flags/headers, without rebuilding.

Source/output volumes stay read-only; only a temporary object/dependency file
and optional evidence are written. Not a guest/first-package validation gate.
"""
import argparse
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--product", choices=("arm64_virt", "armv7a_virt", "x86_64_virt"), required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.source_root.resolve()
    cwd = root / "out" / args.product
    target = "obj/vendor/ohemu/virt/hals/vibrator/libhdi_product_vibrator_impl/qemu_virtual_vibrator.o"
    commands = subprocess.run([
        str(root / "prebuilts/build-tools/linux-x86/bin/ninja"), "-w", "dupbuild=warn",
        "-C", str(cwd), "-t", "commands", target,
    ], text=True, capture_output=True, check=True)
    command = shlex.split(commands.stdout.splitlines()[-1])
    if Path(command[0]).name == "ccache":
        command.pop(0)
    if Path(command[0]).name != "clang++" or any(token in command for token in ("&&", ";", "|")):
        raise ValueError("expected a single product clang++ command")
    source_index = command.index("-c") + 1
    if (cwd / command[source_index]).resolve() != root / "vendor/ohemu/virt/hals/vibrator/qemu_virtual_vibrator.cpp":
        raise ValueError("unexpected VDI source")
    candidate = args.candidate.resolve()
    with tempfile.TemporaryDirectory(prefix="qemu-vibrator-compile-") as temp:
        staged = Path(temp)
        generated = {}
        if not (cwd / "gen/drivers/interface/vibrator/v2_0/ivibrator_interface.h").is_file():
            # Old product outputs may have been pruned. Generate from this
            # checkout's actual IDL, never borrow another architecture's tree.
            idl = cwd / "clang_x64/ability/idl_tool/idl"
            gen = staged / "gen/drivers/interface"
            # The upstream IDL tool insists on W_OK even for its input files.
            # Copy only this interface into scratch; keep the source RO.
            inputs = staged / "drivers/interface"
            shutil.copytree(root / "drivers/interface/vibrator/v2_0", inputs / "vibrator/v2_0")
            idl_command = [str(idl), "--intf-type", "hdi", "--system", "full", "--mode", "ipc",
                           "-d", str(gen), "--gen-cpp"]
            for name in ("IVibratorInterface.idl", "VibratorTypes.idl", "IVibratorPlugCallback.idl"):
                idl_command += ["-c", str(inputs / "vibrator/v2_0" / name)]
            idl_command += ["-r", "ohos.hdi:" + str(inputs)]
            subprocess.run(idl_command, check=True)
            command[1:1] = ["-I" + str(gen), "-I" + str(gen / "vibrator")]
            generated = {str(path.relative_to(gen)): hashlib.sha256(path.read_bytes()).hexdigest()
                         for path in sorted(gen.rglob("*.h"))}
            if not generated:
                raise ValueError("IDL did not generate any HDI headers")
        command[command.index("-c") + 1] = str(candidate)
        command[command.index("-o") + 1] = str(staged / "vibrator.o")
        command[command.index("-MF") + 1] = str(staged / "vibrator.d")
        subprocess.run(command, cwd=cwd, check=True)
        result = {
            "product": args.product,
            "status": "pass",
            "scope": "compile_only_not_runtime",
            "source_sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
            "object_sha256": hashlib.sha256((staged / "vibrator.o").read_bytes()).hexdigest(),
            "compiler_args_sha256": hashlib.sha256(json.dumps(command).encode()).hexdigest(),
            "generated_headers": generated,
        }
    content = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content)
    print(content, end="")


if __name__ == "__main__":
    main()
