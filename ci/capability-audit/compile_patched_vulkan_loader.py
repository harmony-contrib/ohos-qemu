#!/usr/bin/env python3
"""Compile a patched loader translation unit with the product's actual flags.

Copies only vulkan-loader to a temporary tree. The checkout, Ninja graph and
product output are read-only; the running image build is never mutated.
This compile-only check is not a runtime/first-artifact validation gate.
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
    parser.add_argument("--patch", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.source_root.resolve()
    cwd = root / "out" / args.product
    target = "obj/third_party/vulkan-loader/loader/vulkan_loader/wsi.o"
    commands = subprocess.run([
        str(root / "prebuilts/build-tools/linux-x86/bin/ninja"), "-w", "dupbuild=warn",
        "-C", str(cwd), "-t", "commands", target,
    ], text=True, capture_output=True, check=True)
    command = shlex.split(commands.stdout.splitlines()[-1])
    if Path(command[0]).name == "ccache":
        command.pop(0)
    if Path(command[0]).name != "clang":
        raise ValueError("expected a single clang command, not an opaque shell command")
    source_index = command.index("-c") + 1
    if (cwd / command[source_index]).resolve() != root / "third_party/vulkan-loader/loader/wsi.c":
        raise ValueError("unexpected compile source")
    patch = args.patch.resolve()
    with tempfile.TemporaryDirectory(prefix="qemu-vulkan-loader-compile-") as temp:
        staged = Path(temp)
        component = staged / "third_party/vulkan-loader"
        shutil.copytree(root / "third_party/vulkan-loader", component,
                        symlinks=True, ignore=shutil.ignore_patterns(".git"))
        check = subprocess.run(["git", "-C", str(staged), "apply", "--check", str(patch)],
                               capture_output=True)
        if check.returncode == 0:
            subprocess.run(["git", "-C", str(staged), "apply", str(patch)], check=True)
        else:
            # The active representative build may already contain this exact
            # component. Verify it rather than double-applying or silently
            # compiling an unrelated source layout. Only scratch is inspected.
            subprocess.run(["git", "-C", str(staged), "apply", "--reverse", "--check", str(patch)],
                           check=True, capture_output=True)
        command[source_index] = str(component / "loader/wsi.c")
        command[command.index("-o") + 1] = str(staged / "wsi.o")
        command[command.index("-MF") + 1] = str(staged / "wsi.d")
        # Override component-local include directories, retaining all other
        # generated/product/system headers from the real output tree.
        for index, argument in enumerate(command):
            if argument.startswith("-I../../third_party/vulkan-loader/"):
                suffix = argument.removeprefix("-I../../third_party/vulkan-loader/")
                command[index] = "-I" + str(component / suffix)
        subprocess.run(command, cwd=cwd, check=True)
        result = {
            "product": args.product,
            "status": "pass",
            "scope": "compile_only_not_runtime",
            "patch_sha256": hashlib.sha256(patch.read_bytes()).hexdigest(),
            "object_sha256": hashlib.sha256((staged / "wsi.o").read_bytes()).hexdigest(),
            "compiler_args_sha256": hashlib.sha256(json.dumps(command).encode()).hexdigest(),
        }
    text = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    print(text, end="")


if __name__ == "__main__":
    main()
