#!/usr/bin/env python3
"""Stage signed, current-profile SceneBoard HAPs for QEMU 2in1 images."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from zipfile import BadZipFile, ZipFile


MODULES = {
    "SceneBoard.hap": "phone_sceneboard",
    "NotificationManagement.hap": "default_notificationmanagement",
    "ThemeService.hap": "themeservice_core",
    "ThemeComponent.hap": "themecomponent",
}
LIBRARIES = ("libmultimodalinput.so", "libeffectrender.so")
MACHINES = {"arm64-v8a": 183, "armeabi-v7a": 40, "x86_64": 62}
BUNDLE = "com.ohos.sceneboard"
SCENEBOARD_MODULES_ABC_SHA256 = "f1ceb224f8ffa56181c5de199db9bcf7e3c25a84d4dd538f8600330019d63759"
CEM_SOURCE = "base/notification/common_event_service/tools/cem/src/common_event_command.cpp"
CEM_USER_ID_BASELINE = """        Want want;
        want.SetAction(cmdInfo.action);
        CommonEventData commonEventData;
"""
CEM_USER_ID_PATCHED = """        Want want;
        want.SetAction(cmdInfo.action);
        if (cmdInfo.userId != UNDEFINED_USER) {
            want.SetParam(\"userId\", cmdInfo.userId);
        }
        CommonEventData commonEventData;
"""
CEM_ROUTING_BASELINE = """        int32_t publishResult = CommonEvent::GetInstance()->PublishCommonEventAsUser(
            commonEventData, publishInfo, nullptr, cmdInfo.userId);
"""
CEM_ROUTING_PATCHED = """        int32_t publishResult = CommonEvent::GetInstance()->PublishCommonEventAsUser(
            commonEventData, publishInfo, nullptr, UNDEFINED_USER);
"""


def profile_in_hap(path: Path) -> dict:
    data = path.read_bytes()
    text = data.decode("utf-8", errors="ignore")
    decoder = json.JSONDecoder()
    for match in re.finditer(r'\{\s*"version-name"\s*:', text):
        try:
            profile, _ = decoder.raw_decode(text, match.start())
        except json.JSONDecodeError:
            continue
        if profile.get("bundle-info", {}).get("bundle-name") == BUNDLE:
            return profile
    raise SystemExit(f"missing SceneBoard provisioning profile: {path}")


def verify_hap(path: Path, module: str) -> tuple[str, int]:
    try:
        with ZipFile(path) as archive:
            manifest = json.loads(archive.read("module.json"))
            actual = manifest["module"]["name"]
            bundle = manifest["app"]["bundleName"]
            if actual != module or bundle != BUNDLE:
                raise SystemExit(f"wrong SceneBoard module: {path}: {bundle}/{actual}")
            if module == "phone_sceneboard":
                modules_abc = archive.read("ets/modules.abc")
                if hashlib.sha256(modules_abc).hexdigest() != SCENEBOARD_MODULES_ABC_SHA256:
                    raise SystemExit(
                        f"SceneBoard entry HAP does not publish the AbilityManager 7.0 unlock event: {path}"
                    )
                for abi, machine in MACHINES.items():
                    for library in LIBRARIES:
                        filename = f"libs/{abi}/{library}"
                        data = archive.read(filename)
                        if data[:4] != b"\x7fELF" or int.from_bytes(data[18:20], "little") != machine:
                            raise SystemExit(f"wrong SceneBoard native library: {path}: {filename}")
    except (BadZipFile, KeyError, ValueError) as exc:
        raise SystemExit(f"invalid SceneBoard HAP: {path}: {exc}") from exc

    profile = profile_in_hap(path)
    bundle_info = profile.get("bundle-info", {})
    validity = profile.get("validity", {})
    now = int(time.time())
    not_before = validity.get("not-before", 0)
    not_after = validity.get("not-after", 0)
    if bundle_info.get("app-feature") != "hos_system_app" or not_before > now or not_after < now + 31536000:
        raise SystemExit(f"SceneBoard system profile is not valid for another year: {path}")
    if "AllowAppUsePrivilegeExtension" not in profile.get("app-privilege-capabilities", []):
        raise SystemExit(f"SceneBoard profile cannot install privileged extensions: {path}")
    return hashlib.sha256(path.read_bytes()).hexdigest(), not_after


def verify_signature(path: Path, jar: Path) -> None:
    if not jar.is_file():
        raise SystemExit(f"OpenHarmony HAP signature verifier is missing: {jar}")
    with tempfile.TemporaryDirectory(prefix="sceneboard-signature-") as temporary:
        result = subprocess.run(
            ["java", "-jar", str(jar), "verify-app", "-inFile", str(path),
             "-outCertChain", f"{temporary}/cert.cer", "-outProfile", f"{temporary}/profile.p7b"],
            text=True, capture_output=True, check=False,
        )
        if result.returncode or "verify-app success" not in result.stdout:
            raise SystemExit(f"SceneBoard HAP signature failed: {path}\n{result.stdout[-1000:]}{result.stderr[-1000:]}")


def patch_cem_user_id(source: Path) -> None:
    """Carry `-u` in the Want while publishing through the current user."""
    path = source / CEM_SOURCE
    content = path.read_text(encoding="utf-8")
    pairs = (
        (CEM_USER_ID_BASELINE, CEM_USER_ID_PATCHED),
        (CEM_ROUTING_BASELINE, CEM_ROUTING_PATCHED),
    )
    for baseline, patched in pairs:
        if content.count(patched) == 1 and baseline not in content:
            continue
        if content.count(baseline) != 1 or patched in content:
            raise SystemExit(f"unexpected CEM publish implementation: {path}")
        content = content.replace(baseline, patched, 1)
    path.write_text(content, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--asset-root", type=Path, required=True)
    parser.add_argument("--native-source-revision", required=True)
    args = parser.parse_args()
    source = args.source_root.resolve()
    assets = args.asset_root.resolve()
    if not re.fullmatch(r"[0-9a-f]{40}", args.native_source_revision):
        raise SystemExit("native source revision must be a 40-digit Git commit")
    jar = source / "prebuilts/ohos-sdk/linux/26.0.0/toolchains/lib/hap-sign-tool.jar"
    staged = source / "applications/standard/hap/sceneboard"
    patch_cem_user_id(source)
    staged.mkdir(parents=True, exist_ok=True)
    hashes = {}
    expiration = None
    for filename, module in MODULES.items():
        asset = assets / filename
        if not asset.is_file():
            raise SystemExit(f"missing renewed SceneBoard HAP: {asset}")
        digest, not_after = verify_hap(asset, module)
        verify_signature(asset, jar)
        if expiration is not None and expiration != not_after:
            raise SystemExit("SceneBoard modules have different profile expiry dates")
        expiration = not_after
        hashes[filename] = digest
        target = staged / filename
        if not target.is_file() or hashlib.sha256(target.read_bytes()).hexdigest() != digest:
            shutil.copy2(asset, target)

    metadata_path = source / "vendor/ohemu/virt/virt_2in1_full.meta.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["sceneboard_runtime"] = {
        "hap_sha256": hashes,
        "profile_valid_until": expiration,
        "native_source_revision": args.native_source_revision,
    }
    metadata_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("verified and staged renewed SceneBoard runtime HAPs")


if __name__ == "__main__":
    main()
