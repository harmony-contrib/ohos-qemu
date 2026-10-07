#!/usr/bin/env python3
"""Compile AppSpawn capability repairs with each product's system ABI.

Only scratch copies/objects and optional evidence are written. This does not
change the source/Ninja/output volumes or validate an app in a new guest.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--product", choices=("arm64_virt", "armv7a_virt", "x86_64_virt"), required=True)
    parser.add_argument("--patch", type=Path, required=True)
    parser.add_argument("--kind", choices=("userid", "renderer_termination"), default="userid")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.source_root.resolve()
    cwd = root / "out" / args.product
    relative = Path("base/startup/appspawn")
    if args.kind == "userid":
        source = relative / "modules/common/appspawn_common.c"
        target = "obj/base/startup/appspawn/modules/common/appspawn_common/appspawn_common.o"
        compiler = "clang"
    else:
        source = relative / "modules/nweb_adapter/nwebspawn_adapter.cpp"
        target = "obj/base/startup/appspawn/modules/nweb_adapter/appspawn_nweb/nwebspawn_adapter.o"
        compiler = "clang++"
    commands = subprocess.run([
        str(root / "prebuilts/build-tools/linux-x86/bin/ninja"), "-w", "dupbuild=warn",
        "-C", str(cwd), "-t", "commands", target,
    ], text=True, capture_output=True, check=True)
    command = shlex.split(commands.stdout.splitlines()[-1])
    if Path(command[0]).name == "ccache":
        command.pop(0)
    if Path(command[0]).name != compiler or any(token in command for token in ("&&", ";", "|")):
        raise ValueError("expected a single product compiler command")
    source_index = command.index("-c") + 1
    if (cwd / command[source_index]).resolve() != root / source:
        raise ValueError("unexpected AppSpawn compile source")
    patch = args.patch.resolve()
    with tempfile.TemporaryDirectory(prefix="qemu-appspawn-userid-compile-") as temp:
        staged = Path(temp)
        shutil.copytree(root / relative, staged / relative,
                        symlinks=True, ignore=shutil.ignore_patterns(".git"))
        subprocess.run(["git", "-C", str(staged), "apply", str(patch)], check=True)
        candidate = staged / source
        command[source_index] = str(candidate)
        object_path = staged / (source.stem + ".o")
        command[command.index("-o") + 1] = str(object_path)
        command[command.index("-MF") + 1] = str(staged / (source.stem + ".d"))
        for index, argument in enumerate(command):
            if argument.startswith("-I../../base/startup/appspawn/"):
                suffix = argument.removeprefix("-I../../base/startup/appspawn/")
                command[index] = "-I" + str(staged / relative / suffix)
        subprocess.run(command, cwd=cwd, check=True)
        nm = (cwd / command[0]).resolve().with_name("llvm-nm")
        symbols = subprocess.run([str(nm), str(object_path)],
                                 text=True, capture_output=True, check=True).stdout
        if args.kind == "userid" and not re.search(r"^\S+\s+T\s+SetUserId$", symbols, re.MULTILINE):
            raise ValueError("common AppSpawn object does not provide a strong SetUserId")
        if args.kind == "renderer_termination":
            for symbol in ("sigaction", "sigemptyset", "_exit", "getpid"):
                if not re.search(r"^\s+U\s+" + symbol + r"$", symbols, re.MULTILINE):
                    raise ValueError("renderer object does not reference " + symbol)
        result = {
            "product": args.product, "kind": args.kind, "status": "pass", "scope": "compile_only_not_runtime",
            "patch_sha256": hashlib.sha256(patch.read_bytes()).hexdigest(),
            "source_sha256": hashlib.sha256(candidate.read_bytes()).hexdigest(),
            "object_sha256": hashlib.sha256(object_path.read_bytes()).hexdigest(),
            "compiler_args_sha256": hashlib.sha256(json.dumps(command).encode()).hexdigest(),
            "strong_set_user_id": args.kind == "userid",
        }
    content = json.dumps(result, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content)
    print(content, end="")


if __name__ == "__main__":
    main()
