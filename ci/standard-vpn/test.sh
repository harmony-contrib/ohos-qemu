#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
APPLY="${ROOT}/overlays/standard_qemu_vpn/apply.sh"
TEST_ROOT="$(mktemp -d)"
OHOS_ROOT="${TEST_ROOT}/openharmony"

cleanup() {
  rm -rf "${TEST_ROOT}"
}
trap cleanup EXIT

mkdir -p \
  "${OHOS_ROOT}/device/qemu/common/virt_full/kernel/configs" \
  "${OHOS_ROOT}/foundation/communication/netmanager_ext/frameworks/vpn_dialog/dialog_ui/vpn_dialog" \
  "${OHOS_ROOT}/foundation/graphic/graphic_2d/rosen/modules/render_service/composer/composer_service/external_depend/engine" \
  "${OHOS_ROOT}/foundation/graphic/graphic_2d/rosen/modules/render_service/core/pipeline/main_thread" \
  "${OHOS_ROOT}/applications/standard/hap" \
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

cat >"${OHOS_ROOT}/foundation/communication/netmanager_ext/netmanager_ext_config.gni" <<'EOF'
declare_args() {
  netmanager_ext_feature_vpn = false
  netmanager_ext_feature_vpnext = false
}
EOF
: >"${OHOS_ROOT}/foundation/communication/netmanager_ext/frameworks/vpn_dialog/dialog_ui/vpn_dialog/BUILD.gn"
: >"${OHOS_ROOT}/applications/standard/hap/SettingsData.hap"

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
    CONFIG_FS_VERITY_BUILTIN_SIGNATURES
  do
    grep -qx "${option}=y" "${path}"
  done
done

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

# Reapplying the overlay must not duplicate Kconfig or HAP entries.
bash "${APPLY}" \
  --source-root "${OHOS_ROOT}" \
  --product armv7a_virt \
  --product arm64_virt \
  --product x86_64_virt \
  >/dev/null

[ "$(grep -c '^CONFIG_TUN=y$' "${OHOS_ROOT}/device/qemu/common/virt_full/kernel/arm_virt_defconfig")" -eq 1 ]
[ "$(grep -c 'vpn_dialog:dialog_hap' "${OHOS_ROOT}/applications/standard/hap/ohos.build")" -eq 1 ]

echo "standard VPN overlay tests passed"
