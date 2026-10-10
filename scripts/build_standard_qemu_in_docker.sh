#!/usr/bin/env bash
set -euo pipefail

# Ruby-based Ark compiler generators inherit the process locale. Ubuntu's
# empty/POSIX locale makes Ruby treat UTF-8 source as US-ASCII.
export LANG=C.UTF-8
export LC_ALL=C.UTF-8

usage() {
  cat <<'USAGE'
Usage:
  build_standard_qemu_in_docker.sh [armv7a_virt] [arm64_virt] [x86_64_virt]

Default products:
  arm64_virt x86_64_virt

Environment:
  CACHE_ROOT          Persistent mount root, default: /Volumes/PSSD/qemu
  OHOS_ROOT           OpenHarmony checkout, default: $CACHE_ROOT/openharmony
  PACKAGE_ROOT        Package output dir, default: $CACHE_ROOT/packages
  CONTAINER_HOME      Persistent HOME, default: $CACHE_ROOT/home
  OHOS_BRANCH         Manifest baseline name, default: OpenHarmony-7.0-Release
  MANIFEST_REVISION   Exact manifest commit used by repo init, default:
                       f079c4ad9848f9cc4a9a4b3a3613ad8fbb142549
  MANIFEST_URL        Manifest repo, default: https://github.com/openharmony/manifest.git
  OHOS_PROJECT_MIRROR Rewrite official GitCode project URLs to this mirror,
                       default: https://github.com/openharmony/
  OHOS_GITHUB_FALLBACK
                       Apply pinned 7.0 refs for incomplete GitHub mirrors,
                       default: 1
  OHOS_FALLBACK_MIRROR_ROOT
                       Host-prepared bare mirrors for projects absent from
                       GitHub, default: $CACHE_ROOT/git-mirrors/
                       openharmony-7.0-release
  MANIFEST_GROUPS     Repo groups, default includes standard/full system groups
  REPO_URL            Repo tool mirror, default:
                       https://github.com/GerritCodeReview/git-repo.git
  REPO_LAUNCHER_URL   Repo launcher, default:
                       https://raw.githubusercontent.com/GerritCodeReview/git-repo/main/repo
  REPO_JOBS           repo sync jobs, default: 16
  REPO_CHECKOUT_JOBS  repo checkout jobs, default: 4
  REPO_SYNC_RETRIES   repo sync retry attempts, default: 3
  BUILD_JOBS          build jobs, default: nproc
  KERNEL_BUILD_JOBS   nested kernel make jobs, default: BUILD_JOBS
  CCACHE_MAXSIZE      ccache size limit, default: 100G
  CCACHE_DIR          ccache directory, default: $CACHE_ROOT/ccache
  QEMU_CCACHE_ON_OUT_VOLUME
                      Put ccache and its temp files under out/.ccache. Use 1
                      when out/ is a native Linux volume, default: 0.
  GIT_USER_NAME       Global git user.name, default: richerfu
  GIT_USER_EMAIL      Global git user.email, default: southorange0929@foxmail.com
  NPM_REGISTRY        npm registry, default: https://repo.huaweicloud.com/repository/npm/
  PREBUILTS_RETRY     Retry prebuilts_download.sh after cleaning JS deps, default: 1
  PREBUILTS_CLEAN     Clean JS deps before prebuilts_download.sh, default: 0
  CLEAN_KERNEL_OBJ    Remove out/KERNEL_OBJ before each product build, default: 0
  NO_PREBUILT_SDK     Pass --no-prebuilt-sdk=true to build.sh, default: 0
  BUILD_ONLY_LOAD     Pass --build-only-load=true to build.sh, default: 0
  PREPARE_ONLY        Sync, patch, and validate the selected source products,
                       then stop before traversing builds, default: 0
  SKIP_APT            Skip apt dependency installation, default: 0
  SKIP_REPO_SYNC      Reuse existing checkout without repo sync, default: 0
  SKIP_PREBUILTS      Reuse existing prebuilts, default: 0
  SKIP_GIT_LFS        Skip git lfs pull, default: 0
  ALLOW_NON_DOCKER    Allow an isolated Ubuntu 22.04 VM instead of Docker,
                      default: 0
  GIT_LFS_PATHS       Space-separated paths to fetch with Git LFS, default:
                       applications/standard/hap base/web/webview
                       foundation/arkui/ace_engine third_party/icu
                       third_party/libphonenumber
  OHOS_LFS_ASSET_ROOT Host-prepared cache for pinned objects that GitHub mirrors
                       expose as former-LFS text stubs, default:
                       $CACHE_ROOT/artifacts/openharmony-7.0-lfs
  QEMU_MESA_REVISION_CACHE
                       Host-prepared Git cache for the pinned QEMU Mesa 21.3.3
                       source revision, default: $CACHE_ROOT/git-mirrors/
                       qemu-mesa/third_party_mesa3d.git
  QEMU_SERIAL_SOURCE_REPO
                       Read-only fixed Serial SIG git cache for 2in1, default:
                       $CACHE_ROOT/git-mirrors/busmanager_serial_manager.c05fbbf.git
  QEMU_FIX_ACCESS_TOKENID_ABI
                       Real Linux 6.6 permission bitmap ioctl and SPM detection, default: 1
  QEMU_FIX_SYSTEM_COMPAT_SYMLINKS
                       Map ramdisk /system to /usr/system, add
                       /bin/init -> /system/bin/init, and add
                       /chipset -> /vendor for QEMU, default: 1
  QEMU_FIX_CASE_INSENSITIVE_SELINUX_VERSION
                       Avoid libselinux/VERSION shadowing libc++ <version>
                       when the checkout is mounted from a case-insensitive
                       host filesystem, default: 1
  QEMU_FIX_CASE_INSENSITIVE_XMP_ENDIAN
                       Keep XMP Endian.h out of public system-header lookup
                       and suppress private path-case diagnostics on a
                       case-insensitive host filesystem, default: 1
  QEMU_FIX_CASE_INSENSITIVE_IPTABLES_CONNMARK
                       Restore uniquely named iptables match/target sources
                       and combined headers when upstream case-distinct files
                       alias each other on a case-insensitive host filesystem,
                       default: 1
  QEMU_FIX_MINDSPORE_NON_ARM_HWCAP
                       Keep MindSpore's ARM-only asm/hwcap.h include out of
                       x86_64 OHOS builds, default: 1
  QEMU_FIX_VIRTIOFS_NODE_SYMLINK_COPY
                       Copy ArkGuard node_modules launchers as regular files
                       when staging across shared filesystems, default: 1
  QEMU_SERIALIZE_SHARED_ARKOALA_GENERATOR
                       Serialize Arkoala npm install/code generation because
                       it writes node_modules in the shared source tree,
                       default: 1
  QEMU_FIX_VIRTIOFS_KERNEL_COPY
                       Copy the kernel worktree without dereferencing the
                       repo-tool .git symlink on shared filesystems,
                       default: 1
  QEMU_ABSOLUTE_POINTER_COMPONENT
                       Map virtio-tablet absolute events to the active guest
                       display dimensions, default: 1
  QEMU_QOS_COMPONENT  Apply the QEMU QoS kernel component, default: 1
  QEMU_VIBRATOR_COMPONENT
                       Install the QEMU virtual vibrator VDI, default: 1
  QEMU_AUDIO_COMPONENT The pinned 7.0 build always backports the QEMU vendor
                       ALSA source-selection contract before traversal.
  QEMU_ACCESSIBILITY_COMPONENT
                       Add generic accessibility ability enable/disable CLI
                       commands for QEMU test extensions, default: 1
  QEMU_JSVM_COMPONENT Enable JSVM with ArkWeb M144 V8 artifacts. Values:
                       auto (default), 1, or 0. Full phone/2in1 launchers set 1.
  JSVM_ENGINE_ARTIFACTS
                       M144 artifact root, default:
                       $CACHE_ROOT/artifacts/jsvm-m144
  QEMU_VULKAN_COMPONENT
                       Install the QEMU SwiftShader Vulkan ICD. Values:
                       auto (default), 1, or 0.
  QEMU_VULKAN_ARTIFACTS
                       SwiftShader artifact root, default:
                       $CACHE_ROOT/artifacts/swiftshader-m144
  QEMU_AVC_ARTIFACTS    Required pinned real software AVC backend/provenance for
                       every selected ABI, default: $CACHE_ROOT/artifacts/avc-m144
                       Build with scripts/build_m144_avc_encoder.sh first.
  ARMV7A_PRODUCT_COMPONENT
                       Apply the armv7a_virt product components, default: 1
  STANDARD_VPN_COMPONENT
                       Enable and validate the standard VpnExtension stack,
                       default: 1
  QEMU_2IN1_PROFILE_COMPONENT
                       For DEVICE_TYPE=2in1, add the source component/feature
                       profile derived from productdefine 2in1.json. Values:
                       auto (default), 1, or 0. A value of 0 produces only a
                       parameter-level device type and is not a full profile.
  QEMU_PHONE_PROFILE_COMPONENT
                       For DEVICE_TYPE=phone, add the source component/feature
                       profile derived from productdefine phone.json. Values:
                       auto (default), 1, or 0.
  PRUNE_PRODUCT_OUT_AFTER_PACKAGE
                       Remove out/<product> after its verified package is
                       archived. Useful for six-package matrix builds on a
                       space-constrained Docker disk, default: 0.
  PROFILE_STAMP_WRITE_RETRIES
                       Retry the atomic device-profile stamp update while the
                       output volume reclaims deleted blocks, default: 90.
  PROFILE_STAMP_WRITE_RETRY_DELAY
                       Seconds between profile-stamp write attempts,
                       default: 2.
  DEVICE_TYPE         Pass --device-type to build.sh and packaging
                       (default|phone|tablet|2in1|...), default: empty
                       (OpenHarmony default remains "default"). When set to
                       e.g. 2in1, packaged names gain a -2in1 suffix.

Build environment:
  This script is intended to run inside a Docker container based on
  ubuntu:22.04. It refuses other environments before touching the OpenHarmony
  checkout.

This script keeps OpenHarmony changes narrow and repeatable: full QEMU products
keep SELinux, seccomp, screen, and critical-service behavior enabled by default.
The default source-side changes are limited to the QEMU rootfs /system
compatibility path and the access_tokenid kernel ABI that current OpenHarmony
userspace expects from the QEMU kernels.
USAGE
}

if [ "${1:-}" = "-h" ] || [ "${1:-}" = "--help" ]; then
  usage
  exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PACKAGER="${SCRIPT_DIR}/package_standard_qemu.sh"
PATCH_ROOT="${SCRIPT_DIR}/../patches"
ARMV7A_COMPONENT_SCRIPT="${PATCH_ROOT}/common/device/qemu/armv7a_product/apply.sh"
VPN_COMPONENT_SCRIPT="${PATCH_ROOT}/common/standard_vpn/apply.sh"
F2FS_QUOTA_COMPONENT_SCRIPT="${PATCH_ROOT}/common/vendor/ohemu/f2fs_quota/apply.sh"
QEMU_VULKAN_COMPONENT_SCRIPT="${PATCH_ROOT}/common/standard_vpn/components/qemu_vulkan/apply.sh"
QEMU_2IN1_PROFILE_SCRIPT="${PATCH_ROOT}/2in1/product_profile/apply.sh"
SCENEBOARD_RUNTIME_COMPONENT_SCRIPT="${PATCH_ROOT}/2in1/sceneboard_runtime/apply.sh"
PHONE_SCENEBOARD_RUNTIME_COMPONENT_SCRIPT="${PATCH_ROOT}/phone/sceneboard_runtime/apply.sh"
QEMU_PHONE_PROFILE_SCRIPT="${PATCH_ROOT}/phone/product_profile/apply.sh"
QEMU_ABSOLUTE_POINTER_COMPONENT_SCRIPT="${PATCH_ROOT}/common/foundation/multimodalinput/input/absolute_pointer/apply.sh"
QEMU_QOS_COMPONENT_SCRIPT="${PATCH_ROOT}/common/foundation/resourceschedule/qos_manager/apply.sh"
QEMU_VIBRATOR_COMPONENT_SCRIPT="${PATCH_ROOT}/common/drivers/peripheral/vibrator/apply.sh"
QEMU_AUDIO_COMPONENT_SCRIPT="${PATCH_ROOT}/common/drivers/peripheral/audio/apply.sh"
QEMU_ACCESSIBILITY_COMPONENT_SCRIPT="${PATCH_ROOT}/common/foundation/barrierfree/accessibility/apply.sh"
SENSOR_HEALTH_PERMISSION_COMPONENT_SCRIPT="${PATCH_ROOT}/common/interface/sdk-js/sensor_health_permission/apply.sh"
ARKWEB_BUSINESS_ERROR_COMPONENT_SCRIPT="${PATCH_ROOT}/common/base/web/webview/business_error/apply.sh"
NATIVE_CHILD_PROCESS_COMPONENT_SCRIPT="${PATCH_ROOT}/common/foundation/ability/ability_runtime/native_child_process/apply.sh"
QEMU_JSVM_COMPONENT_SCRIPT="${PATCH_ROOT}/common/arkcompiler/jsvm/apply.sh"
LOCATION_NDK_COMPONENT_SCRIPT="${PATCH_ROOT}/common/base/location/location_ndk/apply.sh"
ETHERNET_API26_COMPONENT_SCRIPT="${PATCH_ROOT}/common/foundation/communication/netmanager_ext/ethernet_api26/apply.sh"
TELEPHONY_CORE_ENUMS_COMPONENT_SCRIPT="${PATCH_ROOT}/common/base/telephony/core_service/api26_enums/apply.sh"
TELEPHONY_SMS_ENUMS_COMPONENT_SCRIPT="${PATCH_ROOT}/common/base/telephony/sms_mms/api26_enums/apply.sh"
TELEPHONY_CALL_ENUMS_COMPONENT_SCRIPT="${PATCH_ROOT}/common/base/telephony/call_manager/api26_enums/apply.sh"
SCREENLOCK_ENUMS_COMPONENT_SCRIPT="${PATCH_ROOT}/common/base/theme/screenlock_mgr/api26_enums/apply.sh"
I18N_SUGGESTION_TYPE_COMPONENT_SCRIPT="${PATCH_ROOT}/common/base/global/i18n/api26_suggestion_type/apply.sh"
DEVICE_MANAGER_AUTH_FORM_COMPONENT_SCRIPT="${PATCH_ROOT}/common/foundation/distributedhardware/device_manager/api26_auth_form/apply.sh"
SYSTEM_SOUND_TONE_FEATURE_COMPONENT_SCRIPT="${PATCH_ROOT}/common/foundation/multimedia/player_framework/api26_tone_haptics_feature/apply.sh"
METADATA_FETCH_RESULT_COMPONENT_SCRIPT="${PATCH_ROOT}/common/foundation/multimedia/player_framework/api26_fetch_result/apply.sh"
INSIGHT_CONFIGURATION_MODE_COMPONENT_SCRIPT="${PATCH_ROOT}/common/foundation/ability/ability_runtime/api26_insight_configuration_mode/apply.sh"
CLI_SESSION_STATUS_COMPONENT_SCRIPT="${PATCH_ROOT}/common/foundation/ability/ability_runtime/api26_cli_session_status/apply.sh"
IMAGE_PARTIAL_TYPE_COMPONENT_SCRIPT="${PATCH_ROOT}/common/foundation/arkui/ace_engine/api26_image_partial_type/apply.sh"
IMAGE_MODEL_CALLBACKS_COMPONENT_SCRIPT="${PATCH_ROOT}/common/foundation/arkui/ace_engine/image_model_callbacks/apply.sh"
ACCESSIBILITY_BLINK_ENUMS_COMPONENT_SCRIPT="${PATCH_ROOT}/common/foundation/barrierfree/accessibility/api26_blink_enums/apply.sh"
AUDIO_PUBLIC_ENUMS_COMPONENT_SCRIPT="${PATCH_ROOT}/common/foundation/multimedia/audio_framework/api26_public_enums/apply.sh"
UI_EFFECT_PUBLIC_MODES_COMPONENT_SCRIPT="${PATCH_ROOT}/common/foundation/graphic/graphic_2d/ui_effect/api26_public_modes/apply.sh"
BLUETOOTH_CONTROL_ENUMS_COMPONENT_SCRIPT="${PATCH_ROOT}/common/foundation/communication/bluetooth/api26_control_enums/apply.sh"
CAMERA_DEPTH_CONTRACTS_COMPONENT_SCRIPT="${PATCH_ROOT}/common/foundation/multimedia/camera_framework/api26_depth_contracts/apply.sh"
BLUETOOTH_OPP_ENUMS_COMPONENT_SCRIPT="${PATCH_ROOT}/common/foundation/communication/bluetooth/api26_opp_enums/apply.sh"
PHOTO_PUBLIC_ENUMS_COMPONENT_SCRIPT="${PATCH_ROOT}/common/foundation/multimedia/media_library/api26_photo_enums/apply.sh"
PHOTO_SEARCH_ENUMS_COMPONENT_SCRIPT="${PATCH_ROOT}/common/foundation/multimedia/media_library/api26_photo_search_enums/apply.sh"
PHOTOS_RECENT_INFO_COMPONENT_SCRIPT="${PATCH_ROOT}/common/foundation/multimedia/media_library/photos_recent_info/apply.sh"
EFFECT_LIGHT_DEGREE_COMPONENT_SCRIPT="${PATCH_ROOT}/common/foundation/graphic/graphic_2d/effect_kit/api26_light_degree/apply.sh"
MISSION_STATE_COMPONENT_SCRIPT="${PATCH_ROOT}/common/foundation/ability/ability_runtime/api26_mission_state/apply.sh"
PARTICLE_ERROR_CODE_COMPONENT_SCRIPT="${PATCH_ROOT}/common/foundation/ability/ability_runtime/particle_error_code/apply.sh"
CLOUD_FLAG_COMPONENT_SCRIPT="${PATCH_ROOT}/common/foundation/distributeddatamgr/relational_store/api26_cloud_flag/apply.sh"
CURVE_ENUM_COMPONENT_SCRIPT="${PATCH_ROOT}/common/foundation/arkui/ace_engine/api26_curve_enum/apply.sh"
LOCATION_PUBLIC_ENUMS_COMPONENT_SCRIPT="${PATCH_ROOT}/common/base/location/location/api26_public_enums/apply.sh"
NETMANAGER_API26_FEATURES_SCRIPT="${PATCH_ROOT}/common/foundation/communication/netmanager_ext/api26_features/apply.sh"
VPN_DIALOG_BUNDLE_COMPONENT_SCRIPT="${PATCH_ROOT}/common/foundation/communication/netmanager_ext/vpn_dialog_bundle/apply.sh"
DHW_UI_PREINSTALL_COMPONENT_SCRIPT="${PATCH_ROOT}/common/vendor/ohemu/virt/dhardware_preinstall/apply.sh"
QEMU_AUDIO_DEVICE_COMPONENT_SCRIPT="${PATCH_ROOT}/common/vendor/ohemu/qemu_audio_device/apply.sh"
QEMU_AUDIO_PROFILE_COMPONENT_SCRIPT="${PATCH_ROOT}/common/vendor/ohemu/audio_profile/apply.sh"
QEMU_AUDIO_POLICY_7_COMPONENT_SCRIPT="${PATCH_ROOT}/common/vendor/ohemu/audio_policy_7/apply.sh"
QEMU_CAMERA_PROFILE_COMPONENT_SCRIPT="${PATCH_ROOT}/common/vendor/ohemu/camera_profile/apply.sh"
QEMU_CAMERA_USB_COMPONENT_SCRIPT="${PATCH_ROOT}/common/drivers/peripheral/camera/usb_backend/apply.sh"
QEMU_CAMERA_VIVID_COMPONENT_SCRIPT="${PATCH_ROOT}/common/drivers/peripheral/camera/vivid_capture/apply.sh"
QEMU_CAMERA_JPEG_COMPONENT_SCRIPT="${PATCH_ROOT}/common/drivers/peripheral/camera/jpeg_rotation/apply.sh"
QEMU_CAMERA_JPEG_CAPTURE_COMPONENT_SCRIPT="${PATCH_ROOT}/common/drivers/peripheral/camera/jpeg_capture/apply.sh"
QEMU_CAMERA_FORK_TIMESTAMP_COMPONENT_SCRIPT="${PATCH_ROOT}/common/drivers/peripheral/camera/fork_timestamp/apply.sh"
QEMU_CAMERA_CAPTURE_END_COMPONENT_SCRIPT="${PATCH_ROOT}/common/drivers/peripheral/camera/capture_end/apply.sh"
QEMU_CAMERA_CAPTURE_PUBLICATION_COMPONENT_SCRIPT="${PATCH_ROOT}/common/drivers/peripheral/camera/capture_publication/apply.sh"
QEMU_THERMAL_HDI_COMPONENT_SCRIPT="${PATCH_ROOT}/common/drivers/peripheral/thermal/qemu_backend/apply.sh"
QEMU_THERMAL_SERVICE_COMPONENT_SCRIPT="${PATCH_ROOT}/common/base/powermgr/thermal_manager/qemu_backend/apply.sh"
QEMU_THERMAL_CLIENT_COMPONENT_SCRIPT="${PATCH_ROOT}/common/base/powermgr/thermal_manager/client_reply/apply.sh"
QEMU_THERMAL_NAPI_COMPONENT_SCRIPT="${PATCH_ROOT}/common/base/powermgr/thermal_manager/napi_contract/apply.sh"
QEMU_VIVID_KERNEL_COMPONENT_SCRIPT="${PATCH_ROOT}/common/device/qemu/vivid_capture/apply.sh"
QEMU_WLAN_RADIO_COMPONENT_SCRIPT="${PATCH_ROOT}/common/device/qemu/wlan_radio/apply.sh"
QEMU_WLAN_REGULATORY_COMPONENT_SCRIPT="${PATCH_ROOT}/common/device/qemu/wlan_regulatory/apply.sh"
QEMU_WPA_SCAN_COMPONENT_SCRIPT="${PATCH_ROOT}/common/foundation/communication/wifi/wpa_scan/apply.sh"
QEMU_WPA_SCAN_LIFECYCLE_COMPONENT_SCRIPT="${PATCH_ROOT}/common/foundation/communication/wifi/wpa_scan_lifecycle/apply.sh"
QEMU_WPA_SOFTWARE_PNO_COMPONENT_SCRIPT="${PATCH_ROOT}/common/foundation/communication/wifi/wpa_software_pno/apply.sh"
VIVID_CAPTURE_DEFAULTS_COMPONENT_SCRIPT="${PATCH_ROOT}/common/kernel/linux/linux_6_6/vivid_capture/apply.sh"
SETTINGS_NAVIGATION_COMPONENT_SCRIPT="${PATCH_ROOT}/common/applications/standard/settings/network_navigation/apply.sh"
SETTINGS_TTS_NAMESPACE_COMPONENT_SCRIPT="${PATCH_ROOT}/common/applications/standard/settings/tts_namespace/apply.sh"
PERMISSION_OPEN_SETTING_COMPONENT_SCRIPT="${PATCH_ROOT}/common/applications/standard/permission_manager/open_setting/apply.sh"
MATRIX4_EXPORTS_COMPONENT_SCRIPT="${PATCH_ROOT}/common/foundation/arkui/ace_engine/matrix4_exports/apply.sh"
BACKUP_INIT_COMPONENT_SCRIPT="${PATCH_ROOT}/common/foundation/filemanagement/app_file_service/backup_init/apply.sh"
MODULE_UPDATE_INIT_COMPONENT_SCRIPT="${PATCH_ROOT}/common/base/update/sys_installer/module_update_init/apply.sh"
USAGE_STATS_INIT_COMPONENT_SCRIPT="${PATCH_ROOT}/common/foundation/resourceschedule/device_usage_statistics/init_profile/apply.sh"
HUKS_COMPATIBILITY_COMPONENT_SCRIPT="${PATCH_ROOT}/common/base/security/huks/compatibility_bin/apply.sh"
QEMU_KERNEL_CAPABILITY_COMPONENT_SCRIPT="${PATCH_ROOT}/common/device/qemu/kernel_capability/apply.sh"
QEMU_HOST_GN_EXECUTION_COMPONENT_SCRIPT="${PATCH_ROOT}/common/build/host_gn_execution/apply.sh"
IDL_COMMON_TYPE_OUTPUTS_COMPONENT_SCRIPT="${PATCH_ROOT}/common/build/idl_common_type_outputs/apply.sh"
MESA_KMS_MAPPING_COMPONENT_SCRIPT="${PATCH_ROOT}/common/third_party/mesa3d/kms_mapping_synchronization/apply.sh"
QEMU_KMS_MESA_BUILD_COMPONENT_SCRIPT="${PATCH_ROOT}/common/device/qemu/kms_mesa_build/apply.sh"
MESA_KMS_MAPPING_BUILD_COMPONENT_SCRIPT="${PATCH_ROOT}/common/third_party/mesa3d/kms_mapping_build/apply.sh"
QEMU_POWER_WAKELOCKS_COMPONENT_SCRIPT="${PATCH_ROOT}/common/device/qemu/power_wakelocks/apply.sh"
QEMU_POWER_BUTTON_COMPONENT_SCRIPT="${PATCH_ROOT}/common/kernel/linux/linux_6_6/qemu_power_button/apply.sh"
QEMU_VIRTIO_GPU_S2IDLE_COMPONENT_SCRIPT="${PATCH_ROOT}/common/kernel/linux/linux_6_6/qemu_virtio_gpu_s2idle/apply.sh"
QEMU_BINDER_ASYNC_SENDER_COMPONENT_SCRIPT="${PATCH_ROOT}/common/kernel/linux/linux_6_6/binder_async_sender/apply.sh"
QEMU_BINDER_CONNECTOR_COMPONENT_SCRIPT="${PATCH_ROOT}/common/foundation/communication/ipc/binder_connector_initialization/apply.sh"
QEMU_BINDER_OBJECT_SAFETY_COMPONENT_SCRIPT="${PATCH_ROOT}/common/foundation/communication/ipc/binder_object_safety/apply.sh"
RS_ASYNC_CALLER_IDENTITY_COMPONENT_SCRIPT="${PATCH_ROOT}/common/foundation/graphic/graphic_2d/async_caller_identity/apply.sh"
QEMU_KERNEL_DEPENDENCIES_COMPONENT_SCRIPT="${PATCH_ROOT}/common/device/qemu/kernel_build_dependencies/apply.sh"
DMABUF_PROCESS_INFO_COMPONENT_SCRIPT="${PATCH_ROOT}/common/kernel/linux/linux_6_6/dmabuf_process_info/apply.sh"
ACCESS_TOKEN_ABI_COMPONENT_SCRIPT="${PATCH_ROOT}/common/kernel/linux/linux_6_6/access_token_abi/apply.sh"
RENDER_CONNECTION_REPLY_SCRIPT="${PATCH_ROOT}/common/foundation/graphic/graphic_2d/render_connection_reply/apply.sh"
RS_YUV_CPU_FALLBACK_SCRIPT="${PATCH_ROOT}/common/foundation/graphic/graphic_2d/yuv_cpu_fallback/apply.sh"
SHARED_FENCE_OWNER_SCRIPT="${PATCH_ROOT}/common/foundation/graphic/graphic_surface/shared_fence_owner/apply.sh"
ACCESS_TOKEN_SPM_HANDSHAKE_SCRIPT="${PATCH_ROOT}/common/base/security/access_token/kernel_spm_handshake/apply.sh"
APPSPAWN_KERNEL_USER_ID_SCRIPT="${PATCH_ROOT}/common/base/startup/appspawn/kernel_user_id/apply.sh"
APPSPAWN_RENDER_PID_NAMESPACE_SCRIPT="${PATCH_ROOT}/common/base/startup/appspawn/render_pid_namespace/apply.sh"
I18N_INIT_OWNERSHIP_COMPONENT_SCRIPT="${PATCH_ROOT}/common/base/global/i18n/init_ownership/apply.sh"
I18N_BUILTIN_DATA_COMPONENT_SCRIPT="${PATCH_ROOT}/common/base/global/i18n/builtin_data/apply.sh"
I18N_BUSINESS_ERROR_COMPONENT_SCRIPT="${PATCH_ROOT}/common/base/global/i18n/business_error/apply.sh"
CERTIFICATE_EMPTY_LISTS_COMPONENT_SCRIPT="${PATCH_ROOT}/common/base/security/certificate_manager/empty_lists/apply.sh"
CONTACT_SYNC_MODE_COMPONENT_SCRIPT="${PATCH_ROOT}/common/applications/standard/contacts_data/sync_mode/apply.sh"
AUDIO_DEVICE_BLOCK_STATUS_COMPONENT_SCRIPT="${PATCH_ROOT}/common/foundation/multimedia/audio_framework/device_block_status/apply.sh"
PHOTO_FUSION_ASSET_TYPE_COMPONENT_SCRIPT="${PATCH_ROOT}/common/foundation/multimedia/media_library/fusion_asset_type/apply.sh"
ALSA_CONFIG_INSTALL_COMPONENT_SCRIPT="${PATCH_ROOT}/common/third_party/alsa-lib/config_install/apply.sh"
CALENDAR_SOURCE_PROVIDER_COMPONENT_SCRIPT="${PATCH_ROOT}/common/applications/standard/calendardata/source_provider/apply.sh"
CALENDAR_PREBUILT_COMPONENT_SCRIPT="${PATCH_ROOT}/common/applications/standard/hap/calendar_provider/apply.sh"
CALENDAR_SIGNING_COMPONENT_SCRIPT="${PATCH_ROOT}/common/vendor/ohemu/virt/calendar_provider/apply.sh"
PHOTOS_SOURCE_PROVIDER_COMPONENT_SCRIPT="${PATCH_ROOT}/common/applications/standard/photos/source_provider/apply.sh"
PHOTOS_PREBUILT_COMPONENT_SCRIPT="${PATCH_ROOT}/common/applications/standard/hap/photos_provider/apply.sh"
PHOTOS_SIGNING_COMPONENT_SCRIPT="${PATCH_ROOT}/common/vendor/ohemu/virt/photos_provider/apply.sh"
SETTINGS_SOURCE_PROVIDER_COMPONENT_SCRIPT="${PATCH_ROOT}/common/applications/standard/settings/source_provider/apply.sh"
SETTINGS_EXTERNAL_INPUT_COMPONENT_SCRIPT="${PATCH_ROOT}/common/applications/standard/settings/external_input/apply.sh"
SETTINGS_INPUT_2IN1_COMPONENT_SCRIPT="${PATCH_ROOT}/common/applications/standard/settings/input_2in1_navigation/apply.sh"
SETTINGS_REFRESH_RATE_COMPONENT_SCRIPT="${PATCH_ROOT}/common/applications/standard/settings/refresh_rate_page/apply.sh"
SCREEN_MODES_COMPONENT_SCRIPT="${PATCH_ROOT}/common/foundation/window/window_manager/screen_modes/apply.sh"
QEMU_CAPTURE_BUDGET_COMPONENT_SCRIPT="${PATCH_ROOT}/common/foundation/window/window_manager/capture_budget/apply.sh"
COMPLETION_HANDLER_COMPONENT_SCRIPT="${PATCH_ROOT}/common/foundation/ability/ability_runtime/completion_handler/apply.sh"
QEMU_DISPLAY_MODES_COMPONENT_SCRIPT="${PATCH_ROOT}/common/device/qemu/display_modes/apply.sh"
SETTINGS_PREBUILT_COMPONENT_SCRIPT="${PATCH_ROOT}/common/applications/standard/hap/settings_provider/apply.sh"
SETTINGS_SIGNING_COMPONENT_SCRIPT="${PATCH_ROOT}/common/vendor/ohemu/virt/settings_provider/apply.sh"
PHOTOS_FACARD_COMPONENT_SCRIPT="${PATCH_ROOT}/common/foundation/multimedia/media_library/photos_facard/apply.sh"
SOFTWARE_AVC_COMPONENT_SCRIPT="${PATCH_ROOT}/common/foundation/multimedia/av_codec/software_avc/apply.sh"
AVC_EOS_COMPONENT_SCRIPT="${PATCH_ROOT}/common/foundation/multimedia/av_codec/avc_eos/apply.sh"
QEMU_VIRTIO_YUV_BUFFER_COMPONENT_SCRIPT="${PATCH_ROOT}/common/device/qemu/virtio_yuv_buffer/apply.sh"
AUDIO_SUITE_LIBRARY_PATH_COMPONENT_SCRIPT="${PATCH_ROOT}/common/foundation/multimedia/audio_framework/audio_suite_library_path/apply.sh"
AUDIO_SUITE_DSP_COMPONENT_SCRIPT="${PATCH_ROOT}/common/foundation/multimedia/audio_framework/audio_suite_dsp/apply.sh"
NOTICE_READONLY_INPUT_COMPONENT_SCRIPT="${PATCH_ROOT}/common/build/notice/readonly_input/apply.sh"
LIBJPEG_RELEASE_COMPONENT_SCRIPT="${PATCH_ROOT}/common/third_party/libjpeg-turbo/release_3_1_0/apply.sh"
JSONCPP_GENERATED_SOURCE_COMPONENT_SCRIPT="${PATCH_ROOT}/common/third_party/jsoncpp/generated_source/apply.sh"
SERIAL_METADATA_COMPONENT_SCRIPT="${PATCH_ROOT}/2in1/base/security/selinux_adapter/serial_metadata/apply.sh"
SERIAL_MANAGER_COMPONENT_SCRIPT="${PATCH_ROOT}/2in1/base/busmanager/serial_manager/apply.sh"
SERIAL_DIALOG_COMPONENT_SCRIPT="${PATCH_ROOT}/2in1/base/usb/usb_manager/serial_dialog/apply.sh"
SERIAL_DEVICES_COMPONENT_SCRIPT="${PATCH_ROOT}/2in1/base/startup/init/serial_devices/apply.sh"
SERIAL_USB_ENDPOINT_COMPONENT_SCRIPT="${PATCH_ROOT}/2in1/device/qemu/serial_usb_endpoint/apply.sh"
FUSION_ACCOUNTS_COMPONENT_SCRIPT="${PATCH_ROOT}/common/base/startup/init/fusion_accounts/apply.sh"
FUSION_SERVICE_DOMAINS_COMPONENT_SCRIPT="${PATCH_ROOT}/common/base/security/selinux_adapter/fusion_service_domains/apply.sh"
FUSION_PARTNER_PARAMETER_COMPONENT_SCRIPT="${PATCH_ROOT}/common/base/security/selinux_adapter/fusion_partner_parameter/apply.sh"
ACCOUNT_TABLE_FORMAT_COMPONENT_SCRIPT="${PATCH_ROOT}/common/base/startup/init/account_table_format/apply.sh"
VULKAN_OHOS_SURFACE_COMPONENT_SCRIPT="${PATCH_ROOT}/common/third_party/vulkan-loader/ohos_surface_dispatch/apply.sh"
RELEASE_HAP_DEPENDENCIES_SCRIPT="${PATCH_ROOT}/common/build/compile_app/release_dependencies/apply.sh"
SDK_CORTEX_M_COMPONENT_SCRIPT="${PATCH_ROOT}/common/third_party/musl/cortex_m_sdk/apply.sh"
GITHUB_LFS_ASSET_COMPONENT_SCRIPT="${PATCH_ROOT}/common/build/github_lfs_assets/apply.sh"
GITHUB_LFS_ASSET_MAP="${PATCH_ROOT}/common/build/github_lfs_assets/assets.tsv"

if [ ! -x "${PACKAGER}" ]; then
  echo "missing executable packager: ${PACKAGER}" >&2
  exit 1
fi

CACHE_ROOT="${CACHE_ROOT:-/Volumes/PSSD/qemu}"
SCENEBOARD_RUNTIME_ASSET_ROOT="${SCENEBOARD_RUNTIME_ASSET_ROOT:-${CACHE_ROOT}/artifacts/sceneboard-runtime}"
SCENEBOARD_RUNTIME_NATIVE_REVISION="${SCENEBOARD_RUNTIME_NATIVE_REVISION:-27befcf82a71047a585d725bb8c7805031472e86}"
OHOS_ROOT="${OHOS_ROOT:-${CACHE_ROOT}/openharmony}"
PACKAGE_ROOT="${PACKAGE_ROOT:-${CACHE_ROOT}/packages}"
CONTAINER_HOME="${CONTAINER_HOME:-${CACHE_ROOT}/home}"
OHOS_BRANCH="${OHOS_BRANCH:-OpenHarmony-7.0-Release}"
MANIFEST_REVISION="${MANIFEST_REVISION:-f079c4ad9848f9cc4a9a4b3a3613ad8fbb142549}"
MANIFEST_URL="${MANIFEST_URL:-https://github.com/openharmony/manifest.git}"
OHOS_PROJECT_MIRROR="${OHOS_PROJECT_MIRROR-https://github.com/openharmony/}"
OHOS_GITHUB_FALLBACK="${OHOS_GITHUB_FALLBACK:-1}"
OHOS_GITHUB_FALLBACK_MAP="${OHOS_GITHUB_FALLBACK_MAP:-/work/scripts/openharmony_7_0_release_github_fallback.tsv}"
OHOS_FALLBACK_MIRROR_ROOT="${OHOS_FALLBACK_MIRROR_ROOT:-${CACHE_ROOT}/git-mirrors/openharmony-7.0-release}"
MANIFEST_GROUPS="${MANIFEST_GROUPS:-default,ohos:mini,ohos:small,ohos:standard,ohos:system,ohos:chipset}"
REPO_URL="${REPO_URL:-https://github.com/GerritCodeReview/git-repo.git}"
REPO_LAUNCHER_URL="${REPO_LAUNCHER_URL:-https://raw.githubusercontent.com/GerritCodeReview/git-repo/main/repo}"
REPO_NO_BUNDLE="${REPO_NO_BUNDLE:-1}"
REPO_NO_TAGS="${REPO_NO_TAGS:-1}"
REPO_FORCE_SYNC="${REPO_FORCE_SYNC:-1}"
REPO_JOBS="${REPO_JOBS:-16}"
REPO_CHECKOUT_JOBS="${REPO_CHECKOUT_JOBS:-4}"
REPO_SYNC_RETRIES="${REPO_SYNC_RETRIES:-3}"
BUILD_JOBS="${BUILD_JOBS:-$(nproc)}"
KERNEL_BUILD_JOBS="${KERNEL_BUILD_JOBS:-${BUILD_JOBS}}"
CCACHE_MAXSIZE="${CCACHE_MAXSIZE:-100G}"
CCACHE_DIR="${CCACHE_DIR:-${CACHE_ROOT}/ccache}"
GIT_USER_NAME="${GIT_USER_NAME:-richerfu}"
GIT_USER_EMAIL="${GIT_USER_EMAIL:-southorange0929@foxmail.com}"
NPM_REGISTRY="${NPM_REGISTRY:-https://repo.huaweicloud.com/repository/npm/}"
PREBUILTS_RETRY="${PREBUILTS_RETRY:-1}"
PREBUILTS_CLEAN="${PREBUILTS_CLEAN:-0}"
CLEAN_KERNEL_OBJ="${CLEAN_KERNEL_OBJ:-0}"
NO_PREBUILT_SDK="${NO_PREBUILT_SDK:-0}"
BUILD_ONLY_LOAD="${BUILD_ONLY_LOAD:-0}"
PREPARE_ONLY="${PREPARE_ONLY:-0}"
SOURCE_PREPARE_ONLY="${SOURCE_PREPARE_ONLY:-0}"
PATCH_COMPONENTS_ONLY="${PATCH_COMPONENTS_ONLY:-0}"
SKIP_APT="${SKIP_APT:-0}"
export QEMU_HOST_GN_QEMU_USER="${QEMU_HOST_GN_QEMU_USER:-0}"
case "${QEMU_HOST_GN_QEMU_USER}" in 0|1) ;; *) echo 'QEMU_HOST_GN_QEMU_USER must be 0 or 1' >&2; exit 2 ;; esac
SKIP_REPO_SYNC="${SKIP_REPO_SYNC:-0}"
SKIP_PREBUILTS="${SKIP_PREBUILTS:-0}"
SKIP_GIT_LFS="${SKIP_GIT_LFS:-0}"
ALLOW_NON_DOCKER="${ALLOW_NON_DOCKER:-0}"
GIT_LFS_PATHS="${GIT_LFS_PATHS:-applications/standard/hap base/web/webview foundation/arkui/ace_engine third_party/icu third_party/libphonenumber}"
OHOS_LFS_ASSET_ROOT="${OHOS_LFS_ASSET_ROOT:-${CACHE_ROOT}/artifacts/openharmony-7.0-lfs}"
QEMU_MESA_REVISION_CACHE="${QEMU_MESA_REVISION_CACHE:-${CACHE_ROOT}/git-mirrors/qemu-mesa/third_party_mesa3d.git}"
QEMU_SERIAL_SOURCE_REPO="${QEMU_SERIAL_SOURCE_REPO:-${CACHE_ROOT}/git-mirrors/busmanager_serial_manager.c05fbbf.git}"
export QEMU_MESA_REVISION_CACHE
QEMU_FIX_ACCESS_TOKENID_ABI="${QEMU_FIX_ACCESS_TOKENID_ABI:-1}"
QEMU_FIX_SYSTEM_COMPAT_SYMLINKS="${QEMU_FIX_SYSTEM_COMPAT_SYMLINKS:-1}"
QEMU_FIX_CASE_INSENSITIVE_SELINUX_VERSION="${QEMU_FIX_CASE_INSENSITIVE_SELINUX_VERSION:-1}"
QEMU_FIX_CASE_INSENSITIVE_XMP_ENDIAN="${QEMU_FIX_CASE_INSENSITIVE_XMP_ENDIAN:-1}"
QEMU_FIX_CASE_INSENSITIVE_IPTABLES_CONNMARK="${QEMU_FIX_CASE_INSENSITIVE_IPTABLES_CONNMARK:-1}"
QEMU_FIX_MINDSPORE_NON_ARM_HWCAP="${QEMU_FIX_MINDSPORE_NON_ARM_HWCAP:-1}"
QEMU_FIX_VIRTIOFS_NODE_SYMLINK_COPY="${QEMU_FIX_VIRTIOFS_NODE_SYMLINK_COPY:-1}"
QEMU_SERIALIZE_SHARED_ARKOALA_GENERATOR="${QEMU_SERIALIZE_SHARED_ARKOALA_GENERATOR:-1}"
QEMU_FIX_VIRTIOFS_KERNEL_COPY="${QEMU_FIX_VIRTIOFS_KERNEL_COPY:-1}"
QEMU_ABSOLUTE_POINTER_COMPONENT="${QEMU_ABSOLUTE_POINTER_COMPONENT:-1}"
QEMU_QOS_COMPONENT="${QEMU_QOS_COMPONENT:-1}"
QEMU_VIBRATOR_COMPONENT="${QEMU_VIBRATOR_COMPONENT:-1}"
QEMU_ACCESSIBILITY_COMPONENT="${QEMU_ACCESSIBILITY_COMPONENT:-1}"
QEMU_JSVM_COMPONENT="${QEMU_JSVM_COMPONENT:-auto}"
QEMU_VULKAN_COMPONENT="${QEMU_VULKAN_COMPONENT:-auto}"
QEMU_VULKAN_ARTIFACTS="${QEMU_VULKAN_ARTIFACTS:-${CACHE_ROOT}/artifacts/swiftshader-m144-7.0}"
QEMU_AVC_ARTIFACTS="${QEMU_AVC_ARTIFACTS:-${CACHE_ROOT}/artifacts/avc-m144-7.0}"
QEMU_ARKWEB_CORE_ARTIFACTS="${QEMU_ARKWEB_CORE_ARTIFACTS:-${CACHE_ROOT}/artifacts/arkweb-m144-7.0}"
export QEMU_ARKWEB_CORE_ARTIFACTS
export QEMU_QOS_COMPONENT QEMU_VIBRATOR_COMPONENT QEMU_ACCESSIBILITY_COMPONENT QEMU_JSVM_COMPONENT
QEMU_CCACHE_ON_OUT_VOLUME="${QEMU_CCACHE_ON_OUT_VOLUME:-0}"
ARMV7A_PRODUCT_COMPONENT="${ARMV7A_PRODUCT_COMPONENT:-1}"
STANDARD_VPN_COMPONENT="${STANDARD_VPN_COMPONENT:-1}"
QEMU_2IN1_PROFILE_COMPONENT="${QEMU_2IN1_PROFILE_COMPONENT:-auto}"
QEMU_PHONE_PROFILE_COMPONENT="${QEMU_PHONE_PROFILE_COMPONENT:-auto}"
PRUNE_PRODUCT_OUT_AFTER_PACKAGE="${PRUNE_PRODUCT_OUT_AFTER_PACKAGE:-0}"
PROFILE_STAMP_WRITE_RETRIES="${PROFILE_STAMP_WRITE_RETRIES:-90}"
PROFILE_STAMP_WRITE_RETRY_DELAY="${PROFILE_STAMP_WRITE_RETRY_DELAY:-2}"
DEVICE_TYPE="${DEVICE_TYPE:-}"
DEVICE_TYPE_BUILD_PROFILE="${DEVICE_TYPE_BUILD_PROFILE:-}"
JSVM_ENGINE_ARTIFACTS="${JSVM_ENGINE_ARTIFACTS:-${CACHE_ROOT}/artifacts/jsvm-m144-7.0}"
SDKMANAGER_COMMON_VERSION="${SDKMANAGER_COMMON_VERSION:-2.26.3}"
SDKMANAGER_COMMON_ARTIFACT="${SDKMANAGER_COMMON_ARTIFACT:-${CACHE_ROOT}/artifacts/npm/sdkmanager-common-${SDKMANAGER_COMMON_VERSION}.tgz}"
SDKMANAGER_COMMON_SHA512="${SDKMANAGER_COMMON_SHA512:-1f20b632c759085d79321f3b95425b4ee7608fdd1911c1c9965ab16d49f96c3384657f92dd16cda5710fdaa95215908a323cb1d629b9eede1edb500664170533}"
PRODUCTS=("$@")

if [ "${#PRODUCTS[@]}" -eq 0 ]; then
  PRODUCTS=(arm64_virt x86_64_virt)
fi

for product in "${PRODUCTS[@]}"; do
  case "${product}" in
    armv7a_virt|arm64_virt|x86_64_virt) ;;
    *)
      echo "unsupported product for this no-patch build script: ${product}" >&2
      exit 2
      ;;
  esac
done

if [ "${PRUNE_PRODUCT_OUT_AFTER_PACKAGE}" != "0" ] && \
   [ "${PRUNE_PRODUCT_OUT_AFTER_PACKAGE}" != "1" ]; then
  echo "PRUNE_PRODUCT_OUT_AFTER_PACKAGE must be 0 or 1" >&2
  exit 2
fi
if [ "${PREPARE_ONLY}" != "0" ] && [ "${PREPARE_ONLY}" != "1" ]; then
  echo "PREPARE_ONLY must be 0 or 1" >&2
  exit 2
fi
if [ "${SOURCE_PREPARE_ONLY}" != "0" ] && [ "${SOURCE_PREPARE_ONLY}" != "1" ]; then
  echo "SOURCE_PREPARE_ONLY must be 0 or 1" >&2
  exit 2
fi
case "${PATCH_COMPONENTS_ONLY}" in 0|1) ;; *) echo 'PATCH_COMPONENTS_ONLY must be 0 or 1' >&2; exit 2 ;; esac
if [ "${OHOS_GITHUB_FALLBACK}" != "0" ] && [ "${OHOS_GITHUB_FALLBACK}" != "1" ]; then
  echo "OHOS_GITHUB_FALLBACK must be 0 or 1" >&2
  exit 2
fi
case "${PROFILE_STAMP_WRITE_RETRIES}" in
  ''|*[!0-9]*|0)
    echo "PROFILE_STAMP_WRITE_RETRIES must be a positive integer" >&2
    exit 2
    ;;
esac
case "${PROFILE_STAMP_WRITE_RETRY_DELAY}" in
  ''|*[!0-9]*)
    echo "PROFILE_STAMP_WRITE_RETRY_DELAY must be a non-negative integer" >&2
    exit 2
    ;;
esac

verify_manifest_baseline() {
  local actual
  if [ ! -d "${OHOS_ROOT}/.repo/manifests" ]; then
    echo "manifest checkout is missing under ${OHOS_ROOT}/.repo" >&2
    return 1
  fi
  actual="$(git -C "${OHOS_ROOT}/.repo/manifests" rev-parse HEAD 2>/dev/null || true)"
  if [ "${actual}" != "${MANIFEST_REVISION}" ]; then
    echo "OpenHarmony manifest mismatch: expected ${MANIFEST_REVISION}, found ${actual:-unknown}" >&2
    return 1
  fi
  echo "OpenHarmony manifest verified: ${OHOS_BRANCH} @ ${actual}"
}

require_docker_ubuntu_2204() {
  if [ "$(uname -s)" != "Linux" ]; then
    echo "this script must run inside Docker on Ubuntu 22.04" >&2
    exit 1
  fi
  if [ ! -r /etc/os-release ]; then
    echo "missing /etc/os-release; expected Docker image ubuntu:22.04" >&2
    exit 1
  fi
  # shellcheck disable=SC1091
  . /etc/os-release
  if [ "${ID:-}" != "ubuntu" ] || [ "${VERSION_ID:-}" != "22.04" ]; then
    echo "unsupported build OS: ${PRETTY_NAME:-unknown}; expected ubuntu:22.04" >&2
    exit 1
  fi
  if [ ! -f /.dockerenv ] &&
     ! grep -qaE '/(docker|containerd|kubepods)(/|$)' /proc/1/cgroup 2>/dev/null &&
     [ "${ALLOW_NON_DOCKER}" != "1" ]; then
    echo "this build must run inside Docker, not directly on the host" >&2
    exit 1
  fi
  if [ ! -f /.dockerenv ] &&
     ! grep -qaE '/(docker|containerd|kubepods)(/|$)' /proc/1/cgroup 2>/dev/null; then
    echo "running in an explicitly allowed isolated Ubuntu 22.04 VM"
  fi
}

require_docker_ubuntu_2204

install_deps() {
  if [ "${SKIP_APT}" = "1" ]; then
    return
  fi
  if ! command -v apt-get >/dev/null 2>&1; then
    echo "apt-get not found; set SKIP_APT=1 if dependencies are already installed" >&2
    return
  fi
  if [ "$(id -u)" != "0" ]; then
    echo "not root; skip apt dependency installation" >&2
    return
  fi

  export DEBIAN_FRONTEND=noninteractive
  apt-get update

  # Host-arch package set. x86 multilib packages only exist on amd64 images.
  local host_arch
  host_arch="$(dpkg --print-architecture 2>/dev/null || uname -m)"
  local -a apt_packages=(
    autoconf
    automake
    bc
    bison
    build-essential
    ca-certificates
    ccache
    cmake
    cpio
    curl
    default-jdk
    dosfstools
    e2fsprogs
    file
    flex
    g++
    gcc
    gcc-arm-none-eabi
    genext2fs
    git
    git-lfs
    gettext
    gperf
    libelf-dev
    libfl-dev
    libgmp-dev
    libmpc-dev
    libmpfr-dev
    libncurses5
    libncurses5-dev
    libncursesw5-dev
    libssl-dev
    libxml2-utils
    libtool
    make
    mtd-utils
    mtools
    ninja-build
    openssh-client
    openssl
    pkg-config
    python-is-python3
    python3
    python3-pip
    python3-setuptools
    python3-venv
    rsync
    ruby
    scons
    unzip
    u-boot-tools
    wget
    zip
    zlib1g-dev
  )
  case "${host_arch}" in
    amd64|x86_64|i386)
      apt_packages+=(
        lib32stdc++6
        lib32z1
        libc6-dev-i386
      )
      ;;
    *)
      echo "host architecture ${host_arch}: skipping x86 multilib apt packages"
      ;;
  esac

  if [ "${QEMU_HOST_GN_QEMU_USER}" = 1 ]; then
    apt_packages+=(qemu-user-static)
  fi

  apt-get install -y --no-install-recommends "${apt_packages[@]}"

  command -v git >/dev/null
  command -v ssh >/dev/null
  if [ ! -f /usr/include/FlexLexer.h ]; then
    echo "missing /usr/include/FlexLexer.h; install libfl-dev in the Docker image" >&2
    exit 1
  fi

  git lfs install --system >/dev/null 2>&1 || true
}

verify_armv7_kernel_host_deps() {
  local product
  local needs_armv7=0
  for product in "${PRODUCTS[@]}"; do
    if [ "${product}" = "armv7a_virt" ]; then
      needs_armv7=1
      break
    fi
  done
  if [ "${needs_armv7}" != "1" ]; then
    return
  fi

  # Linux 6.6 enables an ARM GCC host plugin whose GCC-provided headers
  # include <gmp.h>.  Most OHOS targets do not exercise this path, so a stale
  # dependency image can otherwise fail hours into an armv7 build.
  if ! printf '#include <gmp.h>\n' | c++ -E -x c++ - >/dev/null 2>&1; then
    echo "armv7a_virt kernel build requires the host GMP header (libgmp-dev)" >&2
    echo "rerun with SKIP_APT=0 or refresh the Docker dependency image" >&2
    exit 1
  fi
}

ensure_python_module() {
  local python_bin="$1"
  local module="$2"
  local package="$3"
  if ! command -v "${python_bin}" >/dev/null 2>&1 && [ ! -x "${python_bin}" ]; then
    return
  fi
  # Skip host-prebuilt interpreters that cannot actually execute on this
  # container (e.g. linux-x86 python on a pure arm64 image without multiarch).
  if ! "${python_bin}" -c 'import sys' >/dev/null 2>&1; then
    echo "skip unusable python interpreter: ${python_bin}"
    return
  fi
  if "${python_bin}" - "${module}" <<'PY' >/dev/null 2>&1
import importlib
import sys
importlib.import_module(sys.argv[1])
PY
  then
    return
  fi

  echo "install missing python module for ${python_bin}: ${package}"
  local pip_scope_args=()
  if [ "$(id -u)" != "0" ]; then
    pip_scope_args+=(--user)
  fi
  if ! "${python_bin}" -m pip install \
    "${pip_scope_args[@]}" \
    --trusted-host repo.huaweicloud.com \
    -i https://repo.huaweicloud.com/repository/pypi/simple \
    "${package}"; then
    "${python_bin}" -m pip install \
      "${pip_scope_args[@]}" \
      --break-system-packages \
      --trusted-host repo.huaweicloud.com \
      -i https://repo.huaweicloud.com/repository/pypi/simple \
      "${package}"
  fi
}

ensure_python_modules() {
  ensure_python_module python3 typing_extensions "typing_extensions>=4.12.2"
  ensure_python_module python3 json5 json5
  ensure_python_module python3 yaml PyYAML
  ensure_python_module python3 mesonbuild "meson>=1.1,<2"
  ensure_python_module python3 mako "mako>=0.8"

  local python_bin
  for python_bin in \
    "${OHOS_ROOT}/prebuilts/python/linux-x86/current/bin/python3" \
    "${OHOS_ROOT}/prebuilts/python/linux-x86/3.12.10/bin/python3"; do
    if [ -x "${python_bin}" ]; then
      ensure_python_module "${python_bin}" typing_extensions "typing_extensions>=4.12.2"
      ensure_python_module "${python_bin}" json5 json5
      ensure_python_module "${python_bin}" yaml PyYAML
      ensure_python_module "${python_bin}" mako "mako>=0.8"
    fi
  done
}

raise_nofile_limit() {
  local wanted="${NOFILE_LIMIT:-1048576}"
  local current
  current="$(ulimit -n)"
  if [ "${current}" != "unlimited" ] && [ "${current}" -lt "${wanted}" ]; then
    ulimit -n "${wanted}" >/dev/null 2>&1 || true
  fi
}

configure_user_tools() {
  mkdir -p "${CONTAINER_HOME}" "${CACHE_ROOT}/npm-cache" "${CACHE_ROOT}/logs"
  export HOME="${CONTAINER_HOME}"
  export PATH="${CONTAINER_HOME}/.local/bin:${PATH}"
  export npm_config_cache="${CACHE_ROOT}/npm-cache"
  export NPM_CONFIG_CACHE="${CACHE_ROOT}/npm-cache"
  export NPM_CONFIG_REGISTRY="${NPM_REGISTRY}"
  export NPM_CONFIG_FETCH_RETRIES="${NPM_CONFIG_FETCH_RETRIES:-10}"
  export NPM_CONFIG_FETCH_RETRY_MINTIMEOUT="${NPM_CONFIG_FETCH_RETRY_MINTIMEOUT:-20000}"
  export NPM_CONFIG_FETCH_RETRY_MAXTIMEOUT="${NPM_CONFIG_FETCH_RETRY_MAXTIMEOUT:-120000}"
  export NPM_CONFIG_FETCH_TIMEOUT="${NPM_CONFIG_FETCH_TIMEOUT:-600000}"
  export NPM_CONFIG_PROGRESS=false
  export NPM_CONFIG_AUDIT=false
  export NPM_CONFIG_FUND=false

  {
    echo "registry=${NPM_REGISTRY}"
    echo "cache=${CACHE_ROOT}/npm-cache"
    echo "fetch-retries=${NPM_CONFIG_FETCH_RETRIES}"
    echo "fetch-retry-mintimeout=${NPM_CONFIG_FETCH_RETRY_MINTIMEOUT}"
    echo "fetch-retry-maxtimeout=${NPM_CONFIG_FETCH_RETRY_MAXTIMEOUT}"
    echo "fetch-timeout=${NPM_CONFIG_FETCH_TIMEOUT}"
    echo "progress=false"
    echo "audit=false"
    echo "fund=false"
    if [ -n "${HTTP_PROXY:-${http_proxy:-}}" ]; then
      echo "proxy=${HTTP_PROXY:-${http_proxy:-}}"
    fi
    if [ -n "${HTTPS_PROXY:-${https_proxy:-}}" ]; then
      echo "https-proxy=${HTTPS_PROXY:-${https_proxy:-}}"
    elif [ -n "${HTTP_PROXY:-${http_proxy:-}}" ]; then
      echo "https-proxy=${HTTP_PROXY:-${http_proxy:-}}"
    fi
  } > "${CONTAINER_HOME}/.npmrc"

  git config --global --add safe.directory '*' >/dev/null 2>&1 || true
  git config --global user.name "${GIT_USER_NAME}"
  git config --global user.email "${GIT_USER_EMAIL}"
  git config --global checkout.workers 1
  git config --global index.threads 1
  git config --global http.version HTTP/1.1

  # compile_app.py launches ohpm with a minimal environment, so Node falls
  # back to the passwd home instead of CONTAINER_HOME. Keep both paths on the
  # persistent cache without changing OpenHarmony sources.
  local passwd_home
  passwd_home="$(getent passwd "$(id -u)" | cut -d: -f6)"
  local persistent_ohpm="${CONTAINER_HOME}/.ohpm"
  local passwd_ohpm="${passwd_home}/.ohpm"
  mkdir -p "${persistent_ohpm}"
  if [ "${passwd_ohpm}" != "${persistent_ohpm}" ]; then
    if [ -d "${passwd_ohpm}" ] && [ ! -L "${passwd_ohpm}" ]; then
      if [ -d "${passwd_ohpm}/cache" ]; then
        mkdir -p "${persistent_ohpm}/cache"
        cp -an "${passwd_ohpm}/cache/." "${persistent_ohpm}/cache/"
      fi
      if [ -f "${passwd_ohpm}/.ohpmrc" ] && [ ! -e "${persistent_ohpm}/.ohpmrc" ]; then
        cp -p "${passwd_ohpm}/.ohpmrc" "${persistent_ohpm}/.ohpmrc"
      fi
      rm -rf "${passwd_ohpm}"
    fi
    ln -sfn "${persistent_ohpm}" "${passwd_ohpm}"
  fi
}

ensure_host_tools() {
  if ! command -v uv >/dev/null 2>&1; then
    echo "install missing host tool: uv"
    python3 -m pip install --user \
      --trusted-host repo.huaweicloud.com \
      -i https://repo.huaweicloud.com/repository/pypi/simple \
      uv
  fi
  command -v uv >/dev/null
}

ensure_repo_tool() {
  if command -v repo >/dev/null 2>&1; then
    return
  fi
  if [ "$(id -u)" != "0" ]; then
    echo "repo command not found; install repo or rerun as root without SKIP_APT=1" >&2
    exit 1
  fi
  curl -fsSL "${REPO_LAUNCHER_URL}" -o /usr/local/bin/repo
  chmod +x /usr/local/bin/repo
}

configure_project_mirror() {
  local previous_mirror
  previous_mirror="$(git config --global --get ohos-qemu.projectMirror 2>/dev/null || true)"
  if [ -n "${previous_mirror}" ] && [ "${previous_mirror}" != "${OHOS_PROJECT_MIRROR}" ]; then
    git config --global --unset-all \
      "url.${previous_mirror}.insteadOf" \
      "https://gitcode.com/openharmony/" 2>/dev/null || true
    git config --global --unset-all ohos-qemu.projectMirror 2>/dev/null || true
  fi
  if [ -z "${OHOS_PROJECT_MIRROR}" ]; then
    echo "OpenHarmony project mirror rewrite disabled"
    return
  fi
  case "${OHOS_PROJECT_MIRROR}" in
    */) ;;
    *) OHOS_PROJECT_MIRROR="${OHOS_PROJECT_MIRROR}/" ;;
  esac

  # The pinned 7.0 manifest itself comes from GitHub, but its project remote
  # intentionally still names GitCode. Git's insteadOf mapping keeps the
  # upstream manifest byte-for-byte fixed while fetching every project from
  # the corresponding official GitHub mirror.
  git config --global --replace-all \
    "url.${OHOS_PROJECT_MIRROR}.insteadOf" \
    "https://gitcode.com/openharmony/"
  git config --global --replace-all ohos-qemu.projectMirror "${OHOS_PROJECT_MIRROR}"
  echo "OpenHarmony project mirror: https://gitcode.com/openharmony/ -> ${OHOS_PROJECT_MIRROR}"
}

install_github_fallback_manifest() {
  local local_manifest="${OHOS_ROOT}/.repo/local_manifests/ohos-qemu-7.0-github-fallback.xml"
  if [ "${OHOS_GITHUB_FALLBACK}" != "1" ] || [ -z "${OHOS_PROJECT_MIRROR}" ]; then
    rm -f "${local_manifest}"
    echo "OpenHarmony GitHub fallback manifest disabled"
    return
  fi
  if [ ! -f "${OHOS_GITHUB_FALLBACK_MAP}" ]; then
    echo "missing GitHub fallback map: ${OHOS_GITHUB_FALLBACK_MAP}" >&2
    exit 1
  fi

  mkdir -p "$(dirname "${local_manifest}")"
  python3 - "${OHOS_GITHUB_FALLBACK_MAP}" "${OHOS_FALLBACK_MIRROR_ROOT}" \
    "${local_manifest}" <<'PY'
import hashlib
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

mapping = Path(sys.argv[1])
mirror_root = Path(sys.argv[2]).resolve()
destination = Path(sys.argv[3])
rows = []
for number, raw in enumerate(mapping.read_text(encoding="utf-8").splitlines(), 1):
    line = raw.strip()
    if not line or line.startswith("#"):
        continue
    fields = line.split()
    if len(fields) != 3:
        raise SystemExit(f"{mapping}:{number}: expected 3 columns")
    name, source, revision = fields
    if source not in {"github-cache", "gitcode-cache", "omit"}:
        raise SystemExit(f"{mapping}:{number}: unsupported source {source}")
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise SystemExit(f"{mapping}:{number}: invalid pinned commit {revision}")
    rows.append((name, source, revision))

root = ET.Element("manifest")
cache_remote = "ohos-qemu-release-cache"
ET.SubElement(
    root,
    "remote",
    name=cache_remote,
    fetch=mirror_root.as_uri() + "/",
)
release_tag = "refs/tags/OpenHarmony-v7.0-Release"
for name, source, revision in rows:
    if source == "omit":
        ET.SubElement(root, "remove-project", name=name)
        continue
    repository = mirror_root / f"{name}.git"
    if not repository.is_dir():
        raise SystemExit(f"missing host-prepared fallback mirror: {repository}")
    actual = subprocess.check_output(
        ["git", f"--git-dir={repository}", "rev-parse", f"{release_tag}^{{commit}}"],
        text=True,
    ).strip()
    if actual != revision:
        raise SystemExit(
            f"fallback mirror mismatch for {name}: expected {revision}, found {actual}"
        )
    attributes = {
        "name": name,
        "remote": cache_remote,
        "revision": revision,
        "upstream": release_tag,
    }
    ET.SubElement(root, "extend-project", **attributes)

ET.indent(root, space="  ")
payload = ET.tostring(root, encoding="utf-8", xml_declaration=True) + b"\n"
destination.write_bytes(payload)
print(
    f"installed GitHub fallback manifest: {len(rows)} pinned projects, "
    f"map sha256={hashlib.sha256(mapping.read_bytes()).hexdigest()}"
)
PY
}

verify_github_fallback_revisions() {
  if [ "${OHOS_GITHUB_FALLBACK}" != "1" ] || [ -z "${OHOS_PROJECT_MIRROR}" ]; then
    return
  fi
  (
    cd "${OHOS_ROOT}"
    python3 - "${OHOS_GITHUB_FALLBACK_MAP}" <<'PY'
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

mapping = Path(sys.argv[1])
manifest = ET.fromstring(subprocess.check_output(["repo", "manifest"]))
paths = {
    project.attrib["name"]: project.attrib.get("path", project.attrib["name"])
    for project in manifest.findall("project")
}
verified = 0
for number, raw in enumerate(mapping.read_text(encoding="utf-8").splitlines(), 1):
    line = raw.strip()
    if not line or line.startswith("#"):
        continue
    name, source, expected = line.split()
    if source == "omit":
        if name in paths:
            raise SystemExit(f"omitted project is still present in resolved manifest: {name}")
        verified += 1
        continue
    if name not in paths:
        raise SystemExit(f"{mapping}:{number}: project is absent from resolved manifest: {name}")
    checkout = Path(paths[name])
    actual = subprocess.check_output(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True
    ).strip()
    if actual != expected:
        raise SystemExit(
            f"fallback checkout mismatch for {name}: expected {expected}, found {actual}"
        )
    verified += 1
print(f"verified {verified} pinned OpenHarmony 7.0 fallback checkouts")
PY
  )
}

prepare_checkout() {
  mkdir -p "${CACHE_ROOT}" "${OHOS_ROOT}" "${PACKAGE_ROOT}" "${CACHE_ROOT}/logs" "${CCACHE_DIR}"
  cd "${OHOS_ROOT}"
  configure_project_mirror
  if [ "${SKIP_REPO_SYNC}" = "1" ] && [ -d .repo ]; then
    install_github_fallback_manifest
    python3 "${SCRIPT_DIR}/openharmony_release_source_lock.py" --source-root "${OHOS_ROOT}" --install
    if ! verify_manifest_baseline; then
      echo "refusing to reuse a checkout from another baseline; rerun with SKIP_REPO_SYNC=0" >&2
      exit 1
    fi
    verify_github_fallback_revisions
    python3 "${SCRIPT_DIR}/openharmony_release_source_lock.py" --source-root "${OHOS_ROOT}"
    echo "skip repo init/sync; reusing existing checkout at ${OHOS_ROOT}"
    return
  fi

  local repo_init_args=(
    init
    -u "${MANIFEST_URL}"
    -b "${MANIFEST_REVISION}"
    -g "${MANIFEST_GROUPS}"
    --repo-url="${REPO_URL}"
    --no-repo-verify
  )
  if [ "${REPO_NO_BUNDLE}" = "1" ]; then
    repo_init_args+=(--no-clone-bundle)
  fi
  repo "${repo_init_args[@]}"
  install_github_fallback_manifest
  python3 "${SCRIPT_DIR}/openharmony_release_source_lock.py" --source-root "${OHOS_ROOT}" --install
  verify_manifest_baseline

  local repo_sync_args=(
    sync
    -c
    -j"${REPO_JOBS}"
  )
  if [ "${REPO_NO_TAGS}" = "1" ]; then
    repo_sync_args+=(--no-tags)
  fi
  if [ "${REPO_FORCE_SYNC}" = "1" ]; then
    repo_sync_args+=(--force-sync)
  fi
  if [ "${REPO_NO_BUNDLE}" = "1" ]; then
    repo_sync_args+=(--no-clone-bundle)
  fi
  if repo sync -h 2>&1 | grep -q -- '--jobs-checkout'; then
    repo_sync_args+=(--jobs-checkout="${REPO_CHECKOUT_JOBS}")
  fi

  local attempt=1
  while true; do
    if repo "${repo_sync_args[@]}"; then
      break
    fi
    if [ "${attempt}" -ge "${REPO_SYNC_RETRIES}" ]; then
      echo "repo sync failed after ${attempt} attempts" >&2
      exit 1
    fi
    echo "repo sync failed; retry ${attempt}/${REPO_SYNC_RETRIES} after 20s"
    sleep 20
    attempt=$((attempt + 1))
  done
  verify_manifest_baseline
  verify_github_fallback_revisions
  python3 "${SCRIPT_DIR}/openharmony_release_source_lock.py" --source-root "${OHOS_ROOT}"
}

configure_out_volume_ccache() {
  if [ "${QEMU_CCACHE_ON_OUT_VOLUME}" != "1" ]; then
    return
  fi

  # hb's --ccache resolver intentionally replaces CCACHE_DIR with
  # $CCACHE_BASE/$CCACHE_LOCAL_DIR. On a macOS bind mount this eventually
  # exhausts VirtioFS file handles even when the container nofile limit is
  # high. Keep both the cache and temporary files on the native Linux out
  # volume used by the full 2in1 build.
  local native_ccache="${OHOS_ROOT}/out/.ccache"
  local native_tmp="${OHOS_ROOT}/out/.ccache-tmp"
  local seed_marker="${native_ccache}/.ohos-qemu-host-cache-seeded"
  mkdir -p "${native_ccache}" "${native_tmp}"

  if [ ! -f "${seed_marker}" ]; then
    local source_cache
    for source_cache in "${CONTAINER_HOME}/.ccache" "${CCACHE_DIR}"; do
      if [ -d "${source_cache}" ] && [ "${source_cache}" != "${native_ccache}" ]; then
        echo "seed native Linux ccache from ${source_cache}"
        rsync -a --ignore-existing "${source_cache}/" "${native_ccache}/"
      fi
    done
    touch "${seed_marker}"
  fi

  CCACHE_BASE="${OHOS_ROOT}/out"
  CCACHE_LOCAL_DIR=.ccache
  CCACHE_TEMPDIR="${native_tmp}"
  CCACHE_DIR="${native_ccache}"
  export CCACHE_BASE CCACHE_LOCAL_DIR CCACHE_TEMPDIR CCACHE_DIR
  echo "ccache native volume: ${CCACHE_DIR} (temp: ${CCACHE_TEMPDIR})"
}

sync_git_lfs_objects() {
  if [ "${SKIP_GIT_LFS}" = "1" ]; then
    echo "skip git lfs pull"
    return
  fi
  if [ ! -d "${OHOS_ROOT}/.repo" ]; then
    return
  fi
  if ! git lfs version >/dev/null 2>&1; then
    echo "git-lfs not found; install git-lfs or set SKIP_GIT_LFS=1 only if LFS objects are already present" >&2
    exit 1
  fi

  cd "${OHOS_ROOT}"
  echo "sync Git LFS objects: ${GIT_LFS_PATHS}"
  local path
  for path in ${GIT_LFS_PATHS}; do
    if [ ! -e "${OHOS_ROOT}/${path}/.git" ]; then
      echo "skip git lfs path without git metadata: ${path}"
      continue
    fi
    echo "git lfs pull: ${path}"
    git -C "${OHOS_ROOT}/${path}" lfs pull
  done
}

apply_github_lfs_asset_component() {
  if [ ! -x "${GITHUB_LFS_ASSET_COMPONENT_SCRIPT}" ]; then
    echo "missing GitHub/LFS compatibility component: ${GITHUB_LFS_ASSET_COMPONENT_SCRIPT}" >&2
    exit 1
  fi
  bash "${GITHUB_LFS_ASSET_COMPONENT_SCRIPT}" \
    --source-root "${OHOS_ROOT}" \
    --asset-root "${OHOS_LFS_ASSET_ROOT}" \
    --asset-map "${GITHUB_LFS_ASSET_MAP}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_github_lfs_assets.log"
}

restore_staged_sceneboard_lfs_assets() {
  # A previous architecture leaves the renewed HAPs in the persistent source
  # volume. Restore only those exact staged files to their pinned originals so
  # the LFS baseline audit can run again before this build stages them anew.
  local hap target renewed oid object
  for hap in SceneBoard.hap NotificationManagement.hap ThemeService.hap ThemeComponent.hap; do
    target="${OHOS_ROOT}/applications/standard/hap/sceneboard/${hap}"
    renewed="${SCENEBOARD_RUNTIME_ASSET_ROOT}/${hap}"
    if [ ! -f "${target}" ] || [ ! -f "${renewed}" ] || ! cmp -s "${target}" "${renewed}"; then
      continue
    fi
    oid="$(awk -F '\t' -v relative="sceneboard/${hap}" \
      '$1 == "applications/standard/hap" && $2 == relative { print $4 }' \
      "${GITHUB_LFS_ASSET_MAP}")"
    [ "${#oid}" -eq 64 ] || {
      echo "missing pinned LFS object for SceneBoard ${hap}" >&2
      exit 1
    }
    object="${OHOS_LFS_ASSET_ROOT}/${oid:0:2}/${oid}"
    [ -f "${object}" ] && [ "$(sha256sum "${object}" | awk '{print $1}')" = "${oid}" ] || {
      echo "invalid pinned LFS object for SceneBoard ${hap}" >&2
      exit 1
    }
    cp -p "${object}" "${target}"
    echo "restored pinned SceneBoard LFS asset before baseline audit: ${hap}"
  done
}

verify_git_lfs_objects() {
  if ! git lfs version >/dev/null 2>&1; then
    echo "git-lfs not found; cannot verify cached LFS objects" >&2
    exit 1
  fi

  local path
  local relative_path
  local object_path
  local first_line
  local missing=0
  for path in ${GIT_LFS_PATHS}; do
    if [ ! -e "${OHOS_ROOT}/${path}/.git" ]; then
      continue
    fi
    while IFS= read -r relative_path; do
      [ -n "${relative_path}" ] || continue
      object_path="${OHOS_ROOT}/${path}/${relative_path}"
      if [ ! -f "${object_path}" ]; then
        echo "missing Git LFS worktree file: ${path}/${relative_path}" >&2
        missing=1
        continue
      fi
      IFS= read -r first_line < "${object_path}" || true
      if [ "${first_line}" = "version https://git-lfs.github.com/spec/v1" ]; then
        echo "unresolved Git LFS pointer: ${path}/${relative_path}" >&2
        missing=1
      fi
    done < <(git -C "${OHOS_ROOT}/${path}" lfs ls-files --name-only)

    while IFS= read -r object_path; do
      [ -n "${object_path}" ] || continue
      echo "unresolved former-LFS text stub: ${object_path#${OHOS_ROOT}/}" >&2
      missing=1
    done < <(
      find "${OHOS_ROOT}/${path}" -type f -size -1024c \
        -exec grep -Il 'This file was originally tracked by Git LFS' {} + \
        2>/dev/null || true
    )
  done

  if [ "${missing}" -ne 0 ]; then
    echo "cached checkout has unresolved Git LFS objects; rerun without SKIP_GIT_LFS=1" >&2
    exit 1
  fi
}

remove_under_ohos_root() {
  local path="$1"
  case "${path}" in
    "${OHOS_ROOT}"/*) rm -rf "${path}" ;;
    *)
      echo "refusing to remove path outside OHOS_ROOT: ${path}" >&2
      exit 1
      ;;
  esac
}

write_profile_stamp_with_retry() {
  local profile_stamp="$1"
  local profile="$2"
  local profile_stamp_dir
  local profile_stamp_tmp="${profile_stamp}.tmp.$$"
  local attempt
  profile_stamp_dir="$(dirname "${profile_stamp}")"

  for ((attempt = 1; attempt <= PROFILE_STAMP_WRITE_RETRIES; attempt++)); do
    if mkdir -p "${profile_stamp_dir}" 2>/dev/null &&
       (printf '%s\n' "${profile}" > "${profile_stamp_tmp}" &&
        mv -f -- "${profile_stamp_tmp}" "${profile_stamp}") 2>/dev/null; then
      return 0
    fi

    rm -f -- "${profile_stamp_tmp}" 2>/dev/null || true
    if [ "${attempt}" -eq "${PROFILE_STAMP_WRITE_RETRIES}" ]; then
      echo "failed to write profile stamp after ${attempt} attempts: ${profile_stamp}" >&2
      df -h "${profile_stamp_dir}" >&2 || true
      return 1
    fi
    if [ "${attempt}" -eq 1 ] || [ $((attempt % 10)) -eq 0 ]; then
      echo "waiting for output-volume block reclaim before writing profile stamp (${attempt}/${PROFILE_STAMP_WRITE_RETRIES})"
    fi
    sync || true
    sleep "${PROFILE_STAMP_WRITE_RETRY_DELAY}"
  done
}

remove_under_cache_root() {
  local path="$1"
  case "${path}" in
    "${CACHE_ROOT}"/*) rm -rf "${path}" ;;
    *)
      echo "refusing to remove path outside CACHE_ROOT: ${path}" >&2
      exit 1
      ;;
  esac
}

clean_js_prebuilts_state() {
  echo "clean JS dependency/prebuilt state left by interrupted npm installs"
  remove_under_ohos_root "${OHOS_ROOT}/third_party/jsframework/node_modules"
  remove_under_ohos_root "${OHOS_ROOT}/third_party/parse5/packages/parse5/node_modules"
  remove_under_ohos_root "${OHOS_ROOT}/third_party/weex-loader/node_modules"
  remove_under_ohos_root "${OHOS_ROOT}/arkcompiler/ets_frontend/legacy_bin/api8/node_modules"
  remove_under_ohos_root "${OHOS_ROOT}/prebuilts/build-tools/common/js-framework/node_modules"
  remove_under_cache_root "${CACHE_ROOT}/npm-cache"
  remove_under_cache_root "${CONTAINER_HOME}/.npm/_cacache/jsframework"
}

ETS12_PREBUILTS_CONFIG_BACKUP=""
ETS12_SEPARATE_NPM_INSTALL=0

restore_ets12_prebuilts_config() {
  if [ -z "${ETS12_PREBUILTS_CONFIG_BACKUP}" ]; then
    return
  fi
  local config="${OHOS_ROOT}/build/prebuilts_config.json"
  if [ -f "${ETS12_PREBUILTS_CONFIG_BACKUP}" ]; then
    cp -p "${ETS12_PREBUILTS_CONFIG_BACKUP}" "${config}"
    rm -f "${ETS12_PREBUILTS_CONFIG_BACKUP}"
  fi
  ETS12_PREBUILTS_CONFIG_BACKUP=""
}

prepare_ets12_separate_npm_install() {
  if [ "${SKIP_PREBUILTS}" = "1" ]; then
    return
  fi

  local config="${OHOS_ROOT}/build/prebuilts_config.json"
  local package_json="${OHOS_ROOT}/developtools/ace_ets2bundle/ets1.2/package.json"
  if [ ! -f "${config}" ] || [ ! -f "${package_json}" ]; then
    return
  fi

  ETS12_PREBUILTS_CONFIG_BACKUP="$(mktemp "${CACHE_ROOT}/prebuilts_config.ets12.XXXXXX.json")"
  cp -p "${config}" "${ETS12_PREBUILTS_CONFIG_BACKUP}"
  if ! python3 - "${config}" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
target = "${code_dir}/developtools/ace_ets2bundle/ets1.2"
data = json.loads(path.read_text())
removed = 0

def remove_target(value):
    global removed
    if isinstance(value, dict):
        for child in value.values():
            remove_target(child)
    elif isinstance(value, list):
        before = len(value)
        value[:] = [item for item in value if item != target]
        removed += before - len(value)
        for child in value:
            remove_target(child)

remove_target(data)
if removed != 1:
    raise SystemExit(f"expected one ets1.2 npm entry, removed {removed}")
path.write_text(json.dumps(data, ensure_ascii=False, indent=4) + "\n")
PY
  then
    restore_ets12_prebuilts_config
    return 1
  fi

  ETS12_SEPARATE_NPM_INSTALL=1
  echo "install ets1.2 separately to avoid npm 6 local-package staging collision"
}

install_ets12_node_modules() {
  if [ "${ETS12_SEPARATE_NPM_INSTALL}" != "1" ]; then
    return
  fi

  local root="${OHOS_ROOT}/developtools/ace_ets2bundle/ets1.2"
  local npm_tool="${OHOS_ROOT}/prebuilts/build-tools/common/nodejs/current/bin/npm"
  if [ ! -x "${npm_tool}" ]; then
    echo "missing OpenHarmony npm tool: ${npm_tool}" >&2
    exit 1
  fi

  remove_under_ohos_root "${root}/node_modules"
  (
    cd "${root}"
    PATH="$(dirname "${npm_tool}"):${PATH}" \
      "${npm_tool}" install \
      --registry "${NPM_REGISTRY}" \
      --cache "${CONTAINER_HOME}/.npm/_cacache/ets1.2" \
      --package-lock=false \
      --unsafe-perm
  ) 2>&1 | tee "${CACHE_ROOT}/logs/npm_install_ets12.log"
}

download_prebuilts() {
  cd "${OHOS_ROOT}"
  if [ "${SKIP_PREBUILTS}" = "1" ]; then
    echo "skip prebuilts_download.sh; reusing existing prebuilts"
    return
  fi
  if [ ! -x build/prebuilts_download.sh ]; then
    echo "missing build/prebuilts_download.sh under ${OHOS_ROOT}" >&2
    exit 1
  fi
  if [ "${PREBUILTS_CLEAN}" = "1" ]; then
    clean_js_prebuilts_state
  fi

  set +e
  bash build/prebuilts_download.sh 2>&1 | tee "${CACHE_ROOT}/logs/prebuilts_download.log"
  local rc="${PIPESTATUS[0]}"
  set -e
  if [ "${rc}" = "0" ] || [ "${PREBUILTS_RETRY}" != "1" ]; then
    return "${rc}"
  fi

  clean_js_prebuilts_state
  set +e
  bash build/prebuilts_download.sh 2>&1 | tee "${CACHE_ROOT}/logs/prebuilts_download.retry.log"
  rc="${PIPESTATUS[0]}"
  set -e
  return "${rc}"
}

configure_ohos_node_path() {
  local node_root="${OHOS_ROOT}/prebuilts/build-tools/common/nodejs"
  local node_bin=""
  local candidate
  for candidate in \
    "${node_root}"/node-v18*-linux-x64/bin \
    "${node_root}/current/bin"; do
    if [ -x "${candidate}/node" ] && [ -x "${candidate}/npm" ]; then
      node_bin="${candidate}"
      break
    fi
  done
  if [ -z "${node_bin}" ]; then
    echo "missing OpenHarmony Node.js 18 prebuilt under ${node_root}" >&2
    exit 1
  fi

  export PATH="${node_bin}:${PATH}"
  hash -r
  local node_major
  node_major="$(node -p 'Number(process.versions.node.split(".")[0])')"
  if [ "${node_major}" -lt 18 ]; then
    echo "OpenHarmony build requires Node.js 18+, found $(node --version)" >&2
    exit 1
  fi
  echo "OpenHarmony build Node.js: $(node --version) from $(command -v node)"
}

repair_ets12_node_modules() {
  local root="${OHOS_ROOT}/developtools/ace_ets2bundle/ets1.2"
  local npm_tool=(
    "${OHOS_ROOT}/prebuilts/build-tools/common/nodejs/current/bin/npm"
  )
  if [ ! -d "${root}/node_modules" ]; then
    return
  fi
  if [ ! -x "${npm_tool[0]}" ]; then
    echo "missing OpenHarmony npm tool: ${npm_tool[0]}" >&2
    exit 1
  fi

  # npm 6 resolves nested file: dependencies relative to the top-level
  # node_modules symlink. Repair those generated links at their physical
  # package locations so TypeScript project references resolve normally.
  local package
  local dependency
  for package in common compat interop libarkts; do
    mkdir -p "${root}/${package}/node_modules/@koalaui"
  done
  for dependency in build-common compat; do
    ln -sfn "../../../${dependency}" \
      "${root}/common/node_modules/@koalaui/${dependency}"
  done
  ln -sfn "../../../build-common" \
    "${root}/compat/node_modules/@koalaui/build-common"
  for dependency in build-common common compat; do
    ln -sfn "../../../${dependency}" \
      "${root}/interop/node_modules/@koalaui/${dependency}"
  done
  for dependency in build-common common compat interop; do
    ln -sfn "../../../${dependency}" \
      "${root}/libarkts/node_modules/@koalaui/${dependency}"
  done
  if [ -d "${root}/interop/node_modules/@types/node" ]; then
    mkdir -p "${root}/node_modules/@types"
    ln -sfn "../../interop/node_modules/@types/node" \
      "${root}/node_modules/@types/node"
  fi

  if [ ! -x "${root}/node_modules/.bin/arktscgen" ]; then
    echo "restore ets1.2 npm executable links"
    (
      cd "${root}"
      "${npm_tool[@]}" rebuild \
        --registry "${NPM_REGISTRY}" \
        --cache "${CACHE_ROOT}/npm-cache" \
        --unsafe-perm
    )
  fi
}

build_product() {
  local product="$1"
  local kernel_obj="${product}"
  local kernel_image="Image"
  if [ "${product}" = "armv7a_virt" ]; then
    kernel_obj="arm_virt"
    kernel_image="zImage"
  elif [ "${product}" = "x86_64_virt" ]; then
    kernel_image="bzImage"
  fi
  cd "${OHOS_ROOT}"
  export CCACHE_DIR
  export OHOS_KERNEL_BUILD_JOBS="${KERNEL_BUILD_JOBS}"
  ccache -M "${CCACHE_MAXSIZE}" >/dev/null 2>&1 || true

  # A component-profile change must not reuse a target graph or case-collided
  # Taihe outputs from an earlier build. The host runner mounts out/ on a
  # case-sensitive Linux volume; this stamp also makes profile switches safe.
  local profile_stamp="${OHOS_ROOT}/out/.ohos-qemu-build-profile-${product}"
  local previous_profile=""
  if [ -f "${profile_stamp}" ]; then
    previous_profile="$(<"${profile_stamp}")"
  fi
  if [ -n "${previous_profile}" ] && [ "${previous_profile}" != "${DEVICE_TYPE_BUILD_PROFILE}" ]; then
    echo "device profile changed for ${product}: ${previous_profile} -> ${DEVICE_TYPE_BUILD_PROFILE}; clean product output"
    rm -rf "${OHOS_ROOT}/out/${product}" "${OHOS_ROOT}/out/preloader/${product}"
  fi
  # Docker-backed APFS storage can make space from the product cleanup visible
  # asynchronously. Preserve the previous stamp until the replacement can be
  # written and renamed, and give the backing store a bounded reclaim window.
  write_profile_stamp_with_retry "${profile_stamp}" "${DEVICE_TYPE_BUILD_PROFILE}"

  # Recent hb versions persist list-valued arguments in out/hb_args and append
  # the next invocation's values. Without clearing the generated defaults here,
  # sequential product builds can execute Ninja with multiple conflicting -j
  # values (for example, "-j2 -j8"). A preceding component-only validation can
  # also leak its build_target into this invocation, causing hb to build only
  # that component and then fail the --device-type post-image rewrite because
  # packages/phone/system/etc/param/ohos.para was never produced.
  python3 - "${OHOS_ROOT}/out/hb_args/buildargs.json" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
if path.is_file():
    data = json.loads(path.read_text(encoding="utf-8"))
    changed = False
    for name in ("ninja_args", "build_target"):
        argument = data.get(name)
        if isinstance(argument, dict) and argument.get("argDefault"):
            argument["argDefault"] = []
            changed = True
    if changed:
        path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
PY

  if [ "${CLEAN_KERNEL_OBJ}" = "1" ]; then
    rm -rf "${OHOS_ROOT}/out/KERNEL_OBJ"
    rm -rf "${OHOS_ROOT}/out/kernel/OBJ/${kernel_obj}"
    rm -f "${OHOS_ROOT}/out/${product}/packages/phone/images/${kernel_image}"
  fi

  local build_args=(
    ./build.sh
    --product-name "${product}"
    --build-target images
    --ccache
    "--ninja-args=-j${BUILD_JOBS}"
    --load-test-config=false
    --deps-guard=false
  )
  if [ -n "${DEVICE_TYPE}" ]; then
    # Ensure GN sees device_type at compile time (init ohos.para generation).
    # --device-type is a post-image rewrite in hb. In load-only mode explicitly
    # select its no-op "default" value: hb can otherwise inherit the profile's
    # 2in1 device type and try to rewrite ohos.para before it has been built.
    # The GN argument still selects the compile-time device type.
    build_args+=(--gn-args "device_type=${DEVICE_TYPE}")
    case "${DEVICE_TYPE}" in
      phone) build_args+=(--gn-args "target_platform=phone") ;;
      # AccessToken and other platform branches use pc, not the BMS device type
      # 2in1. Leaving GN's phone default disables PC-only permissions even in
      # an otherwise complete 2in1 product. Preserve their APL/ACL policy.
      2in1) build_args+=(--gn-args "target_platform=pc") ;;
    esac
  fi
  if [ "${NO_PREBUILT_SDK}" = "1" ]; then
    build_args+=(--no-prebuilt-sdk=true)
  fi
  if [ "${DEVICE_TYPE}" = "phone" ] || [ "${DEVICE_TYPE}" = "2in1" ]; then
    # Preload the newly patched profile and reject incompatible feature pairs
    # before compiling tens of thousands of targets. Old preloader output is
    # not evidence for the current inputs. Explicit false below also prevents
    # hb's persisted load-only argument leaking into the actual image build.
    "${build_args[@]}" --device-type default --build-only-load=true 2>&1 | tee "${CACHE_ROOT}/logs/load_${product}_${DEVICE_TYPE}.log"
    python3 "${PATCH_ROOT}/lib/network_features.py" \
      --features "${OHOS_ROOT}/out/preloader/${product}/features.json" --device "${DEVICE_TYPE}"
    python3 "${PATCH_ROOT}/lib/graphics_features.py" \
      --features "${OHOS_ROOT}/out/preloader/${product}/features.json" --device "${DEVICE_TYPE}"
    python3 "${PATCH_ROOT}/lib/audio_features.py" \
      --features "${OHOS_ROOT}/out/preloader/${product}/features.json" --device "${DEVICE_TYPE}"
    python3 "${PATCH_ROOT}/lib/camera_features.py" \
      --features "${OHOS_ROOT}/out/preloader/${product}/features.json" --device "${DEVICE_TYPE}"
    if [ "${BUILD_ONLY_LOAD}" = "1" ]; then
      return
    fi
  fi
  if [ "${BUILD_ONLY_LOAD}" = "1" ]; then
    build_args+=(--device-type default --build-only-load=true)
  else
    build_args+=(--build-only-load=false)
    if [ -n "${DEVICE_TYPE}" ]; then
      build_args+=(--device-type "${DEVICE_TYPE}")
    fi
  fi
  "${build_args[@]}" 2>&1 | tee "${CACHE_ROOT}/logs/build_${product}_${DEVICE_TYPE:-default}.log"
  if [ "${DEVICE_TYPE}" = "phone" ] || [ "${DEVICE_TYPE}" = "2in1" ]; then
    python3 "${PATCH_ROOT}/lib/permission_profile.py" \
      --source-root "${OHOS_ROOT}" --product "${product}" --device "${DEVICE_TYPE}"
  fi
}

package_product() {
  local product="$1"
  validate_prebuilt_haps "${product}"
  local package_args=(
    bash "${PACKAGER}"
    --source-root "${OHOS_ROOT}"
    --product "${product}"
    --output-dir "${PACKAGE_ROOT}"
  )
  if [ -n "${DEVICE_TYPE}" ]; then
    package_args+=(--device-type "${DEVICE_TYPE}")
  fi
  package_args+=(--device-type-profile "${DEVICE_TYPE_BUILD_PROFILE}")
  "${package_args[@]}" 2>&1 | tee "${CACHE_ROOT}/logs/package_${product}_${DEVICE_TYPE:-default}.log"
}

validate_prebuilt_haps() {
  local product="$1"
  local image_dir="${OHOS_ROOT}/out/${product}/packages/phone/images"
  local system_app_dir="${OHOS_ROOT}/out/${product}/packages/phone/system/app"
  local pointer_list="${CACHE_ROOT}/logs/lfs_pointer_haps_${product}.txt"

  if [ ! -d "${system_app_dir}" ]; then
    return
  fi

  : > "${pointer_list}"
  while IFS= read -r -d '' hap; do
    if head -c 64 "${hap}" | grep -q 'version https://git-lfs.github.com/spec'; then
      printf '%s\n' "${hap}" >> "${pointer_list}"
    fi
  done < <(find "${system_app_dir}" -type f -name '*.hap' -print0)

  if [ -s "${pointer_list}" ]; then
    echo "Git LFS pointer HAPs found in ${system_app_dir}; run git lfs pull for applications/standard/hap and rebuild ${product}." >&2
    cat "${pointer_list}" >&2
    exit 1
  fi

  if [ -d "${image_dir}" ]; then
    find "${image_dir}" -maxdepth 1 -type f -name '*.img' -size 0 -print -quit | grep -q . && {
      echo "empty image artifact found under ${image_dir}" >&2
      exit 1
    }
  fi

  return 0
}

product_list_contains() {
  local expected="$1"
  local product
  for product in "${PRODUCTS[@]}"; do
    if [ "${product}" = "${expected}" ]; then
      return 0
    fi
  done
  return 1
}

configure_qemu_device_profile() {
  local profile_args=()
  local all_profile_args=()
  local product
  local config_path
  for product in "${PRODUCTS[@]}"; do
    profile_args+=(--product "${product}")
  done
  # The QEMU products share product_virt.para. Clear stale profiles from every
  # architecture before selecting this build's device type, so a later phone
  # build cannot inherit PC-only parameters from an earlier 2in1 build.
  for product in arm64_virt x86_64_virt armv7a_virt; do
    case "${product}" in
      arm64_virt) config_path="vendor/ohemu/qemu_arm64_linux_full/config.json" ;;
      x86_64_virt) config_path="vendor/ohemu/qemu_x86_64_linux_full/config.json" ;;
      armv7a_virt) config_path="vendor/ohemu/qemu_armv7a_linux_full/config.json" ;;
    esac
    if [ -f "${OHOS_ROOT}/${config_path}" ]; then
      all_profile_args+=(--product "${product}")
    fi
  done

  for component_script in "${QEMU_2IN1_PROFILE_SCRIPT}" "${QEMU_PHONE_PROFILE_SCRIPT}"; do
    if [ ! -f "${component_script}" ]; then
      echo "missing QEMU device profile component: ${component_script}" >&2
      exit 1
    fi
  done

  case "${QEMU_2IN1_PROFILE_COMPONENT}" in auto|0|1) ;; *)
    echo "unsupported QEMU_2IN1_PROFILE_COMPONENT=${QEMU_2IN1_PROFILE_COMPONENT}; expected auto, 1, or 0" >&2
    exit 2
  esac
  case "${QEMU_PHONE_PROFILE_COMPONENT}" in auto|0|1) ;; *)
    echo "unsupported QEMU_PHONE_PROFILE_COMPONENT=${QEMU_PHONE_PROFILE_COMPONENT}; expected auto, 1, or 0" >&2
    exit 2
  esac
  if [ "${QEMU_2IN1_PROFILE_COMPONENT}" = "1" ] && [ "${DEVICE_TYPE}" != "2in1" ]; then
    echo "QEMU_2IN1_PROFILE_COMPONENT=1 requires DEVICE_TYPE=2in1" >&2
    exit 2
  fi
  if [ "${QEMU_PHONE_PROFILE_COMPONENT}" = "1" ] && [ "${DEVICE_TYPE}" != "phone" ]; then
    echo "QEMU_PHONE_PROFILE_COMPONENT=1 requires DEVICE_TYPE=phone" >&2
    exit 2
  fi

  # A product may inherit only one generated device profile. Disable both for
  # the selected products before enabling the requested source profile.
  bash "${QEMU_2IN1_PROFILE_SCRIPT}" --source-root "${OHOS_ROOT}" --disable \
    "${all_profile_args[@]}" \
    2>&1 | tee "${CACHE_ROOT}/logs/disable_qemu_2in1_profile_component.log"
  bash "${QEMU_PHONE_PROFILE_SCRIPT}" --source-root "${OHOS_ROOT}" --disable \
    "${all_profile_args[@]}" \
    2>&1 | tee "${CACHE_ROOT}/logs/disable_qemu_phone_profile_component.log"

  if [ "${DEVICE_TYPE}" = "2in1" ] && [ "${QEMU_2IN1_PROFILE_COMPONENT}" != "0" ]; then
    DEVICE_TYPE_BUILD_PROFILE=qemu_2in1_full_source
    bash "${QEMU_2IN1_PROFILE_SCRIPT}" --source-root "${OHOS_ROOT}" \
      "${profile_args[@]}" \
      2>&1 | tee "${CACHE_ROOT}/logs/apply_qemu_2in1_profile_component.log"
  elif [ "${DEVICE_TYPE}" = "phone" ] && [ "${QEMU_PHONE_PROFILE_COMPONENT}" != "0" ]; then
    DEVICE_TYPE_BUILD_PROFILE=qemu_phone_full_source
    bash "${QEMU_PHONE_PROFILE_SCRIPT}" --source-root "${OHOS_ROOT}" \
      "${profile_args[@]}" \
      2>&1 | tee "${CACHE_ROOT}/logs/apply_qemu_phone_profile_component.log"
  elif [ -n "${DEVICE_TYPE}" ]; then
    DEVICE_TYPE_BUILD_PROFILE=param_only
  else
    DEVICE_TYPE_BUILD_PROFILE=default
  fi
  export DEVICE_TYPE_BUILD_PROFILE
}

apply_qemu_serial_components() {
  # Never import or change Serial device permissions for a phone build.
  if [ "${DEVICE_TYPE}" != "2in1" ] || [ "${QEMU_2IN1_PROFILE_COMPONENT}" = "0" ]; then
    return
  fi
  if [ ! -d "${QEMU_SERIAL_SOURCE_REPO}" ]; then
    echo "missing fixed Serial SIG cache; set QEMU_SERIAL_SOURCE_REPO to a git cache containing c05fbbf156230982aa576373da6ee04378b09ca0" >&2
    exit 1
  fi
  bash "${SERIAL_METADATA_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_serial_metadata_component.log"
  bash "${SERIAL_MANAGER_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    --source-repo "${QEMU_SERIAL_SOURCE_REPO}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_serial_manager_component.log"
  bash "${SERIAL_DIALOG_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_serial_dialog_component.log"
  bash "${SERIAL_DEVICES_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_serial_devices_component.log"
  bash "${SERIAL_USB_ENDPOINT_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_serial_usb_endpoint_component.log"
}

apply_armv7a_product_component() {
  if ! product_list_contains armv7a_virt; then
    return
  fi
  if [ "${ARMV7A_PRODUCT_COMPONENT}" != "1" ]; then
    echo "armv7a_virt selected but ARMV7A_PRODUCT_COMPONENT=${ARMV7A_PRODUCT_COMPONENT}; skip component"
    return
  fi
  if [ ! -f "${ARMV7A_COMPONENT_SCRIPT}" ]; then
    echo "missing armv7a component: ${ARMV7A_COMPONENT_SCRIPT}" >&2
    exit 1
  fi
  bash "${ARMV7A_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_armv7a_product_component.log"
}

apply_standard_vpn_component() {
  if [ "${STANDARD_VPN_COMPONENT}" != "1" ]; then
    echo "STANDARD_VPN_COMPONENT=${STANDARD_VPN_COMPONENT}; skip standard VPN configuration"
    return
  fi
  if [ ! -f "${VPN_COMPONENT_SCRIPT}" ]; then
    echo "missing standard VPN component: ${VPN_COMPONENT_SCRIPT}" >&2
    exit 1
  fi

  local vpn_args=()
  local product
  for product in "${PRODUCTS[@]}"; do
    vpn_args+=(--product "${product}")
  done
  bash "${VPN_COMPONENT_SCRIPT}" \
    --source-root "${OHOS_ROOT}" \
    "${vpn_args[@]}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_standard_qemu_vpn_component.log"
}

apply_qemu_vulkan_component() {
  case "${QEMU_VULKAN_COMPONENT}" in auto|0|1) ;; *)
    echo "QEMU_VULKAN_COMPONENT must be auto, 0, or 1" >&2
    exit 2
  esac
  if [ "${QEMU_VULKAN_COMPONENT}" = "0" ]; then
    echo "QEMU_VULKAN_COMPONENT=0; skip QEMU SwiftShader Vulkan ICD"
    return
  fi

  local product arch
  local available=1
  local vulkan_args=()
  for product in "${PRODUCTS[@]}"; do
    case "${product}" in
      armv7a_virt) arch=arm ;;
      arm64_virt) arch=arm64 ;;
      x86_64_virt) arch=x86_64 ;;
      *) echo "unsupported QEMU Vulkan product: ${product}" >&2; exit 2 ;;
    esac
    vulkan_args+=(--product "${product}")
    if [ ! -s "${QEMU_VULKAN_ARTIFACTS}/${arch}/libvk_swiftshader.so" ]; then
      available=0
    fi
  done
  if [ "${available}" = "0" ]; then
    if [ "${QEMU_VULKAN_COMPONENT}" = "1" ]; then
      echo "QEMU_VULKAN_COMPONENT=1 but SwiftShader artifacts are incomplete: ${QEMU_VULKAN_ARTIFACTS}" >&2
      exit 1
    fi
    echo "SwiftShader artifacts are incomplete; skip optional QEMU Vulkan ICD"
    return
  fi
  bash "${QEMU_VULKAN_COMPONENT_SCRIPT}" \
    --source-root "${OHOS_ROOT}" \
    --artifact-root "${QEMU_VULKAN_ARTIFACTS}" \
    "${vulkan_args[@]}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_qemu_vulkan_component.log"
}

apply_qemu_absolute_pointer_component() {
  if [ "${QEMU_ABSOLUTE_POINTER_COMPONENT}" != "1" ]; then
    echo "QEMU_ABSOLUTE_POINTER_COMPONENT=${QEMU_ABSOLUTE_POINTER_COMPONENT}; skip absolute pointer configuration"
    return
  fi
  if [ ! -f "${QEMU_ABSOLUTE_POINTER_COMPONENT_SCRIPT}" ]; then
    echo "missing QEMU absolute-pointer component: ${QEMU_ABSOLUTE_POINTER_COMPONENT_SCRIPT}" >&2
    exit 1
  fi
  bash "${QEMU_ABSOLUTE_POINTER_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_qemu_absolute_pointer_component.log"
}

apply_qemu_runtime_components() {
  local toggle
  for toggle in \
    "${QEMU_QOS_COMPONENT}" \
    "${QEMU_VIBRATOR_COMPONENT}" \
    "${QEMU_ACCESSIBILITY_COMPONENT}"; do
    if [ "${toggle}" != "0" ] && [ "${toggle}" != "1" ]; then
      echo "QEMU QoS/vibrator/accessibility component toggles must be 0 or 1" >&2
      exit 2
    fi
  done
  case "${QEMU_JSVM_COMPONENT}" in auto|0|1) ;; *)
    echo "QEMU_JSVM_COMPONENT must be auto, 0, or 1" >&2
    exit 2
    ;;
  esac

  if [ "${QEMU_QOS_COMPONENT}" = "1" ]; then
    [ -f "${QEMU_QOS_COMPONENT_SCRIPT}" ] || {
      echo "missing QoS component: ${QEMU_QOS_COMPONENT_SCRIPT}" >&2
      exit 1
    }
    bash "${QEMU_QOS_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
      2>&1 | tee "${CACHE_ROOT}/logs/apply_qemu_qos_component.log"
  fi

  if [ "${QEMU_VIBRATOR_COMPONENT}" = "1" ]; then
    [ -f "${QEMU_VIBRATOR_COMPONENT_SCRIPT}" ] || {
      echo "missing virtual vibrator component: ${QEMU_VIBRATOR_COMPONENT_SCRIPT}" >&2
      exit 1
    }
    bash "${QEMU_VIBRATOR_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
      2>&1 | tee "${CACHE_ROOT}/logs/apply_qemu_vibrator_component.log"
  fi

  if [ "${QEMU_ACCESSIBILITY_COMPONENT}" = "1" ]; then
    [ -f "${QEMU_ACCESSIBILITY_COMPONENT_SCRIPT}" ] || {
      echo "missing accessibility component: ${QEMU_ACCESSIBILITY_COMPONENT_SCRIPT}" >&2
      exit 1
    }
    bash "${QEMU_ACCESSIBILITY_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
      2>&1 | tee "${CACHE_ROOT}/logs/apply_qemu_accessibility_component.log"
  fi

  local enable_jsvm=false
  if [ "${QEMU_JSVM_COMPONENT}" = "1" ]; then
    enable_jsvm=true
  elif [ "${QEMU_JSVM_COMPONENT}" = "auto" ] && \
       [ -f "${JSVM_ENGINE_ARTIFACTS}/manifest.json" ]; then
    enable_jsvm=true
  fi
  if [ "${QEMU_JSVM_COMPONENT}" = "1" ] && \
     [ ! -f "${JSVM_ENGINE_ARTIFACTS}/manifest.json" ]; then
    echo "JSVM is required but M144 artifacts are missing: ${JSVM_ENGINE_ARTIFACTS}" >&2
    echo "run scripts/build_m144_v8.sh before the OpenHarmony image build" >&2
    exit 1
  fi

  local metadata=
  case "${DEVICE_TYPE}" in
    phone) metadata=vendor/ohemu/virt/virt_phone_full.meta.json ;;
    2in1) metadata=vendor/ohemu/virt/virt_2in1_full.meta.json ;;
  esac

  local product profile arch
  for product in "${PRODUCTS[@]}"; do
    case "${product}" in
      armv7a_virt)
        profile=vendor/ohemu/qemu_armv7a_linux_full/config.json
        arch=arm
        ;;
      arm64_virt)
        profile=vendor/ohemu/qemu_arm64_linux_full/config.json
        arch=arm64
        ;;
      x86_64_virt)
        profile=vendor/ohemu/qemu_x86_64_linux_full/config.json
        arch=x86_64
        ;;
    esac
    local args=(--source-root "${OHOS_ROOT}" --profile "${profile}")
    if [ -n "${metadata}" ]; then
      args+=(--metadata "${metadata}")
    fi
    if [ "${enable_jsvm}" = true ]; then
      args+=(--artifact-root "${JSVM_ENGINE_ARTIFACTS}" --arch "${arch}")
    else
      args+=(--disable)
    fi
    bash "${QEMU_JSVM_COMPONENT_SCRIPT}" "${args[@]}" \
      2>&1 | tee "${CACHE_ROOT}/logs/apply_qemu_jsvm_${product}.log"
  done
  QEMU_JSVM_ENABLED="${enable_jsvm}"
  export QEMU_JSVM_ENABLED
}

apply_release_hap_dependencies_component() {
  if [ ! -f "${RELEASE_HAP_DEPENDENCIES_SCRIPT}" ]; then
    echo "missing release HAP dependency component: ${RELEASE_HAP_DEPENDENCIES_SCRIPT}" >&2
    exit 1
  fi
  bash "${RELEASE_HAP_DEPENDENCIES_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_release_hap_dependencies.log"
}

apply_sdk_cortex_m_component() {
  if [ ! -f "${SDK_CORTEX_M_COMPONENT_SCRIPT}" ]; then
    echo "missing Cortex-M SDK component: ${SDK_CORTEX_M_COMPONENT_SCRIPT}" >&2
    exit 1
  fi
  bash "${SDK_CORTEX_M_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_sdk_cortex_m_component.log"
}

apply_qemu_audio_component() {
  if [ ! -f "${QEMU_AUDIO_COMPONENT_SCRIPT}" ]; then
    echo "missing QEMU audio component: ${QEMU_AUDIO_COMPONENT_SCRIPT}" >&2
    exit 1
  fi
  bash "${QEMU_AUDIO_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_qemu_audio_component.log"
}

fix_case_insensitive_selinux_version_header() {
  if [ "${QEMU_FIX_CASE_INSENSITIVE_SELINUX_VERSION}" != "1" ]; then
    return
  fi

  python3 - "${OHOS_ROOT}" <<'PY'
import sys
from pathlib import Path

source_root = Path(sys.argv[1])
selinux_root = source_root / "third_party/selinux/libselinux"
version_file = selinux_root / "VERSION"
lowercase_alias = selinux_root / "version"
compat_version_file = selinux_root / "LIBSELINUX_VERSION"
build_file = source_root / "third_party/selinux/BUILD.gn"
make_file = selinux_root / "src/Makefile"

entry_names = {entry.name for entry in selinux_root.iterdir()}
has_version_file = "VERSION" in entry_names
has_compat_version_file = "LIBSELINUX_VERSION" in entry_names
case_insensitive_alias = has_version_file and lowercase_alias.exists()
already_configured = has_compat_version_file
if not case_insensitive_alias and not already_configured:
    print("libselinux VERSION does not alias lowercase <version>; no compatibility fix needed")
    raise SystemExit(0)

quote_only_config = '''config("third_party_selinux_config") {
  include_dirs = [ "$LIBSELINUX_ROOT_DIR/include" ]
  cflags = [
    "-iquote" + rebase_path("$LIBSELINUX_ROOT_DIR", root_build_dir),
  ]
}
'''
original_config = '''config("third_party_selinux_config") {
  include_dirs = [
    "$LIBSELINUX_ROOT_DIR/include",
    "$LIBSELINUX_ROOT_DIR",
  ]
}
'''
text = build_file.read_text()
if original_config in text:
    build_file.write_text(text.replace(original_config, quote_only_config, 1))
elif quote_only_config not in text:
    raise SystemExit(f"unexpected third_party_selinux_config layout in {build_file}")

if has_compat_version_file:
    if has_version_file and version_file.read_bytes() != compat_version_file.read_bytes():
        raise SystemExit(f"conflicting libselinux version files: {version_file} and {compat_version_file}")
    if not has_version_file:
        compat_version_file.rename(version_file)
    else:
        compat_version_file.unlink()

make_text = make_file.read_text()
updated_make_text = make_text.replace("../LIBSELINUX_VERSION", "../VERSION")
if updated_make_text != make_text:
    make_file.write_text(updated_make_text)
elif "../VERSION" not in make_text:
    raise SystemExit(f"unexpected libselinux VERSION reference layout in {make_file}")

if "VERSION" in {entry.name for entry in selinux_root.iterdir()}:
    print(
        "configured case-insensitive libselinux compatibility: "
        f"quote-only private headers in {build_file}; preserved {version_file}"
    )
else:
    raise SystemExit(f"missing libselinux version file: {version_file}")
PY
}

fix_case_insensitive_xmp_endian_header() {
  if [ "${QEMU_FIX_CASE_INSENSITIVE_XMP_ENDIAN}" != "1" ]; then
    return
  fi

  python3 - "${OHOS_ROOT}" <<'PY'
import sys
from pathlib import Path

source_root = Path(sys.argv[1])
xmp_root = source_root / "third_party/xmp_toolkit_sdk"
source_dir = xmp_root / "source"
endian_header = source_dir / "Endian.h"
lowercase_alias = source_dir / "endian.h"
build_file = xmp_root / "BUILD.gn"
warning_flag = '"-Wno-nonportable-include-path"'

entry_names = {entry.name for entry in source_dir.iterdir()}
case_insensitive_alias = "Endian.h" in entry_names and lowercase_alias.exists()
text = build_file.read_text()
public_original = ''']

config("xmpsdk_public_config") {
  include_dirs = _xmpsdk_include_dirs
'''
public_intermediate = ''']

config("xmpsdk_public_config") {
  include_dirs = _xmpsdk_include_dirs
  include_dirs -= [ "source" ]
'''
public_duplicate = ''']

config("xmpsdk_public_config") {
  include_dirs = _xmpsdk_include_dirs
  include_dirs -= [ "source" ]
  include_dirs -= [ "source" ]
'''
public_replacement = ''']

_xmpsdk_public_include_dirs = _xmpsdk_include_dirs
_xmpsdk_public_include_dirs -= [ "source" ]

config("xmpsdk_public_config") {
  include_dirs = _xmpsdk_public_include_dirs
'''
already_configured = warning_flag in text and public_replacement in text
if not case_insensitive_alias and not already_configured:
    print("XMP Endian.h does not alias endian.h; no compatibility fix needed")
    raise SystemExit(0)

if public_duplicate in text:
    text = text.replace(public_duplicate, public_replacement, 1)
elif public_intermediate in text:
    text = text.replace(public_intermediate, public_replacement, 1)
elif public_original in text:
    text = text.replace(public_original, public_replacement, 1)
elif public_replacement not in text:
    raise SystemExit(f"unexpected xmpsdk_public_config layout in {build_file}")

original = '''    "-Wno-tautological-overlap-compare",
    "-Wno-int-to-void-pointer-cast",
  ]
}
'''
replacement = '''    "-Wno-tautological-overlap-compare",
    "-Wno-int-to-void-pointer-cast",
    "-Wno-nonportable-include-path",
  ]
}
'''
if original in text:
    text = text.replace(original, replacement, 1)
elif replacement not in text:
    raise SystemExit(f"unexpected xmpsdk_config cflags_cc layout in {build_file}")
build_file.write_text(text)

if not endian_header.exists():
    raise SystemExit(f"missing XMP endian header: {endian_header}")
print(
    "configured case-insensitive XMP compatibility: "
    f"removed source/ from public include lookup and suppressed "
    f"private path-case diagnostics in {build_file}"
)
PY
}

fix_case_insensitive_iptables_variants() {
  if [ "${QEMU_FIX_CASE_INSENSITIVE_IPTABLES_CONNMARK}" != "1" ]; then
    return
  fi

  python3 "${SCRIPT_DIR}/fix_case_insensitive_iptables.py" \
    --source-root "${OHOS_ROOT}"
}

fix_case_insensitive_kernel_netfilter() {
  if [ "${QEMU_FIX_CASE_INSENSITIVE_IPTABLES_CONNMARK}" != "1" ]; then
    return
  fi

  python3 "${SCRIPT_DIR}/fix_case_insensitive_kernel_netfilter.py" \
    --source-root "${OHOS_ROOT}"
}

fix_mindspore_non_arm_hwcap_header() {
  if [ "${QEMU_FIX_MINDSPORE_NON_ARM_HWCAP}" != "1" ]; then
    return
  fi

  python3 - "${OHOS_ROOT}" <<'PY'
import sys
from pathlib import Path

source_root = Path(sys.argv[1])
source = source_root / (
    "third_party/mindspore/mindspore-src/source/mindspore-lite/"
    "src/common/utils.cc"
)
text = source.read_text()
original = """#if defined(__ANDROID__) || defined(MS_COMPILE_OHOS)
#include <sys/auxv.h>
#include <asm/hwcap.h>
#endif
"""
replacement = """#if defined(__ANDROID__) || defined(MS_COMPILE_OHOS)
#include <sys/auxv.h>
#ifdef ENABLE_ARM64
#include <asm/hwcap.h>
#endif
#endif
"""
if original in text:
    source.write_text(text.replace(original, replacement, 1))
elif replacement not in text:
    raise SystemExit(f"unexpected MindSpore hwcap include layout in {source}")
print(f"configured non-ARM MindSpore hwcap compatibility in {source}")
PY
}

fix_virtiofs_node_symlink_copy() {
  if [ "${QEMU_FIX_VIRTIOFS_NODE_SYMLINK_COPY}" != "1" ]; then
    return
  fi

  python3 - "${OHOS_ROOT}" <<'PY'
import sys
import re
from pathlib import Path

source_root = Path(sys.argv[1])
scripts = [
    source_root / "arkcompiler/ets_frontend/arkguard/compile_arkguard.py",
    source_root / "arkcompiler/ets_frontend/ets2panda/driver/build_system/build_build_system.py",
]
pattern = re.compile(
    r"shutil\.copytree\(source_path,\s*dest_path,\s*"
    r"dirs_exist_ok=True,\s*symlinks=True\)"
)
replacement = (
    "shutil.copytree(source_path, dest_path, "
    "dirs_exist_ok=True, symlinks=False)"
)
for script in scripts:
    text = script.read_text()
    original_text = text
    restore_marker = "Restore symlinks without copying unsupported VirtioFS metadata."
    updated, count = pattern.subn(replacement, text, count=1)
    if count:
        text = updated
    elif replacement not in text and not (
            script.name == "build_build_system.py" and restore_marker in text):
        raise SystemExit(f"unexpected copytree layout in {script}")
    if script.name == "build_build_system.py":
        restore_block = '''shutil.copytree(source_path, dest_path, dirs_exist_ok=True, symlinks=False)
            # Restore symlinks without copying unsupported VirtioFS metadata.
            for source_dir, dirnames, filenames in os.walk(
                    source_path, topdown=False):
                for name in dirnames + filenames:
                    source_entry = os.path.join(source_dir, name)
                    if not os.path.islink(source_entry):
                        continue
                    relative_entry = os.path.relpath(source_entry, source_path)
                    dest_entry = os.path.join(dest_path, relative_entry)
                    if os.path.lexists(dest_entry):
                        if os.path.isdir(dest_entry) and not os.path.islink(
                                dest_entry):
                            shutil.rmtree(dest_entry)
                        else:
                            os.unlink(dest_entry)
                    os.symlink(os.readlink(source_entry), dest_entry)'''
        if restore_marker not in text:
            if replacement not in text:
                raise SystemExit(f"missing copytree call in {script}")
            text = text.replace(replacement, restore_block, 1)
    if text != original_text:
        script.write_text(text)
    print(f"configured shared-filesystem Node launcher copy in {script}")
PY
}

serialize_shared_arkoala_generator() {
  if [ "${QEMU_SERIALIZE_SHARED_ARKOALA_GENERATOR}" != "1" ]; then
    return
  fi

  python3 - "${OHOS_ROOT}" <<'PY'
import sys
from pathlib import Path

source_root = Path(sys.argv[1])
script = source_root / (
    "foundation/arkui/ace_engine/frameworks/bridge/arkts_frontend/"
    "arkoala_generator/gn/command/generation.py"
)
text = script.read_text()
original_text = text
if "import fcntl\n" not in text:
    import_marker = "import argparse\n"
    if import_marker not in text:
        raise SystemExit(f"unexpected import layout in {script}")
    text = text.replace(import_marker, import_marker + "import fcntl\n", 1)

lock_marker = "Waiting for shared Arkoala generator lock:"
if lock_marker not in text:
    original = '''    script_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = os.path.join(script_dir, "../../")
'''
    replacement = '''    script_dir = os.path.dirname(os.path.abspath(__file__))
    base_dir = os.path.join(script_dir, "../../")

    lock_path = os.environ.get(
        "OHOS_ARKOALA_GENERATOR_LOCK",
        "/tmp/openharmony-arkoala-generator.lock",
    )
    print(f"Waiting for shared Arkoala generator lock: {lock_path}")
    generator_lock = open(lock_path, "w", encoding="utf-8")
    fcntl.flock(generator_lock, fcntl.LOCK_EX)
    print(f"Acquired shared Arkoala generator lock: {lock_path}")
'''
    if original not in text:
        raise SystemExit(f"unexpected main layout in {script}")
    text = text.replace(original, replacement, 1)

if text != original_text:
    script.write_text(text)
print(f"serialized shared-source Arkoala generation in {script}")
PY
}

fix_virtiofs_kernel_source_copy() {
  if [ "${QEMU_FIX_VIRTIOFS_KERNEL_COPY}" != "1" ]; then
    return
  fi

  python3 - "${OHOS_ROOT}" <<'PY'
import sys
from pathlib import Path

source_root = Path(sys.argv[1])
script = source_root / "device/qemu/common/virt_full/kernel/build_kernel.sh"
text = script.read_text()
original_text = text
# Prefer rsync over tar/cp -rL: VirtioFS + tar can hit EMFILE ("Too many open
# files") when packing the full kernel tree. rsync streams file-by-file.
rsync_replacement = '''    rm -rf "${KERNEL_BUILD_ROOT}"
    mkdir -p "${KERNEL_BUILD_ROOT}"
    if command -v rsync >/dev/null 2>&1; then
        rsync -a --delete --copy-links --exclude='.git' \\
            "${KERNEL_SOURCE_DIR}/" "${KERNEL_BUILD_ROOT}/"
    else
        tar --exclude='./.git' --exclude='.git' \\
            -C "${KERNEL_SOURCE_DIR}" -chf - . \\
            | tar -C "${KERNEL_BUILD_ROOT}" -xf -
    fi
'''
legacy_cp = '''    rm -rf ${KERNEL_BUILD_ROOT}
    mkdir -p ${OHOS_SOURCE_ROOT}/out/kernel/OBJ
    cp -rL ${KERNEL_SOURCE_DIR}  ${KERNEL_BUILD_ROOT}
'''
legacy_tar = '''    rm -rf "${KERNEL_BUILD_ROOT}"
    mkdir -p "${KERNEL_BUILD_ROOT}"
    tar --exclude='./.git' --exclude='.git' \\
        -C "${KERNEL_SOURCE_DIR}" -chf - . \\
        | tar -C "${KERNEL_BUILD_ROOT}" -xf -
'''
if rsync_replacement in text:
    pass
elif legacy_tar in text:
    text = text.replace(legacy_tar, rsync_replacement, 1)
elif legacy_cp in text:
    text = text.replace(legacy_cp, rsync_replacement, 1)
else:
    raise SystemExit(f"unexpected kernel copy layout in {script}")
old_jobs = "    make ${MAKE_OPTIONS} -j$(nproc)\n"
new_jobs = '    make ${MAKE_OPTIONS} -j"${OHOS_KERNEL_BUILD_JOBS:-$(nproc)}"\n'
if old_jobs in text:
    text = text.replace(old_jobs, new_jobs, 1)
elif new_jobs not in text:
    raise SystemExit(f"unexpected kernel jobs layout in {script}")
reuse_marker = "reuse complete external kernel outputs:"
if reuse_marker not in text:
    main_marker = """##main
# Always refresh the kernel copy."""
    reuse_block = """##main
if [ "${OHOS_SKIP_KERNEL_REBUILD_IF_COMPLETE:-0}" = "1" ]; then
    FINAL_KERNEL_IMAGE="${OHOS_IMAGES_DIR}/$(basename "${KERNEL_OUT_IMAGE}")"
    COMPLETE_KERNEL_OUTPUTS=1
    for OUTPUT in \\
        "${FINAL_KERNEL_IMAGE}" \\
        "${KERNEL_MODULES_OUT}/rtw89_core.ko" \\
        "${KERNEL_MODULES_OUT}/rtw89_pci.ko" \\
        "${KERNEL_MODULES_OUT}/rtw89_8852a.ko" \\
        "${KERNEL_MODULES_OUT}/rtw89_8852ae.ko" \\
        "${KERNEL_MODULES_OUT}/mt7601u.ko" \\
        "${KERNEL_MODULES_OUT}/mac80211_hwsim.ko" \\
        "${KERNEL_MODULES_OUT}/virt_wifi.ko" \\
        "${KERNEL_MODULES_OUT}/libarc4.ko" \\
        "${KERNEL_MODULES_OUT}/mac80211.ko" \\
        "${KERNEL_MODULES_OUT}/cfg80211.ko" \\
        "${KERNEL_MODULES_OUT}/iwlwifi.ko" \\
        "${KERNEL_MODULES_OUT}/iwlmvm.ko"; do
        if [ ! -s "${OUTPUT}" ]; then
            COMPLETE_KERNEL_OUTPUTS=0
            break
        fi
    done
    if [ "${COMPLETE_KERNEL_OUTPUTS}" = "1" ]; then
        echo "reuse complete external kernel outputs: ${FINAL_KERNEL_IMAGE}"
        popd
        exit 0
    fi
fi

# Always refresh the kernel copy."""
    if main_marker not in text:
        raise SystemExit(f"unexpected kernel main layout in {script}")
    text = text.replace(main_marker, reuse_block, 1)
if text != original_text:
    script.write_text(text)
print(f"configured shared-filesystem kernel worktree copy in {script}")
PY
}

configure_qemu_product_features() {
  if [ "${QEMU_FIX_SYSTEM_COMPAT_SYMLINKS}" != "1" ]; then
    return
  fi

  cd "${OHOS_ROOT}"
  QEMU_FIX_SYSTEM_COMPAT_SYMLINKS="${QEMU_FIX_SYSTEM_COMPAT_SYMLINKS}" \
    python3 - <<'PY'
import os
from pathlib import Path

fix_system_compat_symlinks = os.environ.get("QEMU_FIX_SYSTEM_COMPAT_SYMLINKS") == "1"

if fix_system_compat_symlinks:
    path = Path("build/ohos/images/build_image.py")
    if path.exists():
        text = path.read_text()
        original = text
        text = text.replace("os.symlink('/usr', _system_path)", "os.symlink('/usr/system', _system_path)")
        text = text.replace("os.makedirs(_system_path, exist_ok=True)", "os.symlink('/usr/system', _system_path)")
        if "def _prepare_system_seccomp_compat(" not in text:
            marker = '''def _prepare_updater(updater_path: str, target_cpu: str):
'''
            helper = '''def _prepare_system_seccomp_compat(system_path: str, target_cpu: str):
    if target_cpu not in ('arm64', 'x86_64', 'riscv64'):
        return
    _lib64_seccomp = os.path.join(system_path, 'lib64', 'seccomp')
    _lib_seccomp = os.path.join(system_path, 'lib', 'seccomp')
    if not os.path.isdir(_lib64_seccomp) or os.path.lexists(_lib_seccomp):
        return
    os.makedirs(os.path.dirname(_lib_seccomp), exist_ok=True)
    os.symlink('../lib64/seccomp', _lib_seccomp)


'''
            text = text.replace(marker, helper + marker, 1)
        text = text.replace(
            "    if args.image_name == 'system':\n        _prepare_root(args.input_path, args.target_cpu)\n",
            "    if args.image_name == 'system':\n        _prepare_root(args.input_path, args.target_cpu)\n        _prepare_system_seccomp_compat(args.input_path, args.target_cpu)\n",
            1,
        )
        old = '''def _prepare_ramdisk(ramdisk_path: str):
    _dir_list = ['bin', 'dev', 'etc', 'lib', 'proc', 'sys', 'system', 'usr', 'mnt', 'storage']
    for _dir_name in _dir_list:
        _path = os.path.join(ramdisk_path, _dir_name)
        if os.path.exists(_path):
            continue
        os.makedirs(_path, exist_ok=True)
    if not os.path.exists(os.path.join(ramdisk_path, 'init')):
        os.symlink('bin/init_early', os.path.join(ramdisk_path, 'init'))
'''
        new = '''def _prepare_ramdisk(ramdisk_path: str):
    _dir_list = ['bin', 'dev', 'etc', 'lib', 'proc', 'sys', 'system', 'usr', 'mnt', 'storage']
    for _dir_name in _dir_list:
        _path = os.path.join(ramdisk_path, _dir_name)
        if os.path.exists(_path):
            continue
        os.makedirs(_path, exist_ok=True)
    _system_path = os.path.join(ramdisk_path, 'system')
    if os.path.lexists(_system_path):
        if not os.path.islink(_system_path) or os.readlink(_system_path) != '/usr/system':
            if os.path.isdir(_system_path) and not os.path.islink(_system_path):
                os.rmdir(_system_path)
            else:
                os.unlink(_system_path)
    if not os.path.lexists(_system_path):
        os.symlink('/usr/system', _system_path)
    _chipset_path = os.path.join(ramdisk_path, 'chipset')
    if not os.path.exists(_chipset_path):
        os.symlink('/vendor', _chipset_path)
    _bin_init_path = os.path.join(ramdisk_path, 'bin', 'init')
    if os.path.lexists(_bin_init_path):
        if not os.path.islink(_bin_init_path) or os.readlink(_bin_init_path) != '/system/bin/init':
            if os.path.isdir(_bin_init_path) and not os.path.islink(_bin_init_path):
                os.rmdir(_bin_init_path)
            else:
                os.unlink(_bin_init_path)
    if not os.path.lexists(_bin_init_path):
        os.symlink('/system/bin/init', _bin_init_path)
    if not os.path.exists(os.path.join(ramdisk_path, 'init')):
        os.symlink('bin/init_early', os.path.join(ramdisk_path, 'init'))
'''
        if old in text:
            text = text.replace(old, new, 1)
        elif "_bin_init_path = os.path.join(ramdisk_path, 'bin', 'init')" not in text:
            marker = """    _chipset_path = os.path.join(ramdisk_path, 'chipset')
    if not os.path.exists(_chipset_path):
        os.symlink('/vendor', _chipset_path)
"""
            insert = marker + """    _bin_init_path = os.path.join(ramdisk_path, 'bin', 'init')
    if os.path.lexists(_bin_init_path):
        if not os.path.islink(_bin_init_path) or os.readlink(_bin_init_path) != '/system/bin/init':
            if os.path.isdir(_bin_init_path) and not os.path.islink(_bin_init_path):
                os.rmdir(_bin_init_path)
            else:
                os.unlink(_bin_init_path)
    if not os.path.lexists(_bin_init_path):
        os.symlink('/system/bin/init', _bin_init_path)
"""
            text = text.replace(marker, insert, 1)
        if text != original:
            path.write_text(text)
            print(f"configured {path}: map QEMU /system to /usr/system and add QEMU init/chipset symlinks")

PY
}

ensure_flexlexer_header() {
  local src="/usr/include/FlexLexer.h"
  local dst="${OHOS_ROOT}/base/update/updater/services/script/script_interpreter/FlexLexer.h"

  if [ -f "${dst}" ]; then
    return
  fi
  if [ ! -f "${src}" ]; then
    echo "missing ${src}; install libfl-dev in the Docker image" >&2
    exit 1
  fi
  if [ ! -d "$(dirname "${dst}")" ]; then
    echo "missing updater script include dir: $(dirname "${dst}")" >&2
    exit 1
  fi
  if [ ! -f "${dst}" ] || ! cmp -s "${src}" "${dst}"; then
    cp "${src}" "${dst}"
    echo "configured ${dst}: copied Docker FlexLexer.h for updater yacc build"
  fi
}

clean_corrupt_hvigor_state() {
  cd "${OHOS_ROOT}"
  python3 - <<'PY'
from pathlib import Path
import shutil

removed = []
excluded_roots = {".repo", "out", "prebuilts"}
for source_root in Path(".").iterdir():
    if not source_root.is_dir() or source_root.name in excluded_roots:
        continue
    for dep_map in source_root.rglob(".hvigor/dependencyMap/oh-package.json5"):
        try:
            if dep_map.stat().st_size != 0:
                continue
        except FileNotFoundError:
            continue
        hvigor_dir = dep_map.parents[1]
        shutil.rmtree(hvigor_dir, ignore_errors=True)
        removed.append(str(hvigor_dir))

for path in removed:
    print(f"removed corrupt hvigor state: {path}")
PY
}

ensure_hvigor_sdkmanager_common() {
  local version="${SDKMANAGER_COMMON_VERSION}"
  local registry="https://repo.harmonyos.com/npm/"
  local node_bin="${OHOS_ROOT}/prebuilts/build-tools/common/nodejs/current/bin"
  local npm="${node_bin}/npm"
  local target="${OHOS_ROOT}/prebuilts/tool/command-line-tools/6.x/hvigor/hvigor-ohos-plugin/node_modules/@ohos/sdkmanager-common"
  if [ ! -x "${npm}" ] || [ ! -d "$(dirname "${target}")" ]; then
    return
  fi

  local installed=""
  if [ -f "${target}/package.json" ]; then
    installed="$(python3 - "${target}/package.json" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    print(json.load(stream).get("version", ""))
PY
)"
  fi
  if [ "${installed}" = "${version}" ]; then
    return
  fi

  local workdir archive actual
  workdir="$(mktemp -d "${CACHE_ROOT}/sdkmanager-common.XXXXXX")"
  if [ -f "${SDKMANAGER_COMMON_ARTIFACT}" ]; then
    actual="$(sha512sum "${SDKMANAGER_COMMON_ARTIFACT}" | awk '{print $1}')"
    if [ "${actual}" != "${SDKMANAGER_COMMON_SHA512}" ]; then
      echo "sdkmanager-common checksum mismatch: expected ${SDKMANAGER_COMMON_SHA512}, found ${actual}" >&2
      exit 1
    fi
    tar -xzf "${SDKMANAGER_COMMON_ARTIFACT}" -C "${workdir}"
    rm -rf "${target}"
    mv "${workdir}/package" "${target}"
    rm -rf "${workdir}"
    echo "updated Hvigor sdkmanager-common from pinned artifact: ${installed:-missing} -> ${version}"
    return
  fi
  archive="$({
    cd "${workdir}"
    PATH="${node_bin}:${PATH}" "${npm}" pack \
      "@ohos/sdkmanager-common@${version}" \
      --registry "${registry}" \
      --cache "${CACHE_ROOT}/npm-cache" \
      --silent
  } | tail -n 1)"
  tar -xzf "${workdir}/${archive}" -C "${workdir}"
  rm -rf "${target}"
  mv "${workdir}/package" "${target}"
  rm -rf "${workdir}"
  echo "updated Hvigor sdkmanager-common: ${installed:-missing} -> ${version}"
}

ensure_ohos_sdk_ets_loader_modules() {
  local sdk_root="${OHOS_ROOT}/prebuilts/ohos-sdk/linux"
  local node_bin="${OHOS_ROOT}/prebuilts/build-tools/common/nodejs/current/bin"
  local npm="${node_bin}/npm"
  if [ ! -x "${npm}" ] || [ ! -d "${sdk_root}" ]; then
    return
  fi

  local bundled_modules_source=""
  local candidate
  for candidate in \
    "${sdk_root}/23/ets/build-tools/ets-loader/node_modules" \
    "${OHOS_ROOT}/developtools/ace_ets2bundle/compiler/node_modules"; do
    if [ -f "${candidate}/typescript/package.json" ] && \
      [ -f "${candidate}/arkguard/package.json" ]; then
      bundled_modules_source="${candidate}"
      break
    fi
  done

  local loader
  while IFS= read -r loader; do
    if [ ! -f "${loader}/node_modules/json5/package.json" ]; then
      echo "install SDK ets-loader modules: ${loader}"
      (
        cd "${loader}"
        PATH="${node_bin}:${PATH}" "${npm}" ci \
          --registry "${NPM_REGISTRY}" \
          --cache "${CACHE_ROOT}/npm-cache" \
          --ignore-scripts \
          --unsafe-perm
      )
    fi

    local module
    for module in typescript arkguard declgen hypium @ohos/hypium; do
      if [ -f "${loader}/node_modules/${module}/package.json" ]; then
        continue
      fi
      if [ -z "${bundled_modules_source}" ] || \
        [ ! -f "${bundled_modules_source}/${module}/package.json" ]; then
        echo "missing OpenHarmony ${module} prebuilt for SDK ets-loader" >&2
        return 1
      fi

      local module_parent="${loader}/node_modules/${module%/*}"
      local module_name="${module##*/}"
      local module_tmp="${module_parent}/.${module_name}.tmp.$$"
      if [ "${module_parent}" = "${loader}/node_modules/${module}" ]; then
        module_parent="${loader}/node_modules"
        module_tmp="${module_parent}/.${module_name}.tmp.$$"
      fi
      echo "install SDK ets-loader ${module} from: ${bundled_modules_source}"
      mkdir -p "${module_parent}"
      rm -rf "${module_tmp}"
      cp -a "${bundled_modules_source}/${module}" "${module_tmp}"
      rm -rf "${loader}/node_modules/${module}"
      mv "${module_tmp}" "${loader}/node_modules/${module}"
    done

    test -f "${loader}/node_modules/json5/package.json"
    test -f "${loader}/node_modules/typescript/package.json"
    test -f "${loader}/node_modules/arkguard/package.json"
  done < <(
    find "${sdk_root}" -mindepth 5 -maxdepth 5 -type f \
      -path '*/ets/build-tools/ets-loader/package-lock.json' \
      -print \
      | sed 's#/package-lock.json$##' \
      | sort
  )
}

write_source_preparation_metadata() {
  local product relative
  for product in "${PRODUCTS[@]}"; do
    case "${product}" in
      arm64_virt) relative=vendor/ohemu/qemu_arm64_linux_full/config.json ;;
      x86_64_virt) relative=vendor/ohemu/qemu_x86_64_linux_full/config.json ;;
      armv7a_virt) relative=vendor/ohemu/qemu_armv7a_linux_full/config.json ;;
    esac
    if [ ! -f "${OHOS_ROOT}/${relative}" ]; then
      echo "prepared source is missing selected product config: ${relative}" >&2
      exit 1
    fi
  done

  (
    cd "${OHOS_ROOT}"
    repo manifest -r -o .ohos-qemu-resolved-manifest.xml
  )
  python3 "${SCRIPT_DIR}/openharmony_release_source_lock.py" --source-root "${OHOS_ROOT}" \
    --resolved-manifest "${OHOS_ROOT}/.ohos-qemu-resolved-manifest.xml"
  python3 - "${OHOS_ROOT}" "${MANIFEST_URL}" "${OHOS_BRANCH}" \
    "${MANIFEST_REVISION}" "${OHOS_PROJECT_MIRROR}" \
    "${OHOS_GITHUB_FALLBACK_MAP}" "${GITHUB_LFS_ASSET_MAP}" \
    "${OHOS_GITHUB_FALLBACK}" \
    "${DEVICE_TYPE:-default}" "${SCRIPT_DIR}/openharmony_7_0_release_source_lock.json" "${PRODUCTS[@]}" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
resolved = root / ".ohos-qemu-resolved-manifest.xml"
document = {
    "schema_version": 1,
    "manifest_url": sys.argv[2],
    "manifest_branch": sys.argv[3],
    "manifest_revision": sys.argv[4],
    "project_mirror": sys.argv[5],
    "github_fallback_enabled": sys.argv[8] == "1",
    "resolved_manifest": resolved.name,
    "resolved_manifest_sha256": hashlib.sha256(resolved.read_bytes()).hexdigest(),
    "prepared_device_type": sys.argv[9],
    "products": sorted(sys.argv[11:]),
    "qemu_mesa_revision": "995d2506d18924b48db0cf40e6ad7de04fc4e558",
    "qemu_mesa_version": "21.3.3",
    "project_source_lock_sha256": hashlib.sha256(Path(sys.argv[10]).read_bytes()).hexdigest(),
}
fallback_map = Path(sys.argv[6])
asset_map = Path(sys.argv[7])
if document["github_fallback_enabled"]:
    document["github_fallback_map_sha256"] = hashlib.sha256(
        fallback_map.read_bytes()
    ).hexdigest()
document["github_lfs_assets_sha256"] = hashlib.sha256(
    asset_map.read_bytes()
).hexdigest()
(root / ".ohos-qemu-source-baseline.json").write_text(
    json.dumps(document, indent=2, ensure_ascii=False) + "\n",
    encoding="utf-8",
)
PY
  echo "QEMU source preparation verified for: ${PRODUCTS[*]}"
}

prepare_source_and_sdk() {
  echo "cache root: ${CACHE_ROOT}"
  echo "home: ${CONTAINER_HOME}"
  echo "OpenHarmony root: ${OHOS_ROOT}"
  echo "package root: ${PACKAGE_ROOT}"
  echo "manifest: ${MANIFEST_URL} ${OHOS_BRANCH} @ ${MANIFEST_REVISION} groups=${MANIFEST_GROUPS}"
  echo "OpenHarmony project mirror: ${OHOS_PROJECT_MIRROR:-disabled}"
  echo "GitHub fallback map: enabled=${OHOS_GITHUB_FALLBACK} map=${OHOS_GITHUB_FALLBACK_MAP}"
  echo "OpenHarmony release fallback cache: ${OHOS_FALLBACK_MIRROR_ROOT}"
  echo "repo tool: ${REPO_URL}"
  echo "repo jobs: network=${REPO_JOBS} checkout=${REPO_CHECKOUT_JOBS}"
  echo "npm registry: ${NPM_REGISTRY}"
  echo "skip repo sync: ${SKIP_REPO_SYNC}"
  echo "allow non-Docker Ubuntu VM: ${ALLOW_NON_DOCKER}"
  echo "ccache max size: ${CCACHE_MAXSIZE}"
  echo "ccache dir: ${CCACHE_DIR}"
  echo "kernel build jobs: ${KERNEL_BUILD_JOBS}"
  echo "host GN explicit software CPU: ${QEMU_HOST_GN_QEMU_USER}"
  echo "skip prebuilts: ${SKIP_PREBUILTS}"
  echo "no prebuilt sdk: ${NO_PREBUILT_SDK}"
  echo "build only load: ${BUILD_ONLY_LOAD}"
  echo "prepare only: ${PREPARE_ONLY}"
  echo "skip git lfs: ${SKIP_GIT_LFS}"
  echo "git lfs paths: ${GIT_LFS_PATHS}"
  echo "GitHub/LFS compatibility cache: ${OHOS_LFS_ASSET_ROOT}"
  echo "qemu fix access_tokenid abi: ${QEMU_FIX_ACCESS_TOKENID_ABI}"
  echo "qemu fix system compat symlinks: ${QEMU_FIX_SYSTEM_COMPAT_SYMLINKS}"
  echo "qemu fix case-insensitive selinux VERSION: ${QEMU_FIX_CASE_INSENSITIVE_SELINUX_VERSION}"
  echo "qemu fix case-insensitive XMP Endian.h: ${QEMU_FIX_CASE_INSENSITIVE_XMP_ENDIAN}"
  echo "qemu fix case-insensitive iptables variants: ${QEMU_FIX_CASE_INSENSITIVE_IPTABLES_CONNMARK}"
  echo "qemu fix MindSpore non-ARM hwcap include: ${QEMU_FIX_MINDSPORE_NON_ARM_HWCAP}"
  echo "qemu fix VirtioFS node symlink copy: ${QEMU_FIX_VIRTIOFS_NODE_SYMLINK_COPY}"
  echo "qemu serialize shared Arkoala generator: ${QEMU_SERIALIZE_SHARED_ARKOALA_GENERATOR}"
  echo "qemu fix VirtioFS kernel worktree copy: ${QEMU_FIX_VIRTIOFS_KERNEL_COPY}"
  echo "QEMU absolute pointer component: ${QEMU_ABSOLUTE_POINTER_COMPONENT}"
  echo "QEMU QoS component: ${QEMU_QOS_COMPONENT}"
  echo "QEMU virtual vibrator component: ${QEMU_VIBRATOR_COMPONENT}"
  echo "QEMU vendor ALSA component: always"
  echo "QEMU accessibility component: ${QEMU_ACCESSIBILITY_COMPONENT}"
  echo "QEMU JSVM component: ${QEMU_JSVM_COMPONENT}"
  echo "JSVM M144 artifacts: ${JSVM_ENGINE_ARTIFACTS}"
  echo "QEMU Vulkan component: ${QEMU_VULKAN_COMPONENT}"
  echo "QEMU SwiftShader M144 artifacts: ${QEMU_VULKAN_ARTIFACTS}"
  echo "Required software AVC M144 artifacts: ${QEMU_AVC_ARTIFACTS}"
  echo "ccache on native out volume: ${QEMU_CCACHE_ON_OUT_VOLUME}"
  echo "armv7a product component: ${ARMV7A_PRODUCT_COMPONENT}"
  echo "standard VPN component: ${STANDARD_VPN_COMPONENT}"
  echo "QEMU 2in1 profile component: ${QEMU_2IN1_PROFILE_COMPONENT}"
  echo "device type: ${DEVICE_TYPE:-default (unset)}"
  echo "products: ${PRODUCTS[*]}"
  echo "source changes: system_compat_symlinks=${QEMU_FIX_SYSTEM_COMPAT_SYMLINKS} access_tokenid_abi=${QEMU_FIX_ACCESS_TOKENID_ABI} mindspore_non_arm_hwcap=${QEMU_FIX_MINDSPORE_NON_ARM_HWCAP} standard_vpn=${STANDARD_VPN_COMPONENT} vulkan=${QEMU_VULKAN_COMPONENT} absolute_pointer=${QEMU_ABSOLUTE_POINTER_COMPONENT} qos=${QEMU_QOS_COMPONENT} vibrator=${QEMU_VIBRATOR_COMPONENT} audio=1 accessibility=${QEMU_ACCESSIBILITY_COMPONENT} jsvm=${QEMU_JSVM_COMPONENT}"

  raise_nofile_limit
  install_deps
  verify_armv7_kernel_host_deps
  ensure_python_modules
  configure_user_tools
  ensure_host_tools
  ensure_repo_tool
  prepare_checkout
  configure_out_volume_ccache
  sync_git_lfs_objects
  restore_staged_sceneboard_lfs_assets
  apply_github_lfs_asset_component
  verify_git_lfs_objects
  prepare_ets12_separate_npm_install
  trap restore_ets12_prebuilts_config EXIT
  download_prebuilts
  restore_ets12_prebuilts_config
  trap - EXIT
  configure_ohos_node_path
  install_ets12_node_modules
  repair_ets12_node_modules
  ensure_python_modules
  ensure_hvigor_sdkmanager_common
  ensure_ohos_sdk_ets_loader_modules
  if [ "${SOURCE_PREPARE_ONLY}" = 1 ]; then
    echo "fixed release source/SDK preparation complete; no product traversal or artifact acceptance"
    return 0
  fi
}

# The only aggregate capability patch plan, shared by Docker and both profiles.
apply_qemu_capability_patch_plan() {
  bash "${QEMU_HOST_GN_EXECUTION_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_qemu_host_gn_execution_component.log"
  bash "${IDL_COMMON_TYPE_OUTPUTS_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_idl_common_type_outputs_component.log"
  if [ "${QEMU_HOST_GN_QEMU_USER}" = 1 ]; then
    test -x /usr/bin/qemu-x86_64-static
    sha256sum "${OHOS_ROOT}/prebuilts/build-tools/linux-x86/bin/gn" /usr/bin/qemu-x86_64-static
    /usr/bin/qemu-x86_64-static -cpu max "${OHOS_ROOT}/prebuilts/build-tools/linux-x86/bin/gn" --version
  fi
  core_hap_args=(--source-root "${OHOS_ROOT}" --artifact-root "${QEMU_ARKWEB_CORE_ARTIFACTS}")
  for product in "${PRODUCTS[@]}"; do core_hap_args+=(--product "${product}"); done
  bash "${PATCH_ROOT}/common/base/web/webview/core_hap_source/apply.sh" "${core_hap_args[@]}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_source_arkweb_core.log"
  # armv7a_virt is generated from the arm64 product template. Generate it
  # before applying the managed phone/2in1 inheritance; otherwise the armv7
  # component recreates config.json and silently drops the selected profile.
  apply_armv7a_product_component
  bash "${QEMU_AUDIO_PROFILE_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_qemu_audio_profile_component.log"
  bash "${QEMU_AUDIO_POLICY_7_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_qemu_audio_policy_7_component.log"
  bash "${QEMU_CAMERA_PROFILE_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_qemu_camera_profile_component.log"
  bash "${QEMU_CAMERA_USB_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_qemu_camera_usb_component.log"
  bash "${QEMU_CAMERA_VIVID_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_qemu_camera_vivid_component.log"
  bash "${QEMU_CAMERA_JPEG_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_qemu_camera_jpeg_component.log"
  bash "${QEMU_CAMERA_JPEG_CAPTURE_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_qemu_camera_jpeg_capture_component.log"
  bash "${QEMU_CAMERA_FORK_TIMESTAMP_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_qemu_camera_fork_timestamp_component.log"
  bash "${QEMU_CAMERA_CAPTURE_END_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_qemu_camera_capture_end_component.log"
  bash "${QEMU_CAMERA_CAPTURE_PUBLICATION_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_qemu_camera_capture_publication_component.log"
  bash "${QEMU_THERMAL_HDI_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_qemu_thermal_hdi_component.log"
  bash "${QEMU_THERMAL_SERVICE_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_qemu_thermal_service_component.log"
  bash "${QEMU_THERMAL_CLIENT_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_qemu_thermal_client_component.log"
  bash "${QEMU_THERMAL_NAPI_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_qemu_thermal_napi_component.log"
  bash "${QEMU_VIVID_KERNEL_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_qemu_vivid_kernel_component.log"
  bash "${QEMU_WLAN_RADIO_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_qemu_wlan_radio_component.log"
  bash "${QEMU_WLAN_REGULATORY_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_qemu_wlan_regulatory_component.log"
  bash "${QEMU_WPA_SCAN_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_qemu_wpa_scan_component.log"
  bash "${QEMU_WPA_SCAN_LIFECYCLE_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_qemu_wpa_scan_lifecycle_component.log"
  bash "${QEMU_WPA_SOFTWARE_PNO_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_qemu_wpa_software_pno_component.log"
  bash "${VIVID_CAPTURE_DEFAULTS_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_vivid_capture_defaults_component.log"
  bash "${QEMU_POWER_WAKELOCKS_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_qemu_power_wakelocks_component.log"
  bash "${QEMU_POWER_BUTTON_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_qemu_power_button_component.log"
  bash "${QEMU_VIRTIO_GPU_S2IDLE_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_qemu_virtio_gpu_s2idle_component.log"
  bash "${QEMU_VIRTIO_YUV_BUFFER_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_qemu_virtio_yuv_buffer_component.log"
  bash "${QEMU_BINDER_ASYNC_SENDER_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_qemu_binder_async_sender_component.log"
  bash "${QEMU_BINDER_CONNECTOR_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_qemu_binder_connector_component.log"
  bash "${QEMU_BINDER_OBJECT_SAFETY_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_binder_object_safety_component.log"
  bash "${RS_ASYNC_CALLER_IDENTITY_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_rs_async_caller_identity_component.log"
  apply_qemu_serial_components
  configure_qemu_device_profile
  if [ "${DEVICE_TYPE}" = "2in1" ] && [ "${QEMU_2IN1_PROFILE_COMPONENT}" != "0" ]; then
    bash "${SCENEBOARD_RUNTIME_COMPONENT_SCRIPT}" \
      --source-root "${OHOS_ROOT}" \
      --asset-root "${SCENEBOARD_RUNTIME_ASSET_ROOT}" \
      --native-source-revision "${SCENEBOARD_RUNTIME_NATIVE_REVISION}" \
      2>&1 | tee "${CACHE_ROOT}/logs/apply_sceneboard_runtime_component.log"
  elif [ "${DEVICE_TYPE}" = "phone" ] && [ "${QEMU_PHONE_PROFILE_COMPONENT}" != "0" ]; then
    bash "${PHONE_SCENEBOARD_RUNTIME_COMPONENT_SCRIPT}" \
      --source-root "${OHOS_ROOT}" \
      --asset-root "${SCENEBOARD_RUNTIME_ASSET_ROOT}" \
      --native-source-revision "${SCENEBOARD_RUNTIME_NATIVE_REVISION}" \
      2>&1 | tee "${CACHE_ROOT}/logs/apply_phone_sceneboard_runtime_component.log"
  fi
  apply_qemu_runtime_components
  bash "${NATIVE_CHILD_PROCESS_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_native_child_process_component.log"
  apply_release_hap_dependencies_component
  apply_sdk_cortex_m_component
  apply_qemu_audio_component
  apply_standard_vpn_component
  bash "${F2FS_QUOTA_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_f2fs_quota_component.log"
  bash "${MESA_KMS_MAPPING_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_mesa_kms_mapping_component.log"
  bash "${QEMU_KMS_MESA_BUILD_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_qemu_kms_mesa_build_component.log"
  bash "${MESA_KMS_MAPPING_BUILD_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_mesa_kms_mapping_build_component.log"
  apply_qemu_vulkan_component
  bash "${RENDER_CONNECTION_REPLY_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_render_connection_reply.log"
  bash "${RS_YUV_CPU_FALLBACK_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_rs_yuv_cpu_fallback.log"
  bash "${SHARED_FENCE_OWNER_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_shared_fence_owner.log"
  bash "${LOCATION_NDK_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_location_ndk_component.log"
  bash "${SENSOR_HEALTH_PERMISSION_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_sensor_health_permission_component.log"
  bash "${ARKWEB_BUSINESS_ERROR_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_arkweb_business_error_component.log"
  bash "${ETHERNET_API26_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_ethernet_api26_component.log"
  bash "${TELEPHONY_CORE_ENUMS_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_telephony_core_enums_component.log"
  bash "${TELEPHONY_SMS_ENUMS_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_telephony_sms_enums_component.log"
  bash "${TELEPHONY_CALL_ENUMS_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_telephony_call_enums_component.log"
  bash "${SCREENLOCK_ENUMS_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_screenlock_enums_component.log"
  bash "${I18N_SUGGESTION_TYPE_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_i18n_suggestion_type_component.log"
  bash "${DEVICE_MANAGER_AUTH_FORM_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_device_manager_auth_form_component.log"
  bash "${SYSTEM_SOUND_TONE_FEATURE_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_system_sound_tone_feature_component.log"
  bash "${AUDIO_PUBLIC_ENUMS_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_audio_public_enums_component.log"
  bash "${UI_EFFECT_PUBLIC_MODES_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_ui_effect_public_modes_component.log"
  bash "${BLUETOOTH_CONTROL_ENUMS_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_bluetooth_control_enums_component.log"
  bash "${CAMERA_DEPTH_CONTRACTS_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_camera_depth_contracts_component.log"
  bash "${BLUETOOTH_OPP_ENUMS_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_bluetooth_opp_enums_component.log"
  bash "${EFFECT_LIGHT_DEGREE_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_effect_light_degree_component.log"
  bash "${MISSION_STATE_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_mission_state_component.log"
  bash "${PARTICLE_ERROR_CODE_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_particle_error_code_component.log"
  bash "${CLOUD_FLAG_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_cloud_flag_component.log"
  bash "${CURVE_ENUM_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_curve_enum_component.log"
  bash "${LOCATION_PUBLIC_ENUMS_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_location_public_enums_component.log"
  bash "${NETMANAGER_API26_FEATURES_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_netmanager_api26_features_component.log"
  bash "${VPN_DIALOG_BUNDLE_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_vpn_dialog_bundle_component.log"
  bash "${DHW_UI_PREINSTALL_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_dhardware_ui_preinstall_component.log"
  bash "${QEMU_AUDIO_DEVICE_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_qemu_audio_device_component.log"
  bash "${SETTINGS_NAVIGATION_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_settings_navigation_component.log"
  bash "${SETTINGS_TTS_NAMESPACE_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_settings_tts_namespace_component.log"
  bash "${PERMISSION_OPEN_SETTING_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_permission_open_setting_component.log"
  bash "${MATRIX4_EXPORTS_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_matrix4_exports_component.log"
  bash "${BACKUP_INIT_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_backup_init_component.log"
  bash "${MODULE_UPDATE_INIT_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_module_update_init_component.log"
  bash "${USAGE_STATS_INIT_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_usage_stats_init_component.log"
  bash "${HUKS_COMPATIBILITY_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_huks_compatibility_component.log"
  bash "${QEMU_KERNEL_CAPABILITY_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_qemu_kernel_capability_component.log"
  bash "${QEMU_KERNEL_DEPENDENCIES_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_qemu_kernel_dependencies.log"
  bash "${DMABUF_PROCESS_INFO_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_dmabuf_process_info_component.log"
  if [ "${QEMU_FIX_ACCESS_TOKENID_ABI}" = "1" ]; then
    bash "${ACCESS_TOKEN_ABI_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
      2>&1 | tee "${CACHE_ROOT}/logs/apply_access_token_abi_component.log"
    bash "${ACCESS_TOKEN_SPM_HANDSHAKE_SCRIPT}" --source-root "${OHOS_ROOT}" \
      2>&1 | tee "${CACHE_ROOT}/logs/apply_access_token_spm_handshake.log"
    bash "${APPSPAWN_KERNEL_USER_ID_SCRIPT}" --source-root "${OHOS_ROOT}" \
      2>&1 | tee "${CACHE_ROOT}/logs/apply_appspawn_kernel_user_id.log"
  fi
  bash "${APPSPAWN_RENDER_PID_NAMESPACE_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_appspawn_render_pid_namespace.log"
  bash "${I18N_INIT_OWNERSHIP_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_i18n_init_ownership_component.log"
  bash "${I18N_BUILTIN_DATA_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_i18n_builtin_data_component.log"
  bash "${I18N_BUSINESS_ERROR_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_i18n_business_error_component.log"
  bash "${CERTIFICATE_EMPTY_LISTS_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_certificate_empty_lists_component.log"
  bash "${CONTACT_SYNC_MODE_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_contact_sync_mode_component.log"
  bash "${AUDIO_DEVICE_BLOCK_STATUS_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_audio_device_block_status_component.log"
  bash "${PHOTO_FUSION_ASSET_TYPE_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_photo_fusion_asset_type_component.log"
  bash "${PHOTO_PUBLIC_ENUMS_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_photo_public_enums_component.log"
  bash "${PHOTO_SEARCH_ENUMS_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_photo_search_enums_component.log"
  bash "${PHOTOS_RECENT_INFO_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_photos_recent_info_component.log"
  bash "${METADATA_FETCH_RESULT_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_metadata_fetch_result_component.log"
  bash "${INSIGHT_CONFIGURATION_MODE_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_insight_configuration_mode_component.log"
  bash "${CLI_SESSION_STATUS_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_cli_session_status_component.log"
  bash "${IMAGE_PARTIAL_TYPE_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_image_partial_type_component.log"
  bash "${IMAGE_MODEL_CALLBACKS_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_image_model_callbacks_component.log"
  bash "${ACCESSIBILITY_BLINK_ENUMS_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_accessibility_blink_enums_component.log"
  bash "${ALSA_CONFIG_INSTALL_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_alsa_config_install_component.log"
  bash "${CALENDAR_SOURCE_PROVIDER_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_calendar_source_provider_component.log"
  bash "${CALENDAR_PREBUILT_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_calendar_prebuilt_component.log"
  bash "${CALENDAR_SIGNING_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_calendar_signing_component.log"
  python3 "${PATCH_ROOT}/lib/calendar_provider.py" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/verify_calendar_source_provider.log"
  bash "${PHOTOS_SOURCE_PROVIDER_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_photos_source_provider_component.log"
  python3 "${PATCH_ROOT}/common/applications/standard/photos/source_provider/prepare_dependencies.py" \
    --source-root "${OHOS_ROOT}" --cache-root "${CACHE_ROOT}/photos-source-dependencies" \
    --evidence "${CACHE_ROOT}/logs/photos-source-preparation.json" \
    2>&1 | tee "${CACHE_ROOT}/logs/prepare_photos_source_dependencies.log"
  bash "${PHOTOS_PREBUILT_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_photos_prebuilt_component.log"
  bash "${PHOTOS_SIGNING_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_photos_signing_component.log"
  bash "${SETTINGS_SOURCE_PROVIDER_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_settings_source_provider_component.log"
  bash "${SETTINGS_EXTERNAL_INPUT_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_settings_external_input_component.log"
  bash "${SETTINGS_INPUT_2IN1_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_settings_input_2in1_component.log"
  bash "${SCREEN_MODES_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_screen_modes_component.log"
  bash "${QEMU_CAPTURE_BUDGET_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_qemu_capture_budget_component.log"
  bash "${COMPLETION_HANDLER_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_completion_handler_component.log"
  bash "${QEMU_DISPLAY_MODES_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_qemu_display_modes_component.log"
  bash "${SETTINGS_REFRESH_RATE_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_settings_refresh_rate_component.log"
  python3 "${PATCH_ROOT}/common/applications/standard/settings/source_provider/prepare_dependencies.py" \
    --source-root "${OHOS_ROOT}" --cache-root "${CACHE_ROOT}/settings-source-dependencies" \
    --evidence "${CACHE_ROOT}/logs/settings-source-preparation.json" \
    2>&1 | tee "${CACHE_ROOT}/logs/prepare_settings_source_dependencies.log"
  bash "${SETTINGS_PREBUILT_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_settings_prebuilt_component.log"
  bash "${SETTINGS_SIGNING_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_settings_signing_component.log"
  bash "${PHOTOS_FACARD_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_photos_facard_component.log"
  bash "${AVC_EOS_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_avc_eos_component.log"
  avc_component_args=(--source-root "${OHOS_ROOT}" --artifact-root "${QEMU_AVC_ARTIFACTS}")
  for avc_product in "${PRODUCTS[@]}"; do
    avc_component_args+=(--product "${avc_product}")
  done
  bash "${SOFTWARE_AVC_COMPONENT_SCRIPT}" "${avc_component_args[@]}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_software_avc_component.log"
  bash "${AUDIO_SUITE_LIBRARY_PATH_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_audio_suite_library_path_component.log"
  bash "${AUDIO_SUITE_DSP_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_audio_suite_dsp_component.log"
  bash "${NOTICE_READONLY_INPUT_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_notice_readonly_input_component.log"
  bash "${LIBJPEG_RELEASE_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_libjpeg_release_component.log"
  bash "${JSONCPP_GENERATED_SOURCE_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_jsoncpp_generated_source_component.log"
  bash "${FUSION_ACCOUNTS_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_fusion_accounts_component.log"
  bash "${FUSION_SERVICE_DOMAINS_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_fusion_service_domains_component.log"
  bash "${FUSION_PARTNER_PARAMETER_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_fusion_partner_parameter_component.log"
  bash "${ACCOUNT_TABLE_FORMAT_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_account_table_format_component.log"
  bash "${VULKAN_OHOS_SURFACE_COMPONENT_SCRIPT}" --source-root "${OHOS_ROOT}" \
    2>&1 | tee "${CACHE_ROOT}/logs/apply_vulkan_ohos_surface_component.log"
  apply_qemu_absolute_pointer_component
  fix_case_insensitive_selinux_version_header
  fix_case_insensitive_xmp_endian_header
  fix_case_insensitive_iptables_variants
  fix_case_insensitive_kernel_netfilter
  fix_mindspore_non_arm_hwcap_header
  fix_virtiofs_node_symlink_copy
  serialize_shared_arkoala_generator
  fix_virtiofs_kernel_source_copy
  configure_qemu_product_features
  ensure_flexlexer_header
  clean_corrupt_hvigor_state
  # Hash actual, fully patched kernel/config/HDI sources before any traversal.
  # Directory mtimes and a shell environment flag cannot invalidate Ninja's
  # old Image output; the GN action now consumes this stable fingerprint.
  python3 "${OHOS_ROOT}/device/qemu/common/virt_full/kernel/kernel_input_evidence.py" \
    prepare --source-root "${OHOS_ROOT}"
  write_source_preparation_metadata
}

main() {
  if [ "${PATCH_COMPONENTS_ONLY}" = 1 ]; then
    # Prepared Linux sources only: no sync, host install, hb/GN or output pruning.
    verify_manifest_baseline
    python3 "${SCRIPT_DIR}/openharmony_release_source_lock.py" --source-root "${OHOS_ROOT}"
    case "${DEVICE_TYPE}" in phone|2in1) ;; *) echo 'patch plan requires phone or 2in1' >&2; exit 2 ;; esac
    for product in "${PRODUCTS[@]}"; do
      case "${product}" in armv7a_virt) dependency_arch=arm ;; arm64_virt) dependency_arch=arm64 ;; x86_64_virt) dependency_arch=x86_64 ;; esac
      python3 "${SCRIPT_DIR}/m144_core_artifacts.py" --artifact-root "${QEMU_ARKWEB_CORE_ARTIFACTS}" --arch "${dependency_arch}"
      python3 "${PATCH_ROOT}/common/arkcompiler/jsvm/validate_artifacts.py" --artifact-root "${JSVM_ENGINE_ARTIFACTS}" --arch "${dependency_arch}"
      python3 "${SCRIPT_DIR}/verify_m144_swiftshader_artifacts.py" --artifact-root "${QEMU_VULKAN_ARTIFACTS}" --arch "${dependency_arch}"
      python3 "${PATCH_ROOT}/lib/avc_artifacts.py" --artifact-root "${QEMU_AVC_ARTIFACTS}" --arch "${dependency_arch}"
    done
    mkdir -p "${CACHE_ROOT}/logs"
    restore_staged_sceneboard_lfs_assets
    apply_github_lfs_asset_component
    apply_qemu_capability_patch_plan
    echo "complete ${DEVICE_TYPE} capability patch plan applied; no build or runtime acceptance"
    return 0
  fi
  prepare_source_and_sdk
  if [ "${SOURCE_PREPARE_ONLY}" = 1 ]; then return 0; fi
  apply_qemu_capability_patch_plan

  if [ "${PREPARE_ONLY}" = "1" ]; then
    echo
    echo "source preparation complete; build traversal was not started"
    return
  fi

  local product
  for product in "${PRODUCTS[@]}"; do
    build_product "${product}"
    if [ "${BUILD_ONLY_LOAD}" != "1" ]; then
      package_product "${product}"
      if [ "${PRUNE_PRODUCT_OUT_AFTER_PACKAGE}" = "1" ]; then
        echo "prune packaged product output to conserve disk: out/${product}"
        remove_under_ohos_root "${OHOS_ROOT}/out/${product}"
      fi
    fi
  done

  echo
  if [ "${BUILD_ONLY_LOAD}" = "1" ]; then
    echo "done. load-only validation completed for: ${PRODUCTS[*]}"
  else
    echo "done. packages:"
    find "${PACKAGE_ROOT}" -maxdepth 1 \( -name '*.tar.gz' -o -name '*.zip' \) -print | sort
  fi
}

main "$@"
