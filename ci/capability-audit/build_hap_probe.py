#!/usr/bin/env python3
"""Build the app-context capability probe for a booted audit guest."""

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import uuid


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--arch", choices=("arm64", "armv7a", "x86_64"), default="arm64")
parser.add_argument(
    "--sdk",
    type=Path,
    default=Path("/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony"),
)
parser.add_argument("--arkdown", default=os.environ.get("ARKDOWN", "arkdown"))
parser.add_argument("--hap-sign", default=os.environ.get("HAP_SIGN", "hap-sign"))
parser.add_argument("--apl", default="system_basic")
parser.add_argument(
    "--app-feature",
    choices=("normal", "system"),
    default="normal",
    help="Provisioning-profile application feature; use system for system-API probes",
)
parser.add_argument(
    "--restricted-permission",
    action="append",
    default=[
        "ohos.permission.READ_PASTEBOARD",
        "ohos.permission.READ_CONTACTS",
        "ohos.permission.WRITE_CONTACTS",
    ],
)
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
parser.add_argument(
    "--provider-only",
    action="store_true",
    help="Run only provider-backed UI probes so lifecycle deadlines do not hide provider failures",
)
parser.add_argument(
    "--web-only",
    action="store_true",
    help="Run only the staged ArkWeb execution probe with no unrelated API imports",
)
parser.add_argument("--vulkan-window-only", action="store_true",
                    help="Present Vulkan frames into a real ArkUI XComponent; requires host screenshot validation")
parser.add_argument("--i18n-only", action="store_true",
                    help="Test bundled timezone, locale and phone metadata in a normal application")
parser.add_argument("--matrix4-only", action="store_true",
                    help="Test actual typed module-level Matrix4 helpers and existing factory-object arithmetic")
parser.add_argument("--factory-objects-only", action="store_true",
                    help="Test real resource and live TaskPool factory-returned SDK types, without constructor shims")
parser.add_argument("--web-factory-only", action="store_true",
                    help="Test real ArkWeb body streams, response handlers and native media callback objects")
parser.add_argument("--userid-only", action="store_true",
                    help="Test real AppSpawn account tagging and ordinary-app ioctl denial")
parser.add_argument("--audio-stream-only", action="store_true",
                    help="Test normal-app OHAudio renderer PCM callbacks, states and recreation")
parser.add_argument("--avc-media-only", action="store_true",
                    help="Test ordinary-app software AVC encode/decode pixels, timestamps, IDR and EOS")
parser.add_argument("--audio-suite-effects-only", action="store_true",
                    help="Test ordinary-app public AudioSuite pipelines and real three-effect PCM responses")
parser.add_argument("--camera-only", action="store_true",
                    help="Test ordinary-app public Camera C++/ArkTS preview, photo pixels and recreation")
parser.add_argument("--const-enum-only", action="store_true",
                    help="Compile and run every baseline const-enum member using the real API26 SDK")
parser.add_argument("--arkts-exports-only", action="store_true",
                    help="Collect real all-own NAPI properties/types for every original export/load gap module")
parser.add_argument("--contact-sync-mode-only", action="store_true",
                    help="Read real API26 ContactSyncMode, DeviceBlockStatus and FusionAssetType values through typed/native calls")
parser.add_argument("--runtime-enum-only", action="store_true",
                    help="Collect all original regular enums using typed and independent actual NAPI member reads")
parser.add_argument('--curve-only', action='store_true',
                    help='Verify actual ambient Curve strings and real factory interpolation')
parser.add_argument('--binding-only', action='store_true',
                    help='Verify actual public UIUtils Binding/MutableBinding factory returns and exceptions')
parser.add_argument('--storage-stats-only', action='store_true',
                    help='Verify ordinary private data/cache statistics and privileged-query denial')
parser.add_argument('--completion-handler-only', action='store_true',
                    help='Verify the actual SDK completion handler constructor and callback fields')
parser.add_argument('--thermal-only', action='store_true',
                    help='Observe real thermal initial callbacks and four subscription lifetimes; no heat emulation')
parser.add_argument('--wifi-scan-only', action='store_true',
                    help='Observe actual ordinary Wi-Fi scan callbacks; does not prove association or AP/P2P')
parser.add_argument('--image-metadata-only', action='store_true',
                    help='Read actual DNG/TIFF/AVIS factory metadata from pinned upstream fixtures')
parser.add_argument('--image-metadata-fixtures', type=Path)
parser.add_argument('--photos-recent-only', action='store_true',
                    help='Verify actual Photos metadata defaults, immutable options and picker parameter rejection')
parser.add_argument('--photos-asset-only', action='store_true',
                    help='Verify real ordinary-app photo creation, consent, preselected picker and JPEG pixel readback')
parser.add_argument('--settings-navigation-only', action='store_true',
                    help='Build ordinary public Settings callers; host UI verification is required separately')
parser.add_argument('--optional-phone-profile-only', action='store_true',
                    help='Verify ordinary dynamic discovery of four outside-official-phone false declarations')
parser.add_argument("--enum-device", choices=('phone', '2in1'), default='phone')
parser.add_argument("--worker-legacy-only", action="store_true",
                    help="Validate parentPort inside actual legacy Worker threads, in a separate HAP process")
parser.add_argument("--worker-thread-only", action="store_true",
                    help="Validate workerPort inside actual ThreadWorker threads, in a separate HAP process")
parser.add_argument("--probe-run-id", help="Host challenge (32 lowercase hex digits) for a nonce-bearing ordinary HAP")
args = parser.parse_args()
args.sdk = args.sdk.resolve()
worker_only = args.worker_legacy_only or args.worker_thread_only
dedicated_contract_only = args.curve_only or args.binding_only or args.storage_stats_only or args.optional_phone_profile_only or args.photos_recent_only or args.photos_asset_only or args.settings_navigation_only
dedicated_contract_only = dedicated_contract_only or args.completion_handler_only or args.thermal_only
dedicated_contract_only = dedicated_contract_only or args.image_metadata_only or args.wifi_scan_only
if args.probe_run_id is not None and (not (args.userid_only or args.i18n_only or args.matrix4_only or args.factory_objects_only or args.web_factory_only or args.audio_stream_only or args.avc_media_only or args.audio_suite_effects_only or args.camera_only or args.const_enum_only or args.arkts_exports_only or worker_only or args.contact_sync_mode_only or args.runtime_enum_only or dedicated_contract_only) or
                                     not re.fullmatch(r"[0-9a-f]{32}", args.probe_run_id)):
    parser.error("--probe-run-id requires a nonce-bearing ordinary persona and exactly 32 lowercase hex digits")
if sum((args.wifi_scan_only, args.image_metadata_only, args.thermal_only, args.completion_handler_only, args.provider_only, args.web_only, args.vulkan_window_only, args.i18n_only, args.matrix4_only, args.factory_objects_only, args.web_factory_only,
        args.userid_only, args.audio_stream_only, args.avc_media_only, args.audio_suite_effects_only, args.camera_only, args.const_enum_only, args.arkts_exports_only, args.worker_legacy_only, args.worker_thread_only, args.contact_sync_mode_only, args.runtime_enum_only, args.curve_only, args.binding_only, args.storage_stats_only, args.optional_phone_profile_only, args.photos_recent_only, args.photos_asset_only, args.settings_navigation_only)) > 1:
    parser.error("provider and ordinary probe personas are mutually exclusive")
if args.image_metadata_only and args.image_metadata_fixtures is None:
    parser.error('--image-metadata-only requires --image-metadata-fixtures')
minimal_app = args.web_only or args.vulkan_window_only or args.i18n_only or args.matrix4_only or args.factory_objects_only or args.web_factory_only or args.userid_only or args.audio_stream_only or args.avc_media_only or args.audio_suite_effects_only or args.camera_only or args.const_enum_only or args.arkts_exports_only or worker_only or args.contact_sync_mode_only or args.runtime_enum_only or dedicated_contract_only
if args.optional_phone_profile_only and args.enum_device != 'phone':
    parser.error('optional-phone-profile cannot exempt official 2in1 capabilities')
if minimal_app:
    args.restricted_permission = []

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
                    "compatibleSdkVersion": "7.0.0(26)" if (args.const_enum_only or args.arkts_exports_only or args.factory_objects_only or args.web_factory_only or worker_only or args.contact_sync_mode_only or args.runtime_enum_only or dedicated_contract_only) else "5.0.5(17)",
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
                {"name": "ohos.permission.READ_PASTEBOARD", "reason": "$string:permission_reason", "usedScene": {"abilities": ["EntryAbility"], "when": "inuse"}},
                {"name": "ohos.permission.READ_CONTACTS", "reason": "$string:permission_reason", "usedScene": {"abilities": ["EntryAbility"], "when": "inuse"}},
                {"name": "ohos.permission.WRITE_CONTACTS", "reason": "$string:permission_reason", "usedScene": {"abilities": ["EntryAbility"], "when": "inuse"}},
                {"name": "ohos.permission.READ_CALENDAR", "reason": "$string:permission_reason", "usedScene": {"abilities": ["EntryAbility"], "when": "inuse"}},
                {"name": "ohos.permission.WRITE_CALENDAR", "reason": "$string:permission_reason", "usedScene": {"abilities": ["EntryAbility"], "when": "inuse"}},
                {"name": "ohos.permission.GET_BUNDLE_INFO_PRIVILEGED"},
                {"name": "ohos.permission.GET_BUNDLE_RESOURCES"},
                {"name": "ohos.permission.CONNECTIVITY_INTERNAL"},
                {"name": "ohos.permission.STORAGE_MANAGER"},
                {"name": "ohos.permission.MOUNT_UNMOUNT_MANAGER"},
                {"name": "ohos.permission.NOTIFICATION_CONTROLLER"},
                {"name": "ohos.permission.PUBLISH_AGENT_REMINDER"},
                {"name": "ohos.permission.DEVICE_STANDBY_EXEMPTION"},
                {"name": "ohos.permission.GET_DISPOSED_APP_STATUS"},
                {"name": "ohos.permission.READ_HIVIEW_SYSTEM"},
                {"name": "ohos.permission.ACCESS_CERT_MANAGER"},
                {"name": "ohos.permission.ACCESS_CERT_MANAGER_INTERNAL"},
                {"name": "ohos.permission.INPUT_MONITORING"},
                {"name": "ohos.permission.GET_APP_DOMAIN_BUNDLE_INFO"},
                {"name": "ohos.permission.MANAGE_MEDIA_RESOURCES"},
                {"name": "ohos.permission.QUERY_SECURITY_MODEL_RESULT"},
                {"name": "ohos.permission.GET_DONOTDISTURB_STATE", "reason": "$string:permission_reason", "usedScene": {"abilities": ["EntryAbility"], "when": "inuse"}},
                {"name": "ohos.permission.FILE_ACCESS_MANAGER", "reason": "$string:permission_reason", "usedScene": {"abilities": ["EntryAbility"], "when": "inuse"}},
                {"name": "ohos.permission.READ_IMAGEVIDEO", "reason": "$string:permission_reason", "usedScene": {"abilities": ["EntryAbility"], "when": "inuse"}},
                {"name": "ohos.permission.KEEP_BACKGROUND_RUNNING", "reason": "$string:permission_reason", "usedScene": {"abilities": ["EntryAbility"], "when": "inuse"}},
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
                    "backgroundModes": ["dataTransfer"],
                }
            ],
        }
    },
)
if minimal_app:
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
                "requestPermissions": ([{"name": "ohos.permission.CAMERA", "reason": "$string:permission_reason",
                                         "usedScene": {"abilities": ["EntryAbility"], "when": "inuse"}}]
                                       if args.camera_only else [{"name": "ohos.permission.GET_WIFI_INFO"},
                                                                 {"name": "ohos.permission.SET_WIFI_INFO"}]
                                       if args.wifi_scan_only else [] if (args.const_enum_only or args.arkts_exports_only or args.matrix4_only or args.factory_objects_only or args.web_factory_only or worker_only or args.contact_sync_mode_only or args.runtime_enum_only) else [] if dedicated_contract_only else [{"name": "ohos.permission.INTERNET"}]),
                "abilities": [{
                    "name": "EntryAbility",
                    "srcEntry": "./ets/entryability/EntryAbility.ets",
                    "exported": True,
                    "label": "$string:app_name",
                    "icon": "$media:icon",
                    "startWindowIcon": "$media:icon",
                    "startWindowBackground": "$color:background",
                }],
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
entry_ability = """import { UIAbility, common } from '@kit.AbilityKit';
import { photoAccessHelper } from '@kit.MediaLibraryKit';
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
import ranging from '@ohos.FusionConnectivity.ranging';
import partnerAgent from '@ohos.FusionConnectivity.partnerAgent';
import { huks } from '@kit.UniversalKeystoreKit';
import fs from '@ohos.file.fs';
import preferences from '@ohos.data.preferences';
import cryptoFramework from '@ohos.security.cryptoFramework';
import bundleManager from '@ohos.bundle.bundleManager';
import notificationManager from '@ohos.notificationManager';
import emitter from '@ohos.events.emitter';
import pasteboard from '@ohos.pasteboard';
import power from '@ohos.power';
import commonEventManager from '@ohos.commonEventManager';
import systemDateTime from '@ohos.systemDateTime';
import wallpaper from '@ohos.wallpaper';
import inputDevice from '@ohos.multimodalInput.inputDevice';
import image from '@ohos.multimedia.image';
import appAccount from '@ohos.account.appAccount';
import relationalStore from '@ohos.data.relationalStore';
import contact from '@ohos.contact';
import calendarManager from '@ohos.calendarManager';
import distributedKVStore from '@ohos.data.distributedKVStore';
import environment from '@ohos.file.environment';
import zlib from '@ohos.zlib';
import hiAppEvent from '@ohos.hiviewdfx.hiAppEvent';
import hichecker from '@ohos.hichecker';
import avSession from '@ohos.multimedia.avsession';
import backgroundTaskManager from '@ohos.resourceschedule.backgroundTaskManager';
import startupManager from '@ohos.app.appstartup.startupManager';
import quickFixManager from '@ohos.app.ability.quickFixManager';
import formHost from '@ohos.app.form.formHost';
import defaultAppManager from '@ohos.bundle.defaultAppManager';
import launcherBundleManager from '@ohos.bundle.launcherBundleManager';
import bundleResourceManager from '@ohos.bundle.bundleResourceManager';
import overlay from '@ohos.bundle.overlay';
import netSharing from '@ohos.net.sharing';
import configPolicy from '@ohos.configPolicy';
import customConfig from '@ohos.customization.customConfig';
import systemCapability from '@ohos.systemCapability';
import volumeManager from '@ohos.file.volumeManager';
import reminderAgentManager from '@ohos.reminderAgentManager';
import deviceStandby from '@ohos.resourceschedule.deviceStandby';
import systemLoad from '@ohos.resourceschedule.systemload';
import workScheduler from '@ohos.resourceschedule.workScheduler';
import brightness from '@ohos.brightness';
import drm from '@ohos.multimedia.drm';
import media from '@ohos.multimedia.media';
import screenLockFileManager from '@ohos.ability.screenLockFileManager';
import deviceAttest from '@ohos.deviceAttest';
import hiSysEvent from '@ohos.hiSysEvent';
import uiAppearance from '@ohos.uiAppearance';
import appDomainVerify from '@ohos.bundle.appDomainVerify';
import appControl from '@ohos.bundle.appControl';
import hiRetrieval from '@ohos.hiviewdfx.hiRetrieval';
import faultLogger from '@ohos.faultLogger';
import logLibrary from '@ohos.logLibrary';
import batteryStatistics from '@ohos.batteryStatistics';
import colorSpaceManager from '@ohos.graphics.colorSpaceManager';
import pointer from '@ohos.multimodalInput.pointer';
import shortKey from '@ohos.multimodalInput.shortKey';
import inputConsumer from '@ohos.multimodalInput.inputConsumer';
import inputMonitor from '@ohos.multimodalInput.inputMonitor';
import audioHaptic from '@ohos.multimedia.audioHaptic';
import certificateManager from '@ohos.security.certManager';
import certificateManagerDialog from '@ohos.security.certManagerDialog';
import cloudSync from '@ohos.file.cloudSync';
import adminManager from '@ohos.enterprise.adminManager';
import securityGuard from '@ohos.security.securityGuard';
import intelligentScene from '@ohos.intelligentScene';
import router from '@ohos.router';
import fileAccess from '@ohos.file.fileAccess';
import picker from '@ohos.file.picker';
import userFileManager from '@ohos.filemanagement.userFileManager';
import cert from '@ohos.security.cert';
import request from '@ohos.request';
import { Driver } from '@ohos.UiTest';
import { PerfMetric, PerfTest, PerfTestStrategy } from '@ohos.test.PerfTest';
import accessibility from '@ohos.accessibility';
import { Scene } from '@kit.ArkGraphics3D';
import { asset } from '@kit.AssetStoreKit';
import { util } from '@kit.ArkTS';
import probe from 'libcapabilityprobe.so';
const PUBLIC_OHOS_MODULES: string[] = __API_MODULES__;
const PUBLIC_SYSCAPS: string[] = __PUBLIC_SYSCAPS__;
export default class EntryAbility extends UIAbility {
  onWindowStageCreate(stage: window.WindowStage): void {
    stage.loadContent('pages/Index');
    try {
      fs.unlinkSync(this.context.filesDir + '/capability-results.log');
    } catch (_) {
      // A fresh install or the first run has no previous result file.
    }
    // Provider-backed UI calls must run before the native breadth probe.  On
    // slower emulator profiles the synchronous native probe can consume the
    // UIAbility lifecycle deadline and the process is terminated before these
    // calls are reached.
    this.runProviderUiProbes();
__BREADTH_PROBE_CALLS__
  }

  private runProviderUiProbes(): void {
    try {
      const castPicker = new avSession.AVCastPickerHelper(this.context);
      this.report('media.avcast_picker.immediate_invoked', 'true');
      castPicker.select().then((): void => {
        this.report('media.avcast_picker.immediate_result', 'success:true');
      }).catch((error: object): void => {
        this.report('media.avcast_picker.immediate_error', this.errorText(error));
      });
    } catch (error) {
      this.report('media.avcast_picker.immediate_error', this.errorText(error));
    }
  }

  private report(name: string, value: string): void {
    probe.append(name + '=' + value);
  }

  private errorText(error: object): string {
    return error.toString() + ':' + JSON.stringify(error);
  }

  private async runHuksProbe(): Promise<void> {
    try {
      this.report('security.huks.step', 'setup.begin');
      const keyAlias = 'ohos-qemu-capability-audit-key';
      const keyOptions: huks.HuksOptions = {
        properties: [
          { tag: huks.HuksTag.HUKS_TAG_ALGORITHM, value: huks.HuksKeyAlg.HUKS_ALG_AES },
          { tag: huks.HuksTag.HUKS_TAG_PURPOSE,
            value: huks.HuksKeyPurpose.HUKS_KEY_PURPOSE_ENCRYPT | huks.HuksKeyPurpose.HUKS_KEY_PURPOSE_DECRYPT },
          { tag: huks.HuksTag.HUKS_TAG_KEY_SIZE, value: huks.HuksKeySize.HUKS_AES_KEY_SIZE_256 }
        ],
        inData: new Uint8Array([])
      };
      this.report('security.huks.step', 'setup.end');
      this.report('security.huks.step', 'has_key.begin');
      const existed = await huks.hasKeyItem(keyAlias, { properties: [] });
      this.report('security.huks.step', 'has_key.end:' + existed.toString());
      if (existed) {
        await huks.deleteKeyItem(keyAlias, { properties: [] });
        this.report('security.huks.step', 'preexisting_key.deleted');
      }
      this.report('security.huks.step', 'generate.begin');
      await huks.generateKeyItem(keyAlias, keyOptions);
      this.report('security.huks.step', 'generate.end');
      const present = await huks.hasKeyItem(keyAlias, { properties: [] });
      this.report('security.huks.key_lifecycle', 'generated:true,present:' + present.toString());
      await huks.deleteKeyItem(keyAlias, { properties: [] });
      this.report('security.huks.key_deleted', 'true');
    } catch (error) {
      this.report('security.huks.error', this.errorText(error));
    }
  }

  private async runCoreSoftwareProbes(): Promise<void> {
    const auditValue = 'ohos-qemu-capability-audit';
    try {
      const filePath = this.context.filesDir + '/capability-audit.txt';
      const file = fs.openSync(filePath, fs.OpenMode.READ_WRITE | fs.OpenMode.CREATE);
      fs.writeSync(file.fd, auditValue);
      fs.closeSync(file);
      const value = fs.readTextSync(filePath);
      fs.unlinkSync(filePath);
      this.report('file.io.lifecycle', 'value:' + value + ',removed:true');
    } catch (error) {
      this.report('file.io.error', this.errorText(error));
    }
    try {
      const store = await preferences.getPreferences(this.context, 'capability-audit');
      await store.put('probe', auditValue);
      await store.flush();
      const value = await store.get('probe', 'missing');
      await store.delete('probe');
      await store.flush();
      this.report('data.preferences.lifecycle', 'value:' + value.toString() + ',removed:true');
    } catch (error) {
      this.report('data.preferences.error', this.errorText(error));
    }
    try {
      const random = cryptoFramework.createRandom();
      const randomValue = await random.generateRandom(32);
      const md = cryptoFramework.createMd('SHA256');
      await md.update({ data: new Uint8Array([97, 117, 100, 105, 116]) });
      const digest = await md.digest();
      this.report('security.crypto.lifecycle',
        'random:' + randomValue.data.length.toString() + ',sha256:' + digest.data.length.toString());
    } catch (error) {
      this.report('security.crypto.error', this.errorText(error));
    }
    try {
      const info = await bundleManager.getBundleInfoForSelf(0);
      this.report('bundle.self.result', info.name + ':' + info.versionName);
    } catch (error) {
      this.report('bundle.self.error', this.errorText(error));
    }
    try {
      const enabled = await notificationManager.isNotificationEnabled();
      this.report('notification.enabled.result', enabled.toString());
    } catch (error) {
      this.report('notification.enabled.error', this.errorText(error));
    }
    try {
      const event: emitter.InnerEvent = { eventId: 19491, priority: emitter.EventPriority.IMMEDIATE };
      let callbackCount: number = 0;
      const callback = (data: emitter.EventData): void => {
        callbackCount++;
        this.report('notification.emitter.callback', JSON.stringify(data));
      };
      emitter.on(event, callback);
      emitter.emit(event, { data: { value: auditValue } });
      await new Promise<void>((resolve) => setTimeout(resolve, 2000));
      emitter.off(19491, callback);
      this.report('notification.emitter.lifecycle', 'callbacks:' + callbackCount.toString());
    } catch (error) {
      this.report('notification.emitter.error', this.errorText(error));
    }
    try {
      const board = pasteboard.getSystemPasteboard();
      await board.setData(pasteboard.createPlainTextData(auditValue));
      const data = await board.getData();
      const value = data.getPrimaryText();
      await board.clearData();
      this.report('pasteboard.lifecycle', 'value:' + value + ',cleared:true');
    } catch (error) {
      this.report('pasteboard.error', this.errorText(error));
    }
    try {
      this.report('power.state.result',
        'active:' + power.isActive().toString() +
        ',screen:' + (await power.isScreenOn()).toString() +
        ',mode:' + power.getPowerMode().toString());
    } catch (error) {
      this.report('power.state.error', this.errorText(error));
    }
    try {
      const eventName = 'org.harmonycontrib.capabilityaudit.EVENT';
      const subscriber = await commonEventManager.createSubscriber({ events: [eventName] });
      let callbackCount: number = 0;
      commonEventManager.subscribe(subscriber, (error, data) => {
        if (error) {
          this.report('common_event.callback.error', this.errorText(error));
          return;
        }
        callbackCount++;
        this.report('common_event.callback.result', data.event);
      });
      await new Promise<void>((resolve) => {
        commonEventManager.publish(eventName, (error) => {
          if (error) {
            this.report('common_event.publish.error', this.errorText(error));
          }
          resolve();
        });
      });
      await new Promise<void>((resolve) => setTimeout(resolve, 2000));
      await commonEventManager.unsubscribe(subscriber);
      this.report('common_event.lifecycle', 'published:true,callbacks:' + callbackCount.toString());
    } catch (error) {
      this.report('common_event.error', this.errorText(error));
    }
    try {
      this.report('time.state.result',
        'time:' + systemDateTime.getTime().toString() +
        ',timezone:' + (await systemDateTime.getTimezone()));
    } catch (error) {
      this.report('time.state.error', this.errorText(error));
    }
    try {
      const colors = await wallpaper.getColors(wallpaper.WallpaperType.WALLPAPER_SYSTEM);
      this.report('wallpaper.colors.result', 'count:' + colors.length.toString());
    } catch (error) {
      this.report('wallpaper.colors.error', this.errorText(error));
    }
    try {
      const devices = await inputDevice.getDeviceList();
      this.report('input.devices.result', JSON.stringify(devices));
    } catch (error) {
      this.report('input.devices.error', this.errorText(error));
    }
    try {
      const png = new Uint8Array([
        137, 80, 78, 71, 13, 10, 26, 10, 0, 0, 0, 13, 73, 72, 68, 82,
        0, 0, 0, 1, 0, 0, 0, 1, 8, 6, 0, 0, 0, 31, 21, 196, 137,
        0, 0, 0, 13, 73, 68, 65, 84, 8, 215, 99, 248, 207, 192, 240, 31,
        0, 5, 0, 1, 255, 137, 153, 61, 29, 0, 0, 0, 0, 73, 69, 78, 68,
        174, 66, 96, 130
      ]);
      const source = image.createImageSource(png.buffer);
      const info = await source.getImageInfo();
      const pixelMap = await source.createPixelMap();
      const pixelInfo = await pixelMap.getImageInfo();
      const packer = image.createImagePacker();
      const encoded = await packer.packing(pixelMap, { format: 'image/png', quality: 100 });
      await packer.release();
      await pixelMap.release();
      await source.release();
      this.report('image.codec.lifecycle',
        'source:' + info.size.width.toString() + 'x' + info.size.height.toString() +
        ',pixel:' + pixelInfo.size.width.toString() + 'x' + pixelInfo.size.height.toString() +
        ',encoded:' + encoded.byteLength.toString());
    } catch (error) {
      this.report('image.codec.error', this.errorText(error));
    }
    try {
      const manager = appAccount.createAppAccountManager();
      const name = 'ohos-qemu-capability-audit';
      try {
        await manager.removeAccount(name);
      } catch (_) {
      }
      await manager.createAccount(name);
      const accounts = await manager.getAllAccounts();
      let present: boolean = false;
      for (let index = 0; index < accounts.length; index++) {
        if (accounts[index].name === name) {
          present = true;
        }
      }
      await manager.removeAccount(name);
      this.report('account.app.lifecycle', 'created:' + present.toString() + ',removed:true');
    } catch (error) {
      this.report('account.app.error', this.errorText(error));
    }
    try {
      const config: relationalStore.StoreConfig = {
        name: 'CapabilityAudit.db',
        securityLevel: relationalStore.SecurityLevel.S1
      };
      try {
        await relationalStore.deleteRdbStore(this.context, config);
      } catch (_) {
      }
      const store = await relationalStore.getRdbStore(this.context, config);
      await store.executeSql('CREATE TABLE audit (id INTEGER PRIMARY KEY, value TEXT NOT NULL)');
      await store.executeSql('INSERT INTO audit (id, value) VALUES (?, ?)', [1, auditValue]);
      const result = await store.querySql('SELECT value FROM audit WHERE id = ?', [1]);
      const found = result.goToFirstRow();
      const value = found ? result.getString(result.getColumnIndex('value')) : 'missing';
      result.close();
      await store.close();
      await relationalStore.deleteRdbStore(this.context, config);
      this.report('data.rdb.lifecycle', 'value:' + value + ',removed:true');
    } catch (error) {
      this.report('data.rdb.error', this.errorText(error));
    }
    try {
      const encoder = new util.TextEncoder();
      const alias = encoder.encodeInto('ohos-qemu-capability-audit');
      const secret = encoder.encodeInto('secret-one');
      const updatedSecret = encoder.encodeInto('secret-two');
      const query: asset.AssetMap = new Map();
      query.set(asset.Tag.ALIAS, alias);
      try {
        await asset.remove(query);
      } catch (_) {
      }
      const attributes: asset.AssetMap = new Map();
      attributes.set(asset.Tag.ALIAS, alias);
      attributes.set(asset.Tag.SECRET, secret);
      attributes.set(asset.Tag.ACCESSIBILITY, asset.Accessibility.DEVICE_FIRST_UNLOCKED);
      await asset.add(attributes);
      query.set(asset.Tag.RETURN_TYPE, asset.ReturnType.ALL);
      const initial = await asset.query(query);
      const update: asset.AssetMap = new Map();
      update.set(asset.Tag.SECRET, updatedSecret);
      const updateQuery: asset.AssetMap = new Map();
      updateQuery.set(asset.Tag.ALIAS, alias);
      await asset.update(updateQuery, update);
      const updated = await asset.query(query);
      const value = updated[0].get(asset.Tag.SECRET) as Uint8Array;
      await asset.remove(updateQuery);
      this.report('security.asset.lifecycle',
        'initial:' + initial.length.toString() + ',updated_secret:' + value.length.toString() + ',removed:true');
    } catch (error) {
      this.report('security.asset.error', this.errorText(error));
    }
    try {
      const request: notificationManager.NotificationRequest = {
        id: 19491,
        content: {
          notificationContentType: notificationManager.ContentType.NOTIFICATION_CONTENT_BASIC_TEXT,
          normal: { title: 'Capability audit', text: auditValue }
        }
      };
      await notificationManager.publish(request);
      await notificationManager.cancel(19491);
      this.report('notification.publish.lifecycle', 'published:true,cancelled:true');
    } catch (error) {
      this.report('notification.publish.error', this.errorText(error));
    }
    try {
      const contactInfo: contact.Contact = {
        name: { fullName: 'OHOS QEMU Capability Audit' },
        phoneNumbers: [{ phoneNumber: '10086' }]
      };
      const contactId = await contact.addContact(this.context, contactInfo);
      const contacts = await contact.queryContacts(this.context);
      let key: string = '';
      for (let index = 0; index < contacts.length; index++) {
        if (contacts[index].id === contactId && contacts[index].key !== undefined) {
          key = contacts[index].key as string;
        }
      }
      if (key.length > 0) {
        await contact.deleteContact(this.context, key);
      }
      this.report('contacts.lifecycle',
        'id:' + contactId.toString() + ',found:' + (key.length > 0).toString() + ',removed:' + (key.length > 0).toString());
    } catch (error) {
      this.report('contacts.error', this.errorText(error));
    }
    try {
      const manager = calendarManager.getCalendarManager(this.context);
      const calendar = await manager.createCalendar({
        name: 'ohos-qemu-capability-audit',
        type: calendarManager.CalendarType.LOCAL,
        displayName: 'Capability audit'
      });
      const calendars = await manager.getAllCalendars();
      await manager.deleteCalendar(calendar);
      this.report('calendar.lifecycle', 'count:' + calendars.length.toString() + ',removed:true');
    } catch (error) {
      this.report('calendar.error', this.errorText(error));
    }
  }

  private async runExpandedSoftwareProbes(): Promise<void> {
    const encoder = new util.TextEncoder();
    try {
      const generator = cryptoFramework.createSymKeyGenerator('AES128');
      const key = await generator.generateSymKey();
      const cipher = cryptoFramework.createCipher('AES128|ECB|PKCS7');
      await cipher.init(cryptoFramework.CryptoMode.ENCRYPT_MODE, key, null);
      const encrypted = await cipher.doFinal({ data: encoder.encodeInto('ohos-qemu-capability-audit') });
      const macGenerator = cryptoFramework.createSymKeyGenerator('HMAC');
      const macKey = await macGenerator.convertKey({ data: encoder.encodeInto('12345678abcdefgh') });
      const mac = cryptoFramework.createMac('SHA256');
      await mac.init(macKey);
      await mac.update({ data: encoder.encodeInto('ohos-qemu-capability-audit') });
      const macValue = await mac.doFinal();
      this.report('security.crypto.extended',
        'cipher:' + encrypted.data.length.toString() + ',mac:' + macValue.data.length.toString());
    } catch (error) {
      this.report('security.crypto.extended.error', this.errorText(error));
    }
    try {
      const manager = distributedKVStore.createKVManager({
        bundleName: 'org.harmonycontrib.capabilityaudit',
        context: this.context
      });
      const options: distributedKVStore.Options = {
        createIfMissing: true,
        encrypt: false,
        backup: false,
        autoSync: false,
        kvStoreType: distributedKVStore.KVStoreType.SINGLE_VERSION,
        securityLevel: distributedKVStore.SecurityLevel.S1
      };
      const store = await manager.getKVStore<distributedKVStore.SingleKVStore>('capability_audit', options);
      await store.put('payload', 'ohos-qemu-capability-audit');
      const value: string = (await store.get('payload')).toString();
      await store.delete('payload');
      await manager.closeKVStore('org.harmonycontrib.capabilityaudit', 'capability_audit');
      await manager.deleteKVStore('org.harmonycontrib.capabilityaudit', 'capability_audit');
      this.report('data.kv.lifecycle', 'value:' + value + ',removed:true');
    } catch (error) {
      this.report('data.kv.error', this.errorText(error));
    }
    try {
      const source = this.context.filesDir + '/zlib-source.txt';
      const archive = this.context.filesDir + '/zlib-audit.zip';
      const output = this.context.filesDir + '/zlib-output';
      const sourceFile = fs.openSync(source, fs.OpenMode.READ_WRITE | fs.OpenMode.CREATE);
      fs.writeSync(sourceFile.fd, 'ohos-qemu-capability-audit');
      fs.closeSync(sourceFile);
      await zlib.compressFile(source, archive, {});
      fs.mkdirSync(output);
      await zlib.decompressFile(archive, output, {});
      const archiveStat = fs.statSync(archive);
      fs.unlinkSync(source);
      fs.unlinkSync(archive);
      this.report('bundle.zlib.lifecycle', 'archive:' + archiveStat.size.toString() + ',roundtrip:true');
    } catch (error) {
      this.report('bundle.zlib.error', this.errorText(error));
    }
    try {
      let download: string = '';
      try {
        download = environment.getUserDownloadDir();
      } catch (error) {
        download = 'error:' + this.errorText(error);
      }
      this.report('file.environment.result', 'download:' + download);
    } catch (error) {
      this.report('file.environment.error', this.errorText(error));
    }
    try {
      await hiAppEvent.write({
        domain: 'capability_audit',
        name: 'probe_event',
        eventType: hiAppEvent.EventType.BEHAVIOR,
        params: { value: 1 }
      });
      this.report('dfx.hiappevent.result', 'written:true');
    } catch (error) {
      this.report('dfx.hiappevent.error', this.errorText(error));
    }
    try {
      hichecker.addCheckRule(hichecker.RULE_THREAD_CHECK_SLOW_PROCESS);
      hichecker.removeCheckRule(hichecker.RULE_THREAD_CHECK_SLOW_PROCESS);
      this.report('dfx.hichecker.lifecycle', 'added:true,removed:true');
    } catch (error) {
      this.report('dfx.hichecker.error', this.errorText(error));
    }
    try {
      const session = await avSession.createAVSession(this.context, 'capability-audit', 'audio');
      const descriptors = await avSession.getAllSessionDescriptors();
      await session.activate();
      await session.deactivate();
      await session.destroy();
      this.report('media.avsession.lifecycle',
        'manager_count:' + descriptors.length.toString() + ',active:true,destroyed:true');
    } catch (error) {
      this.report('media.avsession.error', this.errorText(error));
    }
    try {
      const delay = backgroundTaskManager.requestSuspendDelay('capability-audit', () => {});
      backgroundTaskManager.cancelSuspendDelay(delay.requestId);
      this.report('resource.background_suspend.lifecycle',
        'request:' + delay.requestId.toString() + ',cancelled:true');
    } catch (error) {
      this.report('resource.background_suspend.error', this.errorText(error));
    }
  }

  private async runBreadthSoftwareProbes(): Promise<void> {
    try {
      const domains = appDomainVerify.queryAssociatedDomains('org.harmonycontrib.capabilityaudit');
      const bundles = appDomainVerify.queryAssociatedBundleNames('example.com');
      this.report('bundle.app_domain.query',
        'domains:' + domains.length.toString() + ',bundles:' + bundles.length.toString());
    } catch (error) {
      this.report('bundle.app_domain.error', this.errorText(error));
    }
    try {
      const rules = appControl.getAllDisposedRules();
      this.report('bundle.app_control.query', 'count:' + rules.length.toString());
    } catch (error) {
      this.report('bundle.app_control.error', this.errorText(error));
    }
    try {
      this.report('ability.startup.initialized',
        startupManager.isStartupTaskInitialized('capability-audit').toString());
    } catch (error) {
      this.report('ability.startup.error', this.errorText(error));
    }
    try {
      await formHost.isSystemReady();
      this.report('ability.form.ready', 'true');
    } catch (error) {
      this.report('ability.form.error', this.errorText(error));
    }
    try {
      const info = await quickFixManager.getApplicationQuickFixInfo('org.harmonycontrib.capabilityaudit');
      this.report('ability.quickfix.query', JSON.stringify(info));
    } catch (error) {
      this.report('ability.quickfix.error', this.errorText(error));
    }
    try {
      const isDefault = await defaultAppManager.isDefaultApplication('browser');
      this.report('bundle.default_app.query', isDefault.toString());
    } catch (error) {
      this.report('bundle.default_app.error', this.errorText(error));
    }
    try {
      const launcherAbilities = await launcherBundleManager.getAllLauncherAbilityInfo(100);
      this.report('bundle.launcher.query', 'count:' + launcherAbilities.length.toString());
    } catch (error) {
      this.report('bundle.launcher.error', this.errorText(error));
    }
    try {
      const resourceInfo = bundleResourceManager.getBundleResourceInfo(
        'org.harmonycontrib.capabilityaudit');
      this.report('bundle.resource.query', 'bundle:' + resourceInfo.bundleName);
    } catch (error) {
      this.report('bundle.resource.error', this.errorText(error));
    }
    try {
      const overlayInfo = await overlay.getOverlayModuleInfo('entry');
      this.report('bundle.overlay.query', JSON.stringify(overlayInfo));
    } catch (error) {
      this.report('bundle.overlay.error', this.errorText(error));
    }
    try {
      const supported = await netSharing.isSharingSupported();
      const sharing = await netSharing.isSharing();
      const interfaces = await netSharing.getSharingIfaces(netSharing.SharingIfaceState.SHARING_NIC_SERVING);
      this.report('network.sharing.query',
        'supported:' + supported.toString() + ',sharing:' + sharing.toString() +
        ',ifaces:' + interfaces.length.toString());
    } catch (error) {
      this.report('network.sharing.error', this.errorText(error));
    }
    try {
      const directories = configPolicy.getCfgDirListSync();
      const parameterFile = configPolicy.getOneCfgFileSync('etc/param/ohos.para');
      this.report('customization.config_policy.query',
        'dirs:' + directories.length.toString() + ',file:' + parameterFile);
    } catch (error) {
      this.report('customization.config_policy.error', this.errorText(error));
    }
    try {
      this.report('customization.channel_id.query', customConfig.getChannelId());
    } catch (error) {
      this.report('customization.channel_id.error', this.errorText(error));
    }
    try {
      const capabilities = await systemCapability.querySystemCapabilities();
      this.report('developtools.syscap.query', 'length:' + capabilities.length.toString());
    } catch (error) {
      this.report('developtools.syscap.error', this.errorText(error));
    }
    try {
      const volumes = await volumeManager.getAllVolumes();
      const disks = await volumeManager.getAllDisks();
      this.report('file.volume.query',
        'volumes:' + volumes.length.toString() + ',disks:' + disks.length.toString());
    } catch (error) {
      this.report('file.volume.error', this.errorText(error));
    }
    try {
      const dnd = await notificationManager.getDoNotDisturbDate();
      this.report('notification.settings.query', JSON.stringify(dnd));
    } catch (error) {
      this.report('notification.settings.error', this.errorText(error));
    }
    try {
      const reminders = await reminderAgentManager.getValidReminders();
      this.report('notification.reminder.query', 'count:' + reminders.length.toString());
    } catch (error) {
      this.report('notification.reminder.error', this.errorText(error));
    }
    try {
      const exempted = await deviceStandby.getExemptedApps(1);
      this.report('resource.device_standby.query', 'count:' + exempted.length.toString());
    } catch (error) {
      this.report('resource.device_standby.error', this.errorText(error));
    }
    try {
      this.report('resource.system_load.query', (await systemLoad.getLevel()).toString());
    } catch (error) {
      this.report('resource.system_load.error', this.errorText(error));
    }
    try {
      const works = await workScheduler.obtainAllWorks();
      this.report('resource.work_scheduler.query', 'count:' + works.length.toString());
    } catch (error) {
      this.report('resource.work_scheduler.error', this.errorText(error));
    }
    try {
      brightness.setValue(255);
      this.report('power.display_brightness.set', 'success:true');
    } catch (error) {
      this.report('power.display_brightness.error', this.errorText(error));
    }
    try {
      const keySystems = drm.getMediaKeySystems();
      this.report('media.drm.query', 'count:' + keySystems.length.toString());
    } catch (error) {
      this.report('media.drm.error', this.errorText(error));
    }
    try {
      const player = await media.createAVPlayer();
      await player.release();
      this.report('media.avplayer.lifecycle', 'created:true,released:true');
    } catch (error) {
      this.report('media.avplayer.error', this.errorText(error));
    }
    try {
      const player = await media.createVideoPlayer();
      await player.release();
      this.report('media.video_player.lifecycle', 'created:true,released:true');
    } catch (error) {
      this.report('media.video_player.error', this.errorText(error));
    }
    try {
      const generator = await media.createAVImageGenerator();
      await generator.release();
      this.report('media.avimage_generator.lifecycle', 'created:true,released:true');
    } catch (error) {
      this.report('media.avimage_generator.error', this.errorText(error));
    }
    try {
      const transcoder = await media.createAVTranscoder();
      await transcoder.release();
      this.report('media.avtranscoder.lifecycle', 'created:true,released:true');
    } catch (error) {
      this.report('media.avtranscoder.error', this.errorText(error));
    }
    try {
      const recorder = await media.createAVScreenCaptureRecorder();
      await recorder.release();
      this.report('media.screen_capture.lifecycle', 'created:true,released:true');
    } catch (error) {
      this.report('media.screen_capture.error', this.errorText(error));
    }
    try {
      const manager = audioHaptic.getAudioHapticManager();
      this.report('media.audio_haptic.manager', 'created:' + (manager !== undefined).toString());
    } catch (error) {
      this.report('media.audio_haptic.error', this.errorText(error));
    }
    try {
      const creator = image.createImageCreator({ width: 1, height: 1 }, image.ImageFormat.JPEG, 1);
      const receiver = image.createImageReceiver({ width: 1, height: 1 }, image.ImageFormat.JPEG, 1);
      await creator.release();
      await receiver.release();
      this.report('image.creator_receiver.lifecycle', 'created:true,released:true');
    } catch (error) {
      this.report('image.creator_receiver.error', this.errorText(error));
    }
    try {
      this.report('security.screenlock_file.query', screenLockFileManager.queryAppKeyState().toString());
    } catch (error) {
      this.report('security.screenlock_file.error', this.errorText(error));
    }
    try {
      this.report('xts.device_attest.query', JSON.stringify(deviceAttest.getAttestStatusSync()));
    } catch (error) {
      this.report('xts.device_attest.error', this.errorText(error));
    }
    try {
      await hiSysEvent.write({
        domain: 'CAPABILITY_AUDIT',
        name: 'PROBE_EVENT',
        eventType: hiSysEvent.EventType.BEHAVIOR,
        params: { value: 1 }
      });
      this.report('dfx.hisysevent.write', 'success:true');
    } catch (error) {
      this.report('dfx.hisysevent.error', this.errorText(error));
    }
    try {
      this.report('arkui.appearance.query',
        'dark:' + uiAppearance.getDarkMode().toString() +
        ',fontScale:' + uiAppearance.getFontScale().toString());
    } catch (error) {
      this.report('arkui.appearance.error', this.errorText(error));
    }
    try {
      const userData = await environment.getUserDataDir();
      this.report('file.environment.user_data', userData);
    } catch (error) {
      this.report('file.environment.user_data.error', this.errorText(error));
    }
    try {
      const manager = colorSpaceManager.create(colorSpaceManager.ColorSpace.SRGB);
      this.report('graphic.color_space.query',
        'name:' + manager.getColorSpaceName().toString() +
        ',white_point:' + manager.getWhitePoint().length.toString());
    } catch (error) {
      this.report('graphic.color_space.error', this.errorText(error));
    }
    setTimeout((): void => {
      try {
        const options = new photoAccessHelper.PhotoSelectOptions();
        options.MIMEType = photoAccessHelper.PhotoViewMIMETypes.IMAGE_TYPE;
        options.maxSelectNumber = 1;
        const picker = new photoAccessHelper.PhotoViewPicker();
        this.report('file.photo_picker.invoked', 'true');
        picker.select(options).then((result: photoAccessHelper.PhotoSelectResult): void => {
          this.report('file.photo_picker.result', JSON.stringify(result));
        }).catch((error: object): void => {
          this.report('file.photo_picker.error', this.errorText(error));
        });
      } catch (error) {
        this.report('file.photo_picker.error', this.errorText(error));
      }
    }, 4500);
    setTimeout((): void => {
      try {
        const documentPicker = new picker.DocumentViewPicker(this.context);
        this.report('file.document_picker.invoked', 'true');
        documentPicker.select().then((uris: Array<string>): void => {
          this.report('file.document_picker.result', JSON.stringify(uris));
        }).catch((error: object): void => {
          this.report('file.document_picker.error', this.errorText(error));
        });
      } catch (error) {
        this.report('file.document_picker.error', this.errorText(error));
      }
    }, 1500);
    setTimeout((): void => {
      try {
        const castPicker = new avSession.AVCastPickerHelper(this.context);
        this.report('media.avcast_picker.invoked', 'true');
        castPicker.select().then((): void => {
          this.report('media.avcast_picker.result', 'success:true');
        }).catch((error: object): void => {
          this.report('media.avcast_picker.error', this.errorText(error));
        });
      } catch (error) {
        this.report('media.avcast_picker.error', this.errorText(error));
      }
    }, 0);
    setTimeout((): void => {
      try {
        const abilityStartCallback: common.AbilityStartCallback = {
          onError: (code: number, name: string, message: string): void => {
            this.report('ability.share_picker.callback_error',
              'code:' + code.toString() + ',name:' + name + ',message:' + message);
          },
          onResult: (result: common.AbilityResult): void => {
            this.report('ability.share_picker.callback_result', JSON.stringify(result));
          }
        };
        this.report('ability.share_picker.invoked', 'true');
        this.context.startAbilityByType('share', {}, abilityStartCallback).then(() => {
          this.report('ability.share_picker.start', 'success:true');
        }).catch((error: object) => {
          this.report('ability.share_picker.error', this.errorText(error));
        });
      } catch (error) {
        this.report('ability.share_picker.error', this.errorText(error));
      }
    }, 3000);
    try {
      this.report('input.pointer.query',
        'speed:' + pointer.getPointerSpeedSync().toString() +
        ',visible:' + pointer.isPointerVisibleSync().toString());
    } catch (error) {
      this.report('input.pointer.error', this.errorText(error));
    }
    try {
      const hotkeys: Array<inputConsumer.HotkeyOptions> = await inputConsumer.getAllSystemHotkeys();
      this.report('input.consumer.query', 'hotkeys:' + hotkeys.length.toString());
    } catch (error) {
      this.report('input.consumer.error', this.errorText(error));
    }
    try {
      const mouseCallback = (): void => {};
      inputMonitor.on('mouse', mouseCallback);
      inputMonitor.off('mouse', mouseCallback);
      this.report('input.monitor.lifecycle', 'mouse_registered:true,removed:true');
    } catch (error) {
      this.report('input.monitor.error', this.errorText(error));
    }
    try {
      hiRetrieval.init();
      const participating = hiRetrieval.isParticipant();
      const timestamp = hiRetrieval.getLastParticipationTimestamp();
      hiRetrieval.quit();
      this.report('dfx.hiretrieval.lifecycle',
        'participant:' + participating.toString() + ',timestamp:' + timestamp.toString() + ',quit:true');
    } catch (error) {
      this.report('dfx.hiretrieval.error', this.errorText(error));
    }
    try {
      const faults = await faultLogger.query(faultLogger.FaultType.JS_CRASH);
      this.report('dfx.fault_logger.query', 'count:' + faults.length.toString());
    } catch (error) {
      this.report('dfx.fault_logger.error', this.errorText(error));
    }
    try {
      const logs = logLibrary.list('FAULTLOG');
      this.report('dfx.log_library.query', 'count:' + logs.length.toString());
    } catch (error) {
      this.report('dfx.log_library.error', this.errorText(error));
    }
    try {
      const stats = await batteryStatistics.getBatteryStats();
      this.report('power.battery_statistics.query', 'count:' + stats.length.toString());
    } catch (error) {
      this.report('power.battery_statistics.error', this.errorText(error));
    }
    try {
      const certificates = await certificateManager.getAllAppPrivateCertificates();
      if (certificates === undefined) {
        this.report('security.certificate_manager.query', 'undefined_result:true');
      } else {
        const count = certificates.credentialList === undefined ? 0 : certificates.credentialList.length;
        this.report('security.certificate_manager.query', 'count:' + count.toString());
      }
    } catch (error) {
      this.report('security.certificate_manager.error', this.errorText(error));
    }
    try {
      this.report('security.certificate_dialog.supported',
        certificateManagerDialog.supportsCACertDialog().toString());
    } catch (error) {
      this.report('security.certificate_dialog.error', this.errorText(error));
    }
    try {
      const keyGenerator = cryptoFramework.createAsyKeyGenerator('X25519');
      const pairA = await keyGenerator.generateKeyPair();
      const pairB = await keyGenerator.generateKeyPair();
      const agreement = cryptoFramework.createKeyAgreement('X25519');
      const secretA = await agreement.generateSecret(pairA.priKey, pairB.pubKey);
      const secretB = await agreement.generateSecret(pairB.priKey, pairA.pubKey);
      this.report('security.crypto.key_agreement',
        'asym_keys:true,bytes:' + secretA.data.length.toString() +
        ',equal:' + (secretA.data.toString() === secretB.data.toString()).toString());
    } catch (error) {
      this.report('security.crypto.key_agreement.error', this.errorText(error));
    }
    try {
      const keyGenerator = cryptoFramework.createAsyKeyGenerator('RSA1024');
      const keyPair = await keyGenerator.generateKeyPair();
      const signer = cryptoFramework.createSign('RSA1024|PKCS1|SHA256');
      const verifier = cryptoFramework.createVerify('RSA1024|PKCS1|SHA256');
      const data: cryptoFramework.DataBlob = { data: new Uint8Array([97, 117, 100, 105, 116]) };
      await signer.init(keyPair.priKey);
      const signature = await signer.sign(data);
      await verifier.init(keyPair.pubKey);
      const valid = await verifier.verify(data, signature);
      this.report('security.crypto.signature',
        'bytes:' + signature.data.length.toString() + ',valid:' + valid.toString());
    } catch (error) {
      this.report('security.crypto.signature.error', this.errorText(error));
    }
    try {
      const spec: cryptoFramework.PBKDF2Spec = {
        algName: 'PBKDF2', password: 'capability-audit', salt: new Uint8Array(16),
        iterations: 1000, keySize: 32
      };
      const kdf = cryptoFramework.createKdf('PBKDF2|SHA256');
      const secret = await kdf.generateSecret(spec);
      this.report('security.crypto.kdf', 'bytes:' + secret.data.length.toString());
    } catch (error) {
      this.report('security.crypto.kdf.error', this.errorText(error));
    }
    try {
      const sync = new cloudSync.FileSync();
      this.report('file.cloud_sync.constructor', 'default:true');
      try {
        const lastSyncTime = await sync.getLastSyncTime();
        this.report('file.cloud_sync.query', 'last_sync:' + lastSyncTime.toString());
      } catch (error) {
        this.report('file.cloud_sync.query.error', this.errorText(error));
      }
    } catch (error) {
      this.report('file.cloud_sync.constructor.error', this.errorText(error));
    }
    try {
      const sync = new cloudSync.FileSync('org.harmonycontrib.capabilityaudit');
      this.report('file.cloud_sync.system_constructor', 'bundle:true');
      try {
        const lastSyncTime = await sync.getLastSyncTime();
        this.report('file.cloud_sync.system_query', 'last_sync:' + lastSyncTime.toString());
      } catch (error) {
        this.report('file.cloud_sync.system_query.error', this.errorText(error));
      }
    } catch (error) {
      this.report('file.cloud_sync.system_constructor.error', this.errorText(error));
    }
    try {
      const enabled = await adminManager.isSuperAdmin('org.harmonycontrib.capabilityaudit');
      this.report('enterprise.admin.query', 'self_super_admin:' + enabled.toString());
    } catch (error) {
      this.report('enterprise.admin.error', this.errorText(error));
    }
    try {
      const result = await securityGuard.getModelResult({ modelName: 'capability-audit' });
      this.report('security.guard.model', result.result);
    } catch (error) {
      this.report('security.guard.model.error', this.errorText(error));
    }
    try {
      const enabled = await intelligentScene.isDoNotDisturbEnabled();
      const allowed = await intelligentScene.isNotifyAllowedInDoNotDisturb();
      this.report('applications.intelligent_scene.query',
        'dnd:' + enabled.toString() + ',notify_allowed:' + allowed.toString());
    } catch (error) {
      this.report('applications.intelligent_scene.error', this.errorText(error));
    }
    try {
      const state = router.getState();
      this.report('arkui.router.query', 'index:' + state.index.toString());
    } catch (error) {
      this.report('arkui.router.error', this.errorText(error));
    }
    try {
      const helper = fileAccess.createFileAccessHelper(this.context);
      const roots = await helper.getRoots();
      const first = roots.next();
      this.report('file.user_file_service.roots', 'first_done:' + first.done.toString());
    } catch (error) {
      this.report('file.user_file_service.error', this.errorText(error));
    }
    try {
      const manager = userFileManager.getUserFileMgr(this.context);
      await manager.release();
      this.report('file.user_file_manager.lifecycle', 'created:true,released:true');
    } catch (error) {
      this.report('file.user_file_manager.error', this.errorText(error));
    }
    try {
      const validator = cert.createCertChainValidator('PKIX');
      this.report('security.cert.validator', 'created:' + (validator !== undefined).toString());
    } catch (error) {
      this.report('security.cert.validator.error', this.errorText(error));
    }
    try {
      const captions = accessibility.getCaptionsManager();
      this.report('accessibility.hearing.captions',
        'created:' + (captions !== undefined).toString() + ',enabled:' + captions.enabled.toString());
    } catch (error) {
      this.report('accessibility.hearing.error', this.errorText(error));
    }
    try {
      const scene = await Scene.load();
      const factory = scene.getResourceFactory();
      scene.destroy();
      this.report('graphics3d.scene.lifecycle',
        'created:true,factory:' + (factory !== undefined).toString() + ',destroyed:true');
    } catch (error) {
      this.report('graphics3d.scene.error', this.errorText(error));
    }
    try {
      await shortKey.setKeyDownDuration('businessId', 500);
      this.report('input.short_key.duration', 'configured:true');
    } catch (error) {
      this.report('input.short_key.error', this.errorText(error));
    }
    try {
      const tasks = await request.agent.search();
      this.report('request.file_transfer_agent.search', 'count:' + tasks.length.toString());
    } catch (error) {
      this.report('request.file_transfer_agent.error', this.errorText(error));
    }
    try {
      const destination = this.context.cacheDir + '/capability-audit-download.html';
      const task = await request.downloadFile(this.context,
        { url: 'http://10.0.2.2:18080/download', filePath: destination });
      task.on('complete', (): void => {
        this.report('request.download.complete', 'exists:' + fs.accessSync(destination).toString());
      });
      task.on('fail', (code: number): void => {
        this.report('request.download.fail', code.toString());
      });
      this.report('request.download.created', 'true');
    } catch (error) {
      this.report('request.download.error', this.errorText(error));
    }
    try {
      const uploadPath = this.context.cacheDir + '/capability-audit-upload.txt';
      const uploadFile = fs.openSync(uploadPath, fs.OpenMode.READ_WRITE | fs.OpenMode.CREATE);
      fs.writeSync(uploadFile.fd, 'ohos-qemu-capability-audit');
      fs.closeSync(uploadFile);
      const task = await request.uploadFile(this.context, {
        url: 'http://10.0.2.2:18080/upload', header: {}, method: 'POST',
        files: [{ filename: 'capability-audit-upload.txt', name: 'file',
          uri: 'internal://cache/capability-audit-upload.txt', type: 'text/plain' }],
        data: [{ name: 'probe', value: 'ohos-qemu-capability-audit' }]
      });
      task.on('complete', (states: Array<request.TaskState>): void => {
        this.report('request.upload.complete', 'states:' + states.length.toString());
      });
      task.on('fail', (states: Array<request.TaskState>): void => {
        this.report('request.upload.fail', 'states:' + states.length.toString());
      });
      this.report('request.upload.created', 'true');
    } catch (error) {
      this.report('request.upload.error', this.errorText(error));
    }
    try {
      const continuous = await backgroundTaskManager.getAllContinuousTasks(this.context);
      this.report('resource.background_continuous.query', 'count:' + continuous.length.toString());
    } catch (error) {
      this.report('resource.background_continuous.error', this.errorText(error));
    }
    try {
      const resources = await backgroundTaskManager.getAllEfficiencyResources();
      this.report('resource.background_efficiency.query', 'count:' + resources.length.toString());
    } catch (error) {
      this.report('resource.background_efficiency.error', this.errorText(error));
    }
    try {
      const driver = Driver.create();
      await driver.delayMs(1);
      this.report('test.ui_driver.lifecycle', 'created:true,delay:true');
    } catch (error) {
      this.report('test.ui_driver.error', this.errorText(error));
    }
    try {
      const strategy: PerfTestStrategy = {
        metrics: [PerfMetric.DURATION],
        actionCode: (finish: Callback<boolean>): void => { finish(true); },
        iterations: 1,
        timeout: 1000
      };
      const performance = PerfTest.create(strategy);
      await performance.run();
      const result = performance.getMeasureResult(PerfMetric.DURATION);
      performance.destroy();
      this.report('test.performance.lifecycle',
        'rounds:' + result.roundValues.length.toString() + ',average:' + result.average.toString());
    } catch (error) {
      this.report('test.performance.error', this.errorText(error));
    }
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
      this.report('i18n.system_languages.count', i18n.System.getSystemLanguages().length.toString());
      this.report('i18n.system_countries.count', i18n.System.getSystemCountries('zh').length.toString());
    } catch (error) {
      this.report('i18n.system.error', this.errorText(error));
    }
    try {
      this.report('fusion.ranging.supported', ranging.isRangingSupported().toString());
    } catch (error) {
      this.report('fusion.ranging.error', this.errorText(error));
    }
    try {
      this.report('fusion.partner_agent.supported', partnerAgent.isPartnerAgentSupported().toString());
    } catch (error) {
      this.report('fusion.partner_agent.error', this.errorText(error));
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
probe_calls = "" if args.provider_only else """    probe.run();
    this.runArkTsProbes();
    this.runHuksProbe();
    this.runCoreSoftwareProbes();
    this.runExpandedSoftwareProbes();
    this.runBreadthSoftwareProbes();"""
write(
    "entry/src/main/ets/entryability/EntryAbility.ets",
    entry_ability.replace("__API_MODULES__", json.dumps(api_modules)).replace(
        "__PUBLIC_SYSCAPS__", json.dumps(public_syscaps)
    ).replace("__BREADTH_PROBE_CALLS__", probe_calls),
)
if minimal_app:
    write(
        "entry/src/main/ets/entryability/EntryAbility.ets",
        """import { UIAbility } from '@kit.AbilityKit';
import window from '@ohos.window';

export default class EntryAbility extends UIAbility {
  onWindowStageCreate(stage: window.WindowStage): void {
    stage.loadContent('pages/Index');
  }
}
""",
    )
def webgl_render_script(version: int) -> str:
    vertex = "attribute vec2 position; void main(){gl_Position=vec4(position,0.0,1.0);}"
    fragment = "precision mediump float; void main(){gl_FragColor=vec4(0.2,0.4,0.6,1.0);}"
    if version == 2:
        vertex = "#version 300 es\nin vec2 position; void main(){gl_Position=vec4(position,0.0,1.0);}"
        fragment = "#version 300 es\nprecision mediump float; out vec4 color; void main(){color=vec4(0.2,0.4,0.6,1.0);}"
    return """(() => {
      const canvas = document.createElement('canvas'); canvas.width = 16; canvas.height = 16;
      const gl = canvas.getContext(__CONTEXT__);
      if (!gl) return JSON.stringify({pass:false, stage:'context'});
      const bad = gl.createShader(gl.VERTEX_SHADER); gl.shaderSource(bad, 'void main( {'); gl.compileShader(bad);
      const invalidShaderRejected = !gl.getShaderParameter(bad, gl.COMPILE_STATUS); gl.deleteShader(bad);
      function shader(kind, source) {
        const value = gl.createShader(kind); gl.shaderSource(value, source); gl.compileShader(value);
        if (!gl.getShaderParameter(value, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(value));
        return value;
      }
      const vs = shader(gl.VERTEX_SHADER, __VERTEX__); const fs = shader(gl.FRAGMENT_SHADER, __FRAGMENT__);
      const program = gl.createProgram(); gl.attachShader(program, vs); gl.attachShader(program, fs);
      gl.linkProgram(program);
      if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program));
      gl.useProgram(program); const buffer = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1,3,-1,-1,3]), gl.STATIC_DRAW);
      const location = gl.getAttribLocation(program, 'position'); gl.enableVertexAttribArray(location);
      gl.vertexAttribPointer(location, 2, gl.FLOAT, false, 0, 0); gl.viewport(0,0,16,16);
      gl.drawArrays(gl.TRIANGLES, 0, 3); const pixel = new Uint8Array(4);
      gl.readPixels(8,8,1,1,gl.RGBA,gl.UNSIGNED_BYTE,pixel); const error = gl.getError();
      const pass = invalidShaderRejected && error === gl.NO_ERROR && Math.abs(pixel[0]-51) <= 1 &&
        Math.abs(pixel[1]-102) <= 1 && Math.abs(pixel[2]-153) <= 1 && pixel[3] === 255;
      gl.deleteBuffer(buffer); gl.deleteProgram(program); gl.deleteShader(vs); gl.deleteShader(fs);
      return JSON.stringify({pass:pass,pixel:Array.from(pixel),error:error,invalid_shader_rejected:invalidShaderRejected});
    })()""".replace("__CONTEXT__", json.dumps("webgl" if version == 1 else "webgl2")).replace(
        "__VERTEX__", json.dumps(vertex)).replace("__FRAGMENT__", json.dumps(fragment))


write(
    "entry/src/main/ets/pages/Index.ets",
    """import web_webview from '@ohos.web.webview';
import probe from 'libcapabilityprobe.so';

class ArkWebAuditProxy {
  private calls: number = 0;

  roundTrip(value: string): string {
    this.calls++;
    probe.append('web.js.proxy.callback=' + value);
    return 'arkts:' + value;
  }

  getCallCount(): number {
    return this.calls;
  }
}

@Entry
@Component
struct Index {
  private controller: web_webview.WebviewController = new web_webview.WebviewController();
  private jsProxy: ArkWebAuditProxy = new ArkWebAuditProxy();
  private webProbeStarted: boolean = false;
  private navigationPending: number = 0;
  private expectedRendererExit: boolean = false;
  private rendererRecoveryComplete: boolean = false;

  private runWebStep(name: string, script: string, next: () => void): void {
    let settled: boolean = false;
    probe.append('web.' + name + '.begin=true');
    setTimeout((): void => {
      if (!settled) {
        settled = true;
        probe.append('web.' + name + '.timeout=true');
        next();
      }
    }, 15000);
    try {
      this.controller.runJavaScript(script).then((value: string) => {
        if (settled) {
          probe.append('web.' + name + '.late=' + value);
          return;
        }
        settled = true;
        probe.append('web.' + name + '.result=' + value);
        next();
      }).catch((error: object) => {
        if (settled) {
          return;
        }
        settled = true;
        probe.append('web.' + name + '.error=' + error.toString() + ':' + JSON.stringify(error));
        next();
      });
    } catch (error) {
      if (!settled) {
        settled = true;
        probe.append('web.' + name + '.sync_error=' + error.toString() + ':' + JSON.stringify(error));
        next();
      }
    }
  }

  private runProxyProbe(name: string, next: () => void): void {
    this.runWebStep(name + '.proxy',
      "(() => { const reply = qemuAuditProxy.roundTrip('" + name + "'); return JSON.stringify({reply:reply,calls:qemuAuditProxy.getCallCount()}); })()",
      next);
  }

  private startRendererRecovery(): void {
    this.expectedRendererExit = true;
    setTimeout((): void => {
      if (!this.rendererRecoveryComplete) {
        probe.append('web.renderer.recovery.timeout=true');
      }
    }, 60000);
    try {
      const terminated: boolean = this.controller.terminateRenderProcess();
      probe.append('web.renderer.terminate.result=' + terminated.toString());
    } catch (error) {
      probe.append('web.renderer.terminate.error=' + error.toString());
    }
  }

  private startReload(): void {
    this.navigationPending = 1;
    setTimeout((): void => {
      if (this.navigationPending === 1) {
        probe.append('web.reload.timeout=true');
      }
    }, 30000);
    try {
      this.controller.refresh();
    } catch (error) {
      probe.append('web.reload.error=' + error.toString());
    }
  }

  private runWebBoundaryProbe(): void {
    this.runWebStep('canvas.2d.render',
      "(() => { const c=document.createElement('canvas'); c.width=4; c.height=4; const ctx=c.getContext('2d'); if (!ctx) return JSON.stringify({pass:false}); ctx.fillStyle='rgb(51,102,153)'; ctx.fillRect(0,0,4,4); const p=Array.from(ctx.getImageData(1,1,1,1).data); return JSON.stringify({pass:p.join(',')==='51,102,153,255',pixel:p}); })()",
      () => {
        this.runWebStep('js.exception',
          "(() => { try { throw new Error('QEMU_WEB_EXPECTED_ERROR'); } catch (e) { return e.name + ':' + e.message; } })()",
          () => {
            this.runWebStep('js.after_exception', '6 * 7', () => {
              this.runProxyProbe('js', () => { this.startReload(); });
            });
          });
      });
  }

  private runWebExecutionProbe(): void {
    this.runWebStep('js.arithmetic', '1 + 1', () => {
      this.runWebStep('js.dom', 'document.title', () => {
        this.runWebStep('canvas.2d',
          "(() => { const canvas = document.createElement('canvas'); return !!canvas.getContext('2d'); })()",
          () => {
            this.runWebStep('graphics.webgl1',
              "(() => { const canvas = document.createElement('canvas'); return !!canvas.getContext('webgl'); })()",
              () => {
                this.runWebStep('graphics.webgl2',
                  "(() => { const canvas = document.createElement('canvas'); return !!canvas.getContext('webgl2'); })()",
                  () => {
                    this.runWebStep('graphics.webgl1.render', __WEBGL1_RENDER__, () => {
                      this.runWebStep('graphics.webgl2.render', __WEBGL2_RENDER__, () => {
                        this.runWebBoundaryProbe();
                      });
                    });
                  });
              });
          });
      });
    });
  }

  build() {
    Column() {
      Text('Capability audit')
      Web({ src: 'https://example.com', controller: this.controller })
        .width('100%')
        .height('90%')
        .javaScriptAccess(true)
        .javaScriptProxy({ object: this.jsProxy, name: 'qemuAuditProxy',
          methodList: ['roundTrip', 'getCallCount'], controller: this.controller })
        .onPageBegin(() => { probe.append('web.page_begin=true'); })
        .onPageEnd(() => {
          probe.append('web.page_end=true');
          try {
            probe.append('web.title=' + this.controller.getTitle());
            probe.append('web.url=' + this.controller.getUrl());
            if (!this.webProbeStarted) {
              this.webProbeStarted = true;
              this.runWebExecutionProbe();
            } else if (this.navigationPending === 1) {
              this.navigationPending = 0;
              this.runWebStep('reload.dom', 'document.title', () => {
                this.runProxyProbe('reload', () => { this.startRendererRecovery(); });
              });
            } else if (this.navigationPending === 2) {
              this.navigationPending = 0;
              this.runWebStep('renderer.recovery.dom', 'document.title', () => {
                this.runProxyProbe('renderer.recovery', () => {
                  this.runWebStep('renderer.recovery.webgl1.render', __WEBGL1_RENDER__, () => {
                    this.runWebStep('renderer.recovery.webgl2.render', __WEBGL2_RENDER__, () => {
                      this.rendererRecoveryComplete = true;
                      probe.append('web.execution.complete=true');
                    });
                  });
                });
              });
            }
          } catch (error) {
            probe.append('web.controller.error=' + error.toString() + ':' + JSON.stringify(error));
          }
        })
        .onErrorReceive((event) => {
          probe.append('web.load.error=' + event.error.getErrorCode().toString() + ':' + event.error.getErrorInfo());
        })
        .onRenderExited(() => {
          if (!this.expectedRendererExit) {
            probe.append('web.renderer.unexpected.error=true');
            return;
          }
          this.expectedRendererExit = false;
          this.navigationPending = 2;
          probe.append('web.renderer.exit.result=true');
          try {
            this.controller.refresh();
          } catch (error) {
            probe.append('web.renderer.recovery.error=' + error.toString());
          }
        })
    }
  }
}
""".replace("__WEBGL1_RENDER__", json.dumps(webgl_render_script(1))).replace(
        "__WEBGL2_RENDER__", json.dumps(webgl_render_script(2))),
)
if args.web_only:
    web_page = root / "entry/src/main/ets/pages/Index.ets"
    web_source = web_page.read_text(encoding="utf-8")
    web_source = web_source.replace(
        "import probe from 'libcapabilityprobe.so';",
        """import hilog from '@ohos.hilog';
import fs from '@ohos.file.fs';
class ProbeSink {
  append(line: string): void {
    hilog.info(0xD003900, 'ArkWebAudit', '%{public}s', line);
    try {
      const file = fs.openSync('/data/storage/el2/base/files/capability-results.log',
        fs.OpenMode.WRITE_ONLY | fs.OpenMode.CREATE | fs.OpenMode.APPEND);
      fs.writeSync(file.fd, line + '\\n');
      fs.closeSync(file);
    } catch (error) {
      hilog.error(0xD003900, 'ArkWebAudit', 'result write failed: %{public}s', error.toString());
    }
  }
}
const probe: ProbeSink = new ProbeSink();""",
    )
    # Keep the Web graphics contract independent of external network access.
    web_source = web_source.replace("src: 'https://example.com'", "src: $rawfile('arkweb-audit.html')")
    write("entry/src/main/resources/rawfile/arkweb-audit.html",
          "<!doctype html><html><head><title>QEMU ArkWeb Audit</title></head><body>Local Web execution probe</body></html>\n")
    web_page.write_text(web_source, encoding="utf-8")

if args.vulkan_window_only:
    write("entry/src/main/ets/pages/Index.ets", """import fs from '@ohos.file.fs';
import hilog from '@ohos.hilog';
interface VulkanWindowNative { getStatus: () => string; }
@Entry
@Component
struct Index {
  @State private surfaceVisible: boolean = true;
  @State private note: string = 'Waiting for native Vulkan presentation';
  private nativeContext?: VulkanWindowNative;
  private timer: number = -1;
  private expectedGeneration: number = 0;

  private record(value: string): void {
    hilog.info(0xD003900, 'VulkanWindowAudit', '%{public}s', value);
    const file = fs.openSync('/data/storage/el2/base/files/vulkan-window-results.log',
      fs.OpenMode.WRITE_ONLY | fs.OpenMode.CREATE | fs.OpenMode.APPEND);
    fs.writeSync(file.fd, value + '\\n');
    fs.closeSync(file);
  }
  private watch(destruction: boolean): void {
    if (this.timer >= 0) { clearInterval(this.timer); }
    let ticks: number = 0;
    this.timer = setInterval(() => {
      ticks++;
      if (this.nativeContext) {
        const status: string = this.nativeContext.getStatus();
        this.note = status;
        const target: string = destruction ? 'destroyed=1' : 'destroyed=0';
        if (status.includes('frames=5 ') && status.includes('cleaned=1 ') &&
            status.includes(target) && status.includes('generation=' + this.expectedGeneration)) {
          this.record((destruction ? 'vulkan_window.destroyed|' : 'vulkan_window.present|') + status);
          clearInterval(this.timer);
          this.timer = -1;
          return;
        }
      }
      if (ticks >= 150) {
        this.record('vulkan_window.timeout|' + this.note);
        clearInterval(this.timer);
        this.timer = -1;
      }
    }, 200);
  }
  aboutToDisappear(): void { if (this.timer >= 0) { clearInterval(this.timer); } }
  build() {
    Column({ space: 12 }) {
      Text('QEMU Vulkan compositor audit').fontSize(18)
      if (this.surfaceVisible) {
        XComponent({ id: 'qemu-vulkan-surface', type: XComponentType.SURFACE,
                     libraryname: 'vulkanwindowprobe' })
          .id('qemu-vulkan-surface').width(320).height(180).backgroundColor(Color.Black)
          .onLoad((context?: object) => {
            this.nativeContext = context as VulkanWindowNative;
            this.expectedGeneration++;
            this.watch(false);
          })
      }
      Text(this.note).fontSize(12)
      Button(this.surfaceVisible ? 'Destroy Vulkan surface' : 'Recreate Vulkan surface')
        .id('qemu-vulkan-lifecycle')
        .onClick(() => {
          this.surfaceVisible = !this.surfaceVisible;
          if (!this.surfaceVisible) { this.watch(true); }
        })
    }.width('100%').height('100%').justifyContent(FlexAlign.Center)
      .backgroundColor(Color.White)
  }
}
""")

if args.settings_navigation_only:
    from run_root_probe import digest
    challenge = args.probe_run_id or uuid.uuid4().hex
    template = Path(__file__).with_name('settings_navigation_probe.ets')
    page = root / 'entry/src/main/ets/pages/Index.ets'
    write('entry/src/main/ets/pages/Index.ets', template.read_text().replace('__SETTINGS_RUN__', challenge))
    write('settings-navigation-probe-inputs.json', {
        'schema_version': 1, 'scope': 'ordinary_Settings_public_calls_NOT_UI_acceptance',
        'run_id': challenge, 'arch': args.arch, 'request_permissions': [],
        'template_sha256': digest(template), 'generated_source_sha256': digest(page),
        'module_sha256': digest(root / 'entry/src/main/module.json5'),
        'settings_declarations_sha256': digest(api_dir / '@ohos.settings.d.ts'),
        'input_method_declarations_sha256': digest(api_dir / '@ohos.inputMethod.d.ts'),
        'screen_declarations_sha256': digest(api_dir / '@ohos.screen.d.ts')})

if args.arkts_exports_only:
    from verify_arkts_exports_results import expected_modules
    from const_enum_contracts import LEDGER, sha256
    challenge = args.probe_run_id or uuid.uuid4().hex
    modules = expected_modules()
    template = Path(__file__).with_name('arkts_exports_probe.ets')
    page = root / 'entry/src/main/ets/pages/Index.ets'
    native_probe = Path(__file__).with_name('arkts_exports_hap_probe.cpp').resolve()
    write('entry/src/main/ets/pages/Index.ets', template.read_text().replace('__RUN__', challenge)
          .replace('__MODULES__', json.dumps(modules)))
    write('entry/src/main/cpp/types/libarktsexportsprobe/index.d.ts',
          'interface Probe { inspect: (names: string[]) => object[]; }\ndeclare const probe: Probe;\nexport default probe;\n')
    write('arkts-exports-probe-inputs.json', {'schema_version': 1, 'run_id': challenge, 'arch': args.arch,
          'role': 'ordinary_app', 'scope': 'actual_all_own_exports_collection_only', 'modules': modules,
          'audit_baseline_sha256': sha256(LEDGER), 'native_source': str(native_probe),
          'native_source_sha256': sha256(native_probe), 'generated_source': str(page),
          'generated_source_sha256': sha256(page), 'template': str(template), 'template_sha256': sha256(template)})
if worker_only:
    from const_enum_contracts import sha256
    from worker_contracts import MODES, generated
    challenge = args.probe_run_id or uuid.uuid4().hex
    mode = 'legacy' if args.worker_legacy_only else 'thread'
    constructor, port, _, _, _ = MODES[mode]
    sources, hashes = generated(mode, challenge)
    for destination, content in sources.items():
        write(destination, content)
    write('worker-' + mode + '-probe-inputs.json', {'schema_version': 1, 'run_id': challenge,
        'arch': args.arch, 'role': 'ordinary_app', 'mode': mode, 'worker_class': constructor,
        'port_name': port, 'scope': 'worker_context_ports_and_transfer_lifecycle_only', 'source_sha256': hashes,
        'sdk_worker_declaration': str(args.sdk / 'ets/api/@ohos.worker.d.ts'),
        'sdk_worker_declaration_sha256': sha256(args.sdk / 'ets/api/@ohos.worker.d.ts')})
if args.contact_sync_mode_only:
    from contact_sync_mode_contract import TEMPLATE, inputs as contact_sync_inputs
    challenge = args.probe_run_id or uuid.uuid4().hex
    write('entry/src/main/ets/pages/Index.ets', TEMPLATE.read_text().replace('__RUN__', challenge))
    write('entry/src/main/cpp/types/libcontactsyncmodeprobe/index.d.ts',
          'interface NativeModes { values: number[]; statuses: number[]; types: number[]; own: boolean[]; exception: boolean; }\n'
          'interface Probe { inspect: () => NativeModes; inspectAudio: () => NativeModes; inspectPhoto: () => NativeModes; }\ndeclare const probe: Probe;\nexport default probe;\n')
    write('contact-sync-mode-probe-inputs.json', contact_sync_inputs(root, args.sdk, args.arch, challenge))
if args.runtime_enum_only or args.curve_only:
    from runtime_enum_contracts import expected, generate, inputs as runtime_enum_inputs
    challenge = args.probe_run_id or uuid.uuid4().hex
    if args.curve_only:
        from curve_contract import TEMPLATE, inputs as curve_inputs
        write('entry/src/main/ets/pages/Index.ets', TEMPLATE.read_text().replace('__CURVE_RUN_ID__', challenge))
        write('curve-probe-inputs.json', curve_inputs(root, args.sdk, args.arch, challenge))
    else:
        contracts = expected(args.sdk, args.enum_device)['contracts']
        write('entry/src/main/ets/pages/Index.ets', generate(contracts, challenge))
        write('runtime-enum-probe-inputs.json', runtime_enum_inputs(root, args.sdk, args.arch, args.enum_device, challenge))
    write('entry/src/main/cpp/types/libruntimeenumprobe/index.d.ts',
          'interface NativeEnum { values: (number | string)[]; statuses: number[]; types: number[]; own: boolean[]; exception: boolean; }\n'
          'interface Probe { inspect: (module: string, name: string, members: string[]) => NativeEnum; }\ndeclare const probe: Probe;\nexport default probe;\n')
if args.binding_only:
    from binding_contract import TEMPLATE, inputs as binding_inputs
    challenge = args.probe_run_id or uuid.uuid4().hex
    write('entry/src/main/ets/pages/Index.ets', TEMPLATE.read_text().replace('__BINDING_RUN_ID__', challenge))
    write('binding-probe-inputs.json', binding_inputs(root, args.sdk, args.arch, challenge))
if args.storage_stats_only:
    from storage_stats_contract import TEMPLATE, inputs as storage_inputs
    challenge = args.probe_run_id or uuid.uuid4().hex
    write('entry/src/main/ets/pages/Index.ets', TEMPLATE.read_text().replace('__STORAGE_RUN_ID__', challenge))
    write('storage-stats-probe-inputs.json', storage_inputs(root, args.sdk, args.arch, challenge))

if args.image_metadata_only:
    from image_metadata_fixtures import verify as verify_image_fixtures
    from run_root_probe import digest
    files = verify_image_fixtures(args.image_metadata_fixtures)
    challenge = args.probe_run_id or uuid.uuid4().hex
    template = Path(__file__).with_name('image_metadata_probe.ets')
    write('entry/src/main/ets/pages/Index.ets', template.read_text().replace('__IMAGE_METADATA_RUN__', challenge))
    assets = root / 'entry/src/main/resources/rawfile'
    assets.mkdir(parents=True, exist_ok=True)
    for name in files:
        shutil.copy2(args.image_metadata_fixtures / name, assets / name)
    write('image-metadata-probe-inputs.json', {'schema_version': 1, 'run_id': challenge, 'arch': args.arch,
        'scope': 'real_typed_image_metadata_factory_values_NOT_public_constructors_or_full_gate',
        'fixtures': files, 'template_sha256': digest(template),
        'generated_source_sha256': digest(root / 'entry/src/main/ets/pages/Index.ets'),
        'sdk_declaration_sha256': digest(api_dir / '@ohos.multimedia.image.d.ts'),
        'module_sha256': digest(root / 'entry/src/main/module.json5'), 'request_permissions': []})
if args.wifi_scan_only:
    from wifi_scan_contract import TEMPLATE, inputs as wifi_inputs
    challenge = args.probe_run_id or uuid.uuid4().hex
    write('entry/src/main/ets/pages/Index.ets', TEMPLATE.read_text().replace('__WIFI_SCAN_RUN_ID__', challenge))
    write('wifi-scan-probe-inputs.json', wifi_inputs(root, args.sdk, args.arch, challenge))
if args.thermal_only:
    from thermal_contract import TEMPLATE, inputs as thermal_inputs
    challenge = args.probe_run_id or uuid.uuid4().hex
    write('entry/src/main/ets/pages/Index.ets', TEMPLATE.read_text().replace('__THERMAL_RUN_ID__', challenge))
    write('thermal-probe-inputs.json', thermal_inputs(root, args.sdk, args.arch, challenge))
if args.completion_handler_only:
    from completion_handler_contract import TEMPLATE, inputs as completion_inputs
    challenge = args.probe_run_id or uuid.uuid4().hex
    write('entry/src/main/ets/pages/Index.ets', TEMPLATE.read_text().replace('__COMPLETION_RUN_ID__', challenge))
    write('completion-handler-probe-inputs.json', completion_inputs(root, args.sdk, args.arch, challenge))
if args.photos_recent_only:
    from photos_recent_contract import TEMPLATE, inputs as photos_inputs
    challenge = args.probe_run_id or uuid.uuid4().hex
    write('entry/src/main/ets/pages/Index.ets', TEMPLATE.read_text().replace('__PHOTO_RUN__', challenge))
    write('photos-recent-probe-inputs.json', photos_inputs(root, args.sdk, args.arch, challenge))
if args.photos_asset_only:
    from photos_asset_contract import TEMPLATE, inputs as photos_asset_inputs
    challenge = args.probe_run_id or uuid.uuid4().hex
    write('entry/src/main/ets/pages/Index.ets', TEMPLATE.read_text().replace('__PHOTO_ASSET_RUN__', challenge))
    write('photos-asset-probe-inputs.json', photos_asset_inputs(root, args.sdk, args.arch, challenge))
if args.optional_phone_profile_only:
    from optional_phone_profile_contract import TEMPLATE, inputs as profile_inputs
    challenge = args.probe_run_id or uuid.uuid4().hex
    write('entry/src/main/ets/pages/Index.ets', TEMPLATE.read_text().replace('__PROFILE_RUN_ID__', challenge))
    write('optional-phone-profile-probe-inputs.json', profile_inputs(root, args.sdk, args.arch, challenge))
if args.const_enum_only:
    from const_enum_contracts import LEDGER, expected_contracts, generate, sha256
    challenge = args.probe_run_id or uuid.uuid4().hex
    contracts = expected_contracts(args.sdk)
    page = root / 'entry/src/main/ets/pages/Index.ets'
    write('entry/src/main/ets/pages/Index.ets', generate(contracts, challenge))
    write('const-enum-probe-inputs.json', {'schema_version': 1, 'run_id': challenge,
          'arch': args.arch, 'role': 'ordinary_app', 'scope': 'compiled_const_enum_contracts_only',
          'sdk': str(args.sdk.resolve()), 'contracts': contracts,
          'audit_baseline_sha256': sha256(LEDGER), 'generated_source': str(page),
          'generated_source_sha256': sha256(page), 'typescript_sha256': sha256(
              args.sdk / 'ets/build-tools/ets-loader/node_modules/typescript/lib/typescript.js')})
if args.factory_objects_only:
    from run_root_probe import digest
    challenge = args.probe_run_id or uuid.uuid4().hex
    template = Path(__file__).with_name('factory_objects_probe.ets')
    page = root / 'entry/src/main/ets/pages/Index.ets'
    write('entry/src/main/ets/pages/Index.ets', template.read_text().replace('__FACTORY_RUN_ID__', challenge))
    declarations = {name: {'path': str((args.sdk / 'ets/api' / name).resolve()),
                          'sha256': digest(args.sdk / 'ets/api' / name)}
                    for name in ('@ohos.resourceManager.d.ts', '@ohos.taskpool.d.ts')}
    write('factory-objects-probe-inputs.json', {'schema_version': 1, 'run_id': challenge, 'arch': args.arch,
          'role': 'ordinary_app', 'scope': 'five_real_factory_returned_types_only', 'request_permissions': [],
          'template_sha256': digest(template), 'generated_source': str(page),
          'generated_source_sha256': digest(page), 'sdk_declarations': declarations})
if args.web_factory_only:
    from run_root_probe import digest
    challenge = args.probe_run_id or uuid.uuid4().hex
    template = Path(__file__).with_name('web_factory_probe.ets')
    page = root / 'entry/src/main/ets/pages/Index.ets'
    write('entry/src/main/ets/pages/Index.ets', template.read_text().replace('__WEB_FACTORY_RUN_ID__', challenge))
    declaration = args.sdk / 'ets/api/@ohos.web.webview.d.ts'
    write('web-factory-probe-inputs.json', {'schema_version': 1, 'run_id': challenge, 'arch': args.arch,
          'role': 'ordinary_app', 'scope': 'four_ArkWeb_factory_and_callback_types_NOT_native_media_decoding',
          'request_permissions': [], 'template_sha256': digest(template), 'generated_source': str(page),
          'generated_source_sha256': digest(page), 'sdk_declaration': str(declaration.resolve()),
          'sdk_declaration_sha256': digest(declaration)})
if args.matrix4_only:
    from run_root_probe import digest
    challenge = args.probe_run_id or uuid.uuid4().hex
    template = Path(__file__).with_name('matrix4_probe.ets')
    page = root / 'entry/src/main/ets/pages/Index.ets'
    declaration = args.sdk / 'ets/api/@ohos.matrix4.d.ts'
    write('entry/src/main/ets/pages/Index.ets', template.read_text().replace('__MATRIX_RUN_ID__', challenge))
    write('matrix4-probe-inputs.json', {'schema_version': 1, 'run_id': challenge, 'arch': args.arch,
          'role': 'ordinary_app', 'scope': 'real_typed_matrix4_helpers_only', 'request_permissions': [],
          'template_sha256': digest(template), 'generated_source': str(page),
          'generated_source_sha256': digest(page), 'sdk_declaration': str(declaration.resolve()),
          'sdk_declaration_sha256': digest(declaration)})
if args.i18n_only:
    challenge = args.probe_run_id or uuid.uuid4().hex
    write("entry/src/main/ets/pages/Index.ets",
          Path(__file__).with_name("i18n_data_probe.ets").read_text().replace("__I18N_RUN_ID__", challenge))
    write("i18n-probe-inputs.json", {"schema_version": 1, "run_id": challenge,
                                   "arch": args.arch, "role": "ordinary_app"})
if args.userid_only:
    challenge = args.probe_run_id or uuid.uuid4().hex
    write("entry/src/main/ets/pages/Index.ets",
          Path(__file__).with_name("userid_probe.ets").read_text().replace("__USERID_RUN_ID__", challenge))
    write("userid-probe-inputs.json", {"schema_version": 1, "run_id": challenge,
                                     "arch": args.arch, "role": "ordinary_app"})
if args.audio_stream_only:
    challenge = args.probe_run_id or uuid.uuid4().hex
    write("entry/src/main/ets/pages/Index.ets",
          Path(__file__).with_name("audio_stream_probe.ets").read_text().replace("__AUDIO_RUN_ID__", challenge))
    write("audio-stream-probe-inputs.json", {"schema_version": 1, "run_id": challenge,
                                           "arch": args.arch, "role": "ordinary_app"})
if args.audio_suite_effects_only:
    challenge = args.probe_run_id or uuid.uuid4().hex
    write("entry/src/main/ets/pages/Index.ets",
          Path(__file__).with_name("audio_suite_effects_probe.ets").read_text().replace("__AUDIO_SUITE_EFFECTS_RUN_ID__", challenge))
    write("audio-suite-effects-probe-inputs.json", {"schema_version": 1, "run_id": challenge,
                                                  "arch": args.arch, "role": "ordinary_app"})
if args.camera_only:
    challenge = args.probe_run_id or uuid.uuid4().hex
    write("entry/src/main/ets/pages/Index.ets",
          Path(__file__).with_name("camera_probe.ets").read_text().replace("__CAMERA_RUN_ID__", challenge))
    from camera_probe_contract import inputs as camera_inputs
    write("camera-probe-inputs.json", camera_inputs(root, args.sdk, args.arch, challenge))
if args.avc_media_only:
    challenge = args.probe_run_id or uuid.uuid4().hex
    write("entry/src/main/ets/pages/Index.ets",
          Path(__file__).with_name("avc_media_probe.ets").read_text().replace("__AVC_RUN_ID__", challenge))
    write("avc-media-probe-inputs.json", {"schema_version": 1, "run_id": challenge,
                                        "arch": args.arch, "role": "ordinary_app"})

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
    "-lnative_media_codecbase",
    "-lnative_media_acodec",
    "-lnative_media_venc",
    "-lnative_media_vdec",
    "-lnative_media_avsource",
    "-lnative_media_avdemuxer",
    "-lnative_media_avmuxer",
    "-lffrt.z",
    "-lohhicollie",
    "-luv",
    "-o",
    str(libs / "libcapabilityprobe.so"),
]
if args.vulkan_window_only:
    command = [str(native / "llvm/bin/clang"), "--target=" + triple,
               "--sysroot=" + str(native / "sysroot"), "-std=c11", "-shared", "-fPIC",
               "-O2", "-Wall", "-Wextra", "-Werror",
               str(Path(__file__).with_name("vulkan_window_probe.c").resolve()),
               "-lvulkan", "-lnative_window", "-lace_ndk.z", "-lace_napi.z",
               "-o", str(libs / "libvulkanwindowprobe.so")]
if args.arch == "armv7a":
    command[1:1] = ["-march=armv7-a", "-mfloat-abi=softfp", "-mfpu=neon"]
if args.userid_only:
    core = root / "userid-core.o"
    flags = ["-march=armv7-a", "-mfloat-abi=softfp", "-mfpu=neon"] if args.arch == "armv7a" else []
    subprocess.run([str(native / "llvm/bin/clang"), "--target=" + triple,
                    "--sysroot=" + str(native / "sysroot"), *flags, "-std=gnu11", "-fPIC", "-O2",
                    "-Wall", "-Wextra", "-Werror", "-DACCESS_TOKEN_USERID_LIBRARY", "-c",
                    str(Path(__file__).with_name("probes") / "access_token_userid.c"), "-o", str(core)], check=True)
    command = [str(native / "llvm/bin/clang++"), "--target=" + triple,
               "--sysroot=" + str(native / "sysroot"), *flags, "-std=c++17", "-shared", "-fPIC", "-O2",
               "-Wall", "-Wextra", "-Werror", str(Path(__file__).with_name("userid_hap_probe.cpp")),
               str(core), "-lace_napi.z", "-o", str(libs / "libuseridprobe.so")]
if args.audio_stream_only:
    flags = ["-march=armv7-a", "-mfloat-abi=softfp", "-mfpu=neon"] if args.arch == "armv7a" else []
    command = [str(native / "llvm/bin/clang++"), "--target=" + triple,
               "--sysroot=" + str(native / "sysroot"), *flags, "-std=c++17", "-shared", "-fPIC", "-O2",
               "-Wall", "-Wextra", "-Werror", str(Path(__file__).with_name("audio_stream_hap_probe.cpp")),
               str(Path(__file__).with_name("probes") / "audio_stream.cpp"), "-lace_napi.z", "-lohaudio",
               "-o", str(libs / "libaudiostreamprobe.so")]
if args.avc_media_only:
    flags = ["-march=armv7-a", "-mfloat-abi=softfp", "-mfpu=neon"] if args.arch == "armv7a" else []
    command = [str(native / "llvm/bin/clang++"), "--target=" + triple,
               "--sysroot=" + str(native / "sysroot"), *flags, "-std=c++17", "-shared", "-fPIC", "-O2",
               "-Wall", "-Wextra", "-Werror", str(Path(__file__).with_name("avc_media_hap_probe.cpp")),
               str(Path(__file__).with_name("probes") / "avc_media.cpp"), "-lace_napi.z",
               "-lnative_media_venc", "-lnative_media_vdec", "-lnative_media_codecbase", "-lnative_media_core",
               "-o", str(libs / "libavcmediaprobe.so")]
if args.audio_suite_effects_only:
    flags = ["-march=armv7-a", "-mfloat-abi=softfp", "-mfpu=neon"] if args.arch == "armv7a" else []
    command = [str(native / "llvm/bin/clang++"), "--target=" + triple,
               "--sysroot=" + str(native / "sysroot"), *flags, "-std=c++17", "-shared", "-fPIC", "-O2",
               "-Wall", "-Wextra", "-Werror", str(Path(__file__).with_name("audio_suite_effects_hap_probe.cpp")),
               str(Path(__file__).with_name("probes") / "audio_suite_effects.cpp"), "-lace_napi.z", "-lohaudiosuite",
               "-o", str(libs / "libaudiosuiteeffectsprobe.so")]
if args.camera_only:
    flags = ["-march=armv7-a", "-mfloat-abi=softfp", "-mfpu=neon"] if args.arch == "armv7a" else []
    command = [str(native / "llvm/bin/clang++"), "--target=" + triple,
               "--sysroot=" + str(native / "sysroot"), *flags, "-std=c++17", "-shared", "-fPIC", "-O2",
               "-Wall", "-Wextra", "-Werror", str(Path(__file__).with_name("camera_hap_probe.cpp")),
               str(Path(__file__).with_name("probes") / "camera_public.cpp"), "-lace_napi.z", "-lohcamera",
               "-o", str(libs / "libcamerapublicprobe.so")]
if args.arkts_exports_only:
    flags = ["-march=armv7-a", "-mfloat-abi=softfp", "-mfpu=neon"] if args.arch == "armv7a" else []
    command = [str(native / 'llvm/bin/clang++'), '--target=' + triple, '--sysroot=' + str(native / 'sysroot'),
               *flags, '-std=c++17', '-shared', '-fPIC', '-O2', '-Wall', '-Wextra', '-Werror',
               '-fno-exceptions', '-fno-rtti', '-nostdlib++',
               str(Path(__file__).with_name('arkts_exports_hap_probe.cpp')), '-lace_napi.z',
               '-o', str(libs / 'libarktsexportsprobe.so')]
if args.contact_sync_mode_only:
    flags = ["-march=armv7-a", "-mfloat-abi=softfp", "-mfpu=neon"] if args.arch == "armv7a" else []
    command = [str(native / 'llvm/bin/clang++'), '--target=' + triple, '--sysroot=' + str(native / 'sysroot'),
               *flags, '-std=c++17', '-shared', '-fPIC', '-O2', '-Wall', '-Wextra', '-Werror',
               '-fno-exceptions', '-fno-rtti', '-nostdlib++',
               str(Path(__file__).with_name('contact_sync_mode_hap_probe.cpp')), '-lace_napi.z',
               '-o', str(libs / 'libcontactsyncmodeprobe.so')]
if args.runtime_enum_only or args.curve_only:
    flags = ["-march=armv7-a", "-mfloat-abi=softfp", "-mfpu=neon"] if args.arch == "armv7a" else []
    command = [str(native / 'llvm/bin/clang++'), '--target=' + triple, '--sysroot=' + str(native / 'sysroot'),
               *flags, '-std=c++17', '-shared', '-fPIC', '-O2', '-Wall', '-Wextra', '-Werror',
               '-fno-exceptions', '-fno-rtti', '-nostdlib++',
               str(Path(__file__).with_name('runtime_enum_hap_probe.cpp')), '-lace_napi.z',
               '-o', str(libs / 'libruntimeenumprobe.so')]
if not (args.wifi_scan_only or args.image_metadata_only or args.thermal_only or args.completion_handler_only or args.web_only or args.i18n_only or args.matrix4_only or args.factory_objects_only or args.web_factory_only or args.const_enum_only or worker_only or args.binding_only or args.storage_stats_only or args.optional_phone_profile_only or args.photos_recent_only or args.photos_asset_only or args.settings_navigation_only):
    subprocess.run(command, check=True)
    if not (args.vulkan_window_only or args.arkts_exports_only or args.contact_sync_mode_only or args.runtime_enum_only or args.curve_only):
        shutil.copy2(native / "llvm/lib" / triple / "libc++_shared.so", libs / "libc++_shared.so")

environment = dict(os.environ, OHOS_SDK_HOME=str(args.sdk))
subprocess.run(
    [args.arkdown, "build", "--project", str(root), "--target", "hap", "--mode", "debug"],
    cwd=root,
    env=environment,
    check=True,
)
output = root / "entry/build/default/outputs/default"
if minimal_app:
    # The Rust signing helper does not emit the code-sign block required by
    # the OHOS 7 guest. Sign this unsigned HAP with sign_web_probe.py instead.
    print(output / "entry-default-unsigned.hap")
    raise SystemExit(0)
sign_command = [
    args.hap_sign,
    "sign",
    str(output / "entry-default-unsigned.hap"),
    "--bundle-name",
    bundle,
    "--compatible-version",
    "17",
    "--device-id",
    args.udid,
    "--apl",
    args.apl,
    "--app-feature",
    args.app_feature,
]
for permission in args.restricted_permission:
    sign_command.extend(["--restricted-permission", permission])
sign_command.extend([
    "--output",
    str(output / "entry-default-signed.hap"),
    "--force",
])
subprocess.run(sign_command, check=True)
print(output / "entry-default-signed.hap")
