#!/usr/bin/env python3
import multiprocessing
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path


QEMU_MESA_REPOSITORY = "https://github.com/openharmony/third_party_mesa3d"
QEMU_MESA_COMMIT = "995d2506d18924b48db0cf40e6ad7de04fc4e558"
QEMU_MESA_VERSION = "21.3.3"


def write_cross_file(path: Path, root: Path, sysroot: Path) -> None:
    clang_bin = root / "prebuilts/clang/ohos/linux-x86_64/llvm/bin"
    common_args = [
        "'-march=armv7-a'",
        "'-mfloat-abi=softfp'",
        "'-mtune=generic-armv7-a'",
        "'-mfpu=neon'",
        "'-mthumb'",
        "'--target=arm-linux-ohos'",
        f"'--sysroot={sysroot}'",
        "'-fPIC'",
    ]
    link_args = common_args + [
        f"'-L{sysroot / 'usr/lib/arm-linux-ohos'}'",
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
cpu_family = 'arm'
cpu = 'armv7'
endian = 'little'
"""
    path.write_text(content, encoding="utf-8")


def write_pkg_config_files(mesa_dir: Path, root: Path, product: str, output: Path) -> None:
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
    if marker.is_file() and marker.read_text(encoding="utf-8").strip() == QEMU_MESA_COMMIT:
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
    marker.write_text(f"{QEMU_MESA_COMMIT}\n", encoding="utf-8")


def backport_ohos_logger_fixes(source_dir: Path) -> None:
    """Apply the later upstream OHOS fixes needed by the current sysroot."""
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


def copy_outputs(install_dir: Path, package_dir: Path, root: Path) -> None:
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

    llvm_nm = root / "prebuilts/clang/ohos/linux-x86_64/llvm/bin/llvm-nm"
    symbols = subprocess.check_output(
        [str(llvm_nm), "-D", "--defined-only", str(packaged_driver)],
        text=True,
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

    required = (
        "libEGL.so.1.0.0",
        "libgbm.so.1.0.0",
        "libGLESv1_CM.so.1.1.0",
        "libGLESv2.so.2.0.0",
        "libglapi.so.0.0.0",
        "kms_swrast_dri.so",
    )
    missing = [name for name in required if not (package_dir / name).is_file()]
    if missing:
        raise RuntimeError(f"Mesa outputs missing: {', '.join(missing)}")


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: build_armv7a_mesa.py OUT_DIR")

    out_dir = Path(sys.argv[1]).resolve()
    root = out_dir.parents[1]
    product = out_dir.name
    if product != "armv7a_virt":
        raise RuntimeError(f"armv7a Mesa builder received unexpected product: {product}")

    mesa_repo = root / "third_party/mesa3d"
    sysroot = out_dir / "obj/third_party/musl"
    source_dir = mesa_repo / "build-ohos-armv7a-qemu-source-21.3.3"
    build_dir = mesa_repo / "build-ohos-armv7a-qemu-21.3.3"
    install_dir = build_dir / "install"
    package_dir = Path(
        os.environ.get("MESA_PACKAGE_DIR", out_dir / "packages/phone/mesa3d")
    ).resolve()
    cross_file = mesa_repo / "cross_file_armv7a_qemu_21.3.3"
    pkg_config_dir = mesa_repo / "pkgconfig_armv7a_qemu_21.3.3"

    prepare_qemu_mesa_source(mesa_repo, source_dir)
    backport_ohos_logger_fixes(source_dir)
    write_cross_file(cross_file, root, sysroot)
    # Historical Mesa sources use dependency paths that predate the current
    # OpenHarmony tree. Use the current OHOS pkg-config templates so headers
    # and already-built libraries resolve from the active checkout.
    write_pkg_config_files(mesa_repo, root, product, pkg_config_dir)
    meson = shutil.which("meson")
    if meson is None:
        raise RuntimeError("meson >= 1.1 is required to build armv7a Mesa")

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
        "-Ddri-search-path=/system/lib",
        "-Dlibdir=lib",
        f"--cross-file={cross_file}",
        f"--prefix={install_dir}",
    ]
    coredata = build_dir / "meson-private/coredata.dat"
    if build_dir.exists() and not coredata.is_file():
        shutil.rmtree(build_dir)
    if coredata.is_file():
        setup.append("--reconfigure")
    subprocess.run(setup, check=True, cwd=source_dir, env=env)

    jobs = min(int(os.environ.get("BUILD_JOBS", multiprocessing.cpu_count())), 16)
    subprocess.run(["ninja", "-C", str(build_dir), f"-j{jobs}"], check=True, env=env)
    shutil.rmtree(install_dir, ignore_errors=True)
    subprocess.run(["ninja", "-C", str(build_dir), "install"], check=True, env=env)
    copy_outputs(install_dir, package_dir, root)


if __name__ == "__main__":
    main()
