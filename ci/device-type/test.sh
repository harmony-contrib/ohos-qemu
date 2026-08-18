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
PROFILE_OVERLAY="${REPO_ROOT}/overlays/qemu_2in1_full/apply.sh"
PHONE_PROFILE_OVERLAY="${REPO_ROOT}/overlays/qemu_phone_full/apply.sh"

if [ ! -x "${REPACKAGE}" ] || [ ! -x "${VERIFY}" ] || \
   [ ! -x "${PROFILE_OVERLAY}" ] || [ ! -x "${PHONE_PROFILE_OVERLAY}" ]; then
  echo "missing repackage/verify scripts under ${REPO_ROOT}/scripts" >&2
  exit 1
fi

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

# Verify that the source overlay derives a usable profile, maps current Wukong,
# preserves the QEMU display VDI flags, and can be cleanly disabled.
FIXTURE_ROOT="${WORKDIR}/source-fixture"
mkdir -p \
  "${FIXTURE_ROOT}/productdefine/common/inherit" \
  "${FIXTURE_ROOT}/vendor/ohemu/virt" \
  "${FIXTURE_ROOT}/vendor/ohemu/virt/etc/param" \
  "${FIXTURE_ROOT}/vendor/ohemu/qemu_arm64_linux_full" \
  "${FIXTURE_ROOT}/vendor/ohemu/qemu_x86_64_linux_full" \
  "${FIXTURE_ROOT}/vendor/ohemu/qemu_armv7a_linux_full" \
  "${FIXTURE_ROOT}/applications/standard/contacts_data" \
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
PY

bash "${PROFILE_OVERLAY}" --source-root "${FIXTURE_ROOT}" --product arm64_virt
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
assert metadata["profile"] == "qemu_2in1_full_source"
assert metadata["app_compatibility_parameter"] == (
    "const.bms.supportAppTypes=2in1,phone,default,tablet"
)
assert "const.bms.supportAppTypes=2in1,phone,default,tablet" in (
    root / "vendor/ohemu/virt/etc/param/product_virt.para"
).read_text()
PY
bash "${PROFILE_OVERLAY}" --source-root "${FIXTURE_ROOT}" --product arm64_virt --disable
python3 -c 'import json,sys; assert "vendor/ohemu/virt/virt_2in1_full.json" not in json.load(open(sys.argv[1]))["inherit"]' \
  "${FIXTURE_ROOT}/vendor/ohemu/qemu_arm64_linux_full/config.json"
if grep -q '^const\.bms\.supportAppTypes=' \
  "${FIXTURE_ROOT}/vendor/ohemu/virt/etc/param/product_virt.para"
then
  echo "2in1 app compatibility parameter was not removed on disable" >&2
  exit 1
fi

bash "${PHONE_PROFILE_OVERLAY}" --source-root "${FIXTURE_ROOT}" --product arm64_virt
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
PY
bash "${PHONE_PROFILE_OVERLAY}" --source-root "${FIXTURE_ROOT}" --product arm64_virt --disable
python3 -c 'import json,sys; assert "vendor/ohemu/virt/virt_phone_full.json" not in json.load(open(sys.argv[1]))["inherit"]' \
  "${FIXTURE_ROOT}/vendor/ohemu/qemu_arm64_linux_full/config.json"
if grep -q '^const\.bms\.supportAppTypes=' \
  "${FIXTURE_ROOT}/vendor/ohemu/virt/etc/param/product_virt.para"
then
  echo "phone app compatibility parameter was not removed on disable" >&2
  exit 1
fi

INPUT_PKG="${WORKDIR}/openharmony-qemu-arm64-arm64_virt"
OUTPUT_ROOT="${WORKDIR}/out"
mkdir -p "${INPUT_PKG}/images" "${INPUT_PKG}/launch"

# Minimal guest placeholders (verifier only requires system.img + launchers structure).
: > "${INPUT_PKG}/images/Image"
: > "${INPUT_PKG}/images/ramdisk.img"
: > "${INPUT_PKG}/images/vendor.img"
# Sparse-ish clean userdata: small raw file that compresses well.
dd if=/dev/zero of="${INPUT_PKG}/images/userdata.img" bs=1m count=8 status=none

# Build a real ext2 system.img with default deviceType params.
SYSTEM_IMG="${INPUT_PKG}/images/system.img"
dd if=/dev/zero of="${SYSTEM_IMG}" bs=1m count=4 status=none
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
  system/bin
do
  debugfs -w -R "mkdir ${dir}" "${OUT_PKG}/images/system.img" >/dev/null 2>&1 || true
done
EMPTY_MARKER="${WORKDIR}/empty-marker"
: > "${EMPTY_MARKER}"
for path in \
  /system/lib64/libdlp_permission_service.z.so \
  /system/lib64/libui_appearance_service.z.so \
  /system/bin/wukong \
  /system/bin/hnp \
  /system/app/com.ohos.launcher/Launcher.hap
do
  debugfs -w -R "write ${EMPTY_MARKER} ${path}" "${OUT_PKG}/images/system.img" >/dev/null
done

SYS_PROD_IMG="${OUT_PKG}/images/sys_prod.img"
dd if=/dev/zero of="${SYS_PROD_IMG}" bs=1m count=4 status=none
mke2fs -t ext2 -F -q "${SYS_PROD_IMG}"
debugfs -w -R "mkdir etc" "${SYS_PROD_IMG}" >/dev/null
debugfs -w -R "mkdir etc/param" "${SYS_PROD_IMG}" >/dev/null
PRODUCT_VIRT_PARA="${WORKDIR}/product_virt.para"
printf '%s\n' 'const.bms.supportAppTypes=2in1,phone,default,tablet' > "${PRODUCT_VIRT_PARA}"
debugfs -w -R "write ${PRODUCT_VIRT_PARA} /etc/param/product_virt.para" \
  "${SYS_PROD_IMG}" >/dev/null
cat >"${OUT_PKG}/launch/qemu_run.sh" <<'EOF'
#!/usr/bin/env bash
exec qemu-system-aarch64 -device virtio-tablet-pci
EOF
chmod +x "${OUT_PKG}/launch/qemu_run.sh"
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
manifest["capabilities"].update({
    "absolute_pointer_sync": True,
    "device_type_profile": "qemu_2in1_full_source",
    "device_type_param_only": False,
    "device_type_full": True,
})
manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
required = [
    "applications:prebuilt_hap",
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
manifest["capabilities"].update({
    "absolute_pointer_sync": True,
    "device_type": "phone",
    "device_type_profile": "qemu_phone_full_source",
    "device_type_param_only": False,
    "device_type_full": True,
})
manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
required = [
    "applications:prebuilt_hap",
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
dd if=/dev/urandom of="${DIRTY_PKG}/images/userdata.img" bs=1m count=220 status=none
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
