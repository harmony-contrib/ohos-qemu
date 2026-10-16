#!/usr/bin/env python3
"""One bounded real OHOS/CFI consumer build and QEMU-user invocation.

Run only in the explicitly leased private container. /ohos and /r52 must be
read-only; all generated headers, libraries and output remain under --output.
No replacement runtime, GNSS interface, system parameter or IPC implementation
is provided. A loader/runtime failure is retained as a failure.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import secrets
import shlex
import shutil
import socket
import stat
import struct
import subprocess
import threading
import time


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + "\n")


def run(argv, log, *, cwd, env=None):
    started = time.time()
    with Path(log).open("wb") as stream:
        try:
            result = subprocess.run(argv, cwd=cwd, env=env, stdout=stream,
                                    stderr=subprocess.STDOUT, timeout=120)
            code = result.returncode
        except subprocess.TimeoutExpired:
            code = 124
    record = {"argv": [str(x) for x in argv], "cwd": str(cwd), "exit_code": code,
              "started_unix": started, "elapsed_seconds": time.time() - started,
              "log": str(log), "log_sha256": sha(log)}
    save(str(log) + ".json", record)
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source", type=Path, default=Path("/ohos"))
    parser.add_argument("--r52", type=Path, default=Path("/r52"))
    parser.add_argument("--repository", type=Path, default=Path("/frozen"))
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if (output / "result.json").exists():
        raise SystemExit("refusing to overwrite an existing attempt")
    result = {"status": "incomplete", "scope": "actual_ohos_qemu_user_public_vendor_abi_cfi",
              "first_artifact_behavior_gate_passed": False, "requirements_closed": 0,
              "commands": [], "source_hashes": {}, "runtime": []}
    save(output / "result.json", result)
    source = args.source.resolve()
    out = source / "out/arm64_virt"
    r52 = args.r52.resolve()
    compiler_root = source / "prebuilts/clang/ohos/linux-x86_64/llvm"
    cxx = compiler_root / "bin/clang++"
    readelf = compiler_root / "bin/llvm-readelf"
    ninja = out / "obj/drivers/peripheral/location/gnss/hdi_service/libgnss_interface_service_2.0.ninja"
    evidence = json.loads((r52 / "evidence.json").read_text())
    result["r52_evidence_sha256"] = sha(r52 / "evidence.json")
    result["target_ninja_sha256"] = sha(ninja)
    if result["target_ninja_sha256"] != evidence["target_ninja_sha256"]:
        raise RuntimeError("actual compile target changed since r52")
    variables = {}
    for line in ninja.read_text().splitlines():
        if " = " in line and not line.startswith(" "):
            key, value = line.split(" = ", 1)
            variables[key] = shlex.split(value)

    # Materialize exactly the patched product headers in a private overlay.
    # All header content comes from the real pinned source and existing patch.
    overlay = output / "headers"
    relative = Path("drivers/peripheral/location/gnss/hdi_service")
    (overlay / relative).mkdir(parents=True)
    component = args.repository / "patches/common/device/qemu/external_gnss"
    manifest = json.loads((component / "manifest.json").read_text())
    for name in ["gnss_interface_impl.cpp", "location_vendor_interface.cpp", "location_vendor_interface.h",
                 "gnss_interface_impl.h", "location_vendor_lib.h"]:
        original = source / relative / name
        result["source_hashes"][str(original)] = sha(original)
        expected = manifest["originals"].get(str(relative / name))
        if expected and sha(original) != expected["before"]:
            raise RuntimeError("source guard: " + str(original))
        shutil.copyfile(original, overlay / relative / name)
    patch = component / "0001-fix-real-gnss-vendor-bridge-lifecycle.patch"
    record = run(["patch", "--batch", "--forward", "-p1", "-i", str(patch)],
                 output / "header-overlay.log", cwd=overlay)
    result["commands"].append(record)
    if record["exit_code"] != 0:
        raise RuntimeError("actual header patch failed")
    for name, guards in manifest["originals"].items():
        if sha(overlay / name) != guards["after"]:
            raise RuntimeError("patched overlay guard: " + name)

    runtime = output / "rootfs/system/lib64"
    runtime.mkdir(parents=True)
    primary = {}
    for link in evidence["links"]:
        binary = r52 / link["name"]
        if sha(binary) != link["binary_sha256"]:
            raise RuntimeError("r52 DSO guard: " + str(binary))
        primary[link["name"]] = binary
        for name, expected in link["library_inputs_sha256"].items():
            path = Path(name) if name.startswith("/") else out / name
            if path.suffix == ".so" and not "/sp/" in name:
                if sha(path) != expected:
                    raise RuntimeError("current real dependency differs from r52: " + str(path))
                primary.setdefault(path.name, path)
    primary["libc++.so"] = compiler_root / "lib/aarch64-linux-ohos/libc++.so"
    # Search only actual runtime directories, never the full build graph.
    search = [out / "packages/phone/system/lib64",
              out / "packages/phone/system/lib64/platformsdk",
              out / "packages/phone/system/lib64/chipset-sdk",
              out / "packages/phone/system/lib64/chipset-sdk-sp",
              out / "packages/phone/system/lib64/ndk",
              out / "packages/phone/vendor/lib64",
              compiler_root / "lib/aarch64-linux-ohos",
              compiler_root / "lib/clang/15.0.4/lib/aarch64-linux-ohos"]

    def inspect(path, name):
        log = output / (name + ".elf.txt")
        record = run([str(readelf), "--file-header", "--program-headers", "--dynamic", "--dyn-syms", str(path)],
                     log, cwd=out)
        result["commands"].append(record)
        if record["exit_code"] != 0:
            raise RuntimeError("ELF inspect: " + str(path))
        txt = log.read_text()
        if "AArch64" not in txt:
            raise RuntimeError("not the actual ARM64 runtime: " + str(path))
        return re.findall(r"\(NEEDED\).*?\[(.*?)\]", txt)

    pending = ["vendorGnssAdapter.so", "libgnss_interface_service_2.0.z.so"]
    seen = set()
    while pending:
        name = pending.pop(0)
        if name in seen:
            continue
        if len(seen) >= 64:
            raise RuntimeError("runtime dependency closure exceeded bounded 64 DSOs")
        seen.add(name)
        path = primary.get(name)
        if path is None:
            path = next((directory / name for directory in search if (directory / name).is_file()), None)
        if path is None:
            result["missing_dependency"] = name
            save(output / "result.json", result)
            raise RuntimeError("no real runtime dependency: " + name)
        needed = inspect(path, name)
        shutil.copyfile(path, runtime / name)
        result["runtime"].append({"name": name, "source": str(path), "sha256": sha(path), "needed": needed})
        pending.extend(needed)
    loader = output / "rootfs/system/bin/ld-musl-aarch64.so.1"
    loader.parent.mkdir(parents=True)
    shutil.copyfile(runtime / "libc.so", loader)
    loader.chmod(0o755)
    result["loader"] = {"source": str(primary["libc.so"]), "sha256": sha(loader)}
    save(output / "runtime-closure.json", result["runtime"])

    # Preserve all product compile flags, CFI blocklists, LTO and trap policy.
    here = Path(__file__).resolve().parent
    consumer = here / "ohos_abi_consumer.cpp"
    flags = variables["defines"] + variables["include_dirs"] + variables["cflags"] + variables["cflags_cc"]
    obj = Path("/tmp/gnss-ohos-abi-consumer.o")
    exe = Path("/tmp/gnss-ohos-abi-consumer")
    record = run([str(cxx), "-I" + str(overlay / relative), *flags, "-MD", "-MF", str(output / "consumer.d"),
                  "-c", str(consumer), "-o", str(obj)], output / "compile.log", cwd=out)
    result["commands"].append(record)
    result["source_hashes"][str(consumer)] = sha(consumer)
    if record["exit_code"] != 0:
        result.update(status="compile_failed", failed_stage="consumer_compile")
        save(output / "result.json", result)
        return 1
    deptext = (output / "consumer.d").read_text().replace("\\\n", " ").split(":", 1)[1]
    for name in shlex.split(deptext):
        path = Path(name) if name.startswith("/") else out / name
        result["source_hashes"][str(path)] = sha(path)

    original = evidence["links"][0]["argv"]
    ldflags = original[2:original.index("-o")]
    ldflags = [x.replace("/work/thinlto-cache", str(output / "thinlto-cache")) for x in ldflags]
    musl = out / "obj/third_party/musl/usr/lib/aarch64-linux-ohos"
    rt = compiler_root / "lib/clang/15.0.4/lib/aarch64-linux-ohos"
    link = [str(cxx), "-pie", *ldflags, "-Wl,--dynamic-linker=/system/bin/ld-musl-aarch64.so.1",
            "-o", str(exe), str(musl / "Scrt1.o"), str(musl / "crti.o"), str(rt / "clang_rt.crtbegin.o"),
            str(obj), str(runtime / "libgnss_interface_service_2.0.z.so"), str(runtime / "libutils.z.so"),
            "-lunwind", "-lc++", str(rt / "libclang_rt.builtins.a"), "-lc",
            str(compiler_root / "lib/aarch64-linux-ohos/libc++abi.a"), str(rt / "libclang_rt.gwp_asan.a"),
            "-ldl", "-lm", str(rt / "libclang_rt.ubsan_minimal.so"),
            str(musl / "crtn.o"), str(rt / "clang_rt.crtend.o")]
    record = run(link, output / "link.log", cwd=out)
    result["commands"].append(record)
    if record["exit_code"] != 0:
        result.update(status="link_failed", failed_stage="consumer_link")
        save(output / "result.json", result)
        return 1
    shutil.copyfile(exe, output / exe.name)
    result["consumer_sha256"] = sha(exe)
    result["consumer_needed"] = inspect(exe, "consumer")
    result["consumer_cfi"] = {"compile": [f for f in flags if any(s in f for s in ["cfi", "lto"])],
                              "link": [f for f in ldflags if any(s in f for s in ["cfi", "lto"])],
                              "defined_check": bool(re.search(r"GLOBAL\s+DEFAULT\s+\d+ __cfi_check", (output / "consumer.elf.txt").read_text()))}
    for dependency in result["consumer_needed"]:
        if dependency not in seen:
            raise RuntimeError("consumer introduced unstaged dependency: " + dependency)

    # Only this container-private directory is created. No host or shared
    # product ownership/permissions are changed, and there is no fake daemon.
    socket_dir = Path("/dev/unix/socket/qemu_gnss")
    if socket_dir.exists():
        info = socket_dir.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 1022 or info.st_gid != 1022 or stat.S_IMODE(info.st_mode) != 0o700:
            raise RuntimeError("refusing incompatible existing private socket directory")
    else:
        socket_dir.mkdir(parents=True)
        os.chown(socket_dir, 1022, 1022)
        socket_dir.chmod(0o700)
    if (socket_dir / "input").exists():
        raise RuntimeError("refusing preexisting endpoint in private test directory")
    latitude = 10 + secrets.randbelow(70000000) / 1000000
    longitude = -170 + secrets.randbelow(340000000) / 1000000
    result["controlled_protocol_challenge"] = {"latitude": latitude, "longitude": longitude,
                                               "kind": "external_test_input_not_real_world_position"}
    qemu = shutil.which("qemu-aarch64-static") or shutil.which("qemu-aarch64")
    if qemu is None:
        raise RuntimeError("no QEMU-user executable in leased image")
    result["qemu_binary"] = {"path": qemu, "sha256": sha(qemu)}
    version = run([qemu, "--version"], output / "qemu-version.log", cwd=output)
    result["commands"].append(version)
    argv = [qemu, "-strace", "-L", str(output / "rootfs"), "-E", "LD_LIBRARY_PATH=" + str(runtime),
            str(exe), repr(latitude), repr(longitude)]
    started = time.time()
    lines = queue.Queue()
    wire = []
    old_frame = None
    previous_nonce = None
    process = None

    def connect_peer():
        peer = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        peer.settimeout(5)
        peer.connect(str(socket_dir / "input"))
        hello = b""
        while len(hello) < 32:
            part = peer.recv(32 - len(hello))
            if not part:
                peer.close()
                raise RuntimeError("actual provider disconnected during hello")
            hello += part
        if hello[:4] != b"QGN1" or struct.unpack_from("<I", hello, 4)[0] != 1:
            peer.close()
            raise RuntimeError("invalid actual provider hello")
        nonce = hello[8:24]
        if nonce == previous_nonce or not any(nonce) or struct.unpack_from("<II", hello, 24) != (88, 0):
            peer.close()
            raise RuntimeError("bad nonce or frame negotiation")
        return peer, hello, nonce

    with (output / "qemu-stderr.log").open("wb") as err, (output / "qemu-stdout.log").open("w") as log:
        process = subprocess.Popen(argv, cwd=output, stdout=subprocess.PIPE, stderr=err,
                                   text=True, bufsize=1)

        def consume():
            for line in process.stdout:
                lines.put(line)
            lines.put(None)

        reader = threading.Thread(target=consume, daemon=True)
        reader.start()
        try:
            while time.time() - started < 120:
                try:
                    line = lines.get(timeout=0.2)
                except queue.Empty:
                    if process.poll() is not None:
                        break
                    continue
                if line is None:
                    break
                log.write(line)
                log.flush()
                if not line.startswith("READY_INPUT generation="):
                    continue
                generation = int(line.strip().split("=")[1])
                rejected = None
                if old_frame is not None:
                    stale_peer, stale_hello, stale_nonce = connect_peer()
                    with stale_peer:
                        stale_peer.sendall(old_frame)
                        if stale_peer.recv(1) != b"":
                            raise RuntimeError("old generation frame was not rejected by disconnect")
                    rejected = {"hello_hex": stale_hello.hex(),
                                "frame_sha256": hashlib.sha256(old_frame).hexdigest(),
                                "peer_eof": True}
                    previous_nonce = stale_nonce
                    time.sleep(0.25)
                peer, hello, nonce = connect_peer()
                with peer:
                    utc = int(time.time() * 1000)
                    frame = struct.pack("<4sI16sQQdddffffII", b"QGF1", 1, nonce, 1, utc,
                                        latitude, longitude, 0, 3.25, 0, 0, 0, 0, 0)
                    peer.sendall(frame)
                    wire.append({"generation": generation, "hello_hex": hello.hex(), "frame_hex": frame.hex(),
                                 "hello_sha256": hashlib.sha256(hello).hexdigest(),
                                 "frame_sha256": hashlib.sha256(frame).hexdigest(),
                                 "old_frame_sent_first": old_frame is not None,
                                 "old_generation_rejection": rejected})
                    old_frame, previous_nonce = frame, nonce
            try:
                code = process.wait(timeout=max(0.1, 120 - (time.time() - started)))
            except subprocess.TimeoutExpired:
                process.kill()
                code = process.wait(timeout=5)
                result["runtime_timeout"] = True
        except Exception as exc:
            result["controller_error"] = repr(exc)
            process.kill()
            code = process.wait(timeout=5)
        reader.join(timeout=1)
    result["commands"].append({"argv": argv, "cwd": str(output), "exit_code": code,
                               "started_unix": started, "elapsed_seconds": time.time() - started,
                               "stdout_sha256": sha(output / "qemu-stdout.log"),
                               "stderr_sha256": sha(output / "qemu-stderr.log")})
    save(output / "wire-inputs.json", wire)
    text = (output / "qemu-stdout.log").read_text()
    passed = code == 0 and len(wire) == 2 and "PASS public-config-start-stop" in text
    result.update(status="pass" if passed else "runtime_failed", actual_qemu_user_passed=passed,
                  guest_kernel_booted=False, full_public_callback_ipc_exercised=False,
                  cfi_wrong_type_negative_test=False)
    save(output / "result.json", result)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
