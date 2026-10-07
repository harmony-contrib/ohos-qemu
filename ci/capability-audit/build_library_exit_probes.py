#!/usr/bin/env python3
"""Build empty-main link-order regressions; never replace guest system DSOs."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess

CASES = {
    "empty": (), "udmf": ("udmf",), "pasteboard": ("pasteboard",),
    "avplayer": ("avplayer",), "udmf-pasteboard": ("udmf", "pasteboard"),
    "pasteboard-udmf": ("pasteboard", "udmf"),
    "avplayer-udmf": ("avplayer", "udmf"), "udmf-avplayer": ("udmf", "avplayer"),
}
ARCHES = {"arm64": ("aarch64-linux-ohos", 2, 183, []),
          "armv7a": ("arm-linux-ohos", 1, 40,
                     ["-march=armv7-a", "-mfloat-abi=softfp", "-mfpu=neon"]),
          "x86_64": ("x86_64-linux-ohos", 2, 62, [])}


def build(sdk, output, arches):
    output.mkdir(parents=True, exist_ok=False)
    source = Path(__file__).parent / "probes/library_exit.c"
    clang = sdk / "llvm/bin/clang"
    readelf = sdk / "llvm/bin/llvm-readelf"
    records = {}
    for arch in arches:
        target, elf_class, machine, flags = ARCHES[arch]
        directory = output / arch
        directory.mkdir()
        for case, libraries in CASES.items():
            executable = directory / case
            command = [str(clang), "--target=" + target,
                       "--sysroot=" + str(sdk / "sysroot"), *flags,
                       "-O0", "-g", "-Wall", "-Wextra", "-Werror",
                       str(source), "-Wl,--no-as-needed", *["-l" + lib for lib in libraries],
                       "-o", str(executable)]
            subprocess.run(command, check=True)
            content = executable.read_bytes()
            if (content[:7] != b"\x7fELF" + bytes((elf_class, 1, 1)) or
                    struct.unpack_from("<H", content, 18)[0] != machine):
                raise ValueError("wrong ELF architecture: " + str(executable))
            dynamic = subprocess.check_output([str(readelf), "-d", str(executable)], text=True)
            needed = re.findall(r"\(NEEDED\).*?\[(.*?)\]", dynamic)
            if [lib for lib in needed if lib in ("libudmf.so", "libpasteboard.so", "libavplayer.so")] != [
                    "lib" + lib + ".so" for lib in libraries]:
                raise ValueError("linker dropped or reordered tested DSOs: " + str(executable))
            records[arch + "/" + case] = {
                "sha256": hashlib.sha256(content).hexdigest(), "needed": needed,
                "link_order": list(libraries), "command": command,
                "elf_class": elf_class, "elf_machine": machine}
    manifest = {"schema_version": 1, "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "scope": "empty_main_exit_cleanup_only_not_public_api_or_full_package_gate",
                "artifacts": records}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--arch", action="append", choices=tuple(ARCHES), required=True)
    args = parser.parse_args()
    build(args.sdk.resolve(), args.output.resolve(), args.arch)
