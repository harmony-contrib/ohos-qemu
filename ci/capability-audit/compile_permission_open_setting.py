#!/usr/bin/env python3
"""Compile the candidate system UI using an isolated full-API SDK overlay.

The output is a syntax-check HAP with a non-system test bundle name. Never
install it as PermissionManager or count it as runtime/first-package proof.
The original SDK/source checkout is not changed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk", type=Path, default=Path("/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony"))
    parser.add_argument("--full-api-dir", type=Path, required=True,
                        help="Actual pinned checkout's prebuilts/ohos-sdk/linux/26.0.0/ets/api, copied read-only")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--arkdown", default="arkdown")
    args = parser.parse_args()
    root = args.output.resolve()
    if root.exists():
        raise ValueError("use a fresh output directory; do not overwrite existing build evidence")
    root.mkdir(parents=True)
    sdk = args.sdk.resolve()
    overlay = root / "sdk-overlay"
    overlay.mkdir()
    for path in sdk.iterdir():
        if path.name == "ets":
            shutil.copytree(path, overlay / path.name, symlinks=True)
        else:
            (overlay / path.name).symlink_to(path, target_is_directory=path.is_dir())
    shutil.copytree(args.full_api_dir.resolve(), overlay / "ets/api", dirs_exist_ok=True)

    def write(name, value):
        path = root / "project" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value if isinstance(value, str) else json.dumps(value, indent=2) + "\n")

    write("AppScope/app.json5", {"app": {"bundleName": "org.harmonycontrib.permissioncompile",
        "vendor": "harmony-contrib", "versionCode": 1, "versionName": "1.0.0",
        "icon": "$media:icon", "label": "$string:app_name"}})
    write("AppScope/resources/base/element/string.json", {"string": [{"name": "app_name", "value": "Compile only"}]})
    write("AppScope/resources/base/media/icon.svg", '<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128"><rect width="128" height="128" fill="#888888"/></svg>')
    write("build-profile.json5", {"app": {"products": [{"name": "default", "targetSdkVersion": "7.0.0(26)",
        "compatibleSdkVersion": "5.0.5(17)", "runtimeOS": "HarmonyOS"}],
        "buildModeSet": [{"name": "debug"}, {"name": "release"}]},
        "modules": [{"name": "entry", "srcPath": "./entry", "targets": [{"name": "default", "applyToProducts": ["default"]}]}]})
    write("oh-package.json5", {"modelVersion": "6.0.0", "name": "permission-compile", "version": "1.0.0", "dependencies": {}})
    write("entry/oh-package.json5", {"modelVersion": "6.0.0", "name": "entry", "version": "1.0.0", "dependencies": {}})
    write("entry/build-profile.json5", {"apiType": "stageMode", "buildOption": {}, "targets": [{"name": "default"}]})
    write("entry/src/main/module.json5", {"module": {"name": "entry", "type": "entry", "mainElement": "EntryAbility",
        "deviceTypes": ["2in1"], "deliveryWithInstall": True, "installationFree": False, "pages": "$profile:main_pages",
        "abilities": [{"name": "EntryAbility", "srcEntry": "./ets/EntryAbility.ets", "exported": True}],
        "extensionAbilities": [{"name": "com.ohos.permissionmanager.OpenSettingAbility", "srcEntry": "./ets/OpenSetting/OpenSettingAbility.ets",
            "type": "sys/commonUI", "exported": True}]}})
    write("entry/src/main/ets/EntryAbility.ets", "import UIAbility from '@ohos.app.ability.UIAbility';\nexport default class EntryAbility extends UIAbility {}\n")
    write("entry/src/main/resources/base/profile/main_pages.json", {"src": ["OpenSetting/OpenSettingDialog"]})
    files = Path(__file__).resolve().parents[2] / "patches/common/applications/standard/permission_manager/open_setting/files"
    source_hashes = {}
    for candidate in sorted(files.glob("*.ets")):
        write("entry/src/main/ets/OpenSetting/" + candidate.name, candidate.read_text())
        source_hashes[candidate.name] = hashlib.sha256(candidate.read_bytes()).hexdigest()
    subprocess.run([args.arkdown, "build", "--project", str(root / "project"), "--target", "hap", "--mode", "debug"],
                   env=dict(os.environ, OHOS_SDK_HOME=str(overlay)), check=True)
    hap = root / "project/entry/build/default/outputs/default/entry-default-unsigned.hap"
    result = {"scope": "compile_only_do_not_install", "status": "pass", "sources": source_hashes,
              "hap": str(hap), "hap_sha256": hashlib.sha256(hap.read_bytes()).hexdigest()}
    (root / "compile-evidence.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
