#!/usr/bin/env python3
"""Reject duplicate SyncFence globals in linked/packaged graphic libraries."""
import argparse
import json
from pathlib import Path
import struct
import subprocess
import tempfile

from verify_alsa_config_image import debugfs_path, file_sha256
from verify_runtime_elf_contract import read_elf, verify_machine
from ext_image_entries import dump_unique_file

ARCHES = {"armv7a": (1, 40), "arm64": (2, 183), "x86_64": (2, 62)}
GLOBAL = "_ZN4OHOS9SyncFence13INVALID_FENCEE"
NATIVE_APIS = {"OH_NativeFence_Wait", "OH_NativeFence_WaitForever", "OH_NativeFence_IsValid", "OH_NativeFence_Close"}
FENCE_SYMBOL_PREFIXES = ("_ZN4OHOS9SyncFence", "_ZNK4OHOS9SyncFence", "_ZTVN4OHOS9SyncFence",
                         "_ZTIN4OHOS9SyncFence", "_ZTSN4OHOS9SyncFence")


def needed_libraries(path):
    data = path.read_bytes()
    if len(data) < 64 or data[:4] != b"\x7fELF" or data[5] != 1:
        raise ValueError("dynamic dependency check requires little-endian ELF")
    if data[4] == 2:
        offset = struct.unpack_from("<Q", data, 40)[0]
        size, count = struct.unpack_from("<HH", data, 58)
        fmt, dynamic_fmt = "<IIQQQQIIQQ", "<qQ"
    elif data[4] == 1:
        offset = struct.unpack_from("<I", data, 32)[0]
        size, count = struct.unpack_from("<HH", data, 46)
        fmt, dynamic_fmt = "<IIIIIIIIII", "<iI"
    else:
        raise ValueError("unsupported ELF class")
    if size < struct.calcsize(fmt) or not count or offset + size * count > len(data):
        raise ValueError("missing/truncated ELF section table")
    sections = [struct.unpack_from(fmt, data, offset + size * index) for index in range(count)]
    dependencies = set()
    dynamic_count = 0
    for section in sections:
        if section[1] != 6:
            continue
        dynamic_count += 1
        begin, length, strings_index, entry_size = section[4], section[5], section[6], section[9]
        if (strings_index >= count or entry_size != struct.calcsize(dynamic_fmt)
                or length % entry_size or begin + length > len(data)):
            raise ValueError("invalid dynamic section")
        strings_section = sections[strings_index]
        start, string_length = strings_section[4], strings_section[5]
        if strings_section[1] != 3 or start + string_length > len(data):
            raise ValueError("invalid dynamic string table")
        strings = data[start:start + string_length]
        terminated = False
        for position in range(begin, begin + length, entry_size):
            tag, value = struct.unpack_from(dynamic_fmt, data, position)
            if tag == 0:
                terminated = True
                break
            if tag == 1:
                end = strings.find(b"\0", value)
                if value >= len(strings) or end < 0:
                    raise ValueError("invalid DT_NEEDED string")
                dependencies.add(strings[value:end].decode("ascii"))
        if not terminated:
            raise ValueError("unterminated dynamic section")
    if dynamic_count != 1:
        raise ValueError("ELF must contain one dynamic dependency section")
    return dependencies


def verify_pair(surface, fence, arch):
    elf_class, machine = ARCHES[arch]
    records = {}
    symbols = {}
    for name, path in (("surface", surface), ("fence", fence)):
        header = path.read_bytes()[:64]
        if header[:7] != b"\x7fELF" + bytes((elf_class, 1, 1)) or struct.unpack_from("<H", header, 16)[0] != 3:
            raise ValueError("wrong shared library ELF class/type: " + name)
        info = read_elf(path)
        symbols[name] = info
        verify_machine(info, machine, path)
        dependencies = needed_libraries(path)
        records[name] = {"sha256": file_sha256(path), "elf_machine": machine,
                         "DT_NEEDED": sorted(dependencies)}
        if name == "surface":
            if any(symbol.startswith(FENCE_SYMBOL_PREFIXES) for symbol in info.defined):
                raise ValueError("libsurface embeds a duplicate SyncFence implementation/global")
            if GLOBAL not in info.undefined or "libsync_fence.z.so" not in dependencies:
                raise ValueError("libsurface does not consume the shared SyncFence owner")
        elif not ({GLOBAL} | NATIVE_APIS) <= info.defined:
            raise ValueError("shared SyncFence provider lacks its global or Native Fence API exports")
    imports = {symbol for symbol in symbols["surface"].undefined if symbol.startswith(FENCE_SYMBOL_PREFIXES)}
    missing = imports - symbols["fence"].defined
    if missing:
        raise ValueError("shared SyncFence provider lacks imported surface ABI: " + ", ".join(sorted(missing)))
    records["surface"]["shared_fence_imports"] = sorted(imports)
    return records


def verify_pixelmap(pixelmap, fence, arch):
    elf_class, machine = ARCHES[arch]
    header = pixelmap.read_bytes()[:64]
    if header[:7] != b"\x7fELF" + bytes((elf_class, 1, 1)) or struct.unpack_from("<H", header, 16)[0] != 3:
        raise ValueError("wrong Pixelmap shared library ELF class/type")
    consumer, provider = read_elf(pixelmap), read_elf(fence)
    verify_machine(consumer, machine, pixelmap)
    dependencies = needed_libraries(pixelmap)
    if "OH_PixelmapNative_CreatePixelmap" not in consumer.defined:
        raise ValueError("Pixelmap native API provider is missing")
    imports = {symbol for symbol in consumer.undefined if symbol.startswith(FENCE_SYMBOL_PREFIXES)}
    if not imports or "libsync_fence.z.so" not in dependencies or imports - provider.defined:
        raise ValueError("Pixelmap must directly consume the matching shared SyncFence provider")
    return {"sha256": file_sha256(pixelmap), "elf_machine": machine,
            "DT_NEEDED": sorted(dependencies), "shared_fence_imports": sorted(imports)}


def verify_image(image, arch):
    abi = "lib" if arch == "armv7a" else "lib64"
    with tempfile.TemporaryDirectory(prefix="qemu-shared-fence-") as directory:
        libraries = []
        for name, subdir in (("libsurface.z.so", "chipset-sdk-sp"), ("libsync_fence.z.so", "ndk")):
            target_directory = Path(directory) / name
            target_directory.mkdir()
            candidates = tuple(f"{prefix}/{abi}/{subdir}/{name}" for prefix in ("", "/system"))
            libraries.append(dump_unique_file(image, candidates, target_directory, debugfs_path()))
        result = verify_pair(libraries[0][0], libraries[1][0], arch)
        for name, (_, identity) in zip(("surface", "fence"), libraries):
            result[name].update(identity)
        pixelmap_directory = Path(directory) / "pixelmap"
        pixelmap_directory.mkdir()
        pixelmap, identity = dump_unique_file(image, tuple(f"{prefix}/{abi}/ndk/libpixelmap.so"
                                                          for prefix in ("", "/system")),
                                             pixelmap_directory, debugfs_path())
        result["pixelmap"] = {**verify_pixelmap(pixelmap, libraries[1][0], arch), **identity}
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--system-image", type=Path)
    parser.add_argument("--surface", type=Path)
    parser.add_argument("--fence", type=Path)
    parser.add_argument("--pixelmap", type=Path,
                        help="add actual relinked NDK Pixelmap consumer verification to a library-pair check")
    parser.add_argument("--arch", choices=tuple(ARCHES), required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if bool(args.system_image) == bool(args.surface or args.fence) or (not args.system_image and not (args.surface and args.fence)):
        parser.error("provide --system-image, or both --surface and --fence")
    if args.system_image and args.pixelmap:
        parser.error("system-image verification reads its own Pixelmap provider")
    result = {"status": "fail", "arch": args.arch, "scope": "offline actual shared SyncFence ownership/ABI only",
              "first_artifact_behavior_gate_passed": False, "library_exit_behavior_validated": False, "failures": []}
    try:
        if args.system_image:
            before = args.system_image.stat()
            result["system_image_sha256"] = file_sha256(args.system_image)
            result["libraries"] = verify_image(args.system_image, args.arch)
            after = args.system_image.stat()
            if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
                raise ValueError("system image changed during verification")
        else:
            result["libraries"] = verify_pair(args.surface, args.fence, args.arch)
            if args.pixelmap:
                result["libraries"]["pixelmap"] = verify_pixelmap(args.pixelmap, args.fence, args.arch)
        result["status"] = "pass"
    except (OSError, ValueError, struct.error, UnicodeError, subprocess.SubprocessError) as error:
        result["failures"].append(str(error))
    if args.output:
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "arch": args.arch, "failures": result["failures"]}))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
