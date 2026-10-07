#!/usr/bin/env python3
"""Check the complete packaged ArkWeb HAP ABI, not JSVM or Web runtime behavior."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import struct
import subprocess
import tempfile
import zipfile
from verify_alsa_config_image import debugfs_path, file_sha256
from ext_image_entries import dump_unique_file

ARCHES = {"armv7a": ("armeabi-v7a", 1, 40), "arm64": ("arm64-v8a", 2, 183),
          "x86_64": ("x86_64", 2, 62)}
REQUIRED_LIBRARIES = {"libadapter_ndk_stub.so", "libarkweb_engine.so", "libarkweb_render.so",
                      "libarkweb_crashpad_handler.so", "libffmpeg.so"}
REQUIRED_RESOURCES = {"resources/rawfile/icudtl.dat", "resources/rawfile/resources.pak",
                      "resources/rawfile/chrome_100_percent.pak", "resources/rawfile/snapshot_blob.bin",
                      "resources/rawfile/locales/en-US.pak", "resources.index", "ets/modules.abc"}
MAX_ENTRY_SIZE = 1024 * 1024 * 1024
MAX_TOTAL_SIZE = 2 * MAX_ENTRY_SIZE


def verify_hap(path, arch):
    abi, elf_class, machine = ARCHES[arch]
    prefix = "libs/" + abi + "/"
    with zipfile.ZipFile(path) as archive:
        entries = archive.infolist()
        names = [entry.filename for entry in entries]
        if len(names) != len(set(names)):
            raise ValueError("duplicate ArkWeb HAP entries")
        if (sum(entry.file_size for entry in entries) > MAX_TOTAL_SIZE or
                any(entry.file_size > MAX_ENTRY_SIZE or entry.flag_bits & 1 for entry in entries)):
            raise ValueError("oversized/encrypted ArkWeb HAP entry")
        for name in names:
            parsed = PurePosixPath(name)
            if parsed.is_absolute() or ".." in parsed.parts or "\\" in name:
                raise ValueError("unsafe ArkWeb HAP entry")
        required = REQUIRED_RESOURCES | {prefix + name for name in REQUIRED_LIBRARIES} | {"module.json"}
        if not required <= set(names):
            raise ValueError("ArkWeb HAP is incomplete for " + arch + ": " + ", ".join(sorted(required - set(names))))
        for name in required:
            if not archive.getinfo(name).file_size:
                raise ValueError("empty ArkWeb runtime entry: " + name)
        module_entry = archive.getinfo("module.json")
        if module_entry.file_size > 1024 * 1024:
            raise ValueError("oversized ArkWeb module metadata")
        module = json.loads(archive.read("module.json"))
        if module.get("app", {}).get("bundleName") != "com.ohos.arkwebcore":
            raise ValueError("wrong ArkWeb engine bundle")
        records = {}
        for name in sorted(name for name in names if name.startswith(prefix) and name.endswith(".so")):
            content = archive.read(name)
            if (len(content) < 64 or content[:7] != b"\x7fELF" + bytes((elf_class, 1, 1)) or
                    struct.unpack_from("<H", content, 16)[0] != 3 or
                    struct.unpack_from("<H", content, 18)[0] != machine):
                raise ValueError("ArkWeb native library has wrong actual ELF ABI: " + name)
            records[name] = {"sha256": hashlib.sha256(content).hexdigest(), "size": len(content),
                             "elf_class": elf_class, "elf_machine": machine}
        return {"abi": abi, "bundle_name": "com.ohos.arkwebcore", "native_libraries": records,
                "hap_sha256": file_sha256(path), "version_name": module.get("app", {}).get("versionName")}


def verify_image(image, arch, executable, packaged_source_core=None):
    with tempfile.TemporaryDirectory(prefix="qemu-arkweb-core-image-") as directory:
        target, identity = dump_unique_file(image, ("/app/com.ohos.arkwebcore/ArkWebCore.hap",
                                                   "/system/app/com.ohos.arkwebcore/ArkWebCore.hap"),
                                            directory, executable)
        observed = {**identity, **verify_hap(target, arch)}
        if packaged_source_core:
            from m144_core_artifacts import validate
            source_arch = {"armv7a": "arm", "arm64": "arm64", "x86_64": "x86_64"}[arch]
            source = validate(packaged_source_core, source_arch, Path(__file__).resolve().parents[1],
                              hap_override=target)
            observed.update(m144_source_provenance_validated=True,
                            core_artifact_sha256=source["core_artifact_sha256"],
                            release_source_lock_sha256=source["release_source_lock_sha256"])
        return observed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--system-image", type=Path)
    source.add_argument("--hap", type=Path)
    parser.add_argument("--arch", choices=tuple(ARCHES), required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--source-artifact-root", type=Path)
    parser.add_argument("--packaged-source-core", type=Path)
    args = parser.parse_args()
    result = {"status": "fail", "arch": args.arch,
              "scope": "offline complete ArkWebCore HAP native ABI/resources only",
              "first_artifact_behavior_gate_passed": False, "arkweb_behavior_validated": False,
              "m144_source_provenance_validated": False, "failures": []}
    try:
        path = args.system_image or args.hap
        before = path.stat()
        result["input_sha256"] = file_sha256(path)
        if args.packaged_source_core and (not args.system_image or args.source_artifact_root):
            raise ValueError("packaged source provenance requires a system image and no external core artifact root")
        result.update(verify_image(path, args.arch, debugfs_path(), args.packaged_source_core)
                      if args.system_image else verify_hap(path, args.arch))
        if args.source_artifact_root:
            # Delayed import avoids a cycle in the dependency verifier.
            from m144_core_artifacts import validate
            source_arch = {"armv7a": "arm", "arm64": "arm64", "x86_64": "x86_64"}[args.arch]
            source = validate(args.source_artifact_root / source_arch, source_arch,
                              Path(__file__).resolve().parents[1])
            if (result["hap_sha256"] != source["hap_sha256"] or
                    result["native_libraries"] != source["native_libraries"]):
                raise ValueError("packaged image does not contain the verified source-built exact-ABI core")
            result.update(m144_source_provenance_validated=True,
                          core_artifact_sha256=source["core_artifact_sha256"],
                          release_source_lock_sha256=source["release_source_lock_sha256"])
        after = path.stat()
        if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
            raise ValueError("ArkWeb input changed during verification")
        result["status"] = "pass"
    except (OSError, ValueError, KeyError, TypeError, struct.error, zipfile.BadZipFile,
            subprocess.SubprocessError) as error:
        result["failures"].append(str(error))
    if args.output:
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "arch": args.arch, "failures": result["failures"]}))
    return 0 if result["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
