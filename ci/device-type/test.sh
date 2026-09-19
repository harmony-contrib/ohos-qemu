#!/usr/bin/env bash
# End-to-end test of the shipped deviceType packaging path.
# Creates a minimal package with an ext2 system.img, runs
# scripts/repackage_device_type.sh and scripts/verify_device_type_package.sh
# against the real tools (not a reimplementation).
set -euo pipefail
export LC_ALL=C
export LANG=C
export COPYFILE_DISABLE=1

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
REPACKAGE="${REPO_ROOT}/scripts/repackage_device_type.sh"
VERIFY="${REPO_ROOT}/scripts/verify_device_type_package.sh"
PROFILE_COMPONENT="${REPO_ROOT}/patches/2in1/product_profile/apply.sh"
PHONE_PROFILE_COMPONENT="${REPO_ROOT}/patches/phone/product_profile/apply.sh"
BUILD_STANDARD="${REPO_ROOT}/scripts/build_standard_qemu_in_docker.sh"
MUSL_SDK_COMPONENT="${REPO_ROOT}/patches/common/third_party/musl/cortex_m_sdk/apply.sh"
SCENEBOARD_2IN1_RUNTIME="${REPO_ROOT}/scripts/configure_2in1_runtime.py"
SCENEBOARD_RUNTIME_COMPONENT="${REPO_ROOT}/patches/2in1/sceneboard_runtime/apply.py"

if [ ! -x "${REPACKAGE}" ] || [ ! -x "${VERIFY}" ] || \
   [ ! -x "${PROFILE_COMPONENT}" ] || [ ! -x "${PHONE_PROFILE_COMPONENT}" ] || \
   [ ! -x "${BUILD_STANDARD}" ] || [ ! -x "${MUSL_SDK_COMPONENT}" ]; then
  echo "missing repackage/verify scripts under ${REPO_ROOT}/scripts" >&2
  exit 1
fi
test -x "${SCENEBOARD_2IN1_RUNTIME}"
test -f "${SCENEBOARD_RUNTIME_COMPONENT}"

# A component-only build interrupted before hb removes out/hb_args can leak its
# target into the next image build. The production runner must both clear that
# persisted list and request the image target explicitly.
grep -Fq 'for name in ("ninja_args", "build_target")' "${BUILD_STANDARD}"
grep -Fq -- '--build-target images' "${BUILD_STANDARD}"
grep -Fq 'write_profile_stamp_with_retry' "${BUILD_STANDARD}"
grep -Fq 'mv -f -- "${profile_stamp_tmp}" "${profile_stamp}"' "${BUILD_STANDARD}"

# Prefer Homebrew e2fsprogs on macOS.
if ! command -v debugfs >/dev/null 2>&1 || ! command -v mke2fs >/dev/null 2>&1; then
  for prefix in /opt/homebrew/opt/e2fsprogs /usr/local/opt/e2fsprogs; do
    if [ -x "${prefix}/sbin/debugfs" ]; then
      export PATH="${prefix}/sbin:${prefix}/bin:${PATH}"
      break
    fi
  done
fi

for cmd in debugfs mke2fs; do
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    echo "missing ${cmd}; install e2fsprogs" >&2
    exit 1
  fi
done

WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/ohos-device-type-test.XXXXXX")"
cleanup() { rm -rf "${WORKDIR}"; }
trap cleanup EXIT

# QEMU TCG needs extra startup time for SceneBoard. Verify the image updater
# is idempotent and preserves the system parameter file's mode and SELinux
# label while changing only the 2in1 timeout value.
ARMV7A_SYSTEM_IMG="${WORKDIR}/armv7a-system.img"
dd if=/dev/zero of="${ARMV7A_SYSTEM_IMG}" bs=1M count=4 status=none
mke2fs -t ext2 -F -q "${ARMV7A_SYSTEM_IMG}"
debugfs -w -R 'mkdir /etc' "${ARMV7A_SYSTEM_IMG}" >/dev/null
debugfs -w -R 'mkdir /etc/param' "${ARMV7A_SYSTEM_IMG}" >/dev/null
ARMV7A_APPFWK="${WORKDIR}/appfwk.para"
printf '%s\n' 'persist.sys.abilityms.timeout_unit_time_ratio = 1' >"${ARMV7A_APPFWK}"
chmod 0500 "${ARMV7A_APPFWK}"
debugfs -w -R "write ${ARMV7A_APPFWK} /etc/param/appfwk.para" \
  "${ARMV7A_SYSTEM_IMG}" >/dev/null
ARMV7A_LABEL="${WORKDIR}/appfwk.selinux"
python3 - "${ARMV7A_LABEL}" <<'PY'
from pathlib import Path
import sys
Path(sys.argv[1]).write_bytes(b"u:object_r:system_etc_file:s0\0")
PY
debugfs -w -R \
  "ea_set -f ${ARMV7A_LABEL} /etc/param/appfwk.para security.selinux" \
  "${ARMV7A_SYSTEM_IMG}" >/dev/null
python3 "${SCENEBOARD_2IN1_RUNTIME}" "${ARMV7A_SYSTEM_IMG}" >/dev/null
python3 "${SCENEBOARD_2IN1_RUNTIME}" "${ARMV7A_SYSTEM_IMG}" >/dev/null
test "$(debugfs -R 'cat /etc/param/appfwk.para' "${ARMV7A_SYSTEM_IMG}" 2>/dev/null)" = \
  'persist.sys.abilityms.timeout_unit_time_ratio = 10'
ARMV7A_PARAM_STAT="$(debugfs -R 'stat /etc/param/appfwk.para' \
  "${ARMV7A_SYSTEM_IMG}" 2>/dev/null)"
printf '%s\n' "${ARMV7A_PARAM_STAT}" | grep -Eq 'Mode:[[:space:]]+0500'
printf '%s\n' "${ARMV7A_PARAM_STAT}" | grep -Eq 'User:[[:space:]]+0[[:space:]]+Group:[[:space:]]+0'
printf '%s\n' "${ARMV7A_PARAM_STAT}" | grep -Fq 'security.selinux'

# Rewriting an ARMv7a 2in1 package maps DISPLAY_TYPE=none to a private VNC
# scanout so the guest creates a DRM connector. The phone profile retains the
# normal -display none behavior.
for profile in qemu_2in1_full_source qemu_phone_full_source; do
  launcher_package="${WORKDIR}/launcher-${profile}"
  mkdir -p "${launcher_package}/launch" "${launcher_package}/images"
  cat >"${launcher_package}/launch/qemu_run.sh" <<'EOF'
#!/usr/bin/env bash
OHOS_IMG="out/armv7a_virt/packages/phone/images"
DISPLAY_TYPE="${QEMU_DISPLAY:-none}"
HDC_HOST_PORT="${QEMU_HDC_HOST_PORT:-5555}"
case "${DISPLAY_TYPE}" in
  none)
    DISPLAY_ARGS="-device virtio-gpu-pci -display none -monitor none"
    ;;
  vnc)
    DISPLAY_ARGS="-device virtio-gpu-pci -vnc :21"
    ;;
esac
QEMU_CMD="qemu-system-arm -cpu cortex-a7 -smp 4 -m 3072 -device virtio-mouse-pci ${DISPLAY_ARGS} -append \"ohos.required_mount.data=/dev/block/vda@/data@ext4@nosuid,nodev@wait\""
eval "${QEMU_CMD}"
EOF
  chmod +x "${launcher_package}/launch/qemu_run.sh"
  python3 - "${launcher_package}/manifest.json" "${profile}" <<'PY'
import json
import sys
json.dump({
    "product": "armv7a_virt",
    "guest_arch": "armv7a",
    "device_type_profile": sys.argv[2],
    "capabilities": {"absolute_pointer_sync": True},
}, open(sys.argv[1], "w"))
PY
  bash "${REPO_ROOT}/scripts/package_standard_qemu.sh" \
    --rewrite-package "${launcher_package}" >/dev/null
done
python3 - "${WORKDIR}" <<'PY'
import re
import sys
from pathlib import Path

root = Path(sys.argv[1])
def headless(profile):
    text = (root / f"launcher-{profile}/launch/qemu_run.sh").read_text()
    display = re.search(r'case\s+"?\$\{DISPLAY_TYPE\}"?\s+in(.*?)esac', text, re.S)
    return re.search(r'\bnone\)(.*?);;', display.group(1), re.S).group(1)

two_in_one = headless("qemu_2in1_full_source")
phone = headless("qemu_phone_full_source")
assert '-vnc 127.0.0.1:${QEMU_VNC_DISPLAY}' in two_in_one
assert "-display none" not in two_in_one
assert "-display none" in phone
assert "-vnc 127.0.0.1:${QEMU_VNC_DISPLAY}" not in phone
PY

# Ubuntu invokes musl's no-shebang porting action with dash. Verify the
# component keeps the Cortex-M override POSIX-compatible and idempotent.
MUSL_FIXTURE="${WORKDIR}/musl-fixture"
mkdir -p "${MUSL_FIXTURE}/third_party/musl/scripts" \
  "${MUSL_FIXTURE}/third_party/musl/crt/linux" \
  "${MUSL_FIXTURE}/third_party/musl/crt/cortex_m" \
  "${MUSL_FIXTURE}/ported/crt"
cat >"${MUSL_FIXTURE}/third_party/musl/scripts/porting.sh" <<'EOF'
cp -rfp ${SRC_DIR}/* ${DST_DIR}
cp -rfp ${SRC_DIR}/src/internal/linux/* ${DST_DIR}/src/internal
cp -rfp ${SRC_DIR}/src/hook/linux/* ${DST_DIR}/src/hook
cp -rfp ${SRC_DIR}/crt/linux/* ${DST_DIR}/crt
if [ "${ARCH}" == "cortex_m" ]; then
    cp -rfp ${SRC_DIR}/crt/cortex_m/crtplus.c ${DST_DIR}/crt/crtplus.c
fi
cp -rfp ${SRC_DIR}/src/linux/arm/linux/* ${DST_DIR}/src/linux/arm
EOF
chmod +x "${MUSL_FIXTURE}/third_party/musl/scripts/porting.sh"
printf 'linux crtplus\n' >"${MUSL_FIXTURE}/third_party/musl/crt/linux/crtplus.c"
: >"${MUSL_FIXTURE}/third_party/musl/crt/cortex_m/crtplus.c"
git -C "${MUSL_FIXTURE}" init -q
bash "${MUSL_SDK_COMPONENT}" --source-root "${MUSL_FIXTURE}" >/dev/null
bash "${MUSL_SDK_COMPONENT}" --source-root "${MUSL_FIXTURE}" >/dev/null
test "$(grep -c 'ARCH.* = .*cortex_m' \
  "${MUSL_FIXTURE}/third_party/musl/scripts/porting.sh")" -eq 1
SRC_DIR="${MUSL_FIXTURE}/third_party/musl" \
DST_DIR="${MUSL_FIXTURE}/ported" ARCH=cortex_m \
  sh -c "$(sed -n '5,7p' \
    "${MUSL_FIXTURE}/third_party/musl/scripts/porting.sh")"
test ! -s "${MUSL_FIXTURE}/ported/crt/crtplus.c"

# Verify that the source component derives a usable profile, maps current Wukong,
# preserves the QEMU display VDI flags, and can be cleanly disabled.
FIXTURE_ROOT="${WORKDIR}/source-fixture"
mkdir -p \
  "${FIXTURE_ROOT}/productdefine/common/inherit" \
  "${FIXTURE_ROOT}/vendor/ohemu/virt" \
  "${FIXTURE_ROOT}/vendor/ohemu/virt/etc" \
  "${FIXTURE_ROOT}/vendor/ohemu/virt/etc/param" \
  "${FIXTURE_ROOT}/vendor/ohemu/qemu_arm64_linux_full" \
  "${FIXTURE_ROOT}/vendor/ohemu/qemu_x86_64_linux_full" \
  "${FIXTURE_ROOT}/vendor/ohemu/qemu_armv7a_linux_full" \
  "${FIXTURE_ROOT}/foundation/window/window_manager/etc" \
  "${FIXTURE_ROOT}/vendor/ohemu/virt/security_config" \
  "${FIXTURE_ROOT}/vendor/ohemu/virt/preinstall-config" \
  "${FIXTURE_ROOT}/applications/standard/hap" \
  "${FIXTURE_ROOT}/applications/standard/contacts_data" \
  "${FIXTURE_ROOT}/base/notification/common_event_service/tools/cem/src" \
  "${FIXTURE_ROOT}/test/ostest/wukong"

python3 - "${FIXTURE_ROOT}" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
required = [
    ("applications", "dlp_manager"),
    ("arkui", "ui_appearance"),
    ("bundlemanager", "bundle_framework"),
    ("communication", "t2stack"),
    ("filemanagement", "storage_service"),
    ("hdf", "drivers_peripheral_input"),
    ("multimodalinput", "input"),
    ("security", "dlp_permission_service"),
    ("window", "window_manager"),
]
subsystems = [
    {"subsystem": subsystem, "components": [{"component": component, "features": []}]}
    for subsystem, component in required
]
subsystems.extend([
    {"subsystem": "hdf", "components": [{"component": "drivers_interface_display", "features": []}]},
    {"subsystem": "thirdparty", "components": [
        {"component": "eudev", "features": []},
        {"component": "libsnd", "features": []},
    ]},
    {"subsystem": "wukong", "components": [{"component": "wukong", "features": []}]},
])
(root / "productdefine/common/inherit/2in1.json").write_text(
    json.dumps({"version": "3.0", "subsystems": subsystems}) + "\n"
)
phone_required = [
    ("account", "os_account"),
    ("applications", "camera"),
    ("applications", "contacts"),
    ("applications", "photos"),
    ("arkui", "ui_appearance"),
    ("bundlemanager", "bundle_framework"),
    ("contacts_data", "contacts_data"),
    ("hdf", "drivers_peripheral_display"),
    ("multimodalinput", "input"),
    ("telephony", "core_service"),
    ("window", "window_manager"),
]
phone_subsystems = [
    {"subsystem": subsystem, "components": [{"component": component, "features": []}]}
    for subsystem, component in phone_required
]
phone_subsystems.extend([
    {"subsystem": "hdf", "components": [{"component": "drivers_interface_display", "features": []}]},
    {"subsystem": "thirdparty", "components": [
        {"component": "eudev", "features": []},
        {"component": "libsnd", "features": []},
    ]},
    {"subsystem": "wukong", "components": [{"component": "wukong", "features": []}]},
])
(root / "productdefine/common/inherit/phone.json").write_text(
    json.dumps({"version": "3.0", "subsystems": phone_subsystems}) + "\n"
)
(root / "productdefine/common/inherit/rich.json").write_text(json.dumps({
    "version": "3.0",
    "subsystems": [{"subsystem": "hdf", "components": [{
        "component": "drivers_interface_display",
        "features": [
            "drivers_interface_display_community = true",
            "drivers_interface_display_vdi_default = true",
        ],
    }]}],
}) + "\n")
for directory in [
    "qemu_arm64_linux_full", "qemu_x86_64_linux_full", "qemu_armv7a_linux_full"
]:
    (root / "vendor/ohemu" / directory / "config.json").write_text(json.dumps({
        "version": "3.0",
        "inherit": [
            "productdefine/common/inherit/rich.json",
            "productdefine/common/inherit/chipset_common.json",
            "vendor/ohemu/virt/virt_common.json",
        ],
        "subsystems": [],
    }) + "\n")
(root / "test/ostest/wukong/bundle.json").write_text("{}\n")
(root / "applications/standard/contacts_data/bundle.json").write_text("{}\n")
(root / "vendor/ohemu/virt/etc/param/product_virt.para").write_text(
    "const.product.brand=default\n"
)
(root / "vendor/ohemu/virt/etc/BUILD.gn").write_text('''group("product_etc_conf") {
  deps = [
    ":product_virt.para",
  ]
}
''')
(root / "foundation/window/window_manager/etc/BUILD.gn").write_text('''group("wms_etc") {
  deps = [ ":wms.para" ]
  if (!window_manager_use_sceneboard) {
    deps += [ ":sceneboard.config" ]
  }
}

if (!window_manager_use_sceneboard) {
  ohos_prebuilt_etc("sceneboard.config") {
    source = "sceneboard.config"
    subsystem_name = "window"
  }
}
''')
(root / "foundation/window/window_manager/etc/sceneboard.config").write_text("DISABLED\n")
(root / "vendor/ohemu/virt/preinstall-config/install_list.json").write_text(
    json.dumps({"install_list": [{"app_dir": "/system/app/com.ohos.launcher", "removable": False}]}) + "\n"
)
(root / "vendor/ohemu/virt/preinstall-config/install_list_capability.json").write_text(
    json.dumps({"install_list": []}) + "\n"
)
(root / "vendor/ohemu/virt/security_config/sanitizer_check_list.gni").write_text(
    'bypass_window_manager = [\n  "libwm_lite",\n]\n'
)
(root / "applications/standard/hap/BUILD.gn").write_text('''import("//build/ohos.gni")

hap_src_dir = ""
ohos_prebuilt_etc("sceneboard_hap") {
  source = hap_src_dir + "SceneBoard.hap"
  module_install_dir = "app/SceneBoard"
}
ohos_prebuilt_etc("sceneboard_notificationManagement_hap") {
  source = hap_src_dir + "NotificationManagement.hap"
  module_install_dir = "app/SceneBoard"
}
ohos_prebuilt_etc("themeservice_hap") {
  source = hap_src_dir + "ThemeService.hap"
  module_install_dir = "app/SceneBoard"
}
ohos_prebuilt_etc("themecomponent_hap") {
  source = hap_src_dir + "ThemeComponent.hap"
  module_install_dir = "app/SceneBoard"
}

group("hap") {
  deps = [ ":launcher_hap" ]
  if (defined(product_name) && product_name == "watchos") {
    deps -= [ ":launcher_hap" ]
  }
}
''')
(root / "base/notification/common_event_service/tools/cem/src/common_event_command.cpp").write_text('''
        Want want;
        want.SetAction(cmdInfo.action);
        CommonEventData commonEventData;
        int32_t publishResult = CommonEvent::GetInstance()->PublishCommonEventAsUser(
            commonEventData, publishInfo, nullptr, cmdInfo.userId);
''')
PY

# The 2in1 runtime component must preserve `-u` as Want metadata while routing
# through the current user. This avoids CES's system-HAP-only special-user
# publisher check for the init-launched native CEM process.
python3 - "${FIXTURE_ROOT}" "${SCENEBOARD_RUNTIME_COMPONENT}" <<'PY'
import importlib.util
import sys
from pathlib import Path

root = Path(sys.argv[1])
spec = importlib.util.spec_from_file_location("sceneboard_runtime_apply", sys.argv[2])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module.patch_cem_user_id(root)
module.patch_cem_user_id(root)
content = (root / module.CEM_SOURCE).read_text()
assert content.count('want.SetParam("userId", cmdInfo.userId);') == 1
assert content.count('commonEventData, publishInfo, nullptr, UNDEFINED_USER);') == 1
assert 'commonEventData, publishInfo, nullptr, cmdInfo.userId);' not in content
PY

bash "${PROFILE_COMPONENT}" --source-root "${FIXTURE_ROOT}" --product arm64_virt
python3 - "${FIXTURE_ROOT}" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
config = json.loads((root / "vendor/ohemu/qemu_arm64_linux_full/config.json").read_text())
profile = json.loads((root / "vendor/ohemu/virt/virt_2in1_full.json").read_text())
metadata = json.loads((root / "vendor/ohemu/virt/virt_2in1_full.meta.json").read_text())
effective = "vendor/ohemu/virt/virt_2in1_full.json"
assert config["inherit"].index(effective) == config["inherit"].index(
    "productdefine/common/inherit/rich.json"
) + 1
parts = {
    (subsystem["subsystem"], component["component"]): component.get("features", [])
    for subsystem in profile["subsystems"]
    for component in subsystem["components"]
}
assert ("thirdparty", "eudev") not in parts
assert ("thirdparty", "libsnd") not in parts
assert ("wukong", "wukong") not in parts
assert ("ostest", "wukong") in parts
assert ("applications", "prebuilt_hap") in parts
assert "drivers_interface_display_vdi_default = true" in parts[
    ("hdf", "drivers_interface_display")
]
assert "window_manager_use_sceneboard = true" in parts[("window", "window_manager")]
assert metadata["profile"] == "qemu_2in1_full_source"
assert metadata["app_compatibility_parameter"] == (
    "const.bms.supportAppTypes=2in1,phone,default,tablet"
)
assert metadata["window_architecture_feature"] == "window_manager_use_sceneboard = true"
assert metadata["pc_window_parameter"] == "const.window.multiWindowUIType=FreeFormMultiWindow"
assert metadata["pc_mode_parameter"] == "persist.sceneboard.ispcmode=true"
assert metadata["boot_unlock_events"] == [
    "usual.event.USER_UNLOCKED",
    "usual.event.SCREEN_UNLOCKED",
]
assert metadata["boot_unlock_trigger"] == "bootevent.boot.completed=true"
assert metadata["boot_unlock_user_id"] == 100
assert "const.bms.supportAppTypes=2in1,phone,default,tablet" in (
    root / "vendor/ohemu/virt/etc/param/product_virt.para"
).read_text()
assert "const.window.multiWindowUIType=FreeFormMultiWindow" in (
    root / "vendor/ohemu/virt/etc/param/product_virt.para"
).read_text()
assert "persist.sceneboard.ispcmode=true" in (
    root / "vendor/ohemu/virt/etc/param/product_virt.para"
).read_text()
assert (root / "foundation/window/window_manager/etc/sceneboard.config").read_text() == "ENABLED\n"
assert (
    root / "foundation/window/window_manager/etc/BUILD.gn"
).read_text().count('if (window_manager_use_sceneboard)') == 2
assert 'if (!window_manager_use_sceneboard)' not in (
    root / "foundation/window/window_manager/etc/BUILD.gn"
).read_text()
assert '"dm_unittest_common_lite"' in (
    root / "vendor/ohemu/virt/security_config/sanitizer_check_list.gni"
).read_text()
preinstall = json.loads((root / "vendor/ohemu/virt/preinstall-config/install_list.json").read_text())
assert {"app_dir": "/system/app/SceneBoard", "removable": False} in preinstall["install_list"]
capabilities = json.loads((root / "vendor/ohemu/virt/preinstall-config/install_list_capability.json").read_text())
assert any(entry.get("bundleName") == "com.ohos.sceneboard" and
           entry.get("allowAppUsePrivilegeExtension") and
           entry.get("app_signature") == ["8E93863FC32EE238060BF69A9B37E2608FFFB21F93C862DD511CBAC9F30024B5"]
           for entry in capabilities["install_list"])
boot_unlock = json.loads((root / "vendor/ohemu/virt/etc/qemu_2in1_unlock.cfg").read_text())
assert boot_unlock["jobs"] == [{
    "name": "param:bootevent.boot.completed=true",
    "condition": "bootevent.boot.completed=true",
    "cmds": ["start qemu_2in1_user_unlock", "start qemu_2in1_unlock"],
}]
common_service = {
    "uid": "system",
    "gid": ["system"],
    "apl": "system_core",
    "permission": [
        "ohos.permission.PUBLISH_SYSTEM_COMMON_EVENT",
        "ohos.permission.INTERACT_ACROSS_LOCAL_ACCOUNTS",
    ],
    "once": 1,
    "start-mode": "condition",
    "secon": "u:r:cem:s0",
}
assert boot_unlock["services"] == [
    {
        **common_service,
        "name": "qemu_2in1_user_unlock",
        "path": ["/system/bin/cem", "publish", "-e", "usual.event.USER_UNLOCKED", "-c", "100"],
    },
    {
        **common_service,
        "name": "qemu_2in1_unlock",
        "path": ["/system/bin/cem", "publish", "-e", "usual.event.SCREEN_UNLOCKED", "-u", "100"],
    },
]
etc_build = (root / "vendor/ohemu/virt/etc/BUILD.gn").read_text()
assert etc_build.count('ohos_prebuilt_etc("qemu_2in1_unlock_cfg")') == 1
assert etc_build.count('":qemu_2in1_unlock_cfg"') == 1
PY

bash "${PROFILE_COMPONENT}" --source-root "${FIXTURE_ROOT}" --product arm64_virt --disable
python3 -c 'import json,sys; assert "vendor/ohemu/virt/virt_2in1_full.json" not in json.load(open(sys.argv[1]))["inherit"]' \
  "${FIXTURE_ROOT}/vendor/ohemu/qemu_arm64_linux_full/config.json"
if grep -q '^const\.bms\.supportAppTypes=' \
  "${FIXTURE_ROOT}/vendor/ohemu/virt/etc/param/product_virt.para"
then
  echo "2in1 app compatibility parameter was not removed on disable" >&2
  exit 1
fi
if grep -q '^const\.window\.multiWindowUIType=' \
  "${FIXTURE_ROOT}/vendor/ohemu/virt/etc/param/product_virt.para"
then
  echo "2in1 PC window parameter was not removed on disable" >&2
  exit 1
fi
if grep -q '^persist\.sceneboard\.ispcmode=' \
  "${FIXTURE_ROOT}/vendor/ohemu/virt/etc/param/product_virt.para"
then
  echo "2in1 PC mode parameter was not removed on disable" >&2
  exit 1
fi
test "$(cat "${FIXTURE_ROOT}/foundation/window/window_manager/etc/sceneboard.config")" = DISABLED
python3 - "${FIXTURE_ROOT}" <<'PY'
import json
import sys
from pathlib import Path
root = Path(sys.argv[1])
preinstall = json.loads((root / "vendor/ohemu/virt/preinstall-config/install_list.json").read_text())
capabilities = json.loads((root / "vendor/ohemu/virt/preinstall-config/install_list_capability.json").read_text())
assert all(entry.get("app_dir") != "/system/app/SceneBoard" for entry in preinstall["install_list"])
assert all(entry.get("bundleName") != "com.ohos.sceneboard" for entry in capabilities["install_list"])
PY
grep -Fq 'if (!window_manager_use_sceneboard)' \
  "${FIXTURE_ROOT}/foundation/window/window_manager/etc/BUILD.gn"
test ! -e "${FIXTURE_ROOT}/vendor/ohemu/virt/etc/qemu_2in1_unlock.cfg"
if grep -Fq 'qemu_2in1_unlock' \
  "${FIXTURE_ROOT}/vendor/ohemu/virt/etc/BUILD.gn"
then
  echo "2in1 boot unlock publisher was not removed on disable" >&2
  exit 1
fi
if grep -Fq '"dm_unittest_common_lite"' \
  "${FIXTURE_ROOT}/vendor/ohemu/virt/security_config/sanitizer_check_list.gni"
then
  echo "2in1 test-only CFI exception was not removed on disable" >&2
  exit 1
fi

bash "${PHONE_PROFILE_COMPONENT}" --source-root "${FIXTURE_ROOT}" --product arm64_virt
python3 - "${FIXTURE_ROOT}" <<'PY'
import json
import sys
from pathlib import Path

root = Path(sys.argv[1])
config = json.loads((root / "vendor/ohemu/qemu_arm64_linux_full/config.json").read_text())
profile = json.loads((root / "vendor/ohemu/virt/virt_phone_full.json").read_text())
metadata = json.loads((root / "vendor/ohemu/virt/virt_phone_full.meta.json").read_text())
effective = "vendor/ohemu/virt/virt_phone_full.json"
assert config["inherit"].index(effective) == config["inherit"].index(
    "productdefine/common/inherit/rich.json"
) + 1
parts = {
    (subsystem["subsystem"], component["component"]): component.get("features", [])
    for subsystem in profile["subsystems"]
    for component in subsystem["components"]
}
assert ("applications", "prebuilt_hap") in parts
assert ("applications", "camera") in parts
assert ("applications", "contacts") not in parts
assert ("contacts_data", "contacts_data") in parts
assert ("telephony", "core_service") in parts
assert ("ostest", "wukong") in parts
assert "drivers_interface_display_vdi_default = true" in parts[
    ("hdf", "drivers_interface_display")
]
assert metadata["profile"] == "qemu_phone_full_source"
assert "applications:contacts->contacts_data:contacts_data" in metadata[
    "mapped_components"
]
assert metadata["app_compatibility_parameter"] == (
    "const.bms.supportAppTypes=2in1,phone,default,tablet"
)
assert "const.window.multiWindowUIType=" not in (
    root / "vendor/ohemu/virt/etc/param/product_virt.para"
).read_text()
PY
bash "${PHONE_PROFILE_COMPONENT}" --source-root "${FIXTURE_ROOT}" --product arm64_virt --disable
python3 -c 'import json,sys; assert "vendor/ohemu/virt/virt_phone_full.json" not in json.load(open(sys.argv[1]))["inherit"]' \
  "${FIXTURE_ROOT}/vendor/ohemu/qemu_arm64_linux_full/config.json"
if grep -q '^const\.bms\.supportAppTypes=' \
  "${FIXTURE_ROOT}/vendor/ohemu/virt/etc/param/product_virt.para"
then
  echo "phone app compatibility parameter was not removed on disable" >&2
  exit 1
fi

# A clean upstream checkout has arm64/x86_64 products but not the optional
# armv7a product created by this repository. Selected-product operations must
# not traverse into that missing optional config (regression for issue log
# ae599fa5cf4aab867a437904b3283655).
rm -rf "${FIXTURE_ROOT}/vendor/ohemu/qemu_armv7a_linux_full"
bash "${PROFILE_COMPONENT}" \
  --source-root "${FIXTURE_ROOT}" --product arm64_virt --disable
bash "${PHONE_PROFILE_COMPONENT}" \
  --source-root "${FIXTURE_ROOT}" --product arm64_virt --disable

INPUT_PKG="${WORKDIR}/openharmony-qemu-arm64-arm64_virt"
OUTPUT_ROOT="${WORKDIR}/out"
mkdir -p "${INPUT_PKG}/images" "${INPUT_PKG}/launch"

# Minimal guest placeholders (verifier only requires system.img + launchers structure).
: > "${INPUT_PKG}/images/Image"
: > "${INPUT_PKG}/images/ramdisk.img"
: > "${INPUT_PKG}/images/vendor.img"
# Sparse-ish clean userdata: small raw file that compresses well.
dd if=/dev/zero of="${INPUT_PKG}/images/userdata.img" bs=1M count=8 status=none

# Build a real ext2 system.img with default deviceType params.
SYSTEM_IMG="${INPUT_PKG}/images/system.img"
dd if=/dev/zero of="${SYSTEM_IMG}" bs=1M count=4 status=none
mke2fs -t ext2 -F -q "${SYSTEM_IMG}"
debugfs -w -R "mkdir etc" "${SYSTEM_IMG}" >/dev/null
debugfs -w -R "mkdir etc/param" "${SYSTEM_IMG}" >/dev/null

OHOS_PARA="${WORKDIR}/ohos.para"
cat > "${OHOS_PARA}" <<'EOF'
const.build.characteristics=default
const.product.devicetype=default
const.security.developermode.state=true
EOF
debugfs -w -R "write ${OHOS_PARA} /etc/param/ohos.para" "${SYSTEM_IMG}" >/dev/null

# Minimal manifest + launch stubs (repackage rewrites launch when asked).
cat > "${INPUT_PKG}/manifest.json" <<'EOF'
{
  "product": "arm64_virt",
  "guest_arch": "arm64",
  "kernel": "Image",
  "qemu_unix": "qemu-system-aarch64",
  "qemu_windows": "qemu-system-aarch64.exe",
  "display_default": "none",
  "network_default": "user",
  "capabilities": {
    "standard_vpn": false
  }
}
EOF

cat > "${INPUT_PKG}/launch/linux.sh" <<'EOF'
#!/usr/bin/env bash
echo "stub"
EOF
chmod +x "${INPUT_PKG}/launch/linux.sh"
cp "${INPUT_PKG}/launch/linux.sh" "${INPUT_PKG}/launch/qemu_run.sh"
chmod +x "${INPUT_PKG}/launch/qemu_run.sh"

# Drive the real repackage entry point.
bash "${REPACKAGE}" \
  --device-type 2in1 \
  --output-dir "${OUTPUT_ROOT}" \
  --input-package "${INPUT_PKG}"

OUT_PKG="${OUTPUT_ROOT}/openharmony-qemu-arm64-arm64_virt-2in1"
test -d "${OUT_PKG}"
test -f "${OUT_PKG}.tar.gz"
test -f "${OUT_PKG}/manifest.json"

# Drive the real offline verifier entry point.
VERIFY_LOG="${WORKDIR}/verify.log"
bash "${VERIFY}" --package "${OUT_PKG}" --expect-device-type 2in1 | tee "${VERIFY_LOG}"

grep -q "RESULT: PASS" "${VERIFY_LOG}"
grep -q "parsed devicetype=2in1 characteristics=2in1" "${VERIFY_LOG}"
python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); assert d.get("device_type")=="2in1"' \
  "${OUT_PKG}/manifest.json"

# Parameter-only repackaging must never satisfy the strict source-build gate.
if bash "${VERIFY}" \
  --package "${OUT_PKG}" \
  --expect-device-type 2in1 \
  --require-full-2in1 >"${WORKDIR}/param-only-strict.log" 2>&1
then
  echo "expected strict verifier to reject a parameter-only 2in1 package" >&2
  exit 1
fi
grep -q "not marked as a full source-built 2in1 profile" \
  "${WORKDIR}/param-only-strict.log"

# Exercise strict full-profile verification with a minimal synthetic evidence
# file and the runtime paths required by the real source packager.
for dir in \
  system \
  system/app \
  system/app/com.ohos.dlpmanager \
  system/app/com.ohos.launcher \
  system/app/com.ohos.systemui \
  system/lib64 \
  system/bin \
  system/bin/cli_tool \
  system/bin/cli_tool/executable
do
  debugfs -w -R "mkdir ${dir}" "${OUT_PKG}/images/system.img" >/dev/null 2>&1 || true
done
EMPTY_MARKER="${WORKDIR}/empty-marker"
: > "${EMPTY_MARKER}"
A11Y_MANAGER="${WORKDIR}/ohos-a11yManager"
cat > "${A11Y_MANAGER}" <<'EOF'
ability-enable
ability-disable
--name
--capabilities
qemu_accessibility_cli
ohos.permission.WRITE_ACCESSIBILITY_CONFIG
GetAccessTokenId
SetSelfTokenID
Failed to initialize the QEMU accessibility token
EOF
VIBRATOR_ELF="${WORKDIR}/vibrator.so"
JSVM_ELF="${WORKDIR}/libjsvm.so"
V8_ELF="${WORKDIR}/libv8_shared.so"
BAD_JSVM_ELF="${WORKDIR}/libjsvm-unresolved.so"
BAD_V8_ELF="${WORKDIR}/libv8_shared-wrong-abi.so"
V8_API='_ZN2v84JSON5ParseENSt3__h8optionalIiEE'
BAD_V8_API='_ZN2v84JSON5ParseENSt4__Cr8optionalIiEE'
python3 "${REPO_ROOT}/ci/make-elf-fixture.py" --machine 183 \
  --defined hdfVdiDesc --output "${VIBRATOR_ELF}"
python3 "${REPO_ROOT}/ci/make-elf-fixture.py" --machine 183 \
  --undefined "${V8_API}" --output "${JSVM_ELF}"
python3 "${REPO_ROOT}/ci/make-elf-fixture.py" --machine 183 \
  --defined "${V8_API}" --output "${V8_ELF}"
python3 "${REPO_ROOT}/ci/make-elf-fixture.py" --machine 183 \
  --undefined "${V8_API}" \
  --undefined _ZN4jsvm8jitparse17JsSymbolExtractorD1Ev \
  --output "${BAD_JSVM_ELF}"
python3 "${REPO_ROOT}/ci/make-elf-fixture.py" --machine 183 \
  --defined "${BAD_V8_API}" --output "${BAD_V8_ELF}"
python3 "${REPO_ROOT}/scripts/verify_runtime_elf_contract.py" --machine 183 \
  --elf "${VIBRATOR_ELF}" --require-defined hdfVdiDesc
python3 "${REPO_ROOT}/scripts/verify_runtime_elf_contract.py" --machine 183 \
  --jsvm "${JSVM_ELF}" --v8 "${V8_ELF}"
if python3 "${REPO_ROOT}/scripts/verify_runtime_elf_contract.py" --machine 183 \
    --elf "${V8_ELF}" --require-defined hdfVdiDesc >/dev/null 2>&1; then
  echo "ELF contract verifier accepted a VDI without hdfVdiDesc" >&2
  exit 1
fi
if python3 "${REPO_ROOT}/scripts/verify_runtime_elf_contract.py" --machine 183 \
    --jsvm "${JSVM_ELF}" --v8 "${BAD_V8_ELF}" >/dev/null 2>&1; then
  echo "ELF contract verifier accepted a mismatched libc++ ABI" >&2
  exit 1
fi
if python3 "${REPO_ROOT}/scripts/verify_runtime_elf_contract.py" --machine 183 \
    --jsvm "${BAD_JSVM_ELF}" --v8 "${V8_ELF}" >/dev/null 2>&1; then
  echo "ELF contract verifier accepted an unresolved JSVM DFX symbol" >&2
  exit 1
fi
for path in \
  /system/lib64/libdlp_permission_service.z.so \
  /system/lib64/libui_appearance_service.z.so \
  /system/bin/wukong \
  /system/bin/hnp \
  /system/app/com.ohos.launcher/Launcher.hap
do
  debugfs -w -R "write ${EMPTY_MARKER} ${path}" "${OUT_PKG}/images/system.img" >/dev/null
done
debugfs -w -R \
  "write ${A11Y_MANAGER} /system/bin/cli_tool/executable/ohos-a11yManager" \
  "${OUT_PKG}/images/system.img" >/dev/null
debugfs -w -R "write ${JSVM_ELF} /system/lib64/libjsvm.so" \
  "${OUT_PKG}/images/system.img" >/dev/null
debugfs -w -R "write ${V8_ELF} /system/lib64/libv8_shared.so" \
  "${OUT_PKG}/images/system.img" >/dev/null

VENDOR_IMG="${OUT_PKG}/images/vendor.img"
dd if=/dev/zero of="${VENDOR_IMG}" bs=1M count=4 status=none
mke2fs -t ext2 -F -q "${VENDOR_IMG}"
debugfs -w -R "mkdir vendor" "${VENDOR_IMG}" >/dev/null
debugfs -w -R "mkdir vendor/lib64" "${VENDOR_IMG}" >/dev/null
debugfs -w -R \
  "write ${VIBRATOR_ELF} /vendor/lib64/libhdi_product_vibrator_impl.z.so" \
  "${VENDOR_IMG}" >/dev/null

cat >"${OUT_PKG}/kernel.config" <<'EOF'
CONFIG_AUTHORITY_CTRL=y
CONFIG_QOS_CTRL=y
CONFIG_QOS_AUTHORITY=y
CONFIG_QOS_POLICY_MAX_NR=6
CONFIG_SCHED_LATENCY_NICE=y
CONFIG_UCLAMP_TASK=y
CONFIG_UCLAMP_TASK_GROUP=y
EOF

SYS_PROD_IMG="${OUT_PKG}/images/sys_prod.img"
dd if=/dev/zero of="${SYS_PROD_IMG}" bs=1M count=4 status=none
mke2fs -t ext2 -F -q "${SYS_PROD_IMG}"
debugfs -w -R "mkdir etc" "${SYS_PROD_IMG}" >/dev/null
debugfs -w -R "mkdir etc/param" "${SYS_PROD_IMG}" >/dev/null
PRODUCT_VIRT_PARA="${WORKDIR}/product_virt.para"
printf '%s\n' 'const.bms.supportAppTypes=2in1,phone,default,tablet' > "${PRODUCT_VIRT_PARA}"
debugfs -w -R "write ${PRODUCT_VIRT_PARA} /etc/param/product_virt.para" \
  "${SYS_PROD_IMG}" >/dev/null
cat >"${OUT_PKG}/launch/qemu_run.sh" <<'EOF'
#!/usr/bin/env bash
exec qemu-system-aarch64 -device virtio-tablet-pci "$@"
EOF
chmod +x "${OUT_PKG}/launch/qemu_run.sh"
cat >"${OUT_PKG}/launch/linux.sh" <<'EOF'
#!/usr/bin/env bash
if [ "${1:-}" = "--a11y" ]; then
  shift
  set -- -device virtio-multitouch-pci \
    -qmp unix:/tmp/openharmony-qemu-a11y.sock,server=on,wait=off "$@"
fi
exec "$(dirname "$0")/qemu_run.sh" "$@"
EOF
chmod +x "${OUT_PKG}/launch/linux.sh"
python3 - "${OUT_PKG}" <<'PY'
import json
import sys
from pathlib import Path

package = Path(sys.argv[1])
manifest_path = package / "manifest.json"
manifest = json.loads(manifest_path.read_text())
manifest["device_type_profile"] = "qemu_2in1_full_source"
manifest["device_type_source"] = "source_product_inherit"
manifest.setdefault("launcher", {})["pointer_device_default"] = "virtio-tablet-pci"
manifest["launcher"].update({"accessibility": True, "qmp_unix": True})
manifest["capabilities"].update({
    "absolute_pointer_sync": True,
    "thread_qos": True,
    "virtual_vibrator": True,
    "virtual_vibrator_mode": "simulated",
    "jsvm": True,
    "jsvm_engine": "ArkWeb M144 V8",
    "standard_vpn": True,
    "accessibility_test": True,
    "accessibility_cli": True,
    "virtio_multitouch": True,
    "device_type_profile": "qemu_2in1_full_source",
    "device_type_param_only": False,
    "device_type_full": True,
})
manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
required = [
    "applications:prebuilt_hap",
    "arkcompiler:jsvm",
    "security:dlp_permission_service",
    "applications:dlp_manager",
]
(package / "device-profile.json").write_text(json.dumps({
    "device_type": "2in1",
    "profile": "qemu_2in1_full_source",
    "inherit": ["vendor/ohemu/virt/virt_2in1_full.json"],
    "required_parts": required,
    "resolved_parts": required,
    "resolved_parts_count": len(required),
    "upstream_sha256": "0" * 64,
    "qemu_adaptations": {
        "app_compatibility_parameter":
            "const.bms.supportAppTypes=2in1,phone,default,tablet",
        "jsvm_engine": "OpenHarmony-TPC ArkWeb M144 V8 shared library",
    },
}, indent=2) + "\n")
PY
bash "${VERIFY}" \
  --package "${OUT_PKG}" \
  --expect-device-type 2in1 \
  --require-full-2in1 | grep -q "RESULT: PASS (full source-built 2in1 profile)"

# The full phone profile has distinct provenance and runtime requirements.
PHONE_PKG="${WORKDIR}/openharmony-qemu-arm64-arm64_virt-phone"
cp -a "${OUT_PKG}" "${PHONE_PKG}"
PHONE_OHOS_PARA="${WORKDIR}/ohos-phone.para"
cat > "${PHONE_OHOS_PARA}" <<'EOF'
const.build.characteristics=phone
const.product.devicetype=phone
const.security.developermode.state=true
EOF
debugfs -w -R 'rm /etc/param/ohos.para' "${PHONE_PKG}/images/system.img" >/dev/null
debugfs -w -R "write ${PHONE_OHOS_PARA} /etc/param/ohos.para" \
  "${PHONE_PKG}/images/system.img" >/dev/null
for dir in \
  system/app/com.ohos.camera \
  system/app/com.ohos.photos \
  system/app/com.ohos.contacts
do
  debugfs -w -R "mkdir ${dir}" "${PHONE_PKG}/images/system.img" >/dev/null 2>&1 || true
done
debugfs -w -R "write ${EMPTY_MARKER} /system/lib64/libtel_core_service.z.so" \
  "${PHONE_PKG}/images/system.img" >/dev/null
python3 - "${PHONE_PKG}" <<'PY'
import json
import sys
from pathlib import Path

package = Path(sys.argv[1])
manifest_path = package / "manifest.json"
manifest = json.loads(manifest_path.read_text())
manifest["device_type"] = "phone"
manifest["device_type_profile"] = "qemu_phone_full_source"
manifest["device_type_source"] = "source_product_inherit"
manifest.setdefault("launcher", {})["pointer_device_default"] = "virtio-tablet-pci"
manifest["launcher"].update({"accessibility": True, "qmp_unix": True})
manifest["capabilities"].update({
    "absolute_pointer_sync": True,
    "thread_qos": True,
    "virtual_vibrator": True,
    "virtual_vibrator_mode": "simulated",
    "jsvm": True,
    "jsvm_engine": "ArkWeb M144 V8",
    "standard_vpn": True,
    "accessibility_test": True,
    "accessibility_cli": True,
    "virtio_multitouch": True,
    "device_type": "phone",
    "device_type_profile": "qemu_phone_full_source",
    "device_type_param_only": False,
    "device_type_full": True,
})
manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
required = [
    "applications:prebuilt_hap",
    "arkcompiler:jsvm",
    "applications:camera",
    "telephony:core_service",
]
(package / "device-profile.json").write_text(json.dumps({
    "device_type": "phone",
    "profile": "qemu_phone_full_source",
    "inherit": ["vendor/ohemu/virt/virt_phone_full.json"],
    "required_parts": required,
    "resolved_parts": required,
    "resolved_parts_count": len(required),
    "upstream_sha256": "1" * 64,
    "qemu_adaptations": {
        "app_compatibility_parameter":
            "const.bms.supportAppTypes=2in1,phone,default,tablet",
        "jsvm_engine": "OpenHarmony-TPC ArkWeb M144 V8 shared library",
    },
}, indent=2) + "\n")
PY
bash "${VERIFY}" \
  --package "${PHONE_PKG}" \
  --expect-device-type phone \
  --require-full-phone | grep -q "RESULT: PASS (full source-built phone profile)"

# Refuse dirty userdata by default: enlarge compressible image with random data.
DIRTY_PKG="${WORKDIR}/openharmony-qemu-arm64-arm64_virt-dirty"
cp -a "${INPUT_PKG}" "${DIRTY_PKG}"
# ~32MB of high-entropy data so gzip -1 exceeds the 200MB threshold when padded,
# or use a larger random blob. 220MB of /dev/urandom is slow; use sparse+random mix.
dd if=/dev/urandom of="${DIRTY_PKG}/images/userdata.img" bs=1M count=220 status=none
set +e
bash "${REPACKAGE}" \
  --device-type 2in1 \
  --output-dir "${WORKDIR}/out-dirty" \
  --input-package "${DIRTY_PKG}" >"${WORKDIR}/dirty.log" 2>&1
dirty_rc=$?
set -e
if [ "${dirty_rc}" -eq 0 ]; then
  echo "expected dirty userdata to be refused without --allow-dirty-userdata" >&2
  cat "${WORKDIR}/dirty.log" >&2
  exit 1
fi
grep -q "looks dirty" "${WORKDIR}/dirty.log"

echo "ci/device-type/test.sh: PASS"
