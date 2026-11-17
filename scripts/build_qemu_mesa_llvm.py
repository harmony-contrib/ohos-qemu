#!/usr/bin/env python3
"""Build Mesa's private LLVM from the pinned M144 SwiftShader source.

This produces one dependency archive. It neither installs a driver in an image
nor satisfies the first packaged-artifact runtime gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import time

from qemu_mesa_llvm_artifacts import expected_identity, write_manifest

PRODUCTS = {
    "armv7a_virt": ("arm", "arm", "arm-linux-ohos",
                    "-march=armv7-a -mfloat-abi=softfp -mfpu=neon -mthumb"),
    "arm64_virt": ("arm64", "aarch64", "aarch64-linux-ohos", ""),
    "x86_64_virt": ("x86_64", "x86_64", "x86_64-linux-ohos", ""),
}
# The vendored SwiftShader target omits public LLVM C entrypoints. Mesa uses
# these actual implementations and their normal pass registration dependencies.
C_API_SOURCES = (
    "Analysis/Analysis.cpp",
    "Bitcode/Reader/BitReader.cpp",
    "Bitcode/Writer/BitWriter.cpp",
    "ExecutionEngine/ExecutionEngineBindings.cpp",
    "ExecutionEngine/MCJIT/MCJIT.cpp",
    "ExecutionEngine/Orc/OrcCBindings.cpp",
    "IR/Core.cpp",
    "IRReader/IRReader.cpp",
    "Linker/LinkModules.cpp",
    "MC/MCDisassembler/Disassembler.cpp",
    "Object/Object.cpp",
    "Remarks/Remark.cpp",
    "Target/Target.cpp",
    "Transforms/IPO/IPO.cpp",
    "Transforms/Scalar/Scalar.cpp",
    "Transforms/Utils/Utils.cpp",
    "Transforms/Vectorize/Vectorize.cpp",
)
COMPLETE_COMPONENTS = (
    "Analysis", "IR", "MC/MCDisassembler", "Transforms/Scalar",
    "Transforms/Utils", "Transforms/IPO", "Transforms/Vectorize",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def cmake_string(value: object) -> str:
    text = str(value)
    if "\n" in text or "\r" in text or "\0" in text:
        raise ValueError("CMake values must be single-line strings")
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$") + '"'


def softfp_config(original: str, names: tuple[str, ...] = (
        "LLVM_DEFAULT_TARGET_TRIPLE", "LLVM_HOST_TRIPLE")) -> str:
    """Keep other platforms' defaults; OHOS ARMv7 uses the base AAPCS ABI."""
    result = original
    for name in names:
        old = f'#define {name} "armv7-linux-gnueabihf"'
        if result.count(old) != 1:
            raise ValueError(f"unexpected pinned LLVM configuration: {name}")
        result = result.replace(
            old,
            f'#if defined(__OHOS__)\n#define {name} "armv7-unknown-linux-gnueabi"\n'
            f"#else\n{old}\n#endif",
        )
    return result


def platform_config(original: str) -> str:
    result = softfp_config(original, ("LLVM_DEFAULT_TARGET_TRIPLE",))
    old = "#define HAVE_DECL_FE_INEXACT 1"
    if result.count(old) != 1:
        raise ValueError("unexpected pinned LLVM floating-point environment configuration")
    # The OHOS ARM base-PCS musl header defines FE_ALL_EXCEPT=0 and does not
    # declare FE_INEXACT. Use LLVM's existing declaration-aware fallback.
    return result.replace(
        old,
        "#if defined(__OHOS__) && defined(__arm__) && !defined(__ARM_PCS_VFP)\n"
        "#define HAVE_DECL_FE_INEXACT 0\n"
        f"#else\n{old}\n#endif",
    )


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


def fixed_sources(m144_source: Path, lock_path: Path) -> tuple[Path, dict]:
    lock = json.loads(lock_path.read_text())
    matches = [item for item in lock["projects"] if item["path"] == "src/third_party/swiftshader"]
    if len(matches) != 1 or lock["chromium_milestone"] != 144:
        raise ValueError("matching M144 SwiftShader source lock is required")
    pin = matches[0]
    repo = m144_source / "third_party/swiftshader"
    if git(repo, "rev-parse", "HEAD") != pin["revision"]:
        raise ValueError("SwiftShader checkout does not match the M144 source lock")
    relative = "third_party/llvm-10.0"
    subprocess.run(["git", "-C", str(repo), "diff", "--quiet", "HEAD", "--", relative], check=True)
    if git(repo, "ls-files", "--others", "--exclude-standard", "--", relative):
        raise ValueError("untracked files in the LLVM source are not allowed")
    llvm = repo / relative
    tracked = set(git(repo, "ls-files", "--", relative).splitlines())
    extra = {llvm / "llvm/lib" / name for name in C_API_SOURCES}
    extra.update(path for component in COMPLETE_COMPONENTS
                 for path in (llvm / "llvm/lib" / component).glob("*.cpp"))
    if not extra or any(path.relative_to(repo).as_posix() not in tracked for path in extra):
        raise ValueError("required LLVM component sources are missing from the fixed checkout")
    return llvm, {
        "swiftshader_revision": pin["revision"],
        "llvm_git_tree": git(repo, "rev-parse", f"HEAD:{relative}"),
        "m144_source_lock_sha256": sha256(lock_path),
        "extra_sources": sorted(str(path) for path in extra),
    }


def unwind_backport(llvm: Path, wrapper: Path, tools: Path,
                    arch: str, target: str) -> tuple[str, dict]:
    if arch == "arm":
        return "", {"mode": "ARM EHABI; no DWARF FDE override"}
    runtime = tools / "lib" / target / "libc++.so"
    exported = subprocess.check_output(
        [str(tools / "bin/llvm-nm"), "-D", "--defined-only", str(runtime)], text=True)
    symbols = {line.split()[-1] for line in exported.splitlines() if line.split()}
    required = {"__register_frame", "__deregister_frame",
                "__unw_add_dynamic_fde", "__unw_remove_dynamic_fde"}
    if not required <= symbols:
        raise ValueError("the prepared OHOS runtime does not provide libunwind's per-FDE registration")
    original = llvm / "llvm/lib/ExecutionEngine/RuntimeDyld/RTDyldMemoryManager.cpp"
    text = original.read_text()
    old = "#ifdef __APPLE__\n\nstatic const char *processFDE"
    if text.count(old) != 1:
        raise ValueError("unexpected pinned RuntimeDyld FDE registration source")
    patched = wrapper / "RTDyldMemoryManager.cpp"
    patched.write_text(text.replace(
        old, "#if defined(__APPLE__) || defined(HAVE_UNW_ADD_DYNAMIC_FDE)\n\n"
        "static const char *processFDE", 1))
    # Source properties must be set in the directory that owns the llvm target.
    # A parent-directory property silently omits this definition in its child.
    cmake = (
        "get_target_property(_qemu_sources llvm SOURCES)\n"
        f"list(FIND _qemu_sources {cmake_string(original)} _qemu_original_index)\n"
        "if(_qemu_original_index EQUAL -1)\n"
        'message(FATAL_ERROR "Original RuntimeDyld source missing")\nendif()\n'
        f"list(REMOVE_ITEM _qemu_sources {cmake_string(original)})\n"
        'set_property(TARGET llvm PROPERTY SOURCES "${_qemu_sources}")\n'
        f"target_sources(llvm PRIVATE {cmake_string(patched)})\n"
        f"set_property(SOURCE {cmake_string(patched)} TARGET_DIRECTORY llvm PROPERTY "
        "COMPILE_DEFINITIONS HAVE_UNW_ADD_DYNAMIC_FDE)\n"
    )
    return cmake, {
        "mode": "libunwind per-FDE registration",
        "runtime_sha256": sha256(runtime), "required_runtime_exports": sorted(required),
        "original_sha256": sha256(original), "patched_sha256": sha256(patched),
        "patched_source": str(patched),
        "upstream": "https://llvm.org/docs/doxygen/RTDyldMemoryManager_8cpp_source.html",
    }


def select_sysroot(source: Path, product: str, target: str) -> tuple[Path, dict]:
    sysroot = source / "out" / product / "obj/third_party/musl"
    sysroot_identity = {"origin": "generated product musl", "path": str(sysroot)}
    if not (sysroot / "usr/lib" / target).is_dir():
        native = source / "prebuilts/ohos-sdk/linux/26.0.0/native"
        metadata_path = native / "oh-uni-package.json"
        metadata = json.loads(metadata_path.read_text())
        if any(str(metadata.get(name)) != value for name, value in {
            "apiVersion": "26", "platformVersion": "26.0.0",
            "releaseType": "Release", "version": "26.0.0.39",
        }.items()):
            raise ValueError("fresh LLVM bootstrap requires the fixed Release API26 native SDK")
        sysroot = native / "sysroot"
        sysroot_identity = {"origin": "fixed Release API26 native SDK",
                            "path": str(sysroot), "metadata": metadata,
                            "metadata_sha256": sha256(metadata_path)}
    sysroot_identity["libc_sha256"] = sha256(sysroot / "usr/lib" / target / "libc.so")
    return sysroot, sysroot_identity


def build(args: argparse.Namespace) -> Path:
    arch, backend, target, flags = PRODUCTS[args.product]
    source = args.ohos_source_root.resolve()
    source_check = subprocess.check_output(
        [sys.executable, str(Path(__file__).with_name("openharmony_release_source_lock.py")),
         "--source-root", str(source)], text=True)
    lock_path = Path(__file__).with_name("m144_release_source_lock.json")
    llvm, identity = fixed_sources(args.m144_source_root.resolve(), lock_path)
    tools = source / "prebuilts/clang/ohos/linux-x86_64/llvm"
    sysroot, sysroot_identity = select_sysroot(source, args.product, target)
    for path in (tools / "bin/clang", tools / "bin/clang++", tools / "bin/llvm-ar",
                 tools / "include/libcxx-ohos/include/c++/v1/vector",
                 sysroot / "usr/lib" / target):
        if not path.exists():
            raise ValueError(f"prepared OHOS toolchain/sysroot is missing: {path}")
    header = softfp_config((llvm / "configs/linux/include/llvm/Config/llvm-config.h").read_text())
    platform = platform_config((llvm / "configs/linux/include/llvm/Config/config.h").read_text())
    artifact_identity = expected_identity()
    output = args.output.resolve()
    build_root = args.build_root.resolve()
    if output.exists() or build_root.exists():
        raise ValueError("fresh output and build directories are required; existing builds are preserved")
    output.mkdir(parents=True)
    build_root.mkdir(parents=True)
    report = dict(schema_version=1, status="preparing", product=args.product, arch=arch,
                  scope="LLVM dependency only; no packaged QEMU runtime validation",
                  started_epoch=time.time(), commands=[], artifact_identity=artifact_identity,
                  sysroot=sysroot_identity,
                  openharmony_source_check_sha256=hashlib.sha256(source_check.encode()).hexdigest(),
                  **identity)

    def save() -> None:
        (output / "build-evidence.json").write_text(json.dumps(report, indent=2) + "\n")

    def run(argv: list[str], label: str) -> None:
        with (output / f"{label}.log").open("xb") as stream:
            process = subprocess.run(argv, stdout=stream, stderr=subprocess.STDOUT)
        report["commands"].append(dict(argv=argv, exit_code=process.returncode,
                                       log=f"{label}.log", sha256=sha256(output / f"{label}.log")))
        save()
        if process.returncode:
            raise RuntimeError(f"{label} failed; see {output / (label + '.log')}")

    save()
    try:
        wrapper = build_root / "recipe"
        wrapper.mkdir()
        # Match the original include search order: platform, common, upstream.
        # Consumers need the generated .inc/.def files as well as public headers.
        for directory in (llvm / "llvm/include", llvm / "configs/common/include",
                          llvm / "configs/linux/include"):
            if any(path.is_symlink() for path in directory.rglob("*")):
                raise ValueError("fixed LLVM consumer headers must be materialized")
            shutil.copytree(directory, output / "include", dirs_exist_ok=True)
        override = output / "include/llvm/Config/llvm-config.h"
        override.parent.mkdir(parents=True, exist_ok=True)
        override.write_text(header)
        platform_override = override.with_name("config.h")
        platform_override.write_text(platform)
        unwind_cmake, unwind_identity = unwind_backport(llvm, wrapper, tools, arch, target)
        (wrapper / "CMakeLists.txt").write_text(
            "cmake_minimum_required(VERSION 3.18)\n"
            "project(QemuPrivateLLVM10 LANGUAGES C CXX)\n"
            "set(CMAKE_CXX_STANDARD 17)\nset(CMAKE_CXX_STANDARD_REQUIRED ON)\n"
            f"set(LINUX TRUE)\nset(ARCH {cmake_string(backend)})\n"
            "set(REACTOR_EMIT_DEBUG_INFO FALSE)\nset(SWIFTSHADER_EMIT_COVERAGE FALSE)\n"
            f"add_subdirectory({cmake_string(llvm)} llvm10)\n"
            "target_sources(llvm PRIVATE\n"
            + "".join(f"  {cmake_string(path)}\n" for path in identity["extra_sources"])
            + ")\n"
            f"target_include_directories(llvm BEFORE PUBLIC {cmake_string(output / 'include')})\n"
            + unwind_cmake
        )
        headers = shlex.quote(str(tools / "include/libcxx-ohos/include/c++/v1"))
        cxx = f"-nostdinc++ -isystem {headers} -fno-exceptions -fno-rtti {flags}"
        toolchain = wrapper / "ohos.cmake"
        toolchain.write_text(
            "set(CMAKE_SYSTEM_NAME Linux)\n"
            f"set(CMAKE_SYSTEM_PROCESSOR {cmake_string(backend)})\n"
            "set(CMAKE_TRY_COMPILE_TARGET_TYPE STATIC_LIBRARY)\n"
            f"set(CMAKE_C_COMPILER {cmake_string(tools / 'bin/clang')})\n"
            f"set(CMAKE_CXX_COMPILER {cmake_string(tools / 'bin/clang++')})\n"
            f"set(CMAKE_C_COMPILER_TARGET {cmake_string(target)})\n"
            f"set(CMAKE_CXX_COMPILER_TARGET {cmake_string(target)})\n"
            f"set(CMAKE_SYSROOT {cmake_string(sysroot)})\n"
            f"set(CMAKE_AR {cmake_string(tools / 'bin/llvm-ar')})\n"
            f"set(CMAKE_RANLIB {cmake_string(tools / 'bin/llvm-ranlib')})\n"
            f"set(CMAKE_C_FLAGS_INIT {cmake_string(flags)})\n"
            f"set(CMAKE_CXX_FLAGS_INIT {cmake_string(cxx)})\n"
        )
        report.update(status="configuring", builder_sha256=sha256(Path(__file__)),
                      compiler_sha256=sha256(tools / "bin/clang"),
                      wrapper_sha256=sha256(wrapper / "CMakeLists.txt"),
                      toolchain_sha256=sha256(toolchain),
                      private_config_sha256=sha256(override),
                      private_platform_config_sha256=sha256(platform_override),
                      unwind_registration=unwind_identity,
                      source_sha256={str(Path(path).relative_to(llvm)): sha256(Path(path))
                                     for path in identity["extra_sources"]})
        save()
        work = build_root / "work"
        run(["cmake", "-S", str(wrapper), "-B", str(work), "-G", "Ninja",
             f"-DCMAKE_TOOLCHAIN_FILE={toolchain}", "-DCMAKE_BUILD_TYPE=Release",
             "-DCMAKE_CXX_FLAGS_RELEASE=-O2 -DNDEBUG"], "configure")
        if "patched_source" in unwind_identity:
            commands = subprocess.check_output(
                ["ninja", "-C", str(work), "-t", "commands", "llvm10/libllvm.a"], text=True)
            selected = [line for line in commands.splitlines()
                        if " -c " in line and unwind_identity["patched_source"] in line]
            if len(selected) != 1 or "-DHAVE_UNW_ADD_DYNAMIC_FDE" not in selected[0]:
                raise ValueError("libunwind FDE definition did not reach the actual LLVM compile command")
            report["actual_unwind_compile_command"] = selected[0]
        report["status"] = "compiling"
        save()
        run(["cmake", "--build", str(work), "--target", "llvm", "--parallel", str(args.jobs)], "compile")
        archive = work / "llvm10/libllvm.a"
        headers = subprocess.check_output([str(tools / "bin/llvm-readelf"), "-h", str(archive)], text=True)
        (output / "archive-headers.log").write_text(headers)
        machines = {line.split(":", 1)[1].strip() for line in headers.splitlines()
                    if line.strip().startswith("Machine:")}
        expected = {"arm": {"ARM"}, "arm64": {"AArch64"},
                    "x86_64": {"Advanced Micro Devices X86-64"}}[arch]
        if machines != expected:
            raise ValueError(f"archive object architecture mismatch: {machines}")
        installed = output / "lib/libllvm.a"
        installed.parent.mkdir()
        shutil.copyfile(archive, installed)
        report.update(status="pass_static_dependency_build_ONLY_NOT_Mesa_or_guest",
                      library="lib/libllvm.a", library_sha256=sha256(installed),
                      library_bytes=installed.stat().st_size, object_machines=sorted(machines),
                      include_directories=["include"])
        write_manifest(output, args.product, identity, report)
    except Exception as error:
        report.update(status="fail", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        report["finished_epoch"] = time.time()
        save()
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--product", choices=PRODUCTS, required=True)
    parser.add_argument("--ohos-source-root", type=Path, required=True)
    parser.add_argument("--m144-source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--build-root", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    print(build(args))


if __name__ == "__main__":
    main()
