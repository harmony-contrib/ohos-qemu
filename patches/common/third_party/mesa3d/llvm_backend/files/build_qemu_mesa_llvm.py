#!/usr/bin/env python3
"""Build the complete QEMU GL stack with its checked, private LLVM dependency."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import multiprocessing
import os
from pathlib import Path
import shutil
import subprocess
import sys

from qemu_mesa_llvm_artifacts import PRODUCTS, digest, validate

BASE_BUILDERS = {
    "armv7a_virt": (
        "device/qemu/arm_virt/linux_full_armv7a/build_armv7a_mesa.py",
        "22116ddc5d03bb440596e02c1336541761614c790b4a12bca67ce63eb5d10169",
    ),
    "arm64_virt": (
        "device/qemu/common/virt_full/hardware/gpu/build_qemu_mesa.py",
        "03e45a069e5aa14d4b710478971771d174fc4e7bd367a22376b1051cf210ed11",
    ),
    "x86_64_virt": (
        "device/qemu/common/virt_full/hardware/gpu/build_qemu_mesa.py",
        "03e45a069e5aa14d4b710478971771d174fc4e7bd367a22376b1051cf210ed11",
    ),
}


def meson_string(value: object) -> str:
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"


def import_base(path: Path, expected: str):
    if digest(path) != expected:
        raise ValueError("unexpected QEMU Mesa base builder; preserving source")
    spec = importlib.util.spec_from_file_location("qemu_mesa_base", path)
    if spec is None or spec.loader is None:
        raise ValueError("cannot import the fixed QEMU Mesa builder")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def check_cached_objects(output: Path, machine: int) -> int:
    """Do not let Ninja reuse empty/non-target objects after an I/O failure."""
    count = 0
    for path in (output / "src").rglob("*.o"):
        with path.open("rb") as stream:
            header = stream.read(20)
        if (path.is_symlink() or len(header) < 20 or header[:4] != b"\x7fELF" or
                header[5] != 1 or int.from_bytes(header[16:18], "little") != 1 or
                int.from_bytes(header[18:20], "little") != machine):
            raise ValueError("invalid cached Mesa object; use a fresh owned build directory: " + str(path))
        count += 1
    return count


def build(out_dir: Path) -> None:
    out_dir = out_dir.resolve()
    product = out_dir.name
    if product not in BASE_BUILDERS:
        raise ValueError("unsupported QEMU Mesa product")
    root = out_dir.parents[1]
    here = Path(__file__).resolve().parent
    identity = json.loads((here / "qemu_llvm_build_identity.json").read_text())
    dependency = Path(os.environ.get(
        "QEMU_MESA_LLVM_DEPENDENCY",
        here / "qemu_llvm" / identity["recipe_sha256"] / product,
    )).resolve()
    artifact = validate(dependency, product, identity)
    base_path, base_sha = BASE_BUILDERS[product]
    base = import_base(root / base_path, base_sha)
    mapping = root / "device/qemu/common/virt_full/hardware/gpu/mesa_kms_mapping/apply_mesa_kms_mapping.py"
    build_id = here / "qemu_build_id"
    build_id_inputs = {name: digest(build_id / name) for name in (
        "apply_mesa_build_id.py",
        "0001-bound-ELF-note-payloads-before-reading-or-advancing.patch",
    )}
    cache_identity = {
        "root": str(root), "product": product, "builder": digest(Path(__file__)),
        "base_builder": base_sha, "mapping": digest(mapping),
        "llvm_manifest": digest(dependency / "manifest.json"),
        "build_id_backport": build_id_inputs,
    }
    cache_key = hashlib.sha256(json.dumps(cache_identity, sort_keys=True).encode()).hexdigest()
    mesa_repo = root / "third_party/mesa3d"
    work_root = Path(os.environ.get("QEMU_MESA_BUILD_ROOT", mesa_repo / "qemu_llvm_build"))
    work = work_root / product / cache_key[:24]
    source = work / "source"
    output = work / "build"
    install = work / "install"
    package = Path(os.environ.get(
        "MESA_PACKAGE_DIR",
        out_dir / "packages/phone" / ("mesa3d" if product == "armv7a_virt" else "qemu_mesa"),
    )).resolve()
    work.mkdir(parents=True, exist_ok=True)
    stamp = work / "build-inputs.json"
    if stamp.exists():
        if json.loads(stamp.read_text()) != cache_identity:
            raise ValueError("Mesa build cache identity changed")
    elif output.exists():
        raise ValueError("unrecognized Mesa output directory; preserving it")
    stamp.write_text(json.dumps(cache_identity, indent=2) + "\n")
    base.prepare_qemu_mesa_source(mesa_repo, source)
    base.backport_ohos_logger_fixes(source)
    subprocess.run([sys.executable, str(mapping), "--source-root", str(source)], check=True)
    subprocess.run([sys.executable, str(build_id / "apply_mesa_build_id.py"),
                    "--source-root", str(source)], check=True)
    cross = work / "cross.txt"
    sysroot = out_dir / "obj/third_party/musl"
    if product == "armv7a_virt":
        base.write_cross_file(cross, root, sysroot)
    else:
        base.write_cross_file(cross, root, sysroot, base.TARGETS[product])
    pkgconfig = work / "pkgconfig"
    base.write_pkg_config_files(mesa_repo, root, product, pkgconfig)
    subproject = source / "subprojects/llvm"
    subproject.mkdir(parents=True, exist_ok=True)
    meson = (
        "project('ohos_qemu_private_llvm10', 'cpp', version : '10.0.0')\n"
        "has_rtti = false\n"
        "cpp = meson.get_compiler('cpp')\n"
        "private_llvm = cpp.find_library('llvm', dirs : ["
        + meson_string(dependency / "lib") + "], static : true, required : true)\n"
        "dep_llvm = declare_dependency(\n"
        "  include_directories : include_directories("
        + meson_string(dependency / "include") + "),\n"
        "  dependencies : private_llvm,\n"
        "  link_args : ['-ldl', '-lm', '-pthread'],\n"
        "  version : '10.0.0',\n)\n"
    )
    generated = subproject / "meson.build"
    if generated.exists() and generated.read_text() != meson:
        raise ValueError("unexpected private LLVM Meson subproject")
    generated.write_text(meson)
    env = dict(os.environ, PKG_CONFIG_PATH=str(pkgconfig))
    executable = shutil.which("meson")
    if executable is None:
        raise ValueError("Meson is required")
    setup = [
        executable, "setup", str(output), str(source),
        "--force-fallback-for=llvm", "--wrap-mode=nofallback",
        "-Dplatforms=ohos", "-Degl-native-platform=ohos", "-Ddri-drivers=",
        "-Dgallium-drivers=swrast,virgl", "-Dvulkan-drivers=", "-Dgbm=enabled",
        "-Degl=enabled", "-Dgles1=enabled", "-Dgles2=enabled", "-Dopengl=true",
        "-Dglx=disabled", "-Dtools=", "-Dllvm=enabled", "-Ddraw-use-llvm=true",
        "-Dshared-llvm=disabled", "-Dcpp_std=c++17", "-Dcpp_rtti=false",
        "-Dglvnd=false", "-Dshared-glapi=enabled", "-Dshader-cache=disabled",
        "-Ddri-search-path=/system/" + ("lib" if product == "armv7a_virt" else "lib64"),
        "-Dlibdir=lib", "--cross-file=" + str(cross), "--prefix=" + str(install),
    ]
    if (output / "meson-private/coredata.dat").is_file():
        setup.append("--reconfigure")
    subprocess.run(setup, check=True, cwd=source, env=env)
    options = json.loads((output / "meson-info/intro-buildoptions.json").read_text())
    selected = {v["name"]: v["value"] for v in options if v["name"] in (
        "llvm", "draw-use-llvm", "shared-llvm", "cpp_std")}
    if selected != {"llvm": "enabled", "draw-use-llvm": True,
                    "shared-llvm": "disabled", "cpp_std": "c++17"}:
        raise ValueError("Mesa did not select the required LLVM backend")
    jobs = min(int(os.environ.get("BUILD_JOBS", multiprocessing.cpu_count())), 16)
    if jobs < 1:
        raise ValueError("BUILD_JOBS must be positive")
    check_cached_objects(output, PRODUCTS[product][1])
    subprocess.run(["ninja", "-C", str(output), f"-j{jobs}"], check=True, env=env)
    check_cached_objects(output, PRODUCTS[product][1])
    subprocess.run(["ninja", "-C", str(output), "install"], check=True, env=env)
    if product == "armv7a_virt":
        base.copy_outputs(install, package, root)
    else:
        base.copy_outputs(install, package, root, base.TARGETS[product])
    driver = package / "kms_swrast_dri.so"
    machine = int.from_bytes(driver.read_bytes()[18:20], "little")
    if machine != PRODUCTS[product][1]:
        raise ValueError("Mesa driver target architecture mismatch")
    nm = root / "prebuilts/clang/ohos/linux-x86_64/llvm/bin/llvm-nm"
    symbols = subprocess.check_output([str(nm), "--defined-only", str(driver)], text=True)
    if "llvmpipe_create_screen" not in symbols or "tgsi_exec_machine_run" not in symbols:
        raise ValueError("Mesa is missing llvmpipe or the software fallback")
    exported = subprocess.check_output([str(nm), "-D", "--defined-only", str(driver)], text=True)
    if any("llvm" in row.lower() for row in exported.splitlines()):
        raise ValueError("private LLVM symbols escaped the DRI library")
    # Bind the inner build outputs to the exact immutable dependency.
    validate(dependency, product, identity)
    (package / "mesa-llvm-build-provenance.json").write_text(json.dumps({
        "schema_version": 1, "product": product, "dependency": artifact["recipe_sha256"],
        "llvm_archive_sha256": artifact["files"]["lib/libllvm.a"]["sha256"],
        "driver_sha256": digest(driver), "actual_options": selected,
        "build_inputs": cache_identity, "runtime_gate_passed": False,
    }, indent=2) + "\n")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: build_qemu_mesa_llvm.py OUT_DIR")
    build(Path(sys.argv[1]))
