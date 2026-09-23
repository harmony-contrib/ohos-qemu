#!/usr/bin/env python3
"""Audit system-app providers used behind public OHOS APIs on phone and 2in1.

SysCap and System Ability checks cannot detect an API whose service delegates to
a missing, disabled, wrongly signed, or wrongly named HAP.  This audit joins
production source references with the packaged HAP inventory and live BMS state.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import subprocess
from typing import Any


DEVICES = ("phone", "2in1")
# Public APIs are implemented outside base/foundation too.  In particular,
# Driver Kit backends live under drivers, Ark runtime APIs under arkcompiler,
# common utility APIs under commonlibrary, and device-side DFX APIs under
# developtools.  A fixed four-directory scan silently omitted those provider
# and dlopen dependencies.
PRODUCTION_SOURCE_AREAS = (
    "applications",
    "arkcompiler",
    "base",
    "commonlibrary",
    "domains",
    "drivers",
    "foundation",
)
RUNTIME_SOURCE_AREAS = PRODUCTION_SOURCE_AREAS + ("developtools",)
FRAMEWORK_OR_SERVICE_AREAS = frozenset(PRODUCTION_SOURCE_AREAS) - {"applications"}
# Broad reverse-domain syntax used while parsing explicit bundle declarations
# and the image inventory.  Production source scanning applies a second,
# semantic retention filter below; scanning this expression alone would also
# collect UTD identifiers, event names, property keys, and host names.
BUNDLE_RE = re.compile(r"(?:com|ohos|org|net|cn)(?:\.[A-Za-z0-9_]+)+")
CORE_PROVIDER_NAMESPACE_RE = re.compile(r"com\.(?:ohos|hmos|huawei|usb)\.")

RULES: tuple[dict[str, Any], ...] = (
    {
        "id": "ability-share-picker",
        "public_surfaces": ["UIAbilityContext.startAbilityByType('share')"],
        "syscaps": ["SystemCapability.Ability.AbilityRuntime.Core"],
        "providers": ["com.ohos.sharepickerdialog"],
        "implementation_targets": ["com.ohos.sharepickerdialog"],
        "required_entrypoints": ["PickerDialog"],
    },
    {
        "id": "ability-send-data-implicit-handler",
        "public_surfaces": [
            "UIAbilityContext.startAbility/startAbilityForResult with ohos.want.action.sendData"
        ],
        "syscaps": [
            "SystemCapability.Ability.AbilityRuntime.Core",
            "SystemCapability.ArkUI.ArkUI.Full",
        ],
        "providers": [
            "com.ohos.bluetooth",
            "com.ohos.calendar",
            "com.ohos.mms",
            "com.ohos.spooler",
        ],
        "implementation_targets": [],
        "provider_mode": "any",
        "required_actions": ["ohos.want.action.sendData"],
    },
    {
        "id": "arkui-expanded-text-menu",
        "public_surfaces": [
            "ArkUI TextMenuItemId SEARCH/SHARE/url/email/phoneNumber/address/dateTime",
            "ArkUI native ARKUI_TEXT_MENU_ITEM_ID_* actions",
            "ArkUI collaboration and application-store menu flows",
        ],
        "syscaps": ["SystemCapability.ArkUI.ArkUI.Full"],
        # The packaged OHOS 7 implementation loads this proprietary plug-in.
        # Its GetAPPName table maps phone/email to Contacts and the remaining
        # entity actions to the Huawei Browser, Calendar, Maps, and
        # SuperDevice bundles.  The QEMU images contain neither the plug-in
        # nor those latter providers.
        "providers": [
            "com.ohos.contacts",
            "com.huawei.hmos.browser",
            "com.huawei.hmos.calendar",
            "com.huawei.hmos.maps.app",
            "com.huawei.hmos.superdevice",
        ],
        "implementation_targets": [
            "com.ohos.contacts",
            "com.huawei.hmos.browser",
            "com.huawei.hmos.calendar",
            "com.huawei.hmos.maps.app",
            "com.huawei.hmos.superdevice",
        ],
        "required_actions": [
            "ohos.want.action.search",
            "ohos.want.action.appdetail",
        ],
        "required_files": [
            "/system/lib64/expanded_menu/libexpanded_menu.z.so",
        ],
    },
    {
        "id": "arkui-text-service-plugins",
        "public_surfaces": [
            "ArkUI TextMenuItemId.SHARE and Text/RichEditor/Web share actions",
            "ArkUI TextMenuItemId.TRANSLATE",
            "ArkUI Text/RichEditor enableDataDetector and dataDetectorConfig",
        ],
        "syscaps": ["SystemCapability.ArkUI.ArkUI.Full"],
        "providers": [],
        "implementation_targets": [],
        # All three loaders fall back to implementations which return failure,
        # an empty result, or no-op when the product plug-in is absent.
        "required_files": [
            "/system/lib64/libsystemshare_innerkits.z.so",
            "/system/lib64/libai_text_translation_innerapi.z.so",
            "/system/lib64/libai_text_analyzer_innerapi.z.so",
        ],
    },
    {
        "id": "app-domain-verification-extension",
        "public_surfaces": [
            "@ohos.bundle.appDomainVerify associated-domain queries backed by verified state",
            "HTTP/HTTPS implicit Want conversion using verified application domains",
        ],
        "syscaps": ["SystemCapability.BundleManager.AppDomainVerify"],
        "providers": [],
        "implementation_targets": [],
        "required_files": [
            "/system/lib64/libapp_domain_verify_extension.z.so",
        ],
    },
    {
        "id": "audio-vivid-metadata-runtime-plugin",
        "public_surfaces": [
            "AVCodec Kit OH_AudioVividMetaBuilder_* API 26 functions",
        ],
        "syscaps": ["SystemCapability.Multimedia.Media.Core"],
        "providers": [],
        "implementation_targets": [],
        # libnative_media_core exposes the documented functions, but Create
        # and CreateEmptyBuilder return AV_ERR_UNSUPPORT without this builder.
        "required_files": [
            "/system/lib64/libAudioVividMetaBuilder.z.so",
        ],
    },
    {
        "id": "selection-input-extension-runtime",
        "public_surfaces": [
            "SelectionExtensionAbility API 26 ANI/ArkTS extension runtime",
            "@ohos.selectionInput.selectionManager panel and content flows",
        ],
        "syscaps": ["SystemCapability.SelectionInput.Selection"],
        "providers": ["com.selection.selectionapplication"],
        "implementation_targets": ["com.selection.selectionapplication"],
        "required_files": [
            "/system/lib64/libselection_extension_ani.z.so",
        ],
    },
    {
        "id": "advertising-service-provider",
        "public_surfaces": ["@ohos.advertising and AdComponent ad loading/rendering APIs"],
        "syscaps": ["SystemCapability.Advertising.Ads"],
        "providers": ["com.samples.AdsServiceDemo"],
        "implementation_targets": ["com.samples.AdsServiceDemo"],
        "required_entrypoints": [
            "AdsCoreService",
            "FullScreenAdAbility",
            "AdsUIExtensionAbility",
            "JsBridgeService",
        ],
    },
    {
        "id": "cloud-sync-service-extension",
        "public_surfaces": [
            "@ohos.data.cloudData",
            "relationalStore RdbStore.cloudSync/cloudSyncEx",
            "@ohos.file.cloudSync and cloudSyncManager",
        ],
        "syscaps": [
            "SystemCapability.DistributedDataManager.CloudSync.Client",
            "SystemCapability.DistributedDataManager.CloudSync.Config",
            "SystemCapability.DistributedDataManager.CloudSync.Server",
            "SystemCapability.FileManagement.DistributedFileService.CloudSync.Core",
            "SystemCapability.FileManagement.DistributedFileService.CloudSyncManager",
        ],
        # The packaged libylong_cloud_extension/libconn_adapter implementation
        # unconditionally connects this sample service.  Neither product
        # supplies it or a parameter/config indirection for a real provider.
        "providers": ["com.example.cloudsync"],
        "implementation_targets": ["com.example.cloudsync"],
        "required_entrypoints": ["ServiceExtAbility"],
    },
    {
        "id": "distributed-hardware-ui",
        "public_surfaces": ["@ohos.distributedHardware.deviceManager UI flows"],
        "syscaps": ["SystemCapability.DistributedHardware.DeviceManager"],
        "providers": ["com.ohos.dhardwareui"],
        "implementation_targets": ["com.ohos.dhardwareui"],
        "required_entrypoints": ["MechExtAbility", "DHardwareUIAbility"],
    },
    {
        "id": "device-manager-pairing-ui",
        "public_surfaces": ["@ohos.distributedDeviceManager authentication and pairing UI"],
        "syscaps": ["SystemCapability.DistributedHardware.DeviceManager"],
        "providers": ["com.ohos.devicemanagerui"],
        "implementation_targets": ["com.ohos.devicemanagerui"],
        "required_entrypoints": ["ConfirmUIExtAbility", "PincodeUIExtAbility", "InputUIExtAbility"],
    },
    {
        "id": "dlp-management-ui",
        "public_surfaces": ["@ohos.dlpPermission"],
        "syscaps": ["SystemCapability.Security.DataLossPrevention"],
        "providers": ["com.ohos.dlpmanager"],
        "implementation_targets": ["com.ohos.dlpmanager"],
        "required_entrypoints": ["MainAbilityEx", "SaveAsAbility"],
    },
    {
        "id": "dlp-credential-service",
        "public_surfaces": ["@ohos.dlpPermission credential and watermark integration"],
        "syscaps": ["SystemCapability.Security.DataLossPrevention"],
        "providers": ["com.huawei.hmos.dlpcredmgr"],
        "implementation_targets": ["com.huawei.hmos.dlpcredmgr"],
        "required_entrypoints": ["DlpPermServiceAbility"],
    },
    {
        "id": "photo-picker-and-photo-ui",
        "public_surfaces": [
            "PhotoViewPicker",
            "PhotoAccessHelper UI operations",
            "@ohos.file.RecentPhotoComponent",
        ],
        "syscaps": ["SystemCapability.FileManagement.PhotoAccessHelper.Core"],
        "providers": ["com.ohos.photos"],
        "implementation_targets": ["com.ohos.photos"],
        "required_entrypoints": [
            "PickerUIExtensionAbility",
            "DeleteUIExtensionAbility",
            "SaveUIExtensionAbility",
            "RecentUIExtensionAbility",
            "RecentPhotoInfoAbility",
            "DefaultAlbumNameUIExtensionAbility",
        ],
    },
    {
        "id": "photo-fa-card-service",
        "public_surfaces": ["PhotoAccessHelper FA card and cloud-change notification integration"],
        "syscaps": [
            "SystemCapability.FileManagement.PhotoAccessHelper.Core",
            "SystemCapability.Ability.Form",
        ],
        "providers": ["com.ohos.photos"],
        "implementation_targets": ["com.huawei.hmos.photos"],
        "required_entrypoints": ["FACardServiceAbility"],
    },
    {
        "id": "media-library-mtp-service",
        "public_surfaces": ["USB MTP server media-library handoff"],
        "syscaps": ["SystemCapability.USB.USBManager"],
        "providers": ["com.ohos.medialibrary.medialibrarydata"],
        "implementation_targets": ["com.ohos.medialibrary.medialibrarydata"],
        "required_entrypoints": ["MtpService"],
        "applicable_devices": ["phone"],
    },
    {
        "id": "print-spooler",
        "public_surfaces": ["@ohos.print", "@ohos.printManager"],
        "syscaps": ["SystemCapability.Print.PrintFramework"],
        "providers": ["com.ohos.spooler"],
        "implementation_targets": ["com.ohos.spooler"],
        "required_entrypoints": ["PrintServiceExtAbility", "PluginPrintIconExtAbility"],
    },
    {
        "id": "calendar-data",
        "public_surfaces": ["@ohos.calendarManager including event reminder callbacks"],
        "syscaps": ["SystemCapability.Applications.CalendarData"],
        "providers": ["com.ohos.calendardata"],
        "implementation_targets": ["com.ohos.calendardata"],
        "required_entrypoints": ["EditorUIExtensionAbility", "ReminderCallbackExtAbility"],
    },
    {
        "id": "calendar-whole-datashare-authority",
        "public_surfaces": [
            "@ohos.calendarManager operations granted READ_WHOLE_CALENDAR or WRITE_WHOLE_CALENDAR"
        ],
        "syscaps": ["SystemCapability.Applications.CalendarData"],
        "providers": ["com.ohos.calendardata"],
        "implementation_targets": ["com.ohos.calendardata"],
        "required_uri_authorities": ["calendardata_whole"],
    },
    {
        "id": "calendar-reminder-ui",
        "public_surfaces": ["@ohos.calendarManager event reminder notification handoff"],
        "syscaps": ["SystemCapability.Applications.CalendarData"],
        "providers": ["com.ohos.calendar"],
        "implementation_targets": ["com.ohos.calendar"],
        "required_entrypoints": ["MainAbility"],
    },
    {
        "id": "media-control-ui",
        "public_surfaces": ["AVCastPickerHelper", "AVCastPicker", "AVInputCastPicker", "AVVolumePanel"],
        "syscaps": ["SystemCapability.Multimedia.AVSession.Core"],
        "providers": ["com.hmos.mediacontroller"],
        "implementation_targets": ["com.ohos.mediacontroller", "com.hmos.mediacontroller"],
        "required_entrypoints": ["UIExtAbility", "AVVolumeExtension", "AVInputCastPickerAbility", "DialogExtension"],
    },
    {
        "id": "avsession-desktop-lyrics",
        "public_surfaces": [
            "AVSession.enableDesktopLyric and desktop-lyric state/visibility APIs"
        ],
        "syscaps": ["SystemCapability.Multimedia.AVSession.Core"],
        "providers": ["com.ohos.mediacontroller"],
        "implementation_targets": ["com.ohos.mediacontroller"],
        "required_entrypoints": ["DesktopLyricAbility"],
    },
    {
        "id": "file-picker",
        "public_surfaces": ["@ohos.file.picker", "@ohos.file.fileAccess"],
        "syscaps": ["SystemCapability.FileManagement.UserFileService"],
        "providers": ["com.ohos.filepicker", "com.ohos.filemanager"],
        "implementation_targets": ["com.ohos.filepicker", "com.ohos.filemanager"],
        "provider_mode": "any",
        "required_entrypoints": ["FilePickerUIExtAbility"],
    },
    {
        "id": "external-file-manager",
        "public_surfaces": ["@ohos.file.volumeManager", "StorageManager file-access UI"],
        "syscaps": ["SystemCapability.FileManagement.StorageService"],
        "providers": ["com.ohos.UserFile.ExternalFileManager"],
        "implementation_targets": ["com.ohos.UserFile.ExternalFileManager"],
    },
    {
        "id": "privacy-center",
        "public_surfaces": ["relational-store privacy and silent-access UI"],
        "syscaps": ["SystemCapability.DistributedDataManager.RelationalStore.Core"],
        "providers": ["com.ohos.security.privacycenter"],
        "implementation_targets": ["com.ohos.security.privacycenter"],
    },
    {
        "id": "permission-manager-dialogs",
        "public_surfaces": ["AccessToken permission request, permission settings and security-component dialogs"],
        "syscaps": ["SystemCapability.Security.AccessToken"],
        "providers": ["com.ohos.permissionmanager"],
        "implementation_targets": ["com.ohos.permissionmanager"],
        "required_entrypoints": [
            "GrantAbility",
            "GlobalExtAbility",
            "SecurityExtAbility",
            "PermissionStateSheetAbility",
            "GlobalSwitchSheetAbility",
            "MainAbility",
            "OpenSettingAbility",
        ],
    },
    {
        "id": "accessibility-screen-reader",
        "public_surfaces": ["AccessibilityManager screen-reader enablement and accessibility shortcut"],
        "syscaps": [
            "SystemCapability.BarrierFree.Accessibility.Core",
            "SystemCapability.BarrierFree.Accessibility.Vision",
        ],
        "providers": [
            "com.ohos.screenreader",
            "com.ohos.hmos.screenreader",
            "com.huawei.hmos.screenreader",
        ],
        "implementation_targets": [
            "com.ohos.screenreader",
            "com.ohos.hmos.screenreader",
            "com.huawei.hmos.screenreader",
        ],
        "provider_mode": "any",
        "required_entrypoints": ["AccessibilityExtAbility"],
    },
    {
        "id": "accessibility-caption-assistant",
        "public_surfaces": ["Accessibility CaptionsManager caption assistant activation"],
        "syscaps": ["SystemCapability.BarrierFree.Accessibility.Hearing"],
        "providers": [
            "com.ohos.vassistant",
            "com.hmos.vassistant",
            "com.huawei.hmos.vassistant",
        ],
        "implementation_targets": [
            "com.ohos.vassistant",
            "com.hmos.vassistant",
            "com.huawei.hmos.vassistant",
        ],
        "provider_mode": "any",
        "required_entrypoints": ["AiCaptionServiceExtAbility"],
    },
    {
        "id": "accessibility-settings-integration",
        "public_surfaces": [
            "AccessibilityManager configuration, shortcut and repeated-click settings integration"
        ],
        "syscaps": [
            "SystemCapability.BarrierFree.Accessibility.Core",
            "SystemCapability.BarrierFree.Accessibility.Vision",
        ],
        "providers": ["com.ohos.settings"],
        "implementation_targets": ["com.ohos.settings"],
        "required_entrypoints": ["SettingsExtService", "IgnoreRepeatClickExtService"],
    },
    {
        "id": "location-dialog",
        "public_surfaces": ["location permission and switch dialogs"],
        "syscaps": ["SystemCapability.Location.Location.Core"],
        "providers": ["com.ohos.locationdialog"],
        "implementation_targets": ["com.ohos.locationdialog"],
        "required_entrypoints": ["LocationPrivacyExtAbility"],
    },
    {
        "id": "location-privacy-detail-ui",
        "public_surfaces": ["Location privacy dialog detail-page handoff"],
        "syscaps": ["SystemCapability.Location.Location.Core"],
        "providers": ["com.huawei.hmos.location"],
        "implementation_targets": ["com.huawei.hmos.location"],
        "required_entrypoints": ["LocationPrivacyDetailAbility"],
    },
    {
        "id": "bluetooth-dialog",
        "public_surfaces": ["Bluetooth pairing and sharing UI"],
        "syscaps": ["SystemCapability.Communication.Bluetooth.Core"],
        "providers": ["com.ohos.bluetooth"],
        "implementation_targets": ["com.ohos.bluetooth"],
    },
    {
        "id": "camera-picker-ui",
        "public_surfaces": ["@ohos.multimedia.cameraPicker", "camera capture UI"],
        "syscaps": ["SystemCapability.Multimedia.Camera.Core"],
        "providers": ["com.ohos.camera"],
        "implementation_targets": ["com.ohos.camera"],
        # Phone and 2in1 are both non-TV devices.  The OHOS 7 NAPI/ANI
        # implementation defaults to the UIAbility branch and launches
        # PickerAbility; ExtensionPickerAbility is selected only for TV.
        "required_entrypoints": ["PickerAbility"],
    },
    {
        "id": "settings-ui",
        "public_surfaces": ["Settings UIExtension and settings ability flows"],
        "syscaps": ["SystemCapability.Applications.Settings.Core"],
        "providers": ["com.ohos.settings"],
        "implementation_targets": ["com.ohos.settings"],
    },
    {
        "id": "settings-navigation-api",
        "public_surfaces": [
            "@ohos.settings openNetworkManagerSettings",
            "@ohos.settings openInputMethodSettings/openInputMethodDetail",
            "@ohos.settings open*SettingsPage APIs",
        ],
        "syscaps": ["SystemCapability.Applications.Settings.Core"],
        "providers": ["com.ohos.settings"],
        "implementation_targets": ["com.huawei.hmos.settings"],
        "required_entrypoints": [
            "com.huawei.hmos.settings.MainAbility",
            "OpenNetworkUIExtensionAbility",
            "ExternalCommonUIExtensionAbility",
        ],
    },
    {
        "id": "settings-app-info-implicit-action",
        "public_surfaces": ["@ohos.settings openAppDetailSettingsPage"],
        "syscaps": ["SystemCapability.Applications.Settings.Core"],
        "providers": ["com.ohos.settings"],
        "implementation_targets": [],
        "required_actions": ["action.settings.app.info"],
    },
    {
        "id": "system-ui",
        "public_surfaces": ["notification, system-dialog, status-bar and screen-lock UI"],
        "syscaps": ["SystemCapability.Notification.Notification"],
        "providers": ["com.ohos.systemui", "com.ohos.sceneboard"],
        "implementation_targets": ["com.ohos.systemui", "com.ohos.sceneboard"],
        "provider_mode": "any",
    },
    {
        "id": "launcher-ui",
        "public_surfaces": ["launcher and recent-task UI"],
        "syscaps": ["SystemCapability.BundleManager.BundleFramework.Launcher"],
        "providers": ["com.ohos.launcher", "com.ohos.sceneboard"],
        "implementation_targets": ["com.ohos.launcher", "com.ohos.sceneboard"],
        "provider_mode": "any",
    },
    {
        "id": "contacts-ui",
        "public_surfaces": ["@ohos.contact selectContact/selectContacts picker APIs"],
        "syscaps": ["SystemCapability.Applications.Contacts"],
        "providers": ["com.ohos.contacts"],
        "implementation_targets": ["com.ohos.contacts"],
        "required_entrypoints": ["ContactUiExtentionAbility"],
    },
    {
        "id": "telephony-call-and-message-ui",
        "public_surfaces": ["call-management and SMS/MMS UI flows"],
        "syscaps": ["SystemCapability.Telephony.CallManager", "SystemCapability.Telephony.SmsMms"],
        "providers": ["com.ohos.callui", "com.ohos.mms"],
        "implementation_targets": ["com.ohos.callui", "com.ohos.mms"],
        "provider_mode": "all",
    },
    {
        "id": "telephony-spam-shield-service",
        "public_surfaces": ["CallManager incoming-call spam detection and NumberMarkInfo"],
        "syscaps": ["SystemCapability.Telephony.CallManager"],
        "providers": ["com.spamshield"],
        "implementation_targets": ["com.spamshield"],
        "required_entrypoints": ["SpamShieldServiceExtAbility"],
        "applicable_devices": ["phone"],
    },
    {
        "id": "telephony-antifraud-hsdr-service",
        "public_surfaces": ["CallManager incoming-call anti-fraud cloud result integration"],
        "syscaps": ["SystemCapability.Telephony.CallManager"],
        "providers": ["com.hmos.hsdr"],
        "implementation_targets": ["com.hmos.hsdr"],
        "required_entrypoints": ["HSDRService"],
        "applicable_devices": ["phone"],
    },
    {
        "id": "intelligent-scene",
        "public_surfaces": ["@ohos.intelligentScene"],
        "syscaps": ["SystemCapability.Applications.IntelligentScene"],
        "providers": ["com.ohos.intelligentscene"],
        "implementation_targets": ["com.ohos.intelligentscene"],
    },
    {
        "id": "emergency-communication",
        "public_surfaces": ["telephony emergency communication UI"],
        "syscaps": ["SystemCapability.Telephony.CoreService"],
        "providers": ["com.ohos.emergencycommunication"],
        "implementation_targets": ["com.ohos.emergencycommunication"],
    },
    {
        "id": "enterprise-provisioning",
        "public_surfaces": ["@ohos.enterprise.adminManager provisioning"],
        "syscaps": ["SystemCapability.Customization.EnterpriseDeviceManager"],
        "providers": ["com.ohos.adminprovisioning"],
        "implementation_targets": ["com.ohos.adminprovisioning"],
    },
    {
        "id": "wallpaper-ui",
        "public_surfaces": ["@ohos.wallpaper UI extension operations"],
        "syscaps": ["SystemCapability.MiscServices.Wallpaper"],
        "providers": ["com.ohos.wallpaper"],
        "implementation_targets": ["com.ohos.wallpaper"],
    },
    {
        "id": "usb-dialog",
        "public_surfaces": ["@ohos.usbManager permission and function-switch dialogs"],
        "syscaps": ["SystemCapability.USB.USBManager"],
        "providers": ["com.usb.right"],
        "implementation_targets": ["com.usb.right"],
        "stale_config_targets": ["com.usb.function"],
        "required_entrypoints": ["UsbFunctionSwitchExtAbility"],
    },
    {
        "id": "notification-enable-dialog",
        "public_surfaces": ["Notification authorization dialog"],
        "syscaps": ["SystemCapability.Notification.Notification"],
        "providers": ["com.ohos.notificationdialog"],
        "implementation_targets": ["com.ohos.notificationdialog"],
        "required_entrypoints": ["EnableNotificationDialog"],
    },
    {
        "id": "notification-extension-subscription-settings",
        "public_surfaces": [
            "@ohos.notificationExtensionSubscription.openSubscriptionSettings",
            "@ohos.notificationExtensionSubscription.openSubscriptionSettingsWithResult",
        ],
        "syscaps": ["SystemCapability.Notification.Notification"],
        "providers": ["com.ohos.sceneboard"],
        "implementation_targets": ["com.ohos.sceneboard"],
        "required_entrypoints": ["NotificationAccessGrantUIExtensionAbility"],
    },
    {
        "id": "notification-manager-settings",
        "public_surfaces": [
            "@ohos.notificationManager.openNotificationSettings",
            "@ohos.notificationManager.openNotificationSettingsWithResult",
        ],
        "syscaps": ["SystemCapability.Notification.NotificationSettings"],
        "providers": ["com.ohos.sceneboard"],
        "implementation_targets": ["com.ohos.sceneboard"],
        "required_entrypoints": ["NotificationManangerUIExtensionAbility"],
    },
    {
        "id": "pasteboard-privacy-dialog",
        "public_surfaces": ["Pasteboard privacy toast and progress UI"],
        "syscaps": ["SystemCapability.MiscServices.Pasteboard"],
        "providers": ["com.ohos.pasteboarddialog"],
        "implementation_targets": ["com.ohos.pasteboarddialog"],
        "required_entrypoints": ["ToastExtensionAbility", "PasteboardProgressAbility"],
    },
    {
        "id": "background-task-authorization-dialog",
        "public_surfaces": ["BackgroundTaskManager continuous-task authorization UI"],
        "syscaps": ["SystemCapability.ResourceSchedule.BackgroundTaskManager.ContinuousTask"],
        "providers": ["com.ohos.backgroundtaskmgr.resources"],
        "implementation_targets": ["com.ohos.backgroundtaskmgr.resources"],
        "required_entrypoints": ["EnableBgTaskAuthDialog"],
    },
    {
        "id": "input-method-chooser-dialog",
        "public_surfaces": ["InputMethodController input-method chooser"],
        "syscaps": ["SystemCapability.MiscServices.InputMethodFramework"],
        "providers": ["com.ohos.inputmethodchoosedialog"],
        "implementation_targets": ["com.ohos.inputmethodchoosedialog"],
        "required_entrypoints": ["InputMethod"],
    },
    {
        "id": "vpn-dialog",
        "public_surfaces": ["VpnExtension authorization and status UI"],
        "syscaps": ["SystemCapability.Communication.NetManager.Vpn"],
        "providers": ["com.ohos.vpndialog"],
        "implementation_targets": ["com.ohos.vpndialog", "com.huawei.hmos.vpndialog"],
        "required_entrypoints": ["VpnServiceExtAbility"],
    },
    {
        "id": "network-policy-settings-ui",
        "public_surfaces": ["@ohos.net.policy.showAppNetPolicySettings"],
        "syscaps": ["SystemCapability.Communication.NetManager.Core"],
        "providers": ["com.huawei.hmos.communicationsetting"],
        "implementation_targets": ["com.huawei.hmos.communicationsetting"],
        "required_entrypoints": ["NetAccessPolicySettingUIExtension"],
        "applicable_devices": ["phone"],
    },
    {
        "id": "network-statistics-settings-ui",
        "public_surfaces": ["network usage-limit notification settings handoff"],
        "syscaps": ["SystemCapability.Communication.NetManager.Core"],
        "providers": ["com.huawei.hmos.settings"],
        "implementation_targets": ["com.huawei.hmos.settings"],
        "required_entrypoints": ["com.huawei.hmos.settings.MainAbility"],
    },
    {
        "id": "telephony-apn-settings-ui",
        "public_surfaces": ["@ohos.telephony.data.showSystemApnSettings"],
        "syscaps": ["SystemCapability.Telephony.CellularData"],
        "providers": ["com.huawei.hmos.callsetting"],
        "implementation_targets": ["com.huawei.hmos.callsetting"],
        "required_entrypoints": ["GeneralCallSettingDialogAbility"],
    },
    {
        "id": "wifi-service-dialogs",
        "public_surfaces": ["Wi-Fi STA and hotspot system notification actions"],
        "syscaps": [
            "SystemCapability.Communication.WiFi.STA",
            "SystemCapability.Communication.WiFi.AP.Core",
        ],
        "providers": ["com.ohos.locationdialog"],
        "implementation_targets": ["com.ohos.locationdialog"],
        "required_entrypoints": ["WifiServiceAbility", "HotSpotServiceAbility"],
    },
    {
        "id": "wifi-captive-portal",
        "public_surfaces": ["Wi-Fi captive-portal authentication handoff"],
        "syscaps": ["SystemCapability.Communication.WiFi.STA"],
        "providers": ["com.wifiservice.portallogin"],
        "implementation_targets": ["com.wifiservice.portallogin"],
        "required_entrypoints": ["EntryAbility"],
    },
    {
        "id": "certificate-manager-dialog",
        "public_surfaces": ["CertificateManagerDialog certificate picker and management UI"],
        "syscaps": ["SystemCapability.Security.CertificateManagerDialog"],
        "providers": ["com.ohos.certmanager"],
        "implementation_targets": ["com.ohos.certmanager"],
        "required_entrypoints": ["MainExtensionAbility", "CertPickerUIExtAbility"],
    },
    {
        "id": "screen-capture-privacy-dialog",
        "public_surfaces": ["AVScreenCapture privacy and authorization modal UI"],
        "syscaps": ["SystemCapability.Multimedia.Media.AVScreenCapture"],
        "providers": ["com.ohos.systemui"],
        "implementation_targets": ["com.ohos.systemui"],
        "required_entrypoints": ["com.ohos.systemui.dialog"],
    },
    {
        "id": "user-auth-widget",
        "public_surfaces": ["UserAuth authentication modal UI"],
        "syscaps": ["SystemCapability.UserIAM.UserAuth.Core"],
        "providers": ["com.ohos.useriam.authwidget"],
        "implementation_targets": ["com.ohos.useriam.authwidget"],
        "required_entrypoints": ["userauthuiextensionability"],
    },
    {
        "id": "user-auth-application-modal",
        "public_surfaces": ["@ohos.userIAM.userAuth WidgetParam.uiContext application-modal authentication"],
        "syscaps": ["SystemCapability.UserIAM.UserAuth.Core"],
        "providers": ["com.ohos.useriam.authwidget"],
        "implementation_targets": ["com.ohos.useriam.authwidget"],
        "required_entrypoints": ["UserAuthModalUIAbility"],
        "applicable_devices": ["2in1"],
    },
    {
        "id": "form-render-service",
        "public_surfaces": ["FormExtension hosted rendering"],
        "syscaps": ["SystemCapability.Ability.Form"],
        "providers": ["com.ohos.formrenderservice"],
        "implementation_targets": ["com.ohos.formrenderservice"],
        "required_entrypoints": ["ServiceExtension"],
    },
    {
        "id": "power-and-thermal-dialog",
        "public_surfaces": ["PowerManager and ThermalManager system UI"],
        "syscaps": [
            "SystemCapability.PowerManager.PowerManager.Core",
            "SystemCapability.PowerManager.ThermalManager",
        ],
        "providers": ["com.ohos.powerdialog"],
        "implementation_targets": ["com.ohos.powerdialog"],
        "required_entrypoints": ["PowerUiExtensionAbility"],
    },
    {
        "id": "ability-manager-system-dialog",
        "public_surfaces": ["AbilityManager selector, interceptor, user-switch and assertion dialogs"],
        "syscaps": ["SystemCapability.Ability.AbilityRuntime.Core"],
        "providers": ["com.ohos.amsdialog"],
        "implementation_targets": ["com.ohos.amsdialog"],
        "required_entrypoints": ["SelectorDialog", "JumpInterceptorDialog", "SwitchUserDialog"],
    },
    {
        "id": "print-vendor-extension",
        "public_surfaces": ["PrintService printer discovery and vendor extension"],
        "syscaps": ["SystemCapability.Print.PrintFramework"],
        "providers": ["com.ohos.hwprintext"],
        "implementation_targets": ["com.ohos.hwprintext"],
    },
    {
        "id": "print-remote-printer-service",
        "public_surfaces": ["PrintManager printer discovery remote-printer integration"],
        "syscaps": ["SystemCapability.Print.PrintFramework"],
        "providers": ["com.ohos.remotesvc"],
        "implementation_targets": ["com.ohos.remotesvc"],
        "required_entrypoints": ["RemoteServiceExtAbility"],
    },
    {
        "id": "print-voice-assistant-action",
        "public_surfaces": ["Print job notification AI action on PC/2in1"],
        "syscaps": ["SystemCapability.Print.PrintFramework"],
        "providers": ["com.ohos.vassistant"],
        "implementation_targets": ["com.ohos.vassistant"],
        "required_entrypoints": ["VoicePcServiceExtAbility"],
        "applicable_devices": ["2in1"],
    },
    {
        "id": "wallpaper-launcher-extension",
        "public_surfaces": ["Wallpaper service extension synchronization when ThemeService is absent"],
        "syscaps": ["SystemCapability.MiscServices.Wallpaper"],
        "providers": ["com.ohos.launcher"],
        "implementation_targets": ["com.ohos.launcher"],
        "required_entrypoints": ["WallpaperExtAbility"],
    },
    {
        "id": "telephony-number-identity-service",
        "public_surfaces": ["CallManager number-mark data refresh and number identity integration"],
        "syscaps": ["SystemCapability.Telephony.CallManager"],
        "providers": ["com.numberidentity"],
        "implementation_targets": ["com.numberidentity"],
        "required_entrypoints": ["NumberIdentityServiceExtAbility"],
    },
)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ohos-root", required=True, type=Path)
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--matrix", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    return parser.parse_args()


def read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def enabled_bundles(path: Path) -> set[str]:
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()
        if BUNDLE_RE.fullmatch(line.strip())
    }


def runtime_parameters(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    pattern = re.compile(r"\bparam:\s*([^=\s]+)=(.*)$")
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        match = pattern.search(line)
        if match:
            values[match.group(1)] = match.group(2).strip()
    return values


def source_references(
    root: Path,
    canonical_bundles: set[str],
) -> tuple[Counter[str], dict[str, list[str]], dict[str, Counter[str]]]:
    paths = [root / name for name in PRODUCTION_SOURCE_AREAS if (root / name).is_dir()]
    command = [
        "rg", "-n", "--no-heading", "-o", BUNDLE_RE.pattern,
        *map(str, paths),
        "-g", "*.c", "-g", "*.cc", "-g", "*.cpp", "-g", "*.cxx",
        "-g", "*.h", "-g", "*.hpp", "-g", "*.ets", "-g", "*.ts", "-g", "*.js",
        "-g", "*.json", "-g", "*.json5", "-g", "*.cfg", "-g", "*.conf",
        "-g", "!**/test/**", "-g", "!**/tests/**", "-g", "!**/unittest/**",
        "-g", "!**/unittests/**", "-g", "!**/fuzztest/**", "-g", "!**/fuzz/**",
        "-g", "!**/example/**", "-g", "!**/examples/**", "-g", "!**/sample/**",
        "-g", "!**/samples/**", "-g", "!**/app_samples/**", "-g", "!**/mock/**",
        "-g", "!**/build/**", "-g", "!**/out/**",
    ]
    proc = subprocess.run(command, check=False, capture_output=True, text=True)
    if proc.returncode not in (0, 1):
        raise RuntimeError(proc.stderr.strip() or "rg source scan failed")
    counts: Counter[str] = Counter()
    locations: dict[str, list[str]] = defaultdict(list)
    areas: dict[str, Counter[str]] = defaultdict(Counter)
    for line in proc.stdout.splitlines():
        match = re.match(r"(.+?):(\d+):(" + BUNDLE_RE.pattern + r")$", line)
        if not match:
            continue
        bundle = match.group(3).rstrip(".")
        if not CORE_PROVIDER_NAMESPACE_RE.match(bundle) and not any(
            bundle == known
            or bundle.startswith(known + ".")
            or bundle.startswith(known + "_")
            for known in canonical_bundles
        ):
            continue
        counts[bundle] += 1
        try:
            relative = Path(match.group(1)).relative_to(root)
            area = relative.parts[0] if relative.parts else "unknown"
        except ValueError:
            relative = Path(match.group(1))
            area = "external"
        areas[bundle][area] += 1
        if len(locations[bundle]) < 20:
            source = str(relative)
            locations[bundle].append(f"{source}:{match.group(2)}")
    return counts, locations, areas


def source_declared_bundles(root: Path) -> dict[str, list[str]]:
    """Collect actual app bundle declarations for token normalization."""
    paths = [root / name for name in PRODUCTION_SOURCE_AREAS if (root / name).is_dir()]
    command = [
        "rg", "-n", "bundleName", *map(str, paths),
        "-g", "**/AppScope/app.json", "-g", "**/AppScope/app.json5",
        "-g", "!**/test/**", "-g", "!**/tests/**", "-g", "!**/ohosTest/**",
        "-g", "!**/example/**", "-g", "!**/examples/**",
        "-g", "!**/sample/**", "-g", "!**/samples/**",
    ]
    proc = subprocess.run(command, check=False, capture_output=True, text=True)
    if proc.returncode not in (0, 1):
        raise RuntimeError(proc.stderr.strip() or "rg bundle declaration scan failed")
    declared: dict[str, list[str]] = defaultdict(list)
    declaration = re.compile(
        r"^(.+?):(\d+):.*?[\"']bundleName[\"']\s*:\s*[\"'](" + BUNDLE_RE.pattern + r")[\"']"
    )
    for line in proc.stdout.splitlines():
        match = declaration.match(line)
        if not match:
            continue
        try:
            source = str(Path(match.group(1)).relative_to(root))
        except ValueError:
            source = match.group(1)
        declared[match.group(3)].append(f"{source}:{match.group(2)}")
    return declared


def source_uri_authorities(
    root: Path,
) -> tuple[Counter[str], dict[str, list[str]], dict[str, Counter[str]], dict[str, set[str]]]:
    """Inventory literal DataShare/DataAbility/FileAccess provider authorities."""
    paths = [root / name for name in PRODUCTION_SOURCE_AREAS if (root / name).is_dir()]
    # Require an alphanumeric first and last character.  Framework code also
    # contains regular expressions such as ``datashare://.*?/media``; treating
    # the ``.`` wildcard as a provider authority creates a false missing
    # provider on every product.
    authority_pattern = r"[A-Za-z0-9](?:[A-Za-z0-9_.-]*[A-Za-z0-9])?"
    uri_pattern = (
        r"(?:datashare|dataability|fileAccess|ServiceExtension):///?"
        + authority_pattern
    )
    command = [
        "rg", "-n", "--no-heading", "-o", uri_pattern, *map(str, paths),
        "-g", "*.c", "-g", "*.cc", "-g", "*.cpp", "-g", "*.cxx",
        "-g", "*.h", "-g", "*.hpp", "-g", "*.ets", "-g", "*.ts", "-g", "*.js",
        "-g", "*.json", "-g", "*.json5", "-g", "*.cfg", "-g", "*.conf",
        "-g", "!**/test/**", "-g", "!**/tests/**", "-g", "!**/unittest/**",
        "-g", "!**/unittests/**", "-g", "!**/fuzztest/**", "-g", "!**/fuzz/**",
        "-g", "!**/example/**", "-g", "!**/examples/**", "-g", "!**/sample/**",
        "-g", "!**/samples/**", "-g", "!**/app_samples/**", "-g", "!**/mock/**",
        "-g", "!**/build/**", "-g", "!**/out/**",
    ]
    proc = subprocess.run(command, check=False, capture_output=True, text=True)
    if proc.returncode not in (0, 1):
        raise RuntimeError(proc.stderr.strip() or "rg source URI authority scan failed")
    counts: Counter[str] = Counter()
    locations: dict[str, list[str]] = defaultdict(list)
    areas: dict[str, Counter[str]] = defaultdict(Counter)
    schemes: dict[str, set[str]] = defaultdict(set)
    result_pattern = re.compile(
        r"^(.+?):(\d+):([A-Za-z]+):///?(" + authority_pattern + r")$"
    )
    for line in proc.stdout.splitlines():
        match = result_pattern.match(line)
        if not match:
            continue
        authority = match.group(4)
        counts[authority] += 1
        schemes[authority].add(match.group(3))
        try:
            relative = Path(match.group(1)).relative_to(root)
            area = relative.parts[0] if relative.parts else "unknown"
        except ValueError:
            relative = Path(match.group(1))
            area = "external"
        areas[authority][area] += 1
        if len(locations[authority]) < 20:
            locations[authority].append(f"{relative}:{match.group(2)}")
    return counts, locations, areas, schemes


def source_want_actions(
    root: Path,
) -> tuple[Counter[str], dict[str, list[str]], dict[str, Counter[str]]]:
    """Inventory standard implicit-Want action tokens in production sources.

    These actions are resolved through HAP ``skills`` instead of an explicit
    bundle/ability pair.  They need a separate join against the live product's
    enabled bundles; otherwise a payload-only handler looks usable in source
    and package inspection while BMS cannot resolve it.
    """
    paths = [root / name for name in PRODUCTION_SOURCE_AREAS if (root / name).is_dir()]
    action_pattern = (
        r"(?:ohos\.want\.action\.[A-Za-z0-9_.-]+"
        r"|action\.(?:system|form|settings|access)\.[A-Za-z0-9_.-]+"
        r"|com\.ohos\.action\.[A-Za-z0-9_.-]+"
        r"|collaborationFwk\.[A-Za-z0-9_.-]+)"
    )
    command = [
        "rg", "-n", "--no-heading", "-o", action_pattern, *map(str, paths),
        "-g", "*.c", "-g", "*.cc", "-g", "*.cpp", "-g", "*.cxx",
        "-g", "*.h", "-g", "*.hpp", "-g", "*.ets", "-g", "*.ts", "-g", "*.js",
        "-g", "*.json", "-g", "*.json5", "-g", "*.cfg", "-g", "*.conf",
        "-g", "!**/test/**", "-g", "!**/tests/**", "-g", "!**/unittest/**",
        "-g", "!**/unittests/**", "-g", "!**/fuzztest/**", "-g", "!**/fuzz/**",
        "-g", "!**/example/**", "-g", "!**/examples/**", "-g", "!**/sample/**",
        "-g", "!**/samples/**", "-g", "!**/app_samples/**", "-g", "!**/mock/**",
        "-g", "!**/build/**", "-g", "!**/out/**",
    ]
    proc = subprocess.run(command, check=False, capture_output=True, text=True)
    if proc.returncode not in (0, 1):
        raise RuntimeError(proc.stderr.strip() or "rg implicit Want action scan failed")
    counts: Counter[str] = Counter()
    locations: dict[str, list[str]] = defaultdict(list)
    areas: dict[str, Counter[str]] = defaultdict(Counter)
    result_pattern = re.compile(r"^(.+?):(\d+):(" + action_pattern + r")$")
    for line in proc.stdout.splitlines():
        match = result_pattern.match(line)
        if not match:
            continue
        action = match.group(3)
        counts[action] += 1
        try:
            relative = Path(match.group(1)).relative_to(root)
            area = relative.parts[0] if relative.parts else "unknown"
        except ValueError:
            relative = Path(match.group(1))
            area = "external"
        areas[action][area] += 1
        if len(locations[action]) < 20:
            locations[action].append(f"{relative}:{match.group(2)}")
    return counts, locations, areas


def source_runtime_libraries(root: Path) -> dict[str, Any]:
    """Inventory production dlopen targets without assuming they are packaged.

    Literal first arguments and file-local string constants are resolved. Calls
    assembled from parameters, configuration, or multiple variables remain in
    an explicit unresolved list instead of disappearing from the audit.
    """
    paths = [root / name for name in RUNTIME_SOURCE_AREAS if (root / name).is_dir()]
    command = [
        "rg", "-l", r"\bdlopen\s*\(", *map(str, paths),
        "-g", "*.c", "-g", "*.cc", "-g", "*.cpp", "-g", "*.cxx",
        "-g", "*.h", "-g", "*.hpp",
        "-g", "!**/test/**", "-g", "!**/tests/**", "-g", "!**/unittest/**",
        "-g", "!**/unittests/**", "-g", "!**/fuzztest/**", "-g", "!**/fuzz/**",
        "-g", "!**/example/**", "-g", "!**/examples/**", "-g", "!**/sample/**",
        "-g", "!**/samples/**", "-g", "!**/app_samples/**", "-g", "!**/mock/**",
        "-g", "!**/demo/**", "-g", "!**/ohosTest/**", "-g", "!**/build/**",
        "-g", "!**/out/**", "-g", "!**/test_main.*",
    ]
    proc = subprocess.run(command, check=False, capture_output=True, text=True)
    if proc.returncode not in (0, 1):
        raise RuntimeError(proc.stderr.strip() or "rg dlopen scan failed")

    library_re = re.compile(
        r"^(?:/?[A-Za-z0-9_.+%{}-]+/)*lib[A-Za-z0-9_.+%{}-]+(?:\.z)?\.so$"
    )
    quoted_re = re.compile(r"[\"']([^\"']+)[\"']")
    assignment_res = (
        re.compile(
            r"#\s*define\s+([A-Za-z_][A-Za-z0-9_]*)\s+[\"']([^\"']+)[\"']"
        ),
        re.compile(
            r"\b([A-Za-z_][A-Za-z0-9_]*)\s*(?:\[\s*\])?\s*(?:=|\{)\s*"
            r"[\"']([^\"']+)[\"']"
        ),
    )
    references: dict[str, list[dict[str, Any]]] = defaultdict(list)
    areas: dict[str, Counter[str]] = defaultdict(Counter)
    unresolved: list[dict[str, Any]] = []
    callsite_count = 0
    resolved_callsite_count = 0

    for raw_path in proc.stdout.splitlines():
        path = Path(raw_path)
        try:
            source_text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        relative = str(path.relative_to(root))
        area = relative.split("/", 1)[0]
        constants: dict[str, set[str]] = defaultdict(set)
        for pattern in assignment_res:
            for match in pattern.finditer(source_text):
                value = match.group(2)
                if library_re.fullmatch(value):
                    constants[match.group(1)].add(value)

        for call in re.finditer(r"\bdlopen\s*\(", source_text):
            callsite_count += 1
            start = call.end()
            index = start
            nested = 0
            quote: str | None = None
            escaped = False
            while index < len(source_text):
                char = source_text[index]
                if quote:
                    if escaped:
                        escaped = False
                    elif char == "\\":
                        escaped = True
                    elif char == quote:
                        quote = None
                elif char in "\"'":
                    quote = char
                elif char == "(":
                    nested += 1
                elif char == ")":
                    if nested == 0:
                        break
                    nested -= 1
                elif char == "," and nested == 0:
                    break
                index += 1
            expression = source_text[start:index].strip()
            line = source_text.count("\n", 0, call.start()) + 1
            values: set[str] = set()
            literal = quoted_re.fullmatch(expression)
            if literal and library_re.fullmatch(literal.group(1)):
                values.add(literal.group(1))
            else:
                identifier_match = re.match(r"([A-Za-z_][A-Za-z0-9_]*)", expression)
                if identifier_match:
                    values.update(constants.get(identifier_match.group(1), set()))
            if values:
                resolved_callsite_count += 1
                for value in sorted(values):
                    references[value].append({
                        "location": f"{relative}:{line}",
                        "argument_expression": expression[:300],
                    })
                    areas[value][area] += 1
            else:
                unresolved.append({
                    "location": f"{relative}:{line}",
                    "argument_expression": expression[:300],
                })

    return {
        "references": references,
        "areas": areas,
        "callsite_count": callsite_count,
        "resolved_callsite_count": resolved_callsite_count,
        "unresolved_calls": unresolved,
    }


def direct_element_targets(
    root: Path,
) -> tuple[
    Counter[tuple[str, str]],
    dict[tuple[str, str], list[str]],
    dict[tuple[str, str], Counter[str]],
    dict[str, Any],
]:
    """Find literal bundle/entrypoint pairs used to launch an ability.

    The broad token inventory deliberately retains constants and namespaces,
    but only a semantic pair proves that a string is used as a launch target.
    This pass catches public component implementations such as Calendar
    ``editEvent`` and RecentPhotoComponent without requiring a hand-written
    rule before the missing entrypoint becomes visible.
    """
    paths = [root / name for name in PRODUCTION_SOURCE_AREAS if (root / name).is_dir()]
    command = [
        "rg", "-l", "SetElementName|SetAbilityName|bundleName", *map(str, paths),
        "-g", "*.c", "-g", "*.cc", "-g", "*.cpp", "-g", "*.cxx",
        "-g", "*.h", "-g", "*.hpp", "-g", "*.ets", "-g", "*.ts", "-g", "*.js",
        "-g", "!**/test/**", "-g", "!**/tests/**", "-g", "!**/unittest/**",
        "-g", "!**/unittests/**", "-g", "!**/fuzztest/**", "-g", "!**/fuzz/**",
        "-g", "!**/example/**", "-g", "!**/examples/**", "-g", "!**/sample/**",
        "-g", "!**/samples/**", "-g", "!**/app_samples/**", "-g", "!**/mock/**",
        "-g", "!**/demo/**", "-g", "!**/ohosTest/**", "-g", "!**/build/**", "-g", "!**/out/**",
    ]
    proc = subprocess.run(command, check=False, capture_output=True, text=True)
    if proc.returncode not in (0, 1):
        raise RuntimeError(proc.stderr.strip() or "rg direct element target scan failed")
    quoted_bundle = r"((?:com|ohos)\.[A-Za-z0-9_.]+)"
    quoted_entrypoint = r"([A-Za-z0-9_.]+)"
    patterns = (
        re.compile(
            r"SetElementName\s*\(\s*[\"']" + quoted_bundle
            + r"[\"']\s*,\s*[\"']" + quoted_entrypoint + r"[\"']",
            re.DOTALL,
        ),
    )
    counts: Counter[tuple[str, str]] = Counter()
    locations: dict[tuple[str, str], list[str]] = defaultdict(list)
    areas: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    cpp_callsite_count = 0
    resolved_cpp_callsite_count = 0
    unresolved_calls: list[dict[str, str]] = []
    js_element_object_count = 0
    resolved_js_element_object_count = 0
    unresolved_js_objects: list[dict[str, str]] = []

    # Launch constants are often declared in a companion header instead of
    # the call-site file.  Retain only globally unambiguous definitions;
    # generic names such as BUNDLE_NAME deliberately remain unresolved when
    # multiple subsystems assign different values to them.
    constant_command = [
        "rg", "-n", "--no-heading", "-o",
        r"\b[A-Za-z_][A-Za-z0-9_]*\s*(?:\[\s*\])?\s*=\s*[\"'][^\"']+[\"']",
        *map(str, paths),
        "-g", "*.c", "-g", "*.cc", "-g", "*.cpp", "-g", "*.cxx",
        "-g", "*.h", "-g", "*.hpp", "-g", "*.ets", "-g", "*.ts", "-g", "*.js",
        "-g", "!**/test/**", "-g", "!**/tests/**", "-g", "!**/unittest/**",
        "-g", "!**/unittests/**", "-g", "!**/fuzztest/**", "-g", "!**/fuzz/**",
        "-g", "!**/mock/**", "-g", "!**/build/**", "-g", "!**/out/**",
    ]
    constant_proc = subprocess.run(constant_command, check=False, capture_output=True, text=True)
    if constant_proc.returncode not in (0, 1):
        raise RuntimeError(constant_proc.stderr.strip() or "rg global launch-constant scan failed")
    global_constant_values: dict[str, set[str]] = defaultdict(set)
    constant_result = re.compile(
        r".+?:\d+:([A-Za-z_][A-Za-z0-9_]*)\s*(?:\[\s*\])?\s*=\s*[\"']([^\"']+)[\"']$"
    )
    for line in constant_proc.stdout.splitlines():
        match = constant_result.match(line)
        if match:
            global_constant_values[match.group(1)].add(match.group(2))
    global_constants = {
        name: next(iter(values)) for name, values in global_constant_values.items() if len(values) == 1
    }

    def call_arguments(text: str, name_pattern: str) -> list[tuple[int, str]]:
        """Return balanced argument text for calls, including multiline calls."""
        result: list[tuple[int, str]] = []
        for match in re.finditer(name_pattern + r"\s*\(", text):
            start = match.end()
            depth = 1
            quote: str | None = None
            escaped = False
            index = start
            while index < len(text) and depth:
                char = text[index]
                if quote:
                    if escaped:
                        escaped = False
                    elif char == "\\":
                        escaped = True
                    elif char == quote:
                        quote = None
                elif char in "\"'":
                    quote = char
                elif char == "(":
                    depth += 1
                elif char == ")":
                    depth -= 1
                index += 1
            if depth == 0:
                result.append((match.start(), text[start:index - 1]))
        return result

    def split_arguments(value: str) -> list[str]:
        result: list[str] = []
        start = 0
        depth = 0
        quote: str | None = None
        escaped = False
        for index, char in enumerate(value):
            if quote:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = None
            elif char in "\"'":
                quote = char
            elif char in "([{<":
                depth += 1
            elif char in ")]}>":
                depth = max(0, depth - 1)
            elif char == "," and depth == 0:
                result.append(value[start:index].strip())
                start = index + 1
        result.append(value[start:].strip())
        return result

    def member_call_arguments(
        value: str, method_pattern: str
    ) -> list[tuple[str, int, str]]:
        """Return receiver, position and balanced arguments for member calls."""
        result: list[tuple[str, int, str]] = []
        pattern = re.compile(
            r"\b([A-Za-z_][A-Za-z0-9_]*)\s*(?:\.|->)\s*"
            + method_pattern
            + r"\s*\("
        )
        for match in pattern.finditer(value):
            start = match.end()
            depth = 1
            quote: str | None = None
            escaped = False
            index = start
            while index < len(value) and depth:
                char = value[index]
                if quote:
                    if escaped:
                        escaped = False
                    elif char == "\\":
                        escaped = True
                    elif char == quote:
                        quote = None
                elif char in "\"'":
                    quote = char
                elif char == "(":
                    depth += 1
                elif char == ")":
                    depth -= 1
                index += 1
            if depth == 0:
                result.append((match.group(1), match.start(), value[start:index - 1]))
        return result

    def brace_pairs(value: str) -> list[tuple[int, int]]:
        """Return object-like brace spans without crossing strings/comments.

        ArkTS/TS/JS Want objects may put ``abilityName`` before
        ``bundleName``.  A flat proximity regex both misses that order and can
        pair fields from adjacent objects.  Brace scopes let us require both
        properties to belong to the same object.
        """
        stack: list[int] = []
        result: list[tuple[int, int]] = []
        quote: str | None = None
        escaped = False
        line_comment = False
        block_comment = False
        index = 0
        while index < len(value):
            char = value[index]
            following = value[index + 1] if index + 1 < len(value) else ""
            if line_comment:
                if char == "\n":
                    line_comment = False
            elif block_comment:
                if char == "*" and following == "/":
                    block_comment = False
                    index += 1
            elif quote:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = None
            elif char == "/" and following == "/":
                line_comment = True
                index += 1
            elif char == "/" and following == "*":
                block_comment = True
                index += 1
            elif char in "\"'`":
                quote = char
            elif char == "{":
                stack.append(index)
            elif char == "}" and stack:
                result.append((stack.pop(), index))
            index += 1
        return result

    for filename in proc.stdout.splitlines():
        path = Path(filename)
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
            relative = path.relative_to(root)
        except (OSError, ValueError):
            continue
        area = relative.parts[0] if relative.parts else "unknown"
        file_matches: set[tuple[tuple[str, str], int]] = set()
        for pattern in patterns:
            for match in pattern.finditer(text):
                pair = (match.group(1), match.group(2))
                line = text.count("\n", 0, match.start()) + 1
                file_matches.add((pair, line))

        # Resolve file-local string constants used by C/C++ launch calls.  A
        # literal-only scan misses precisely the prefix-drift cases where the
        # provider name is factored into SETTINGS_PACKAGE_NAME or
        # VPN_DIALOG_BUNDLENAME.
        assignments: dict[str, list[tuple[int, str | None]]] = defaultdict(list)
        for match in re.finditer(
            r"\b([A-Za-z_][A-Za-z0-9_]*)\s*(?:\[\s*\])?\s*=\s*([^;,\n]+)",
            text,
        ):
            expression = match.group(2).strip()
            literal = re.match(r"(?:std::string\s*\(\s*)?[\"']([^\"']+)[\"']", expression)
            assignments[match.group(1)].append((match.start(), literal.group(1) if literal else None))
        for match in re.finditer(r"^\s*#\s*define\s+([A-Za-z_][A-Za-z0-9_]*)\s+[\"']([^\"']+)[\"']", text,
                                 re.MULTILINE):
            assignments[match.group(1)].append((match.start(), match.group(2)))
        for values in assignments.values():
            values.sort()

        def resolve(argument: str, position: int) -> str | None:
            argument = argument.strip()
            if len(argument) >= 2 and argument[0] in "\"'" and argument[-1] == argument[0]:
                return argument[1:-1]
            normalized = re.sub(r"\.c_str\s*\(\s*\)$", "", argument).strip()
            wrapper = re.fullmatch(r"(?:std::)?string\s*\(\s*(.+)\s*\)", normalized)
            if wrapper:
                normalized = wrapper.group(1).strip()
            name = re.split(r"::|\.", normalized)[-1]
            preceding = [item for item in assignments.get(name, []) if item[0] < position]
            if preceding:
                return preceding[-1][1]
            return global_constants.get(name)

        if path.suffix in {".ets", ".ts", ".js"} and not path.name.endswith((".d.ts", ".d.ets")):
            spans = brace_pairs(text)
            innermost: dict[int, tuple[int, int]] = {}

            def enclosing_span(position: int) -> tuple[int, int] | None:
                if position not in innermost:
                    candidates = [span for span in spans if span[0] < position < span[1]]
                    if candidates:
                        innermost[position] = min(candidates, key=lambda span: span[1] - span[0])
                return innermost.get(position)

            field_pattern = re.compile(
                r"[\"']?(bundleName|abilityName)[\"']?\s*:\s*"
                r"((?:[\"'][^\"']*[\"'])|(?:[A-Za-z_][A-Za-z0-9_:.]*))"
            )
            scoped_fields: dict[tuple[int, int], dict[str, list[tuple[int, str]]]] = defaultdict(
                lambda: defaultdict(list)
            )
            for field in field_pattern.finditer(text):
                span = enclosing_span(field.start())
                if span:
                    scoped_fields[span][field.group(1)].append((field.start(), field.group(2)))
            for span, fields in scoped_fields.items():
                bundles = fields.get("bundleName", [])
                abilities = fields.get("abilityName", [])
                if len(bundles) != 1 or len(abilities) != 1:
                    continue
                scope_prefix = text[max(0, span[0] - 160):span[0]]
                if re.search(
                    r"(?:\b(?:interface|class|enum|namespace)\s+[A-Za-z_][A-Za-z0-9_]*"
                    r"|\btype\s+[A-Za-z_][A-Za-z0-9_]*(?:\s*<[^;{}]+>)?\s*=)\s*$",
                    scope_prefix,
                ):
                    continue
                bundle_position, bundle_expression = bundles[0]
                ability_position, ability_expression = abilities[0]
                type_expressions = {"string", "number", "boolean", "object", "undefined"}
                if (
                    bundle_expression in type_expressions
                    or ability_expression in type_expressions
                ):
                    continue
                placeholder_values = {"", "undefined", "null"}
                if (
                    bundle_expression.strip("\"'") in placeholder_values
                    and ability_expression.strip("\"'") in placeholder_values
                ):
                    continue
                js_element_object_count += 1
                bundle = resolve(bundle_expression, bundle_position)
                entrypoint = resolve(ability_expression, ability_position)
                line = text.count("\n", 0, span[0]) + 1
                if not bundle or not entrypoint or not BUNDLE_RE.fullmatch(bundle):
                    unresolved_js_objects.append({
                        "source": f"{relative}:{line}",
                        "area": area,
                        "bundle_expression": bundle_expression[:300],
                        "entrypoint_expression": ability_expression[:300],
                    })
                    continue
                resolved_js_element_object_count += 1
                file_matches.add(((bundle, entrypoint), line))

        cpp_calls = call_arguments(text, r"\bSetElementName")
        # Direct ElementName constructors passed to Want::SetElement or other
        # launch APIs use (deviceId, bundleName, abilityName[, moduleName]).
        cpp_calls.extend(call_arguments(text, r"(?<!Set)\bElementName"))
        for position, argument_text in cpp_calls:
            arguments = split_arguments(argument_text)
            cpp_callsite_count += 1
            if len(arguments) == 2:
                bundle_arg, entrypoint_arg = arguments
            elif len(arguments) >= 3:
                bundle_arg, entrypoint_arg = arguments[1:3]
            else:
                bundle_arg = entrypoint_arg = ""
            bundle = resolve(bundle_arg, position)
            entrypoint = resolve(entrypoint_arg, position)
            if not bundle or not entrypoint or not BUNDLE_RE.fullmatch(bundle):
                line = text.count("\n", 0, position) + 1
                unresolved_calls.append({
                    "source": f"{relative}:{line}",
                    "area": area,
                    "bundle_expression": bundle_arg[:300],
                    "entrypoint_expression": entrypoint_arg[:300],
                })
                continue
            resolved_cpp_callsite_count += 1
            line = text.count("\n", 0, position) + 1
            file_matches.add(((bundle, entrypoint), line))

        # Some framework paths construct an ElementName by calling the two
        # setters separately.  Pair only calls on the same receiver in the
        # same innermost brace scope, and only when they are close enough to
        # represent one construction.  Dynamic values remain explicit
        # unresolved records instead of disappearing from the inventory.
        setter_bundles = member_call_arguments(text, r"SetBundle(?:Name)?")
        setter_abilities = member_call_arguments(text, r"SetAbilityName")
        setter_spans = brace_pairs(text)

        def setter_scope(position: int) -> tuple[int, int] | None:
            candidates = [span for span in setter_spans if span[0] < position < span[1]]
            return min(candidates, key=lambda span: span[1] - span[0]) if candidates else None

        used_abilities: set[int] = set()
        for receiver, bundle_position, bundle_expression in setter_bundles:
            bundle_scope = setter_scope(bundle_position)
            candidates = [
                (index, ability_position, ability_expression)
                for index, (ability_receiver, ability_position, ability_expression)
                in enumerate(setter_abilities)
                if index not in used_abilities
                and ability_receiver == receiver
                and setter_scope(ability_position) == bundle_scope
                and abs(ability_position - bundle_position) <= 2000
            ]
            if not candidates:
                continue
            ability_index, ability_position, ability_expression = min(
                candidates, key=lambda item: abs(item[1] - bundle_position)
            )
            used_abilities.add(ability_index)
            cpp_callsite_count += 1
            bundle_args = split_arguments(bundle_expression)
            ability_args = split_arguments(ability_expression)
            bundle_arg = bundle_args[0] if len(bundle_args) == 1 else bundle_expression
            entrypoint_arg = ability_args[0] if len(ability_args) == 1 else ability_expression
            bundle = resolve(bundle_arg, bundle_position)
            entrypoint = resolve(entrypoint_arg, ability_position)
            line = text.count("\n", 0, min(bundle_position, ability_position)) + 1
            if not bundle or not entrypoint or not BUNDLE_RE.fullmatch(bundle):
                unresolved_calls.append({
                    "source": f"{relative}:{line}",
                    "area": area,
                    "kind": "paired_element_setters",
                    "bundle_expression": bundle_arg[:300],
                    "entrypoint_expression": entrypoint_arg[:300],
                })
                continue
            resolved_cpp_callsite_count += 1
            file_matches.add(((bundle, entrypoint), line))

        for pair, line in sorted(file_matches):
            counts[pair] += 1
            areas[pair][area] += 1
            if len(locations[pair]) < 20:
                locations[pair].append(f"{relative}:{line}")
    return counts, locations, areas, {
        "cpp_element_launch_callsite_count": cpp_callsite_count,
        "resolved_cpp_element_launch_callsite_count": resolved_cpp_callsite_count,
        "unresolved_cpp_element_launch_callsite_count": cpp_callsite_count - resolved_cpp_callsite_count,
        "unresolved_cpp_element_launch_calls": unresolved_calls,
        "js_element_object_count": js_element_object_count,
        "resolved_js_element_object_count": resolved_js_element_object_count,
        "unresolved_js_element_object_count":
            js_element_object_count - resolved_js_element_object_count,
        "unresolved_js_element_objects": unresolved_js_objects,
    }


def bundle_state(bundle: str, enabled: set[str], payload: set[str], configured: set[str]) -> str:
    if bundle in enabled:
        return "enabled"
    if bundle in payload:
        return "payload_not_enabled"
    if bundle in configured:
        return "configured_but_payload_missing"
    return "absent"


def has_entrypoint(available: set[str], required: str) -> bool:
    return any(value == required or value.endswith("." + required) for value in available)


def element_target_state(bundle: str, entrypoint: str, data: dict[str, Any]) -> str:
    state = bundle_state(bundle, data["enabled"], data["payload"], data["configured"])
    if state != "enabled":
        return state
    if not has_entrypoint(data["entrypoints"].get(bundle, set()), entrypoint):
        return "entrypoint_missing"
    return "enabled"


def uri_provider_state(rows: list[dict[str, Any]], data: dict[str, Any]) -> str:
    """Summarise all HAP providers declaring the same URI authority."""
    states = {
        bundle_state(row["bundle"], data["enabled"], data["payload"], data["configured"])
        for row in rows
        if row.get("bundle")
    }
    for state in ("enabled", "payload_not_enabled", "configured_but_payload_missing", "absent"):
        if state in states:
            return state
    return "absent"


def main() -> int:
    args = arguments()
    declared_bundles = source_declared_bundles(args.ohos_root)
    matrix = {row["syscap"]: row for row in read(args.matrix)["capabilities"]}
    device_data: dict[str, dict[str, Any]] = {}
    known_bundles: set[str] = set()
    for device in DEVICES:
        root = args.runtime_root / f"arm64-{device}"
        preinstall = read(root / "preinstalled-hap-audit.json")
        config = read(root / "config-bundle-reference-audit.json")
        payload = {row["bundle"] for row in preinstall["haps"] if row.get("bundle")}
        enabled = enabled_bundles(root / "bundles.txt")
        configured = {row["bundle"] for row in config["references"]}
        entrypoints: dict[str, set[str]] = defaultdict(set)
        action_handlers: dict[str, list[dict[str, Any]]] = defaultdict(list)
        uri_providers: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in preinstall["haps"]:
            if not row.get("bundle"):
                continue
            for kind in ("abilities", "extensions"):
                for item in row.get(kind, []):
                    if item.get("name"):
                        entrypoints[row["bundle"]].add(item["name"])
                    for skill in item.get("skills", []):
                        for action in skill.get("actions", []):
                            action_handlers[action].append({
                                "bundle": row["bundle"],
                                "entrypoint": item.get("name"),
                                "component_kind": "ability" if kind == "abilities" else "extension",
                                "entities": sorted(skill.get("entities", [])),
                                "uris": skill.get("uris", []),
                                "domain_verify": skill.get("domainVerify"),
                            })
        for row in preinstall.get("extension_uri_providers", []):
            if row.get("authority"):
                uri_providers[row["authority"].lower()].append(row)
        known_bundles.update(payload | enabled | configured)
        device_data[device] = {
            "enabled": enabled,
            "payload": payload,
            "configured": configured,
            "certificate_mismatches": {
                row["bundle"] for row in preinstall["certificate_mismatches"] if row.get("bundle")
            },
            "path_mismatches": {
                bundle
                for row in preinstall.get("preinstall_path_mismatch_candidates", [])
                for bundle in [Path(row["app_dir"]).name]
            },
            "entrypoints": entrypoints,
            "action_handlers": action_handlers,
            "uri_providers": uri_providers,
            "parameters": runtime_parameters(root / "parameters.txt"),
            "filesystem": {
                line.strip()
                for line in (root / "filesystem-manifest.txt").read_text(
                    encoding="utf-8", errors="ignore"
                ).splitlines()
                if line.strip().startswith("/")
            },
        }

    all_rule_targets = {
        bundle
        for rule in RULES
        for key in ("providers", "implementation_targets", "stale_config_targets")
        for bundle in rule.get(key, [])
    }
    # Every semantically retained production provider candidate is kept.  The
    # previous implementation first
    # intersected source tokens with already-known packages, which hid exactly
    # the most important case: a framework naming a provider that is absent
    # from both the image and its install configuration.
    canonical_bundles = known_bundles | all_rule_targets | set(declared_bundles)
    counts, locations, areas = source_references(args.ohos_root, canonical_bundles)
    uri_counts, uri_locations, uri_areas, uri_schemes = source_uri_authorities(args.ohos_root)
    action_counts, action_locations, action_areas = source_want_actions(args.ohos_root)
    runtime_library_scan = source_runtime_libraries(args.ohos_root)
    target_counts, target_locations, target_areas, target_scan = direct_element_targets(args.ohos_root)
    source_rows: list[dict[str, Any]] = []
    for token in sorted(counts):
        candidates = [
            bundle
            for bundle in canonical_bundles
            if token == bundle or token.startswith(bundle + ".") or token.startswith(bundle + "_")
        ]
        bundle = max(candidates, key=len) if candidates else None
        authority_key = token.lower()
        authority_rows = {
            device: device_data[device]["uri_providers"].get(authority_key, [])
            for device in DEVICES
        }
        is_uri_authority = not bundle and any(authority_rows.values())
        source_rows.append({
            "token": token,
            "normalized_bundle": bundle,
            "classification": (
                "exact_bundle"
                if token == bundle
                else "bundle_entrypoint_or_namespace"
                if bundle
                else "extension_uri_authority"
                if is_uri_authority
                else "nonlocal_namespace_or_external_bundle"
            ),
            "declared_in_source_tree": bool(bundle and bundle in declared_bundles),
            "declaration_locations": declared_bundles.get(bundle, [])[:10] if bundle else [],
            "production_source_reference_count": counts[token],
            "source_area_counts": dict(sorted(areas[token].items())),
            "sample_locations": sorted(set(locations[token]))[:20],
            "extension_uri_providers": {
                device: [
                    {
                        "bundle": row.get("bundle"),
                        "entrypoint": row.get("entrypoint"),
                        "extension_type": row.get("extension_type"),
                        "uri": row.get("uri"),
                    }
                    for row in authority_rows[device]
                ]
                for device in DEVICES
            },
            "devices": {
                device: (
                    bundle_state(
                        bundle,
                        device_data[device]["enabled"],
                        device_data[device]["payload"],
                        device_data[device]["configured"],
                    )
                    if bundle
                    else uri_provider_state(authority_rows[device], device_data[device])
                    if authority_rows[device]
                    else "unresolved_token"
                )
                for device in DEVICES
            },
        })

    uri_authority_rows: list[dict[str, Any]] = []
    for authority in sorted(uri_counts, key=str.lower):
        devices: dict[str, Any] = {}
        for device in DEVICES:
            data = device_data[device]
            provider_rows = data["uri_providers"].get(authority.lower(), [])
            bundle_by_lower = {
                bundle.lower(): bundle
                for bundle in data["enabled"] | data["payload"] | data["configured"]
            }
            proxy_bundle = bundle_by_lower.get(authority.lower())
            if provider_rows:
                state = uri_provider_state(provider_rows, data)
                classification = "declared_extension_authority"
            elif proxy_bundle:
                state = "proxy_bundle_" + bundle_state(
                    proxy_bundle, data["enabled"], data["payload"], data["configured"]
                )
                classification = "proxy_bundle_authority"
            else:
                state = "unresolved_authority"
                classification = "unresolved_authority"
            devices[device] = {
                "classification": classification,
                "state": state,
                "proxy_bundle": proxy_bundle,
                "extension_providers": [
                    {
                        "bundle": row.get("bundle"),
                        "entrypoint": row.get("entrypoint"),
                        "extension_type": row.get("extension_type"),
                        "uri": row.get("uri"),
                    }
                    for row in provider_rows
                ],
            }
        uri_authority_rows.append({
            "authority": authority,
            "schemes": sorted(uri_schemes[authority]),
            "production_source_reference_count": uri_counts[authority],
            "source_area_counts": dict(sorted(uri_areas[authority].items())),
            "sample_locations": sorted(set(uri_locations[authority]))[:20],
            "devices": devices,
        })

    want_action_rows: list[dict[str, Any]] = []
    for action in sorted(action_counts):
        devices: dict[str, Any] = {}
        for device in DEVICES:
            data = device_data[device]
            handlers = data["action_handlers"].get(action, [])
            handler_rows = [
                {
                    **handler,
                    "constraint_bound": bool(
                        handler.get("entities")
                        or handler.get("uris")
                        or handler.get("domain_verify")
                    ),
                    "state": bundle_state(
                        handler["bundle"], data["enabled"], data["payload"], data["configured"]
                    ),
                }
                for handler in handlers
            ]
            states = {handler["state"] for handler in handler_rows}
            enabled_handler_rows = [
                handler for handler in handler_rows if handler["state"] == "enabled"
            ]
            if any(not handler["constraint_bound"] for handler in enabled_handler_rows):
                state = "enabled_handler"
            elif enabled_handler_rows:
                state = "enabled_handler_constraint_match_required"
            elif "payload_not_enabled" in states:
                state = "handler_payload_not_enabled"
            elif "configured_but_payload_missing" in states:
                state = "handler_configured_but_payload_missing"
            elif "absent" in states:
                state = "handler_absent"
            else:
                state = "no_preinstalled_handler"
            devices[device] = {"state": state, "handlers": handler_rows}
        want_action_rows.append({
            "action": action,
            "production_source_reference_count": action_counts[action],
            "source_area_counts": dict(sorted(action_areas[action].items())),
            "sample_locations": sorted(set(action_locations[action]))[:20],
            "devices": devices,
        })

    runtime_library_groups: dict[str, list[str]] = defaultdict(list)
    for library in runtime_library_scan["references"]:
        runtime_library_groups[Path(library).name].append(library)
    runtime_library_rows: list[dict[str, Any]] = []
    for basename in sorted(runtime_library_groups):
        source_values = sorted(runtime_library_groups[basename])
        refs = [
            reference
            for value in source_values
            for reference in runtime_library_scan["references"][value]
        ]
        area_counts: Counter[str] = Counter()
        for value in source_values:
            area_counts.update(runtime_library_scan["areas"][value])
        devices: dict[str, Any] = {}
        for device in DEVICES:
            present_paths = sorted(
                path
                for path in device_data[device]["filesystem"]
                if Path(path).name == basename
            )
            devices[device] = {
                "state": (
                    "dynamic_template"
                    if any("%" in value or "{" in value for value in source_values)
                    else "present"
                    if present_paths
                    else "missing"
                ),
                "present_paths": present_paths,
            }
        runtime_library_rows.append({
            "basename": basename,
            "source_values": source_values,
            "production_source_reference_count": len(refs),
            "source_area_counts": dict(sorted(area_counts.items())),
            "sample_references": refs[:20],
            "devices": devices,
        })

    rule_rows: list[dict[str, Any]] = []
    for rule in RULES:
        devices: dict[str, Any] = {}
        for device in DEVICES:
            data = device_data[device]
            provider_states = {
                bundle: bundle_state(bundle, data["enabled"], data["payload"], data["configured"])
                for bundle in rule["providers"]
            }
            target_states = {
                bundle: bundle_state(bundle, data["enabled"], data["payload"], data["configured"])
                for bundle in rule["implementation_targets"]
            }
            enabled_providers = [bundle for bundle, state in provider_states.items() if state == "enabled"]
            payload_providers = [
                bundle for bundle, state in provider_states.items() if state == "payload_not_enabled"
            ]
            wrong_targets = [
                bundle
                for bundle, state in target_states.items()
                if state in {"absent", "configured_but_payload_missing"}
                and counts.get(bundle, 0) > 0
                and any(
                    other.rsplit(".", 1)[-1] == bundle.rsplit(".", 1)[-1]
                    for other in data["payload"] | data["enabled"]
                )
            ]
            required_entrypoints = rule.get("required_entrypoints", [])
            available_entrypoints = {
                value
                for bundle in rule["providers"]
                for value in data["entrypoints"].get(bundle, set())
            }
            missing_entrypoints = [
                value for value in required_entrypoints if not has_entrypoint(available_entrypoints, value)
            ]
            required_actions = rule.get("required_actions", [])
            enabled_actions = {
                action
                for action in required_actions
                if any(
                    handler["bundle"] in data["enabled"]
                    and not (
                        handler.get("entities")
                        or handler.get("uris")
                        or handler.get("domain_verify")
                    )
                    for handler in data["action_handlers"].get(action, [])
                )
            }
            missing_actions = [action for action in required_actions if action not in enabled_actions]
            required_uri_authorities = [
                value.lower() for value in rule.get("required_uri_authorities", [])
            ]
            enabled_uri_authorities = [
                authority
                for authority in required_uri_authorities
                if uri_provider_state(data["uri_providers"].get(authority, []), data) == "enabled"
            ]
            missing_uri_authorities = [
                authority
                for authority in required_uri_authorities
                if authority not in enabled_uri_authorities
            ]
            required_files = rule.get("required_files", [])
            present_required_files = [
                path for path in required_files if path in data["filesystem"]
            ]
            missing_required_files = [
                path for path in required_files if path not in data["filesystem"]
            ]
            mode = rule.get("provider_mode", "all")
            providers_enabled = (
                bool(enabled_providers)
                if mode == "any"
                else len(enabled_providers) == len(rule["providers"])
            )
            providers_in_payload = (
                bool(enabled_providers or payload_providers)
                if mode == "any"
                else len(enabled_providers) + len(payload_providers) == len(rule["providers"])
            )
            applicable = device in rule.get("applicable_devices", DEVICES)
            contract_expected = applicable and any(
                matrix.get(syscap, {}).get("devices", {}).get(device, {}).get("contract_expected", False)
                for syscap in rule["syscaps"]
            )
            if not applicable:
                status = "not_applicable"
            elif missing_required_files:
                status = "provider_file_missing"
            elif wrong_targets:
                status = "implementation_target_mismatch"
            elif missing_actions:
                status = "provider_action_not_enabled"
            elif missing_uri_authorities:
                status = "provider_uri_not_enabled"
            elif providers_enabled and missing_entrypoints:
                status = "provider_entrypoint_missing"
            elif providers_enabled:
                status = "provider_enabled"
            elif providers_in_payload:
                status = "provider_payload_not_enabled"
            elif any(state == "configured_but_payload_missing" for state in provider_states.values()):
                status = "provider_configured_but_payload_missing"
            else:
                status = "provider_absent"
            devices[device] = {
                "contract_expected": contract_expected,
                "status": status,
                "provider_states": provider_states,
                "implementation_target_states": target_states,
                "certificate_mismatch_providers": sorted(set(rule["providers"]) & data["certificate_mismatches"]),
                "preinstall_path_mismatch_providers": sorted(set(rule["providers"]) & data["path_mismatches"]),
                "available_provider_entrypoints": sorted(available_entrypoints),
                "missing_required_entrypoints": missing_entrypoints,
                "enabled_required_actions": sorted(enabled_actions),
                "missing_required_actions": missing_actions,
                "enabled_required_uri_authorities": sorted(enabled_uri_authorities),
                "missing_required_uri_authorities": sorted(missing_uri_authorities),
                "present_required_files": sorted(present_required_files),
                "missing_required_files": sorted(missing_required_files),
                "stale_config_target_states": {
                    bundle: bundle_state(bundle, data["enabled"], data["payload"], data["configured"])
                    for bundle in rule.get("stale_config_targets", [])
                },
            }
        rule_rows.append({**rule, "devices": devices})

    direct_target_rows = [
        {
            "bundle": bundle,
            "entrypoint": entrypoint,
            "production_source_reference_count": target_counts[(bundle, entrypoint)],
            "source_area_counts": dict(sorted(target_areas[(bundle, entrypoint)].items())),
            "sample_locations": sorted(set(target_locations[(bundle, entrypoint)]))[:20],
            "devices": {
                device: element_target_state(bundle, entrypoint, device_data[device])
                for device in DEVICES
            },
        }
        for bundle, entrypoint in sorted(target_counts)
    ]

    parameter_pair_keys: set[tuple[str, str]] = set()
    for device in DEVICES:
        parameters = device_data[device]["parameters"]
        for key in parameters:
            if key.lower().endswith("bundlename"):
                ability_key = key[:-len("bundlename")] + "abilityname"
                if ability_key in parameters:
                    parameter_pair_keys.add((key, ability_key))
    parameter_target_rows: list[dict[str, Any]] = []
    for bundle_key, ability_key in sorted(parameter_pair_keys):
        devices: dict[str, Any] = {}
        for device in DEVICES:
            parameters = device_data[device]["parameters"]
            bundle = parameters.get(bundle_key, "")
            entrypoint = parameters.get(ability_key, "")
            devices[device] = {
                "bundle": bundle,
                "entrypoint": entrypoint,
                "state": (
                    element_target_state(bundle, entrypoint, device_data[device])
                    if BUNDLE_RE.fullmatch(bundle) and entrypoint
                    else "parameter_pair_missing_or_invalid"
                ),
            }
        parameter_target_rows.append({
            "bundle_parameter": bundle_key,
            "entrypoint_parameter": ability_key,
            "devices": devices,
        })

    unresolved = {
        device: sum(
            row["devices"][device]["contract_expected"]
            and row["devices"][device]["status"] != "provider_enabled"
            for row in rule_rows
        )
        for device in DEVICES
    }
    result = {
        "schema_version": 10,
        "summary": {
            "production_bundle_token_count": sum(counts.values()),
            "production_bundle_token_unique_count": len(counts),
            "system_bundle_reference_count": len(source_rows),
            "framework_or_service_bundle_token_count": sum(
                any(row["source_area_counts"].get(area) for area in FRAMEWORK_OR_SERVICE_AREAS)
                for row in source_rows
            ),
            "nonlocal_namespace_or_external_bundle_token_count": sum(
                row["classification"] == "nonlocal_namespace_or_external_bundle" for row in source_rows
            ),
            "extension_uri_authority_token_count": sum(
                row["classification"] == "extension_uri_authority" for row in source_rows
            ),
            "declared_extension_uri_authority_count": {
                device: len(device_data[device]["uri_providers"]) for device in DEVICES
            },
            "source_uri_authority_count": len(uri_authority_rows),
            "source_uri_reference_count": sum(uri_counts.values()),
            "source_want_action_count": len(want_action_rows),
            "source_want_action_reference_count": sum(action_counts.values()),
            "runtime_library_candidate_count": len(runtime_library_rows),
            "runtime_library_reference_count": sum(
                row["production_source_reference_count"] for row in runtime_library_rows
            ),
            "runtime_library_dlopen_callsite_count":
                runtime_library_scan["callsite_count"],
            "resolved_runtime_library_dlopen_callsite_count":
                runtime_library_scan["resolved_callsite_count"],
            "unresolved_runtime_library_dlopen_callsite_count": len(
                runtime_library_scan["unresolved_calls"]
            ),
            "missing_runtime_library_candidate_count": {
                device: sum(
                    row["devices"][device]["state"] == "missing"
                    for row in runtime_library_rows
                )
                for device in DEVICES
            },
            "non_usable_source_want_action_count": {
                device: sum(
                    row["devices"][device]["state"] != "enabled_handler"
                    for row in want_action_rows
                )
                for device in DEVICES
            },
            "unresolved_source_uri_authority_count": {
                device: sum(
                    row["devices"][device]["state"] == "unresolved_authority"
                    for row in uri_authority_rows
                )
                for device in DEVICES
            },
            "non_usable_source_uri_authority_count": {
                device: sum(
                    row["devices"][device]["state"]
                    not in {"enabled", "proxy_bundle_enabled"}
                    for row in uri_authority_rows
                )
                for device in DEVICES
            },
            "source_declared_bundle_count": len(declared_bundles),
            "provider_rule_count": len(rule_rows),
            "provider_rule_required_file_count": sum(
                len(row.get("required_files", [])) for row in rule_rows
            ),
            "direct_element_target_count": len(direct_target_rows),
            "framework_or_service_direct_element_target_count": sum(
                any(row["source_area_counts"].get(area) for area in FRAMEWORK_OR_SERVICE_AREAS)
                for row in direct_target_rows
            ),
            "cpp_element_launch_callsite_count": target_scan["cpp_element_launch_callsite_count"],
            "resolved_cpp_element_launch_callsite_count":
                target_scan["resolved_cpp_element_launch_callsite_count"],
            "unresolved_cpp_element_launch_callsite_count":
                target_scan["unresolved_cpp_element_launch_callsite_count"],
            "js_element_object_count": target_scan["js_element_object_count"],
            "resolved_js_element_object_count":
                target_scan["resolved_js_element_object_count"],
            "unresolved_js_element_object_count":
                target_scan["unresolved_js_element_object_count"],
            "runtime_parameter_element_target_count": len(parameter_target_rows),
            "non_usable_direct_element_target_count": {
                device: sum(row["devices"][device] != "enabled" for row in direct_target_rows)
                for device in DEVICES
            },
            "phone_non_usable_provider_rule_count": unresolved["phone"],
            "2in1_non_usable_provider_rule_count": unresolved["2in1"],
        },
        "provider_rules": rule_rows,
        "source_uri_authorities": uri_authority_rows,
        "source_want_actions": want_action_rows,
        "source_runtime_library_dependencies": runtime_library_rows,
        "unresolved_runtime_library_calls": runtime_library_scan["unresolved_calls"],
        "direct_element_targets": direct_target_rows,
        "unresolved_direct_element_calls": target_scan["unresolved_cpp_element_launch_calls"],
        "unresolved_js_element_objects": target_scan["unresolved_js_element_objects"],
        "runtime_parameter_element_targets": parameter_target_rows,
        "source_bundle_references": source_rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
