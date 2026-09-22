#!/usr/bin/env python3
"""Build the app-context capability probe for a booted audit guest."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--arch", choices=("arm64", "armv7a", "x86_64"), default="arm64")
parser.add_argument(
    "--sdk",
    type=Path,
    default=Path("/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony"),
)
parser.add_argument("--arkdown", default=os.environ.get("ARKDOWN", "arkdown"))
parser.add_argument("--hap-sign", default=os.environ.get("HAP_SIGN", "hap-sign"))
parser.add_argument("--udid", required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--syscap-registry", type=Path)
parser.add_argument(
    "--api-dir",
    type=Path,
    help="Public interface-sdk-js api directory; defaults to the installed SDK ets/api",
)
parser.add_argument(
    "--kits-dir",
    type=Path,
    help="Public interface-sdk-js kits directory; defaults to the sibling of --api-dir when present",
)
args = parser.parse_args()

root = args.output.resolve()
root.mkdir(parents=True, exist_ok=True)
triple, abi = {
    "arm64": ("aarch64-linux-ohos", "arm64-v8a"),
    "armv7a": ("arm-linux-ohos", "armeabi-v7a"),
    "x86_64": ("x86_64-linux-ohos", "x86_64"),
}[args.arch]
bundle = "org.harmonycontrib.capabilityaudit"
api_dir = (args.api_dir or (args.sdk / "ets/api")).resolve()
kits_dir = (args.kits_dir or (api_dir.parent / "kits")).resolve()
api_modules = {
    path.name.removesuffix(".d.ts")
    for pattern in ("@ohos*.d.ts", "@system*.d.ts")
    for path in api_dir.glob(pattern)
}
if kits_dir.is_dir():
    api_modules.update(
        path.name.removesuffix(".d.ts")
        for path in kits_dir.glob("@kit*.d.ts")
    )
api_modules = sorted(api_modules)
if args.syscap_registry:
    public_syscaps = sorted(
        row["syscap"]
        for row in json.loads(args.syscap_registry.read_text(encoding="utf-8"))["capabilities"]
    )
else:
    public_syscaps = sorted({
        cap
        for path in api_dir.glob("*.d.ts")
        for cap in re.findall(
            r"@syscap\s+(SystemCapability\.[A-Za-z0-9_.]+)",
            path.read_text(encoding="utf-8", errors="ignore"),
        )
    })


def write(name: str, value: object) -> None:
    target = root / name
    target.parent.mkdir(parents=True, exist_ok=True)
    text = value if isinstance(value, str) else json.dumps(value, indent=2)
    target.write_text(text, encoding="utf-8")


write(
    "AppScope/app.json5",
    {
        "app": {
            "bundleName": bundle,
            "vendor": "harmony-contrib",
            "versionCode": 1,
            "versionName": "1.0.0",
            "icon": "$media:icon",
            "label": "$string:app_name",
        }
    },
)
write(
    "AppScope/resources/base/element/string.json",
    {"string": [{"name": "app_name", "value": "Capability audit"}]},
)
write(
    "AppScope/resources/base/media/icon.svg",
    '<svg xmlns="http://www.w3.org/2000/svg" width="128" height="128"><rect width="128" height="128" fill="#7a32a8"/></svg>',
)
write(
    "build-profile.json5",
    {
        "app": {
            "products": [
                {
                    "name": "default",
                    "targetSdkVersion": "7.0.0(26)",
                    "compatibleSdkVersion": "5.0.5(17)",
                    "runtimeOS": "HarmonyOS",
                }
            ],
            "buildModeSet": [{"name": "debug"}, {"name": "release"}],
        },
        "modules": [
            {
                "name": "entry",
                "srcPath": "./entry",
                "targets": [{"name": "default", "applyToProducts": ["default"]}],
            }
        ],
    },
)
write(
    "oh-package.json5",
    {"modelVersion": "6.0.0", "name": "capability-audit", "version": "1.0.0", "dependencies": {}},
)
write(
    "entry/oh-package.json5",
    {"modelVersion": "6.0.0", "name": "entry", "version": "1.0.0", "dependencies": {}},
)
write(
    "entry/build-profile.json5",
    {
        "apiType": "stageMode",
        "buildOption": {"externalNativeOptions": {"abiFilters": [abi]}},
        "targets": [{"name": "default"}],
    },
)
write(
    "entry/src/main/module.json5",
    {
        "module": {
            "name": "entry",
            "type": "entry",
            "mainElement": "EntryAbility",
            "deviceTypes": ["phone", "2in1"],
            "deliveryWithInstall": True,
            "installationFree": False,
            "pages": "$profile:main_pages",
            "requestPermissions": [
                {"name": "ohos.permission.CAMERA", "reason": "$string:permission_reason", "usedScene": {"abilities": ["EntryAbility"], "when": "inuse"}},
                {"name": "ohos.permission.ACCELEROMETER", "reason": "$string:permission_reason", "usedScene": {"abilities": ["EntryAbility"], "when": "inuse"}},
                {"name": "ohos.permission.GYROSCOPE", "reason": "$string:permission_reason", "usedScene": {"abilities": ["EntryAbility"], "when": "inuse"}},
                {"name": "ohos.permission.ACCESS_BLUETOOTH", "reason": "$string:permission_reason", "usedScene": {"abilities": ["EntryAbility"], "when": "inuse"}},
                {"name": "ohos.permission.LOCATION", "reason": "$string:permission_reason", "usedScene": {"abilities": ["EntryAbility"], "when": "inuse"}},
                {"name": "ohos.permission.APPROXIMATELY_LOCATION", "reason": "$string:permission_reason", "usedScene": {"abilities": ["EntryAbility"], "when": "inuse"}},
                {"name": "ohos.permission.GET_NETWORK_INFO"},
                {"name": "ohos.permission.INTERNET"},
                {"name": "ohos.permission.GET_WIFI_INFO"},
                {"name": "ohos.permission.APP_TRACKING_CONSENT", "reason": "$string:permission_reason", "usedScene": {"abilities": ["EntryAbility"], "when": "inuse"}},
                {"name": "ohos.permission.ACCESS_BIOMETRIC", "reason": "$string:permission_reason", "usedScene": {"abilities": ["EntryAbility"], "when": "inuse"}},
                {"name": "ohos.permission.VIBRATE"},
                {"name": "ohos.permission.MANAGE_INPUT_INFRARED_EMITTER"},
                {"name": "ohos.permission.PRINT", "reason": "$string:permission_reason", "usedScene": {"abilities": ["EntryAbility"], "when": "inuse"}},
            ],
            "abilities": [
                {
                    "name": "EntryAbility",
                    "srcEntry": "./ets/entryability/EntryAbility.ets",
                    "exported": True,
                    "label": "$string:app_name",
                    "icon": "$media:icon",
                    "startWindowIcon": "$media:icon",
                    "startWindowBackground": "$color:background",
                }
            ],
        }
    },
)
write(
    "entry/src/main/resources/base/element/string.json",
    {"string": [{"name": "permission_reason", "value": "Validate emulator capability behavior"}]},
)
write(
    "entry/src/main/resources/base/element/color.json",
    {"color": [{"name": "background", "value": "#ffffff"}]},
)
write("entry/src/main/resources/base/profile/main_pages.json", {"src": ["pages/Index"]})
entry_ability = """import { UIAbility } from '@kit.AbilityKit';
import window from '@ohos.window';
import infraredEmitter from '@ohos.multimodalInput.infraredEmitter';
import thermal from '@ohos.thermal';
import usbManager from '@ohos.usbManager';
import usbSerial from '@ohos.usbManager.serial';
import audio from '@ohos.multimedia.audio';
import settings from '@ohos.settings';
import connection from '@ohos.net.connection';
import mdns from '@ohos.net.mdns';
import identifier from '@ohos.identifier.oaid';
import deviceInfo from '@ohos.deviceInfo';
import { userAuth } from '@kit.UserAuthenticationKit';
import selectionManager from '@ohos.selectionInput.selectionManager';
import pipWindow from '@ohos.PiPWindow';
import floatingBall from '@ohos.window.floatingBall';
import floatView from '@ohos.window.floatView';
import printManager from '@ohos.print';
import i18n from '@ohos.i18n';
import probe from 'libcapabilityprobe.so';
const PUBLIC_OHOS_MODULES: string[] = __API_MODULES__;
const PUBLIC_SYSCAPS: string[] = __PUBLIC_SYSCAPS__;
export default class EntryAbility extends UIAbility {
  onWindowStageCreate(stage: window.WindowStage): void {
    stage.loadContent('pages/Index');
    probe.run();
    this.runArkTsProbes();
  }

  private report(name: string, value: string): void {
    probe.append(name + '=' + value);
  }

  private errorText(error: object): string {
    return error.toString() + ':' + JSON.stringify(error);
  }

  private async runArkTsProbes(): Promise<void> {
    let enabledSysCaps: number = 0;
    for (let index = 0; index < PUBLIC_SYSCAPS.length; index++) {
      const enabled = canIUse(PUBLIC_SYSCAPS[index]);
      if (enabled) {
        enabledSysCaps++;
      }
      this.report('syscap.canIUse.' + PUBLIC_SYSCAPS[index], enabled.toString());
    }
    this.report('syscap.canIUse.summary', 'enabled:' + enabledSysCaps.toString() + ',total:' + PUBLIC_SYSCAPS.length.toString());
    try {
      const oaid = await identifier.getOAID();
      this.report('advertising.oaid.result', oaid);
    } catch (error) {
      this.report('advertising.oaid.error', this.errorText(error));
    }
    try {
      const discovery = mdns.createDiscoveryService(this.context, '_http._tcp');
      discovery.startSearchingMDNS();
      this.report('network.mdns.discovery.result', 'started:true');
      discovery.stopSearchingMDNS();
    } catch (error) {
      this.report('network.mdns.discovery.error', this.errorText(error));
    }
    try {
      const addresses = await connection.getAddressesByName('localhost');
      this.report('network.dns.localhost.result', JSON.stringify(addresses));
      const externalAddresses = await connection.getAddressesByName('example.com');
      this.report('network.dns.external.result', JSON.stringify(externalAddresses));
    } catch (error) {
      this.report('network.dns.localhost.error', this.errorText(error));
    }
    try {
      this.report('device.info.type.result', deviceInfo.deviceType);
      this.report('device.info.product_model.result', deviceInfo.productModel);
    } catch (error) {
      this.report('device.info.error', this.errorText(error));
    }
    try {
      userAuth.getAvailableStatus(
        userAuth.UserAuthType.FINGERPRINT,
        userAuth.AuthTrustLevel.ATL1
      );
      this.report('useriam.fingerprint.available_status.result', 'available:true');
    } catch (error) {
      this.report('useriam.fingerprint.available_status.error', this.errorText(error));
    }
    try {
      const brightnessKey = settings.display.SCREEN_BRIGHTNESS_STATUS;
      const brightnessUri = settings.getUriSync(brightnessKey);
      const brightness = settings.getValueSync(this.context, brightnessKey, '__audit_default__');
      this.report('settings.brightness.uri', brightnessUri);
      this.report('settings.brightness.sync', brightness);
      this.report('settings.brightness.async', await settings.getValue(this.context, brightnessKey));
    } catch (error) {
      this.report('settings.brightness.error', this.errorText(error));
    }
    try {
      const timeFormat = settings.getValueSync(this.context, settings.date.TIME_FORMAT, '__audit_default__');
      this.report('settings.time_format.sync', timeFormat);
    } catch (error) {
      this.report('settings.time_format.error', this.errorText(error));
    }
    try {
      this.report('thermal.level.result', thermal.getLevel().toString());
    } catch (error) {
      this.report('thermal.level.error', this.errorText(error));
    }
    try {
      const devices = usbManager.getDevices();
      this.report('usb.devices.result', 'count:' + devices.length.toString());
    } catch (error) {
      this.report('usb.devices.error', this.errorText(error));
    }
    try {
      const accessories = usbManager.getAccessoryList();
      this.report('usb.accessories.result', 'count:' + accessories.length.toString());
    } catch (error) {
      this.report('usb.accessories.error', this.errorText(error));
    }
    try {
      const ports = usbSerial.getPortList();
      this.report('usb.serial.ports.result', 'count:' + ports.length.toString());
    } catch (error) {
      this.report('usb.serial.ports.error', this.errorText(error));
    }
    try {
      const enhanceManager = audio.getAudioManager().getDeviceEnhanceManager();
      this.report('audio.device_enhance.manager', 'created:true');
      this.report('audio.device_enhance.supported', enhanceManager.isEnhancedRoutingSupported().toString());
    } catch (error) {
      this.report('audio.device_enhance.error', this.errorText(error));
    }
    try {
      const frequencies = infraredEmitter.getInfraredFrequencies();
      this.report('infrared.frequencies.result', JSON.stringify(frequencies));
    } catch (error) {
      this.report('infrared.frequencies.error', this.errorText(error));
    }
    try {
      const hasEmitter = await infraredEmitter.hasIrEmitter();
      this.report('infrared.has_emitter.result', hasEmitter.toString());
    } catch (error) {
      this.report('infrared.has_emitter.error', this.errorText(error));
    }
    try {
      const selectionListener = (info: selectionManager.SelectionInfo): void => {
        this.report('selection.completed.callback', JSON.stringify(info));
      };
      selectionManager.on('selectionCompleted', selectionListener);
      this.report('selection.listener.result', 'registered:true');
      selectionManager.off('selectionCompleted', selectionListener);
      this.report('selection.listener.stop', 'success:true');
    } catch (error) {
      this.report('selection.listener.error', this.errorText(error));
    }
    try {
      const content = await selectionManager.getSelectionContent();
      this.report('selection.content.result', JSON.stringify(content));
    } catch (error) {
      this.report('selection.content.error', this.errorText(error));
    }
    try {
      this.report('window.pip.enabled', pipWindow.isPiPEnabled().toString());
      this.report('window.floating_ball.enabled', floatingBall.isFloatingBallEnabled().toString());
      this.report('window.float_view.enabled', floatView.isFloatViewEnabled().toString());
    } catch (error) {
      this.report('window.session_features.error', this.errorText(error));
    }
    try {
      await printManager.startDiscoverPrinter([]);
      this.report('print.discovery.result', 'started:true');
      await printManager.stopDiscoverPrinter();
      this.report('print.discovery.stop', 'success:true');
    } catch (error) {
      this.report('print.discovery.error', this.errorText(error));
    }
    try {
      this.report('i18n.system_language.result', i18n.getSystemLanguage());
      this.report('i18n.system_region.result', i18n.getSystemRegion());
      this.report('i18n.system_locale.result', i18n.getSystemLocale());
    } catch (error) {
      this.report('i18n.system.error', this.errorText(error));
    }
    let loaded: number = 0;
    for (let index = 0; index < PUBLIC_OHOS_MODULES.length; index++) {
      if (probe.loadModule(PUBLIC_OHOS_MODULES[index]) === 0) {
        loaded++;
      }
    }
    this.report('module.load.summary', 'loaded:' + loaded.toString() + ',total:' + PUBLIC_OHOS_MODULES.length.toString());
    this.report('SUMMARY_ARKTS', 'complete:1');
  }
}
"""
write(
    "entry/src/main/ets/entryability/EntryAbility.ets",
    entry_ability.replace("__API_MODULES__", json.dumps(api_modules)).replace(
        "__PUBLIC_SYSCAPS__", json.dumps(public_syscaps)
    ),
)
write(
    "entry/src/main/ets/pages/Index.ets",
    '@Entry\n@Component\nstruct Index { build() { Column() { Text("Capability audit") } } }\n',
)

libs = root / "entry/libs" / abi
libs.mkdir(parents=True, exist_ok=True)
native = args.sdk / "native"
command = [
    str(native / "llvm/bin/clang++"),
    "--target=" + triple,
    "--sysroot=" + str(native / "sysroot"),
    "-std=c++17",
    "-shared",
    "-fPIC",
    "-O2",
    "-Wall",
    "-Wextra",
    "-Werror",
    str(Path(__file__).with_name("hap_probe.cpp").resolve()),
    "-lace_napi.z",
    "-lohbattery_info",
    "-lbluetooth_ndk",
    "-lwifi_ndk",
    "-llocation_ndk",
    "-lnet_connection",
    "-lohaudio",
    "-lohcamera",
    "-lohsensor",
    "-lohvibrator.z",
    "-ltelephony_radio",
    "-lnative_display_manager",
    "-o",
    str(libs / "libcapabilityprobe.so"),
]
if args.arch == "armv7a":
    command[1:1] = ["-march=armv7-a", "-mfloat-abi=softfp", "-mfpu=neon"]
subprocess.run(command, check=True)
shutil.copy2(native / "llvm/lib" / triple / "libc++_shared.so", libs / "libc++_shared.so")

environment = dict(os.environ, OHOS_SDK_HOME=str(args.sdk))
subprocess.run(
    [args.arkdown, "build", "--project", str(root), "--target", "hap", "--mode", "debug"],
    cwd=root,
    env=environment,
    check=True,
)
output = root / "entry/build/default/outputs/default"
subprocess.run(
    [
        args.hap_sign,
        "sign",
        str(output / "entry-default-unsigned.hap"),
        "--bundle-name",
        bundle,
        "--compatible-version",
        "17",
        "--device-id",
        args.udid,
        "--output",
        str(output / "entry-default-signed.hap"),
        "--force",
    ],
    check=True,
)
print(output / "entry-default-signed.hap")
