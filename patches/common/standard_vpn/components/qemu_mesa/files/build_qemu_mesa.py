#!/usr/bin/env python3
"""Build the portable OpenHarmony QEMU GL stack from a fixed Mesa revision."""

import multiprocessing
import os
import shutil
import subprocess
import sys
import tarfile
from dataclasses import dataclass
from pathlib import Path


QEMU_MESA_REPOSITORY = "https://github.com/openharmony/third_party_mesa3d"
QEMU_MESA_COMMIT = "995d2506d18924b48db0cf40e6ad7de04fc4e558"
QEMU_MESA_VERSION = "21.3.3"
OHOS_LOGGER_FIX_COMMIT = "c285df95c30d1d7af26d8203c736ecf3f23dc67c"


@dataclass(frozen=True)
class Target:
    triple: str
    cpu_family: str
    cpu: str
    sysroot_lib: str
    elf_machine: int


TARGETS = {
    "arm64_virt": Target(
        "aarch64-linux-ohos", "aarch64", "armv8", "aarch64-linux-ohos", 183
    ),
    "x86_64_virt": Target(
        "x86_64-linux-ohos", "x86_64", "x86_64", "x86_64-linux-ohos", 62
    ),
}

REQUIRED_OUTPUTS = (
    "libEGL.so.1.0.0",
    "libgbm.so.1.0.0",
    "libGLESv1_CM.so.1.1.0",
    "libGLESv2.so.2.0.0",
    "libglapi.so.0.0.0",
    "kms_swrast_dri.so",
)


def write_cross_file(
    path: Path, root: Path, sysroot: Path, target: Target
) -> None:
    clang_bin = root / "prebuilts/clang/ohos/linux-x86_64/llvm/bin"
    common_args = [
        f"'--target={target.triple}'",
        f"'--sysroot={sysroot}'",
        "'-fPIC'",
    ]
    link_args = common_args + [
        f"'-L{sysroot / 'usr/lib' / target.sysroot_lib}'",
        "'-fuse-ld=lld'",
        "'--rtlib=compiler-rt'",
    ]
    content = f"""[properties]
needs_exe_wrapper = true

[binaries]
ar = '{clang_bin / 'llvm-ar'}'
c = ['ccache', '{clang_bin / 'clang'}']
cpp = ['ccache', '{clang_bin / 'clang++'}']
c_ld = 'lld'
cpp_ld = 'lld'
strip = '{clang_bin / 'llvm-strip'}'
pkg-config = '/usr/bin/pkg-config'

[built-in options]
c_args = [{', '.join(common_args)}]
cpp_args = [{', '.join(common_args)}]
c_link_args = [{', '.join(link_args)}]
cpp_link_args = [{', '.join(link_args)}]

[host_machine]
system = 'linux'
cpu_family = '{target.cpu_family}'
cpu = '{target.cpu}'
endian = 'little'
"""
    path.write_text(content, encoding="utf-8")


def write_pkg_config_files(
    mesa_dir: Path, root: Path, product: str, output: Path
) -> None:
    output.mkdir(parents=True, exist_ok=True)
    templates = mesa_dir / "ohos/pkgconfig_template"
    for source in templates.iterdir():
        if not source.is_file():
            continue
        content = source.read_text(encoding="utf-8")
        content = content.replace("ohos_project_directory_stub", str(root))
        content = content.replace("ohos-arm-release", product)
        if source.name == "expat.pc":
            content = content.replace("libexpat.z.so", "-lexpat.z")
        elif source.name == "libqos.pc":
            content = content.replace(
                "prebuilts/ohos-sdk/linux/23/native/sysroot/usr/lib/aarch64-linux-ohos/",
                f"out/{product}/resourceschedule/qos_manager",
            )
        (output / source.name).write_text(content, encoding="utf-8")


def prepare_qemu_mesa_source(mesa_repo: Path, source_dir: Path) -> None:
    marker = source_dir / ".ohos-qemu-source-revision"
    expected_marker = f"{QEMU_MESA_COMMIT}+{OHOS_LOGGER_FIX_COMMIT}\n"
    if marker.is_file() and marker.read_text(encoding="utf-8") == expected_marker:
        return

    version = subprocess.check_output(
        ["git", "show", f"{QEMU_MESA_COMMIT}:VERSION"],
        cwd=mesa_repo,
        text=True,
    ).strip()
    if version != QEMU_MESA_VERSION:
        raise RuntimeError(
            f"Mesa revision {QEMU_MESA_COMMIT} from {QEMU_MESA_REPOSITORY} "
            f"has version {version}, expected {QEMU_MESA_VERSION}"
        )

    shutil.rmtree(source_dir, ignore_errors=True)
    source_dir.mkdir(parents=True)
    archive = subprocess.Popen(
        ["git", "archive", "--format=tar", QEMU_MESA_COMMIT],
        cwd=mesa_repo,
        stdout=subprocess.PIPE,
    )
    if archive.stdout is None:
        raise RuntimeError("failed to read Mesa git archive")
    try:
        with tarfile.open(fileobj=archive.stdout, mode="r|") as source_tar:
            source_tar.extractall(source_dir)
    finally:
        archive.stdout.close()
    if archive.wait() != 0:
        raise RuntimeError(f"failed to extract Mesa revision {QEMU_MESA_COMMIT}")

    backport_ohos_logger_fixes(source_dir)
    marker.write_text(expected_marker, encoding="utf-8")


def backport_ohos_logger_fixes(source_dir: Path) -> None:
    """Backport the upstream OHOS va_list fix that prevents EGL startup crashes."""
    path = source_dir / "src/loader/loader.c"
    content = path.read_text(encoding="utf-8")
    old_default = """        vfprintf(stderr, fmt, args);
        sprintf_s(log_string, MAX_BUFFER_LEN, fmt, args);
        va_end(args);
"""
    fixed_default = """        vfprintf(stderr, fmt, args);
        va_end(args);
"""
    if old_default in content:
        content = content.replace(old_default, fixed_default, 1)
    elif fixed_default not in content:
        raise RuntimeError(f"unexpected default logger implementation in {path}")

    old_ohos = "(void)sprintf_s(log_string, MAX_BUFFER_LEN, fmt, args);"
    fixed_ohos = "(void)vsnprintf(log_string, MAX_BUFFER_LEN, fmt, args);"
    if old_ohos in content:
        content = content.replace(old_ohos, fixed_ohos, 1)
    elif fixed_ohos not in content:
        raise RuntimeError(f"unexpected OHOS logger implementation in {path}")
    path.write_text(content, encoding="utf-8")


def elf_machine(path: Path) -> int:
    data = path.read_bytes()
    if len(data) <= 4096 or not data.startswith(b"\x7fELF"):
        raise RuntimeError(f"Mesa output is not a materialized ELF file: {path}")
    byteorder = "little" if data[5] == 1 else "big" if data[5] == 2 else None
    if byteorder is None:
        raise RuntimeError(f"Mesa output has an invalid ELF byte order: {path}")
    return int.from_bytes(data[18:20], byteorder)


def copy_outputs(
    install_dir: Path, package_dir: Path, root: Path, target: Target
) -> None:
    lib_dir = install_dir / "lib"
    package_dir.mkdir(parents=True, exist_ok=True)
    for output in package_dir.iterdir():
        if output.is_file() or output.is_symlink():
            output.unlink()

    for source in lib_dir.glob("lib*.so*"):
        if source.is_file() and not source.is_symlink():
            shutil.copy2(source, package_dir / source.name)

    dri_driver = lib_dir / "dri/kms_swrast_dri.so"
    if not dri_driver.is_file():
        raise RuntimeError(f"Mesa did not produce its KMS swrast driver: {dri_driver}")
    packaged_driver = package_dir / "kms_swrast_dri.so"
    shutil.copy2(dri_driver, packaged_driver)

    if elf_machine(packaged_driver) != target.elf_machine:
        raise RuntimeError(f"Mesa driver has the wrong target architecture: {packaged_driver}")

    llvm_nm = root / "prebuilts/clang/ohos/linux-x86_64/llvm/bin/llvm-nm"
    symbols = subprocess.check_output(
        [str(llvm_nm), "-D", "--defined-only", str(packaged_driver)], text=True
    )
    required_driver_symbols = (
        "__driDriverGetExtensions_swrast",
        "__driDriverGetExtensions_kms_swrast",
        "__driDriverGetExtensions_virtio_gpu",
    )
    missing_symbols = [
        symbol for symbol in required_driver_symbols if symbol not in symbols
    ]
    if missing_symbols:
        raise RuntimeError(
            "Mesa driver entry points missing: " + ", ".join(missing_symbols)
        )

    llvm_objdump = root / "prebuilts/clang/ohos/linux-x86_64/llvm/bin/llvm-objdump"
    logger_disassembly = subprocess.check_output(
        [
            str(llvm_objdump),
            "-d",
            "--disassemble-symbols=ohos_logger",
            str(packaged_driver),
        ],
        text=True,
    )
    if "<vsnprintf@plt>" not in logger_disassembly:
        raise RuntimeError(
            "Mesa ohos_logger did not compile with the upstream va_list fix: "
            f"{packaged_driver}"
        )

    missing = [name for name in REQUIRED_OUTPUTS if not (package_dir / name).is_file()]
    if missing:
        raise RuntimeError(f"Mesa outputs missing: {', '.join(missing)}")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: build_qemu_mesa.py OUT_DIR")

    out_dir = Path(sys.argv[1]).resolve()
    root = out_dir.parents[1]
    product = out_dir.name
    try:
        target = TARGETS[product]
    except KeyError as error:
        raise RuntimeError(f"unsupported 64-bit QEMU Mesa product: {product}") from error

    mesa_repo = root / "third_party/mesa3d"
    sysroot = out_dir / "obj/third_party/musl"
    tag = product.replace("_virt", "")
    source_dir = mesa_repo / "build-ohos-qemu-source-21.3.3-fixed"
    build_dir = mesa_repo / f"build-ohos-qemu-{tag}-21.3.3-fixed"
    install_dir = build_dir / "install"
    package_dir = Path(
        os.environ.get("MESA_PACKAGE_DIR", out_dir / "packages/phone/qemu_mesa")
    ).resolve()
    cross_file = mesa_repo / f"cross_file_qemu_{tag}_21.3.3"
    pkg_config_dir = mesa_repo / f"pkgconfig_qemu_{tag}_21.3.3"

    prepare_qemu_mesa_source(mesa_repo, source_dir)
    # Reapply and validate even when a cached extracted source tree is reused.
    backport_ohos_logger_fixes(source_dir)
    write_cross_file(cross_file, root, sysroot, target)
    write_pkg_config_files(mesa_repo, root, product, pkg_config_dir)
    meson = shutil.which("meson")
    if meson is None:
        raise RuntimeError("meson >= 1.1 is required to build QEMU Mesa")

    env = os.environ.copy()
    env["PKG_CONFIG_PATH"] = str(pkg_config_dir)
    setup = [
        meson,
        "setup",
        str(build_dir),
        str(source_dir),
        "-Dplatforms=ohos",
        "-Degl-native-platform=ohos",
        "-Ddri-drivers=",
        "-Dgallium-drivers=swrast,virgl",
        "-Dvulkan-drivers=",
        "-Dgbm=enabled",
        "-Degl=enabled",
        "-Dgles1=enabled",
        "-Dgles2=enabled",
        "-Dopengl=true",
        "-Dglx=disabled",
        "-Dtools=",
        "-Dllvm=disabled",
        "-Ddraw-use-llvm=false",
        "-Dcpp_rtti=false",
        "-Dglvnd=false",
        "-Dshared-glapi=enabled",
        "-Dshader-cache=disabled",
        "-Ddri-search-path=/system/lib64",
        "-Dlibdir=lib",
        f"--cross-file={cross_file}",
        f"--prefix={install_dir}",
    ]
    coredata = build_dir / "meson-private/coredata.dat"
    build_root_stamp = build_dir / ".ohos-qemu-build-root"
    expected_build_root = f"{root}\n"
    cached_build_root = (
        build_root_stamp.read_text(encoding="utf-8")
        if build_root_stamp.is_file()
        else ""
    )
    if build_dir.exists() and (
        not coredata.is_file() or cached_build_root != expected_build_root
    ):
        shutil.rmtree(build_dir)
    if coredata.is_file():
        setup.append("--reconfigure")
    subprocess.run(setup, check=True, cwd=source_dir, env=env)
    build_root_stamp.write_text(expected_build_root, encoding="utf-8")

    jobs = min(int(os.environ.get("BUILD_JOBS", multiprocessing.cpu_count())), 16)
    subprocess.run(["ninja", "-C", str(build_dir), f"-j{jobs}"], check=True, env=env)
    shutil.rmtree(install_dir, ignore_errors=True)
    subprocess.run(["ninja", "-C", str(build_dir), "install"], check=True, env=env)
    copy_outputs(install_dir, package_dir, root, target)


if __name__ == "__main__":
    main()
