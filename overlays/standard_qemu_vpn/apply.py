#!/usr/bin/env python3

import base64
import hashlib
import json
import re
import sys
from pathlib import Path


SUPPORTED_PRODUCTS = {
    "armv7a_virt": (
        "device/qemu/common/virt_full/kernel/arm_virt_defconfig",
        "device/qemu/common/virt_full/kernel/configs/arm_virt_defconfig",
    ),
    "arm64_virt": (
        "device/qemu/common/virt_full/kernel/arm64_virt_defconfig",
    ),
    "x86_64_virt": (
        "device/qemu/common/virt_full/kernel/x86_64_virt_defconfig",
    ),
}

VPN_KERNEL_OPTIONS = (
    "CONFIG_NAMESPACES",
    "CONFIG_NET",
    "CONFIG_UNIX",
    "CONFIG_INET",
    "CONFIG_NET_NS",
    "CONFIG_NETDEVICES",
    "CONFIG_TUN",
    "CONFIG_IP_ADVANCED_ROUTER",
    "CONFIG_IP_MULTIPLE_TABLES",
    "CONFIG_IPV6",
    "CONFIG_IPV6_MULTIPLE_TABLES",
    "CONFIG_SYSTEM_DATA_VERIFICATION",
    "CONFIG_FS_VERITY",
    "CONFIG_FS_VERITY_BUILTIN_SIGNATURES",
    "CONFIG_SECURITY_CODE_SIGN",
    "CONFIG_HCK",
    "CONFIG_HCK_VENDOR_HOOKS",
    "CONFIG_CRYPTO_ECC",
    "CONFIG_CRYPTO_ECDSA",
    "CONFIG_CRYPTO_SHA256",
    "CONFIG_FS_ENCRYPTION",
    "CONFIG_F2FS_FS",
    "CONFIG_F2FS_FS_XATTR",
    "CONFIG_F2FS_FS_POSIX_ACL",
    "CONFIG_F2FS_FS_SECURITY",
    "CONFIG_QUOTA",
    "CONFIG_QUOTACTL",
)

VPN_64BIT_KERNEL_OPTIONS = (
    "CONFIG_ARCH_USES_HIGH_VMA_FLAGS",
    "CONFIG_SECURITY_XPM",
    "CONFIG_DSMM_DEVELOPER_ENABLE",
)

VPN_DIALOG_TARGET = (
    "//foundation/communication/netmanager_ext/frameworks/vpn_dialog/"
    "dialog_ui/vpn_dialog:dialog_hap"
)

VPN_DIALOG_PROFILE_ASSET = (
    Path(__file__).resolve().parent / "assets/vpndialog.p7b.b64"
)
VPN_DIALOG_PROFILE_SHA256 = (
    "ae9c5803dd72143810aa1c87d306e7b04d7e1854924161e9bcd8a8de0c623022"
)

QEMU_GRAPHICS_FEATURES = {
    # Keep the common RS/Canvas/OpenGL ABI compiled in so existing QEMU build
    # caches remain reusable. The RenderService source fix below forces QEMU's
    # composer onto its raster path without changing the public graphics ABI.
    "graphic_2d_feature_ace_enable_gpu": True,
    "graphic_2d_feature_enable_opengl": True,
    "graphic_2d_feature_enable_vulkan": False,
    "graphic_2d_feature_rs_enable_eglimage": True,
    # Upstream only defines rs_enable_parallel_render in the true branch, but
    # render_service references it unconditionally during GN evaluation.
    "graphic_2d_feature_parallel_render_enable": True,
}

RENDER_ENGINE_PATH = (
    "foundation/graphic/graphic_2d/rosen/modules/render_service/composer/"
    "composer_service/external_depend/engine/rs_base_render_engine.cpp"
)

RS_MAIN_THREAD_PATH = (
    "foundation/graphic/graphic_2d/rosen/modules/render_service/core/pipeline/"
    "main_thread/rs_main_thread.cpp"
)


def die(message: str) -> None:
    raise SystemExit(message)


def read_text(path: Path) -> str:
    if not path.is_file():
        die(f"required OpenHarmony source file is missing: {path}")
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def set_config_bool(content: str, option: str) -> str:
    replacement = f"{option}=y"
    pattern = re.compile(
        rf"^(?:{re.escape(option)}=.*|# {re.escape(option)} is not set)$",
        re.MULTILINE,
    )
    if pattern.search(content):
        return pattern.sub(replacement, content)
    if content and not content.endswith("\n"):
        content += "\n"
    return content + replacement + "\n"


def configure_kernel(root: Path, product: str) -> None:
    options = VPN_KERNEL_OPTIONS
    if product != "armv7a_virt":
        options += VPN_64BIT_KERNEL_OPTIONS
    configured = 0
    for relative in SUPPORTED_PRODUCTS[product]:
        path = root / relative
        if not path.exists():
            continue
        content = read_text(path)
        updated = content
        for option in options:
            updated = set_config_bool(updated, option)
        if updated != content:
            write_text(path, updated)
            print(f"configured standard VPN kernel options: {path}")
        configured += 1
    if configured == 0:
        die(f"no QEMU kernel defconfig found for {product}")


def configure_kernel_code_sign_integration(root: Path) -> None:
    path = root / "device/qemu/common/virt_full/kernel/patch/virt.patch"
    content = read_text(path)
    disabled_kconfig = (
        "@@ -129,10 +128,6 @@ config FILE_LOCKING\n"
        " \n"
        ' source "fs/crypto/Kconfig"\n'
        " \n"
        '-source "fs/code_sign/Kconfig"\n'
        "-\n"
        '-source "fs/dec/Kconfig"\n'
        "-\n"
        ' source "fs/verity/Kconfig"\n'
        " \n"
        ' source "fs/notify/Kconfig"\n'
    )
    enabled_kconfig = (
        "@@ -129,10 +128,8 @@ config FILE_LOCKING\n"
        " \n"
        ' source "fs/crypto/Kconfig"\n'
        " \n"
        ' source "fs/code_sign/Kconfig"\n'
        " \n"
        '-source "fs/dec/Kconfig"\n'
        "-\n"
        ' source "fs/verity/Kconfig"\n'
        " \n"
        ' source "fs/notify/Kconfig"\n'
    )
    disabled_makefile = (
        "@@ -30,8 +30,6 @@ obj-$(CONFIG_USERFAULTFD)\t+= userfaultfd.o\n"
        " obj-$(CONFIG_AIO)               += aio.o\n"
        " obj-$(CONFIG_FS_DAX)\t\t+= dax.o\n"
        " obj-$(CONFIG_FS_ENCRYPTION)\t+= crypto/\n"
        "-obj-$(CONFIG_SECURITY_CODE_SIGN)\t+= code_sign/\n"
        "-obj-$(CONFIG_SECURITY_DEC)\t+= dec/\n"
        " obj-$(CONFIG_FS_VERITY)\t\t+= verity/\n"
        " obj-$(CONFIG_FILE_LOCKING)      += locks.o\n"
        " obj-$(CONFIG_BINFMT_MISC)\t+= binfmt_misc.o\n"
    )
    enabled_makefile = (
        "@@ -30,8 +30,7 @@ obj-$(CONFIG_USERFAULTFD)\t+= userfaultfd.o\n"
        " obj-$(CONFIG_AIO)               += aio.o\n"
        " obj-$(CONFIG_FS_DAX)\t\t+= dax.o\n"
        " obj-$(CONFIG_FS_ENCRYPTION)\t+= crypto/\n"
        " obj-$(CONFIG_SECURITY_CODE_SIGN)\t+= code_sign/\n"
        "-obj-$(CONFIG_SECURITY_DEC)\t+= dec/\n"
        " obj-$(CONFIG_FS_VERITY)\t\t+= verity/\n"
        " obj-$(CONFIG_FILE_LOCKING)      += locks.o\n"
        " obj-$(CONFIG_BINFMT_MISC)\t+= binfmt_misc.o\n"
    )
    disabled_xpm_kconfig = (
        "@@ -193,9 +193,7 @@ source \"security/loadpin/Kconfig\"\n"
        " source \"security/yama/Kconfig\"\n"
        " source \"security/safesetid/Kconfig\"\n"
        " source \"security/lockdown/Kconfig\"\n"
        '-source "security/xpm/Kconfig"\n'
        " source \"security/landlock/Kconfig\"\n"
        '-source "security/container_escape_detection/Kconfig"\n'
        " \n"
        " source \"security/integrity/Kconfig\"\n"
    )
    enabled_xpm_kconfig = (
        "@@ -193,9 +193,8 @@ source \"security/loadpin/Kconfig\"\n"
        " source \"security/yama/Kconfig\"\n"
        " source \"security/safesetid/Kconfig\"\n"
        " source \"security/lockdown/Kconfig\"\n"
        ' source "security/xpm/Kconfig"\n'
        " source \"security/landlock/Kconfig\"\n"
        '-source "security/container_escape_detection/Kconfig"\n'
        " \n"
        " source \"security/integrity/Kconfig\"\n"
    )
    disabled_xpm_makefile = (
        "@@ -24,9 +23,7 @@ obj-$(CONFIG_SECURITY_SAFESETID)       += safesetid/\n"
        " obj-$(CONFIG_SECURITY_LOCKDOWN_LSM)\t+= lockdown/\n"
        " obj-$(CONFIG_CGROUPS)\t\t\t+= device_cgroup.o\n"
        " obj-$(CONFIG_BPF_LSM)\t\t\t+= bpf/\n"
        "-obj-$(CONFIG_SECURITY_XPM)\t\t+= xpm/\n"
        " obj-$(CONFIG_SECURITY_LANDLOCK)\t\t+= landlock/\n"
        "-obj-$(CONFIG_SECURITY_CONTAINER_ESCAPE_DETECTION) += container_escape_detection/\n"
        " \n"
        " # Object integrity file lists\n"
    )
    enabled_xpm_makefile = (
        "@@ -24,9 +23,8 @@ obj-$(CONFIG_SECURITY_SAFESETID)       += safesetid/\n"
        " obj-$(CONFIG_SECURITY_LOCKDOWN_LSM)\t+= lockdown/\n"
        " obj-$(CONFIG_CGROUPS)\t\t\t+= device_cgroup.o\n"
        " obj-$(CONFIG_BPF_LSM)\t\t\t+= bpf/\n"
        " obj-$(CONFIG_SECURITY_XPM)\t\t+= xpm/\n"
        " obj-$(CONFIG_SECURITY_LANDLOCK)\t\t+= landlock/\n"
        "-obj-$(CONFIG_SECURITY_CONTAINER_ESCAPE_DETECTION) += container_escape_detection/\n"
        " \n"
        " # Object integrity file lists\n"
    )

    updated = content
    if enabled_kconfig not in updated:
        if disabled_kconfig not in updated:
            die(f"QEMU code-sign Kconfig patch has changed: {path}")
        updated = updated.replace(disabled_kconfig, enabled_kconfig, 1)
    if enabled_makefile not in updated:
        if disabled_makefile not in updated:
            die(f"QEMU code-sign Makefile patch has changed: {path}")
        updated = updated.replace(disabled_makefile, enabled_makefile, 1)
    if enabled_xpm_kconfig not in updated:
        if disabled_xpm_kconfig not in updated:
            die(f"QEMU XPM Kconfig patch has changed: {path}")
        updated = updated.replace(
            disabled_xpm_kconfig, enabled_xpm_kconfig, 1
        )
    if enabled_xpm_makefile not in updated:
        if disabled_xpm_makefile not in updated:
            die(f"QEMU XPM Makefile patch has changed: {path}")
        updated = updated.replace(
            disabled_xpm_makefile, enabled_xpm_makefile, 1
        )
    if updated != content:
        write_text(path, updated)
        print(
            "preserved advanced code-sign and developer-mode XPM "
            f"integration in QEMU kernel: {path}"
        )


def configure_kernel_security_module_copy(root: Path) -> None:
    path = root / "device/qemu/common/virt_full/kernel/build_kernel.sh"
    content = read_text(path)
    xpm_copy = (
        "    cp -arfL  $OHOS_SOURCE_ROOT/kernel/linux/common_modules/xpm "
        "${KERNEL_BUILD_ROOT}/security\n"
    )
    check_dir_copy = (
        "    cp $OHOS_SOURCE_ROOT/kernel/linux/linux-5.10/scripts/"
        "ohos-check-dir.sh ${KERNEL_BUILD_ROOT}/scripts/\n"
    )
    updated = content
    code_sign_copy = (
        "    cp -arfL  $OHOS_SOURCE_ROOT/kernel/linux/common_modules/"
        "code_sign ${KERNEL_BUILD_ROOT}/fs\n"
    )
    if xpm_copy not in updated:
        if code_sign_copy not in updated:
            die(f"QEMU kernel common-module copy block has changed: {path}")
        updated = updated.replace(
            code_sign_copy, code_sign_copy + xpm_copy, 1
        )
    if check_dir_copy not in updated:
        updated = updated.replace(
            xpm_copy, xpm_copy + check_dir_copy, 1
        )
    if updated == content:
        return
    write_text(path, updated)
    print(f"enabled QEMU XPM module and Kconfig helper copy: {path}")


def configure_code_sign_portable_includes(root: Path) -> None:
    path = root / "kernel/linux/common_modules/code_sign/code_sign_misc.c"
    content = read_text(path)
    include = "#include <linux/fs.h>\n"
    if include in content:
        return
    marker = "#include <linux/module.h>\n"
    if marker not in content:
        die(f"code-sign misc includes have changed: {path}")
    updated = content.replace(marker, marker + include, 1)
    write_text(path, updated)
    print(f"enabled portable 32-bit code-sign declarations: {path}")


def configure_code_sign_statx_syscall(root: Path) -> None:
    header = (
        root
        / "base/security/code_signature/interfaces/inner_api/"
        "code_sign_utils/include/stat_utils.h"
    )
    header_content = read_text(header)
    portable_include = "#include <sys/syscall.h>\n"
    architecture_include = "#include <asm/unistd.h>\n"
    updated_header = header_content
    if portable_include not in updated_header:
        if architecture_include not in updated_header:
            die(f"code-sign statx syscall include has changed: {header}")
        updated_header = updated_header.replace(
            architecture_include, portable_include, 1
        )
    if updated_header != header_content:
        write_text(header, updated_header)

    implementation = (
        root
        / "base/security/code_signature/interfaces/inner_api/"
        "code_sign_utils/src/stat_utils.cpp"
    )
    implementation_content = read_text(implementation)
    portable_syscall = "return syscall(SYS_statx,"
    architecture_syscall = "return syscall(__NR_statx,"
    updated_implementation = implementation_content
    if portable_syscall not in updated_implementation:
        if architecture_syscall not in updated_implementation:
            die(
                "code-sign statx syscall implementation has changed: "
                f"{implementation}"
            )
        updated_implementation = updated_implementation.replace(
            architecture_syscall, portable_syscall, 1
        )
    if (
        updated_header != header_content
        or updated_implementation != implementation_content
    ):
        write_text(implementation, updated_implementation)
        print(
            "enabled target-architecture statx syscall selection for "
            f"code-sign: {implementation}"
        )


def configure_key_enable_syscalls(root: Path) -> None:
    path = (
        root
        / "base/security/code_signature/services/key_enable/"
        "utils/src/key_utils.cpp"
    )
    content = read_text(path)
    portable_include = "#include <sys/syscall.h>\n"
    architecture_include = "#include <asm/unistd.h>\n"
    updated = content
    if portable_include not in updated:
        if architecture_include not in updated:
            die(f"key-enable syscall include has changed: {path}")
        updated = updated.replace(
            architecture_include, portable_include, 1
        )

    replacements = (
        ("syscall(__NR_add_key,", "syscall(SYS_add_key,"),
        ("syscall(__NR_keyctl,", "syscall(SYS_keyctl,"),
    )
    for architecture_syscall, portable_syscall in replacements:
        if portable_syscall in updated:
            continue
        if architecture_syscall not in updated:
            die(f"key-enable syscall implementation has changed: {path}")
        updated = updated.replace(
            architecture_syscall, portable_syscall, 1
        )

    if updated != content:
        write_text(path, updated)
        print(
            "enabled target-architecture keyring syscall selection for "
            f"code-sign: {path}"
        )


def configure_x86_64_uapi_headers(root: Path) -> None:
    build_path = root / "third_party/musl/BUILD.gn"
    build_content = read_text(build_path)
    legacy_selection = (
        '      } else {  # aarch64 and x86_64 use same file\n'
        '        file_name = "asm-arm64"\n'
        "      }\n"
    )
    target_selection = (
        '      } else if ("${musl_arch}" == "x86_64") {\n'
        '        file_name = "asm-x86"\n'
        "      } else {  # aarch64\n"
        '        file_name = "asm-arm64"\n'
        "      }\n"
    )
    updated_build = build_content
    if target_selection not in updated_build:
        if legacy_selection not in updated_build:
            die(f"musl architecture UAPI selection has changed: {build_path}")
        updated_build = updated_build.replace(
            legacy_selection, target_selection, 1
        )
        write_text(build_path, updated_build)

    copy_path = root / "third_party/musl/scripts/copy_uapi.sh"
    copy_content = read_text(copy_path)
    legacy_copy = (
        'elif [ ${TARGET_ARCH} = "x86_64" ]; then\n'
        "    mv ${OUT_DIR}/asm-arm64/asm ${OUT_DIR}/asm\n"
        "    rm -rf ${OUT_DIR}/asm-arm64\n"
        "    rm -rf ${OUT_DIR}/asm-arm\n"
    )
    target_copy = (
        'elif [ ${TARGET_ARCH} = "x86_64" ]; then\n'
        "    mv ${OUT_DIR}/asm-x86/asm ${OUT_DIR}/asm\n"
        "    rm -rf ${OUT_DIR}/asm-x86\n"
        "    rm -rf ${OUT_DIR}/asm-arm64\n"
        "    rm -rf ${OUT_DIR}/asm-arm\n"
    )
    updated_copy = copy_content
    if target_copy not in updated_copy:
        if legacy_copy not in updated_copy:
            die(f"musl UAPI copy script has changed: {copy_path}")
        updated_copy = updated_copy.replace(legacy_copy, target_copy, 1)
        write_text(copy_path, updated_copy)

    generator_path = root / "third_party/musl/scripts/generate_uapi.py"
    generator_content = read_text(generator_path)
    legacy_exclude = (
        '    exclude_pattern = "^asm$|^scsi$" if uapi_from == "make" '
        'else "^asm-arm$|^asm-arm64$|^scsi$"\n'
    )
    target_exclude = (
        '    exclude_pattern = "^asm$|^scsi$" if uapi_from == "make" '
        'else "^asm-(arm|arm64|x86|riscv|loongarch)$|^scsi$"\n'
    )
    updated_generator = generator_content
    if target_exclude not in updated_generator:
        if legacy_exclude not in updated_generator:
            die(f"musl UAPI generator exclusions have changed: {generator_path}")
        updated_generator = updated_generator.replace(
            legacy_exclude, target_exclude, 1
        )
        write_text(generator_path, updated_generator)

    if (
        updated_build != build_content
        or updated_copy != copy_content
        or updated_generator != generator_content
    ):
        print(
            "enabled native x86_64 Linux UAPI headers for the musl "
            f"sysroot: {build_path}"
        )


def configure_fsverity_portable_math(root: Path) -> None:
    path = root / "kernel/linux/linux-6.6/fs/verity/enable.c"
    content = read_text(path)
    updated = content
    math_include = "#include <linux/math64.h>\n"
    if math_include not in updated:
        marker = "#include <crypto/hash.h>\n"
        if marker not in updated:
            die(f"fs-verity includes have changed: {path}")
        updated = updated.replace(marker, marker + math_include, 1)

    updated = updated.replace(
        "offset / params->block_size",
        "div_u64(offset, params->block_size)",
    )
    updated = updated.replace(
        "(offset - tree_offset) / params->block_size,",
        "div_u64(offset - tree_offset, params->block_size),",
        1,
    )

    unsafe_alignment_check = (
        "\tif (arg.tree_offset % arg.block_size != 0)\n"
        "\t\treturn -EINVAL;\n"
        "\n"
        "\tif (!is_power_of_2(arg.block_size))\n"
        "\t\treturn -EINVAL;\n"
    )
    portable_alignment_check = (
        "\tif (!is_power_of_2(arg.block_size))\n"
        "\t\treturn -EINVAL;\n"
        "\n"
        "\tif (arg.tree_offset & (arg.block_size - 1))\n"
        "\t\treturn -EINVAL;\n"
    )
    if unsafe_alignment_check in updated:
        updated = updated.replace(
            unsafe_alignment_check, portable_alignment_check, 1
        )
    elif portable_alignment_check not in updated:
        die(f"fs-verity code-sign alignment check has changed: {path}")

    if updated != content:
        write_text(path, updated)
        print(f"enabled portable 32-bit fs-verity math: {path}")


def configure_hck_jit_error_initialization(root: Path) -> None:
    path = root / "kernel/linux/linux-6.6/mm/mprotect.c"
    content = read_text(path)
    function_marker = (
        "static int do_mprotect_pkey(unsigned long start, size_t len,\n"
        "\t\tunsigned long prot, int pkey)\n"
        "{\n"
        "\tunsigned long nstart, end, tmp, reqprot;\n"
        "\tstruct vm_area_struct *vma, *prev;\n"
    )
    legacy = function_marker + "\tint error;\n"
    fixed = function_marker + "\tint error = 0;\n"
    if fixed in content:
        return
    if legacy not in content:
        die(f"Linux HCK mprotect initialization has changed: {path}")
    updated = content.replace(legacy, fixed, 1)
    write_text(path, updated)
    print(f"initialized optional HCK JIT mprotect result: {path}")


def configure_xpm_high_vma_flags(root: Path) -> None:
    path = root / "kernel/linux/common_modules/xpm/Kconfig"
    content = read_text(path)
    selection = "\tselect ARCH_USES_HIGH_VMA_FLAGS\n"
    if selection in content:
        return
    dependency = "\tdepends on SECURITY_CODE_SIGN\n"
    if dependency not in content:
        die(f"XPM Kconfig dependencies have changed: {path}")
    updated = content.replace(
        dependency, dependency + selection, 1
    )
    write_text(path, updated)
    print(f"enabled XPM high VMA flag allocation: {path}")


def configure_xpm_pageflag_names(root: Path) -> None:
    path = (
        root
        / "kernel/linux/linux-6.6/include/trace/events/mmflags.h"
    )
    content = read_text(path)
    readonly_name = "IF_HAVE_PG_XPM_INTEGRITY(xpm_readonly)"
    if readonly_name in content:
        return
    marker = re.search(
        r"^IF_HAVE_PG_PURGEABLE\(purgeable\).*$",
        content,
        re.MULTILINE,
    )
    if marker is None:
        die(f"Linux 6.6 page flag name table has changed: {path}")
    xpm_names = (
        "\nIF_HAVE_PG_XPM_INTEGRITY(xpm_readonly)"
        "\t\t\t\t\t\\"
        "\nIF_HAVE_PG_XPM_INTEGRITY(xpm_writetainted)"
        "\t\t\t\t\\"
    )
    updated = (
        content[:marker.end()]
        + xpm_names
        + content[marker.end():]
    )
    write_text(path, updated)
    print(f"registered XPM page flag names: {path}")


def set_gni_bool(content: str, name: str, value: bool) -> str:
    replacement = f"  {name} = {'true' if value else 'false'}"
    pattern = re.compile(rf"^[ \t]*{re.escape(name)}[ \t]*=.*$", re.MULTILINE)
    if not pattern.search(content):
        die(f"OpenHarmony netmanager_ext option is missing: {name}")
    return pattern.sub(replacement, content)


def configure_netmanager_ext(root: Path) -> None:
    path = root / "foundation/communication/netmanager_ext/netmanager_ext_config.gni"
    content = read_text(path)
    updated = set_gni_bool(content, "netmanager_ext_feature_vpn", True)
    updated = set_gni_bool(updated, "netmanager_ext_feature_vpnext", True)
    if updated != content:
        write_text(path, updated)
        print(f"enabled VPN and VpnExtension features: {path}")


def configure_userdata_code_sign_fs(root: Path) -> None:
    userdata_config = root / "vendor/ohemu/virt/image_conf/userdata_image_conf.txt"
    config = read_text(userdata_config)
    lines = [
        line for line in config.splitlines()
        if line.strip() != "--verity"
    ]
    replaced = False
    for index, line in enumerate(lines):
        if line.strip() == "--fs_type=ext4":
            lines[index] = "--fs_type=f2fs"
            replaced = True
        elif line.strip() == "--fs_type=f2fs":
            replaced = True
    if not replaced:
        die(f"QEMU userdata filesystem type is missing: {userdata_config}")
    updated = "\n".join(lines) + "\n"
    if updated != config:
        write_text(userdata_config, updated)
        print(
            "enabled F2FS verity/code-sign ioctl support for QEMU userdata: "
            f"{userdata_config}"
        )


def configure_vpn_dialog_profile(root: Path) -> None:
    if not VPN_DIALOG_PROFILE_ASSET.is_file():
        die(f"QEMU VpnDialog profile asset is missing: {VPN_DIALOG_PROFILE_ASSET}")
    try:
        encoded = "".join(
            VPN_DIALOG_PROFILE_ASSET.read_text(encoding="ascii").split()
        )
        profile = base64.b64decode(encoded, validate=True)
    except (ValueError, UnicodeError) as error:
        die(f"invalid QEMU VpnDialog profile asset: {error}")

    digest = hashlib.sha256(profile).hexdigest()
    if digest != VPN_DIALOG_PROFILE_SHA256:
        die(
            "QEMU VpnDialog profile checksum mismatch: "
            f"expected {VPN_DIALOG_PROFILE_SHA256}, got {digest}"
        )

    destination = (
        root
        / "foundation/communication/netmanager_ext/frameworks/vpn_dialog/"
        "dialog_ui/signature/vpndialog.p7b"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and destination.read_bytes() == profile:
        return
    destination.write_bytes(profile)
    print(f"installed the non-expired QEMU VpnDialog profile: {destination}")


def configure_vpn_dialog_build(root: Path) -> None:
    dialog_build = (
        root
        / "foundation/communication/netmanager_ext/frameworks/vpn_dialog/"
        "dialog_ui/vpn_dialog/BUILD.gn"
    )
    read_text(dialog_build)

    path = root / "applications/standard/hap/ohos.build"
    document = json.loads(read_text(path))
    try:
        modules = document["parts"]["prebuilt_hap"]["module_list"]
    except (KeyError, TypeError):
        die(f"unexpected applications HAP build structure: {path}")
    if not isinstance(modules, list):
        die(f"applications HAP module_list is not an array: {path}")
    if VPN_DIALOG_TARGET not in modules:
        modules.append(VPN_DIALOG_TARGET)
        write_text(path, json.dumps(document, ensure_ascii=False, indent=2) + "\n")
        print(f"added the VPN authorization dialog build target: {path}")


def require_json_entry(path: Path, predicate, description: str) -> None:
    document = json.loads(read_text(path))
    entries = document.get("install_list") if isinstance(document, dict) else None
    if not isinstance(entries, list):
        die(f"expected an install_list array in {path}")
    if not any(isinstance(entry, dict) and predicate(entry) for entry in entries):
        die(f"{description} is missing from {path}")


def set_component_bool_feature(features: list, name: str, value: bool) -> bool:
    assignment = f"{name} = {'true' if value else 'false'}"
    pattern = re.compile(rf"^[ \t]*{re.escape(name)}[ \t]*=")
    matching = [
        index
        for index, feature in enumerate(features)
        if isinstance(feature, str) and pattern.match(feature)
    ]
    if not matching:
        features.append(assignment)
        return True

    changed = features[matching[0]] != assignment or len(matching) > 1
    features[matching[0]] = assignment
    for index in reversed(matching[1:]):
        del features[index]
    return changed


def configure_portable_qemu_graphics(root: Path, relative: str) -> None:
    path = root / relative
    document = json.loads(read_text(path))
    subsystems = document.get("subsystems") if isinstance(document, dict) else None
    if not isinstance(subsystems, list):
        die(f"expected a subsystems array in {path}")

    graphic_2d = None
    for subsystem in subsystems:
        if not isinstance(subsystem, dict) or subsystem.get("subsystem") != "graphic":
            continue
        for component in subsystem.get("components", []):
            if (
                isinstance(component, dict)
                and component.get("component") == "graphic_2d"
            ):
                graphic_2d = component
                break
    if graphic_2d is None:
        die(f"graphic_2d is missing from QEMU product configuration: {path}")

    features = graphic_2d.get("features")
    if not isinstance(features, list):
        die(f"graphic_2d features are not an array in {path}")
    changed = False
    for name, value in QEMU_GRAPHICS_FEATURES.items():
        changed |= set_component_bool_feature(features, name, value)
    if changed:
        write_text(path, json.dumps(document, ensure_ascii=False, indent=2) + "\n")
        print(f"configured portable software rendering for QEMU: {path}")


def configure_portable_render_context(root: Path) -> None:
    path = root / RENDER_ENGINE_PATH
    content = read_text(path)
    supported_guards = (
        "#if (defined RS_ENABLE_GL) || (defined RS_ENABLE_VK)\n"
        "    renderContext_ = RenderContext::Create();",
        "#if (defined(RS_ENABLE_GL) && defined(RS_ENABLE_EGLIMAGE)) || "
        "defined(RS_ENABLE_VK)\n"
        "    renderContext_ = RenderContext::Create();",
    )
    render_context_guard = supported_guards[0]
    legacy_portable_guard = (
        "#if defined(RS_ENABLE_VK)\n"
        "    renderContext_ = RenderContext::Create();"
    )
    updated = content
    if render_context_guard not in updated:
        for supported_guard in (*supported_guards[1:], legacy_portable_guard):
            if supported_guard in updated:
                updated = updated.replace(
                    supported_guard, render_context_guard, 1
                )
                break
        else:
            die(f"RenderService context initialization guard has changed: {path}")

    gl_gpu_setup = (
        "#else\n"
        "    renderContext_->SetUpGpuContext();\n"
        "#endif\n"
        "#endif // RS_ENABLE_GL || RS_ENABLE_VK"
    )
    portable_gl_gpu_setup = (
        "#else\n"
        '    RS_LOGI("QEMU portable raster composition skips GPU context setup");\n'
        "#endif\n"
        "#endif // RS_ENABLE_GL || RS_ENABLE_VK"
    )
    if portable_gl_gpu_setup not in updated:
        if gl_gpu_setup not in updated:
            die(f"RenderService OpenGL initialization has changed: {path}")
        updated = updated.replace(gl_gpu_setup, portable_gl_gpu_setup, 1)

    manager_guard = (
        "#if (defined(RS_ENABLE_EGLIMAGE) && defined(RS_ENABLE_GPU)) || "
        "defined(RS_ENABLE_VK)\n"
        "    imageManager_ = RSImageManager::Create(renderContext_);"
    )
    portable_manager_guard = (
        "#if defined(RS_ENABLE_VK)\n"
        "    imageManager_ = RSImageManager::Create(renderContext_);"
    )
    if portable_manager_guard not in updated:
        if manager_guard not in updated:
            die(f"RenderService image manager guard has changed: {path}")
        updated = updated.replace(manager_guard, portable_manager_guard, 1)

    force_cpu = "    bool forceCPU = false;"
    portable_force_cpu = "    bool forceCPU = true;"
    if portable_force_cpu not in updated:
        if force_cpu not in updated:
            die(f"RenderService CPU composition default has changed: {path}")
        updated = updated.replace(force_cpu, portable_force_cpu, 1)

    if updated != content:
        write_text(path, updated)
        print(f"configured portable raster composition for QEMU: {path}")


def configure_portable_main_thread(root: Path) -> None:
    path = root / RS_MAIN_THREAD_PATH
    content = read_text(path)
    gpu_cache_setup = """        auto gpuContext = isUniRender_? GetRenderEngine()->GetRenderContext()->GetDrGPUContext() :
            renderEngine_->GetRenderContext()->GetDrGPUContext();
        if (gpuContext == nullptr) {
            RS_LOGE("Init gpuContext is nullptr!");
            return;
        }
        int32_t maxResources = 0;
        size_t maxResourcesSize = 0;
        gpuContext->GetResourceCacheLimits(&maxResources, &maxResourcesSize);
        if (maxResourcesSize > 0) {
            gpuContext->SetResourceCacheLimits(cacheLimitsTimes * maxResources, cacheLimitsTimes *
                std::fmin(maxResourcesSize, DEFAULT_SKIA_CACHE_SIZE));
        } else {
            gpuContext->SetResourceCacheLimits(DEFAULT_SKIA_CACHE_COUNT, DEFAULT_SKIA_CACHE_SIZE);
        }"""
    portable_gpu_cache_setup = """        auto gpuContext = isUniRender_? GetRenderEngine()->GetRenderContext()->GetDrGPUContext() :
            renderEngine_->GetRenderContext()->GetDrGPUContext();
        if (gpuContext == nullptr) {
            RS_LOGI("GPU context is unavailable; continuing with QEMU CPU raster composition");
        } else {
            int32_t maxResources = 0;
            size_t maxResourcesSize = 0;
            gpuContext->GetResourceCacheLimits(&maxResources, &maxResourcesSize);
            if (maxResourcesSize > 0) {
                gpuContext->SetResourceCacheLimits(cacheLimitsTimes * maxResources, cacheLimitsTimes *
                    std::fmin(maxResourcesSize, DEFAULT_SKIA_CACHE_SIZE));
            } else {
                gpuContext->SetResourceCacheLimits(DEFAULT_SKIA_CACHE_COUNT, DEFAULT_SKIA_CACHE_SIZE);
            }
        }"""

    updated = content
    if portable_gpu_cache_setup not in updated:
        if gpu_cache_setup not in updated:
            die(f"RenderService GPU cache initialization has changed: {path}")
        updated = updated.replace(gpu_cache_setup, portable_gpu_cache_setup, 1)

    if updated != content:
        write_text(path, updated)
        print(f"configured CPU-raster main-thread startup for QEMU: {path}")


def validate_product_integration(root: Path, products: list[str]) -> None:
    common_files = set()
    for product in products:
        if product == "x86_64_virt":
            common_files.add("vendor/ohemu/virt/virt_common_x86_64.json")
        else:
            common_files.add("vendor/ohemu/virt/virt_common.json")

    for relative in sorted(common_files):
        configure_portable_qemu_graphics(root, relative)
        path = root / relative
        document = json.loads(read_text(path))
        subsystems = document.get("subsystems") if isinstance(document, dict) else None
        if not isinstance(subsystems, list):
            die(f"expected a subsystems array in {path}")
        components = [
            component.get("component")
            for subsystem in subsystems
            if isinstance(subsystem, dict)
            for component in subsystem.get("components", [])
            if isinstance(component, dict)
        ]
        if "netmanager_ext" not in components:
            die(f"netmanager_ext is missing from QEMU product configuration: {path}")

    install_list = root / "vendor/ohemu/virt/preinstall-config/install_list.json"
    require_json_entry(
        install_list,
        lambda entry: entry.get("app_dir") == "/system/app/VpnDialog"
        and entry.get("removable") is False,
        "non-removable /system/app/VpnDialog",
    )

    capability_list = (
        root / "vendor/ohemu/virt/preinstall-config/install_list_capability.json"
    )
    require_json_entry(
        capability_list,
        lambda entry: entry.get("bundleName") == "com.ohos.vpndialog"
        and entry.get("allowAppUsePrivilegeExtension") is True,
        "com.ohos.vpndialog privileged-extension capability",
    )

    settings_data = root / "applications/standard/hap/SettingsData.hap"
    if not settings_data.is_file():
        die(f"SettingsData HAP is missing: {settings_data}")


def main() -> None:
    if len(sys.argv) < 2:
        die(
            "usage: apply.py OHOS_ROOT "
            "[armv7a_virt|arm64_virt|x86_64_virt ...]"
        )
    root = Path(sys.argv[1]).resolve()
    products = sys.argv[2:] or list(SUPPORTED_PRODUCTS)
    unsupported = sorted(set(products) - set(SUPPORTED_PRODUCTS))
    if unsupported:
        die(f"unsupported QEMU VPN products: {', '.join(unsupported)}")

    for product in products:
        configure_kernel(root, product)
    configure_kernel_code_sign_integration(root)
    configure_kernel_security_module_copy(root)
    configure_code_sign_portable_includes(root)
    configure_code_sign_statx_syscall(root)
    configure_key_enable_syscalls(root)
    if "x86_64_virt" in products:
        configure_x86_64_uapi_headers(root)
    configure_fsverity_portable_math(root)
    configure_hck_jit_error_initialization(root)
    configure_xpm_high_vma_flags(root)
    configure_xpm_pageflag_names(root)
    configure_netmanager_ext(root)
    configure_userdata_code_sign_fs(root)
    configure_vpn_dialog_profile(root)
    configure_vpn_dialog_build(root)
    configure_portable_render_context(root)
    configure_portable_main_thread(root)
    validate_product_integration(root, products)
    print(f"standard VPN support configured for: {' '.join(products)}")


if __name__ == "__main__":
    main()
