#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
APPLY="${ROOT}/overlays/standard_qemu_vpn/apply.sh"
VERIFY_HAP_PROFILE="${ROOT}/scripts/verify_hap_profile.py"
TEST_ROOT="$(mktemp -d)"
OHOS_ROOT="${TEST_ROOT}/openharmony"

cleanup() {
  rm -rf "${TEST_ROOT}"
}
trap cleanup EXIT

mkdir -p \
  "${OHOS_ROOT}/device/qemu/common/virt_full/kernel/configs" \
  "${OHOS_ROOT}/device/qemu/common/virt_full/kernel/patch" \
  "${OHOS_ROOT}/base/security/code_signature/interfaces/inner_api/code_sign_utils/include" \
  "${OHOS_ROOT}/base/security/code_signature/interfaces/inner_api/code_sign_utils/src" \
  "${OHOS_ROOT}/base/security/code_signature/services/key_enable/utils/src" \
  "${OHOS_ROOT}/kernel/linux/common_modules/code_sign" \
  "${OHOS_ROOT}/kernel/linux/common_modules/xpm" \
  "${OHOS_ROOT}/kernel/linux/linux-6.6/fs/verity" \
  "${OHOS_ROOT}/kernel/linux/linux-6.6/include/trace/events" \
  "${OHOS_ROOT}/kernel/linux/linux-6.6/mm" \
  "${OHOS_ROOT}/third_party/musl/scripts" \
  "${OHOS_ROOT}/foundation/communication/netmanager_ext/frameworks/vpn_dialog/dialog_ui/vpn_dialog" \
  "${OHOS_ROOT}/foundation/graphic/graphic_2d/rosen/modules/render_service/composer/composer_service/external_depend/engine" \
  "${OHOS_ROOT}/foundation/graphic/graphic_2d/rosen/modules/render_service/core/pipeline/main_thread" \
  "${OHOS_ROOT}/applications/standard/hap" \
  "${OHOS_ROOT}/build/ohos/images/mkimage" \
  "${OHOS_ROOT}/vendor/ohemu/virt/image_conf" \
  "${OHOS_ROOT}/vendor/ohemu/virt/preinstall-config"

for config in \
  arm_virt_defconfig \
  configs/arm_virt_defconfig \
  arm64_virt_defconfig \
  x86_64_virt_defconfig
do
  mkdir -p "$(dirname "${OHOS_ROOT}/device/qemu/common/virt_full/kernel/${config}")"
  cat >"${OHOS_ROOT}/device/qemu/common/virt_full/kernel/${config}" <<'EOF'
CONFIG_NET=y
CONFIG_UNIX=y
CONFIG_INET=y
# CONFIG_NAMESPACES is not set
# CONFIG_NET_NS is not set
# CONFIG_NETDEVICES is not set
# CONFIG_TUN is not set
# CONFIG_IP_ADVANCED_ROUTER is not set
# CONFIG_IP_MULTIPLE_TABLES is not set
CONFIG_IPV6=m
# CONFIG_IPV6_MULTIPLE_TABLES is not set
CONFIG_SYSTEM_DATA_VERIFICATION=y
# CONFIG_FS_VERITY is not set
EOF
done

cat >"${OHOS_ROOT}/device/qemu/common/virt_full/kernel/patch/virt.patch" <<'EOF'
diff --git a/fs/Kconfig b/fs/Kconfig
index dc6d08423..2f7b06ce8 100644
--- a/fs/Kconfig
+++ b/fs/Kconfig
@@ -129,10 +128,6 @@ config FILE_LOCKING
__PATCH_BLANK__
 source "fs/crypto/Kconfig"
__PATCH_BLANK__
-source "fs/code_sign/Kconfig"
-
-source "fs/dec/Kconfig"
-
 source "fs/verity/Kconfig"
__PATCH_BLANK__
 source "fs/notify/Kconfig"
diff --git a/fs/Makefile b/fs/Makefile
index 66438333e..8b9107451 100644
--- a/fs/Makefile
+++ b/fs/Makefile
@@ -30,8 +30,6 @@ obj-$(CONFIG_USERFAULTFD)	+= userfaultfd.o
 obj-$(CONFIG_AIO)               += aio.o
 obj-$(CONFIG_FS_DAX)		+= dax.o
 obj-$(CONFIG_FS_ENCRYPTION)	+= crypto/
-obj-$(CONFIG_SECURITY_CODE_SIGN)	+= code_sign/
-obj-$(CONFIG_SECURITY_DEC)	+= dec/
 obj-$(CONFIG_FS_VERITY)		+= verity/
 obj-$(CONFIG_FILE_LOCKING)      += locks.o
 obj-$(CONFIG_BINFMT_MISC)	+= binfmt_misc.o
diff --git a/security/Kconfig b/security/Kconfig
index 89e5dbcb46e0..52c9af08ad35 100644
--- a/security/Kconfig
+++ b/security/Kconfig
@@ -193,9 +193,7 @@ source "security/loadpin/Kconfig"
 source "security/yama/Kconfig"
 source "security/safesetid/Kconfig"
 source "security/lockdown/Kconfig"
-source "security/xpm/Kconfig"
 source "security/landlock/Kconfig"
-source "security/container_escape_detection/Kconfig"
__PATCH_BLANK__
 source "security/integrity/Kconfig"
diff --git a/security/Makefile b/security/Makefile
index 1fbed3e27..18121f8f8 100644
--- a/security/Makefile
+++ b/security/Makefile
@@ -24,9 +23,7 @@ obj-$(CONFIG_SECURITY_SAFESETID)       += safesetid/
 obj-$(CONFIG_SECURITY_LOCKDOWN_LSM)	+= lockdown/
 obj-$(CONFIG_CGROUPS)			+= device_cgroup.o
 obj-$(CONFIG_BPF_LSM)			+= bpf/
-obj-$(CONFIG_SECURITY_XPM)		+= xpm/
 obj-$(CONFIG_SECURITY_LANDLOCK)		+= landlock/
-obj-$(CONFIG_SECURITY_CONTAINER_ESCAPE_DETECTION) += container_escape_detection/
__PATCH_BLANK__
 # Object integrity file lists
EOF
sed -i.bak 's/^__PATCH_BLANK__$/ /' \
  "${OHOS_ROOT}/device/qemu/common/virt_full/kernel/patch/virt.patch"
rm -f "${OHOS_ROOT}/device/qemu/common/virt_full/kernel/patch/virt.patch.bak"

cat >"${OHOS_ROOT}/device/qemu/common/virt_full/kernel/build_kernel.sh" <<'EOF'
#!/usr/bin/env bash
    cp -arfL  $OHOS_SOURCE_ROOT/kernel/linux/common_modules/memory_security ${KERNEL_BUILD_ROOT}/fs/proc
    cp -arfL  $OHOS_SOURCE_ROOT/kernel/linux/common_modules/code_sign ${KERNEL_BUILD_ROOT}/fs
    cp -arfL  $OHOS_SOURCE_ROOT/kernel/linux/common_modules/dec ${KERNEL_BUILD_ROOT}/fs
EOF

cat >"${OHOS_ROOT}/kernel/linux/common_modules/xpm/Kconfig" <<'EOF'
menu "Executable permission manager"
config SECURITY_XPM
	def_bool $(success, $(srctree)/scripts/ohos-check-dir.sh $(srctree)/security/xpm)
	depends on 64BIT
	depends on SECURITY_CODE_SIGN
endmenu
EOF

cat >"${OHOS_ROOT}/kernel/linux/common_modules/code_sign/code_sign_misc.c" <<'EOF'
#include <linux/module.h>
#include <linux/cdev.h>
#include <linux/miscdevice.h>
#include <linux/hck/lite_hck_code_sign.h>
EOF

cat >"${OHOS_ROOT}/base/security/code_signature/interfaces/inner_api/code_sign_utils/include/stat_utils.h" <<'EOF'
#ifndef CODE_SIGN_STAT_UTILS_H
#define CODE_SIGN_STAT_UTILS_H
#include <unistd.h>
#include <asm/unistd.h>
#include <linux/stat.h>
int Statx(int dfd, const char *filename, int flags,
    unsigned int mask, struct statx *buffer);
#endif
EOF

cat >"${OHOS_ROOT}/base/security/code_signature/interfaces/inner_api/code_sign_utils/src/stat_utils.cpp" <<'EOF'
#include "stat_utils.h"
int Statx(int dfd, const char *filename, int flags,
    unsigned int mask, struct statx *buffer)
{
    return syscall(__NR_statx, dfd, filename, flags, mask, buffer);
}
EOF

cat >"${OHOS_ROOT}/base/security/code_signature/services/key_enable/utils/src/key_utils.cpp" <<'EOF'
#include "key_utils.h"
#include <asm/unistd.h>
#include <unistd.h>
KeySerial AddKey(const char *type, const char *description,
    const unsigned char *payload, size_t pLen, KeySerial ringId)
{
    return syscall(__NR_add_key, type, description, payload, pLen, ringId);
}
KeySerial KeyctlRestrictKeyring(KeySerial ringId, const char *type,
    const char *restriction)
{
    return syscall(__NR_keyctl, 29, ringId, type, restriction);
}
EOF

cat >"${OHOS_ROOT}/third_party/musl/BUILD.gn" <<'EOF'
      if ("${musl_arch}" == "arm") {
        file_name = "asm-arm"
      } else if ("${musl_arch}" == "riscv64") {
        file_name = "asm-riscv"
      } else if ("${musl_arch}" == "loongarch64") {
        file_name = "asm-loongarch"
      } else {  # aarch64 and x86_64 use same file
        file_name = "asm-arm64"
      }
EOF

cat >"${OHOS_ROOT}/third_party/musl/scripts/copy_uapi.sh" <<'EOF'
if [ ${TARGET_ARCH} = "arm" ]; then
    mv ${OUT_DIR}/asm-arm/asm ${OUT_DIR}/asm
elif [ ${TARGET_ARCH} = "x86_64" ]; then
    mv ${OUT_DIR}/asm-arm64/asm ${OUT_DIR}/asm
    rm -rf ${OUT_DIR}/asm-arm64
    rm -rf ${OUT_DIR}/asm-arm
elif [ ${TARGET_ARCH} = "riscv64" ]; then
    mv ${OUT_DIR}/asm-riscv/asm ${OUT_DIR}/asm
fi
EOF

cat >"${OHOS_ROOT}/third_party/musl/scripts/generate_uapi.py" <<'EOF'
def configure(uapi_from):
    exclude_pattern = "^asm$|^scsi$" if uapi_from == "make" else "^asm-arm$|^asm-arm64$|^scsi$"
    return exclude_pattern
EOF

cat >"${OHOS_ROOT}/kernel/linux/linux-6.6/fs/verity/enable.c" <<'EOF'
#include <crypto/hash.h>
static int code_sign_copy_merkle_tree(void)
{
	err = log_error(err, offset / params->block_size);
	err = log_short_read(offset / params->block_size);
	err = write_merkle_tree_block(inode, buffer.data,
		(offset - tree_offset) / params->block_size,
		params);
}
static int fsverity_ioctl_enable_code_sign(void)
{
	if (arg.tree_offset % arg.block_size != 0)
		return -EINVAL;

	if (!is_power_of_2(arg.block_size))
		return -EINVAL;
}
EOF

cat >"${OHOS_ROOT}/kernel/linux/linux-6.6/mm/mprotect.c" <<'EOF'
static int do_mprotect_pkey(unsigned long start, size_t len,
		unsigned long prot, int pkey)
{
	unsigned long nstart, end, tmp, reqprot;
	struct vm_area_struct *vma, *prev;
	int error;
	const int grows = prot & (PROT_GROWSDOWN|PROT_GROWSUP);

	start = untagged_addr(start);

	if (prot & PROT_EXEC) {
		CALL_HCK_LITE_HOOK(find_jit_memory_lhck, current, start, len, &error);
		if (error) {
			pr_info("JITINFO: mprotect protection triggered");
			return error;
		}
	}
}
EOF

cat >"${OHOS_ROOT}/kernel/linux/linux-6.6/include/trace/events/mmflags.h" <<'EOF'
#define __def_pageflag_names \
	DEF_PAGEFLAG_NAME(unevictable) \
IF_HAVE_PG_PURGEABLE(purgeable)						\
IF_HAVE_PG_MLOCK(mlocked)
EOF

cat >"${OHOS_ROOT}/foundation/communication/netmanager_ext/netmanager_ext_config.gni" <<'EOF'
declare_args() {
  netmanager_ext_feature_vpn = false
  netmanager_ext_feature_vpnext = false
}
EOF
: >"${OHOS_ROOT}/foundation/communication/netmanager_ext/frameworks/vpn_dialog/dialog_ui/vpn_dialog/BUILD.gn"
: >"${OHOS_ROOT}/applications/standard/hap/SettingsData.hap"

cat >"${OHOS_ROOT}/build/ohos/images/mkimage/mkextimage.py" <<'EOF'
def args_parse(parser):
    parser.add_argument("--encrypt", help="The fscrypt support.")


def build_run_mke2fs(args):
    mke2fs_opts = ""
    is_data = "data" in args.mount_point
    if is_data:
        mke2fs_opts += " -O encrypt"
    return mke2fs_opts
EOF

cat >"${OHOS_ROOT}/vendor/ohemu/virt/image_conf/userdata_image_conf.txt" <<'EOF'
/data
2147483648
--fs_type=ext4
EOF

cat >"${OHOS_ROOT}/foundation/graphic/graphic_2d/rosen/modules/render_service/composer/composer_service/external_depend/engine/rs_base_render_engine.cpp" <<'EOF'
void RSBaseRenderEngine::Init(RenderEngineType type)
{
#if (defined RS_ENABLE_GL) || (defined RS_ENABLE_VK)
    renderContext_ = RenderContext::Create();
    renderContext_->Init();
#if defined(RS_ENABLE_VK)
    renderContext_->SetUpGpuContext(skContext_);
#else
    renderContext_->SetUpGpuContext();
#endif
#endif // RS_ENABLE_GL || RS_ENABLE_VK
#if (defined(RS_ENABLE_EGLIMAGE) && defined(RS_ENABLE_GPU)) || defined(RS_ENABLE_VK)
    imageManager_ = RSImageManager::Create(renderContext_);
#endif
}

bool RSBaseRenderEngine::NeedForceCPU(const std::vector<RSLayerPtr>& layers)
{
    bool forceCPU = false;
    return forceCPU;
}
EOF

cat >"${OHOS_ROOT}/foundation/graphic/graphic_2d/rosen/modules/render_service/core/pipeline/main_thread/rs_main_thread.cpp" <<'EOF'
void RSMainThread::Init()
{
#ifdef RS_ENABLE_GL
    if (RSSystemProperties::GetGpuApiType() == GpuApiType::OPENGL) {
        int cacheLimitsTimes = 3;
        auto gpuContext = isUniRender_? GetRenderEngine()->GetRenderContext()->GetDrGPUContext() :
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
        }
    }
#endif // RS_ENABLE_GL
}
EOF

cat >"${OHOS_ROOT}/applications/standard/hap/ohos.build" <<'EOF'
{
  "parts": {
    "prebuilt_hap": {
      "module_list": [
        "//applications/standard/hap"
      ]
    }
  }
}
EOF

cat >"${OHOS_ROOT}/vendor/ohemu/virt/virt_common.json" <<'EOF'
{
  "subsystems": [
    {
      "subsystem": "graphic",
      "components": [
        {
          "component": "graphic_2d",
          "features": [
            "graphic_2d_feature_ace_enable_gpu = true",
            "graphic_2d_feature_rs_enable_eglimage = true",
            "graphic_2d_feature_parallel_render_enable = true"
          ]
        }
      ]
    },
    {
      "subsystem": "communication",
      "components": [
        {"component": "netmanager_ext", "features": []}
      ]
    }
  ]
}
EOF
cp \
  "${OHOS_ROOT}/vendor/ohemu/virt/virt_common.json" \
  "${OHOS_ROOT}/vendor/ohemu/virt/virt_common_x86_64.json"

cat >"${OHOS_ROOT}/vendor/ohemu/virt/preinstall-config/install_list.json" <<'EOF'
{
  "install_list": [
    {
      "app_dir": "/system/app/VpnDialog",
      "removable": false
    }
  ]
}
EOF

cat >"${OHOS_ROOT}/vendor/ohemu/virt/preinstall-config/install_list_capability.json" <<'EOF'
{
  "install_list": [
    {
      "bundleName": "com.ohos.vpndialog",
      "allowAppUsePrivilegeExtension": true
    }
  ]
}
EOF

bash "${APPLY}" \
  --source-root "${OHOS_ROOT}" \
  --product armv7a_virt \
  --product arm64_virt \
  --product x86_64_virt \
  >/dev/null

for config in \
  arm_virt_defconfig \
  configs/arm_virt_defconfig \
  arm64_virt_defconfig \
  x86_64_virt_defconfig
do
  path="${OHOS_ROOT}/device/qemu/common/virt_full/kernel/${config}"
  for option in \
    CONFIG_NAMESPACES \
    CONFIG_NET_NS \
    CONFIG_NETDEVICES \
    CONFIG_TUN \
    CONFIG_IP_ADVANCED_ROUTER \
    CONFIG_IP_MULTIPLE_TABLES \
    CONFIG_IPV6 \
    CONFIG_IPV6_MULTIPLE_TABLES \
    CONFIG_FS_VERITY \
    CONFIG_FS_VERITY_BUILTIN_SIGNATURES \
    CONFIG_SECURITY_CODE_SIGN \
    CONFIG_HCK \
    CONFIG_HCK_VENDOR_HOOKS \
    CONFIG_CRYPTO_ECC \
    CONFIG_CRYPTO_ECDSA \
    CONFIG_CRYPTO_SHA256 \
    CONFIG_FS_ENCRYPTION \
    CONFIG_F2FS_FS \
    CONFIG_F2FS_FS_XATTR \
    CONFIG_F2FS_FS_POSIX_ACL \
    CONFIG_F2FS_FS_SECURITY \
    CONFIG_QUOTA \
    CONFIG_QUOTACTL
  do
    grep -qx "${option}=y" "${path}"
  done
done

for config in arm64_virt_defconfig x86_64_virt_defconfig
do
  path="${OHOS_ROOT}/device/qemu/common/virt_full/kernel/${config}"
  grep -qx 'CONFIG_ARCH_USES_HIGH_VMA_FLAGS=y' "${path}"
  grep -qx 'CONFIG_SECURITY_XPM=y' "${path}"
  grep -qx 'CONFIG_DSMM_DEVELOPER_ENABLE=y' "${path}"
done
if grep -q '^CONFIG_SECURITY_XPM=y$' \
  "${OHOS_ROOT}/device/qemu/common/virt_full/kernel/arm_virt_defconfig"; then
  echo "armv7a defconfig unexpectedly enabled 64-bit-only XPM" >&2
  exit 1
fi

grep -Eq '^[[:space:]]*netmanager_ext_feature_vpn = true$' \
  "${OHOS_ROOT}/foundation/communication/netmanager_ext/netmanager_ext_config.gni"
grep -Eq '^[[:space:]]*netmanager_ext_feature_vpnext = true$' \
  "${OHOS_ROOT}/foundation/communication/netmanager_ext/netmanager_ext_config.gni"
for product_config in \
  "${OHOS_ROOT}/vendor/ohemu/virt/virt_common.json" \
  "${OHOS_ROOT}/vendor/ohemu/virt/virt_common_x86_64.json"
do
  grep -Fq \
    '"graphic_2d_feature_ace_enable_gpu = true"' \
    "${product_config}"
  grep -Fq \
    '"graphic_2d_feature_enable_opengl = true"' \
    "${product_config}"
  grep -Fq \
    '"graphic_2d_feature_rs_enable_eglimage = true"' \
    "${product_config}"
  for feature in \
    graphic_2d_feature_enable_vulkan
  do
    grep -Fq "\"${feature} = false\"" "${product_config}"
  done
  grep -Fq \
    '"graphic_2d_feature_parallel_render_enable = true"' \
    "${product_config}"
done
grep -Fq \
  '#if (defined RS_ENABLE_GL) || (defined RS_ENABLE_VK)' \
  "${OHOS_ROOT}/foundation/graphic/graphic_2d/rosen/modules/render_service/composer/composer_service/external_depend/engine/rs_base_render_engine.cpp"
grep -Fq \
  'QEMU portable raster composition skips GPU context setup' \
  "${OHOS_ROOT}/foundation/graphic/graphic_2d/rosen/modules/render_service/composer/composer_service/external_depend/engine/rs_base_render_engine.cpp"
grep -Fq \
  'bool forceCPU = true;' \
  "${OHOS_ROOT}/foundation/graphic/graphic_2d/rosen/modules/render_service/composer/composer_service/external_depend/engine/rs_base_render_engine.cpp"
grep -Fq \
  'GPU context is unavailable; continuing with QEMU CPU raster composition' \
  "${OHOS_ROOT}/foundation/graphic/graphic_2d/rosen/modules/render_service/core/pipeline/main_thread/rs_main_thread.cpp"
if grep -Fq 'RS_LOGE("Init gpuContext is nullptr!");' \
  "${OHOS_ROOT}/foundation/graphic/graphic_2d/rosen/modules/render_service/core/pipeline/main_thread/rs_main_thread.cpp"; then
  echo "fatal GPU-context startup branch was not replaced" >&2
  exit 1
fi
grep -Fq \
  '//foundation/communication/netmanager_ext/frameworks/vpn_dialog/dialog_ui/vpn_dialog:dialog_hap' \
  "${OHOS_ROOT}/applications/standard/hap/ohos.build"
grep -Fxq -- '--fs_type=f2fs' \
  "${OHOS_ROOT}/vendor/ohemu/virt/image_conf/userdata_image_conf.txt"
if grep -Fxq -- '--verity' \
  "${OHOS_ROOT}/vendor/ohemu/virt/image_conf/userdata_image_conf.txt"; then
  echo "F2FS userdata config retained the obsolete ext4-only --verity flag" >&2
  exit 1
fi
python3 "${VERIFY_HAP_PROFILE}" \
  "${OHOS_ROOT}/foundation/communication/netmanager_ext/frameworks/vpn_dialog/dialog_ui/signature/vpndialog.p7b" \
  --bundle-name com.ohos.vpndialog \
  --app-feature hos_system_app \
  --allowed-acl ohos.permission.MANAGE_SECURE_SETTINGS \
  --allowed-acl ohos.permission.GET_BUNDLE_INFO_PRIVILEGED \
  --allowed-acl ohos.permission.SYSTEM_FLOAT_WINDOW \
  --allowed-acl ohos.permission.GET_BUNDLE_RESOURCES \
  --allowed-acl ohos.permission.GET_RUNNING_INFO \
  --at-time 1785196800 \
  --min-valid-seconds 31536000 \
  >/dev/null

# Reapplying the overlay must not duplicate Kconfig or HAP entries.
bash "${APPLY}" \
  --source-root "${OHOS_ROOT}" \
  --product armv7a_virt \
  --product arm64_virt \
  --product x86_64_virt \
  >/dev/null

[ "$(grep -c '^CONFIG_TUN=y$' "${OHOS_ROOT}/device/qemu/common/virt_full/kernel/arm_virt_defconfig")" -eq 1 ]
[ "$(grep -c '^ source \"fs/code_sign/Kconfig\"$' "${OHOS_ROOT}/device/qemu/common/virt_full/kernel/patch/virt.patch")" -eq 1 ]
[ "$(grep -c '^ obj-$(CONFIG_SECURITY_CODE_SIGN)' "${OHOS_ROOT}/device/qemu/common/virt_full/kernel/patch/virt.patch")" -eq 1 ]
[ "$(grep -c '^ source \"security/xpm/Kconfig\"$' "${OHOS_ROOT}/device/qemu/common/virt_full/kernel/patch/virt.patch")" -eq 1 ]
[ "$(grep -c '^ obj-$(CONFIG_SECURITY_XPM)' "${OHOS_ROOT}/device/qemu/common/virt_full/kernel/patch/virt.patch")" -eq 1 ]
[ "$(grep -c 'common_modules/xpm' "${OHOS_ROOT}/device/qemu/common/virt_full/kernel/build_kernel.sh")" -eq 1 ]
[ "$(grep -c 'ohos-check-dir.sh' "${OHOS_ROOT}/device/qemu/common/virt_full/kernel/build_kernel.sh")" -eq 1 ]
[ "$(grep -c '^#include <linux/fs.h>$' "${OHOS_ROOT}/kernel/linux/common_modules/code_sign/code_sign_misc.c")" -eq 1 ]
[ "$(grep -c '^#include <sys/syscall.h>$' "${OHOS_ROOT}/base/security/code_signature/interfaces/inner_api/code_sign_utils/include/stat_utils.h")" -eq 1 ]
[ "$(grep -c 'return syscall(SYS_statx,' "${OHOS_ROOT}/base/security/code_signature/interfaces/inner_api/code_sign_utils/src/stat_utils.cpp")" -eq 1 ]
[ "$(grep -c '__NR_statx' "${OHOS_ROOT}/base/security/code_signature/interfaces/inner_api/code_sign_utils/src/stat_utils.cpp")" -eq 0 ]
[ "$(grep -c '^#include <sys/syscall.h>$' "${OHOS_ROOT}/base/security/code_signature/services/key_enable/utils/src/key_utils.cpp")" -eq 1 ]
[ "$(grep -c 'syscall(SYS_add_key,' "${OHOS_ROOT}/base/security/code_signature/services/key_enable/utils/src/key_utils.cpp")" -eq 1 ]
[ "$(grep -c 'syscall(SYS_keyctl,' "${OHOS_ROOT}/base/security/code_signature/services/key_enable/utils/src/key_utils.cpp")" -eq 1 ]
[ "$(grep -Ec '__NR_(add_key|keyctl)' "${OHOS_ROOT}/base/security/code_signature/services/key_enable/utils/src/key_utils.cpp")" -eq 0 ]
[ "$(grep -c 'file_name = "asm-x86"' "${OHOS_ROOT}/third_party/musl/BUILD.gn")" -eq 1 ]
[ "$(grep -c 'mv ${OUT_DIR}/asm-x86/asm ${OUT_DIR}/asm' "${OHOS_ROOT}/third_party/musl/scripts/copy_uapi.sh")" -eq 1 ]
[ "$(grep -c 'asm-(arm|arm64|x86|riscv|loongarch)' "${OHOS_ROOT}/third_party/musl/scripts/generate_uapi.py")" -eq 1 ]
[ "$(grep -c '^#include <linux/math64.h>$' "${OHOS_ROOT}/kernel/linux/linux-6.6/fs/verity/enable.c")" -eq 1 ]
[ "$(grep -c 'div_u64(offset, params->block_size)' "${OHOS_ROOT}/kernel/linux/linux-6.6/fs/verity/enable.c")" -eq 2 ]
[ "$(grep -c 'div_u64(offset - tree_offset, params->block_size)' "${OHOS_ROOT}/kernel/linux/linux-6.6/fs/verity/enable.c")" -eq 1 ]
[ "$(grep -c 'arg.tree_offset & (arg.block_size - 1)' "${OHOS_ROOT}/kernel/linux/linux-6.6/fs/verity/enable.c")" -eq 1 ]
[ "$(grep -c $'^\tint error = 0;$' "${OHOS_ROOT}/kernel/linux/linux-6.6/mm/mprotect.c")" -eq 1 ]
[ "$(grep -c 'select ARCH_USES_HIGH_VMA_FLAGS' "${OHOS_ROOT}/kernel/linux/common_modules/xpm/Kconfig")" -eq 1 ]
[ "$(grep -c 'IF_HAVE_PG_XPM_INTEGRITY(xpm_readonly)' "${OHOS_ROOT}/kernel/linux/linux-6.6/include/trace/events/mmflags.h")" -eq 1 ]
[ "$(grep -c 'IF_HAVE_PG_XPM_INTEGRITY(xpm_writetainted)' "${OHOS_ROOT}/kernel/linux/linux-6.6/include/trace/events/mmflags.h")" -eq 1 ]
[ "$(grep -c 'vpn_dialog:dialog_hap' "${OHOS_ROOT}/applications/standard/hap/ohos.build")" -eq 1 ]
[ "$(grep -c '^--fs_type=f2fs$' "${OHOS_ROOT}/vendor/ohemu/virt/image_conf/userdata_image_conf.txt")" -eq 1 ]
[ "$(grep -c '^--verity$' "${OHOS_ROOT}/vendor/ohemu/virt/image_conf/userdata_image_conf.txt")" -eq 0 ]

echo "standard VPN overlay tests passed"
