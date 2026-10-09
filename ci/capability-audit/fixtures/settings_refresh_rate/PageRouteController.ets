/*
 * Copyright (c) Huawei Technologies Co., Ltd. 2024-2025. All rights reserved.
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import {
  HiSysAboutDeviceEventGroup,
  HiSysAboutSystemSettingsEventGroup,
  HiSysBatteryEventGroup,
  HiSysDisplayBrightnessEventGroup,
  HiSysOtherGroup,
  HiSysNFCEventGroup,
  HiSysMoreConnectionEventGroup,
  HiSysMoreConnectionGroup,
  HiSysApplicationsAndServicesEventGroup,
  HiSysSystemAndUpdatesEventGroup
} from '@ohos/settings.common/src/main/ets/systemEvent/BehaviorEventConsts';
import { NavEntryKey, PHONE_SETTING_HOME_MENU_KEYS } from '@ohos/settings.common/src/main/ets/utils/Consts';

const PAGE_PATH_MAP: Map<string, string> = new Map<string, string>([
  [NavEntryKey.PENG_LAI_HOME_PAGE, '../../Setting/Home/PengLaiHomePage'],
  [NavEntryKey.CLOUD_SPACE_ENTRY, '../../Setting/Account/CloudSpaceSettings'],
  [NavEntryKey.SUBSCRIBE_PAGE_ENTRY, '../../Setting/Account/SubscribeSettings'],
  [NavEntryKey.ACCOUNT_RECOMMENDATION_PAGE_ENTRY, '../../Setting/Account/AccountRecommendationSettings'],
  [NavEntryKey.FIND_DEVICE_ENTRY, '../../Setting/Account/FindDeviceSettings'],
  // 移动网络界面配置
  [NavEntryKey.SIM_CARD_MANAGEMENT_ENTRY, '../../Setting/MobileNetwork/SIMCardManagementPage'],
  [NavEntryKey.MOBILE_DATA_SETTING_ENTRY, '../../Setting/MobileNetwork/MobileDataPage'],
  [NavEntryKey.DATA_USAGE_MANAGEMENT_ENTRY, '../../Setting/MobileNetwork/DataUsageManagementPage'],
  [NavEntryKey.HOTSPOT_ENTRY, '../../Setting/MobileNetwork/HotSpot/HotspotSettingsPage'],
  [NavEntryKey.HOTSPOT_SHARE_ENTRY, '../../Setting/MobileNetwork/HotSpot/MoreShareSettingsPage'],
  [NavEntryKey.HOTSPOT_CONNECTED_ENTRY, '../../Setting/MobileNetwork/HotSpot/HotSpotConnectedPage'],
  [NavEntryKey.ADD_ESIM_PROFILE_ENTRY, '../../Setting/MobileNetwork/AddEsimProfile/AddEsimProfilePage'],

  // 网络设置页面
  [NavEntryKey.NETWORK_SETTINGS, '../../Setting/Network/NetworkPage'],
  [NavEntryKey.PC_NETWORK_PROXY_SETTINGS, '../../Setting/Network/PcProxySettingPage'],

  //关于本机界面配置
  [NavEntryKey.ABOUT_DEVICE_ENTRY, '../../Setting/AboutDevice/SubHome/AboutDeviceSettingPage'],
  [NavEntryKey.OUC_ALL_SCENE_UPDATE_ENTRY, '../../Setting/AboutDevice/OUC/OucAllSceneUpdatePage'],
  [NavEntryKey.OUC_PARAM_VERSION, '../../Setting/AboutDevice/OUC/OucParamVersionPage'],
  [NavEntryKey.EID_DETAIL_ENTRY, '../../Setting/AboutDevice/eSIM/EIDDetailPage'],
  [NavEntryKey.STATUS_INFO_SETTING, '../../Setting/AboutDevice/StatusInfo/StatusInfoSettingPage'],
  [NavEntryKey.NETWORK_INFO_SETTING, '../../Setting/AboutDevice/StatusInfo/NetworkInfoSettingPage'],
  [NavEntryKey.LEGAL_INFO_SETTING, '../../Setting/AboutDevice/LegalInfo/LegalInfoSettingPage'],
  [NavEntryKey.APP_OPEN_SOURCE_STATEMENT_ENTRY, '../../Setting/AboutDevice/LegalInfo/AppOpenSourceStatementPage'],
  [NavEntryKey.APP_OPEN_SOURCE_SHOW, '../../Setting/AboutDevice/LegalInfo/AppOpenSourceShowPage'],
  [NavEntryKey.ENTERPRISE_CUSTOM_INFO_ENTRY, '../../Setting/AboutDevice/EnterpriseCustom/CustomInformationPage'],

  // WLAN界面配置
  [NavEntryKey.WIFI_PRECISION_MENU_ENTRY, '../../Setting/Wlan/WifiPrecisionSetting'],
  [NavEntryKey.WIFI_MENU_ENTRY, '../../Setting/Wlan/WifiPasswordSettings'],
  [NavEntryKey.OPEN_NETWORK_ENTRY, '../../Setting/Wlan/OpenNetworkEntryPage'],
  [NavEntryKey.ADD_OTHER_WIFI_ENTRY, '../../Setting/Wlan/AddOtherWifiPage'],
  [NavEntryKey.WIFI_MENU_CONFIG_ENTRY, '../../Setting/Wlan/WifiConfigSetting'],
  [NavEntryKey.WIFI_SETUP_PROXY_ENTRY, '../../Setting/Wlan/WifiSetupProxyPage'],
  [NavEntryKey.WIFI_SETUP_IP_ENTRY, '../../Setting/Wlan/WifiSetupIpPage'],
  [NavEntryKey.WIFI_ENTRY, '../../Setting/Wlan/WlanPage'],
  [NavEntryKey.WLAN_PRIVACY_STATEMENT, '../../Setting/Wlan/SuperWlanSecurityPage'],
  [NavEntryKey.BLUETOOTH_ENTRY, '../../Setting/Bluetooth/BluetoothPage'],
  [NavEntryKey.MOBILE_ENTRY, '../../Setting/MobileNetwork/MobileNetworkPage'],
  [NavEntryKey.MORE_CONNECTION_ENTRY, '../../Setting/MoreConnection/MoreConnectionPage'],
  [NavEntryKey.WIRELESS_PROJECTION_ENTRY, '../../Setting/MoreConnection/WirelessProjectionPage'],
  [NavEntryKey.WIRELESS_TRUSTED_DEVICE_ENTRY, '../../Setting/MoreConnection/WirelessProjection/TrustedDevicesPage'],
  [NavEntryKey.DEVICE_INTERCONNECTIVITY_ENTRY, '../../Setting/MoreConnection/DeviceInterconnectivityPage'],
  [NavEntryKey.PAD_COCKPIT_ENTRY, '../../Setting/MoreConnection/PadCockpitSettingPage'],
  [NavEntryKey.NFC_ENTRY, '../../Setting/MoreConnection/NFCSettingsPage'],
  [NavEntryKey.PAYMENT_APPLICATION, '../../Setting/MoreConnection/NFC/DefaultPaymentApplicationPage'],
  [NavEntryKey.MORE_COLLABORATION_SETTINGS_ENTRY, '../../Setting/MoreConnection/MoreCollaborationSettingsPage'],
  [NavEntryKey.HI_WRITE_SETTINGS_ENTRY, '../../Setting/HiWrite/HiWritePage'],
  [NavEntryKey.FAR_FIELD_COMMUNICATION_SERVICE_PRIVACY, '../../Setting/MoreConnection/FarFieldCommunicationPage'],
  [NavEntryKey.THEME_ENTRY, '../../Setting/Theme/ThemePage'],
  [NavEntryKey.DISPLAY_ENTRY, '../../Setting/Display/DisplaySettingsPage'],
  [NavEntryKey.VOLUME_ENTRY, '../../Setting/Volume/VolumeSettingsPage'],
  [NavEntryKey.SOUND_EFFECT_DETAIL, '../../Setting/Volume/SoundEffectDetailPage'],
  [NavEntryKey.PHONE_NOTIFICATION_SETTINGS_ENTRY, '../../Setting/SystemUi/SystemUiPage'],
  [NavEntryKey.NOTIFICATION_SETTINGS_DETAIL_ENTRY, '../../Setting/SystemUi/SystemUiDetailPage'],
  [NavEntryKey.SYSTEM_UPDATE_ENTRY, '../../Setting/System/SystemPage'],
  [NavEntryKey.APPLICATION_SERVICE_ENTRY, '../../Setting/Application/ApplicationPage'],
  [NavEntryKey.APPLICATION_LIST_ENTRY, '../../Setting/Application/ApplicationPage'],
  [NavEntryKey.ACCESSIBILITY_FEATURE_ENTRY, '../../Setting/Accessibility/AccessibilityPage'],
  [NavEntryKey.ACCESSIBILITY_ELDER_CARE_ENTRY, '../../Setting/Accessibility/eldercare/ElderCarePage'],
  [NavEntryKey.ACCESSIBILITY_ELDER_CARE_TIPS_ENTRY,
    '../../Setting/Accessibility/eldercare/ElderCareViewMoreTipsPage'],
  [NavEntryKey.ACCESSIBILITY_ZOOM_GESTURE_ENTRY, '../../Setting/Accessibility/AccessibilityZoomGesturePage'],
  [NavEntryKey.ACCESSIBILITY_HIGH_CONTRAST_TEXT_ENTRY, '../../Setting/Accessibility/AccessibilityHighContrastTextPage'],
  [NavEntryKey.ACCESSIBILITY_INVERT_COLOR_ENTRY, '../../Setting/Accessibility/AccessibilityInvertColorPage'],
  [NavEntryKey.ACCESSIBILITY_ADVANCED_VISUAL_ENTRY, '../../Setting/Accessibility/AccessibilityAdvancedVisualPage'],
  [NavEntryKey.ACCESSIBILITY_TRANSITION_ANIMATIONS_ENTRY, '../../Setting/Accessibility/AccessibilityTransitionAnimationsPage'],
  [NavEntryKey.ACCESSIBILITY_AUDIO_ADJUSTMENT_ENTRY, '../../Setting/Accessibility/AccessibilityAudioAdjustmentPage'],
  [NavEntryKey.ACCESSIBILITY_COLOR_FILTER_ENTRY, '../../Setting/Accessibility/AccessibilityColorFilterPage'],
  [NavEntryKey.ACCESSIBILITY_FLASH_REMINDER_ENTRY, '../../Setting/Accessibility/AccessibilityFlashReminderPage'],
  [NavEntryKey.ACCESSIBILITY_TOUCHSCREEN_ENTRY, '../../Setting/Accessibility/AccessibilityTouchscreenPage'],
  [NavEntryKey.ACCESSIBILITY_OPERATION_ENTRY, '../../Setting/Accessibility/AccessibilityShortKeyPage'],
  [NavEntryKey.STORAGE_ENTRY, '../../Setting/Storage/StoragePage'],
  [NavEntryKey.BATTERY_ENTRY, '../../Setting/Battery/BatteryPage'],
  [NavEntryKey.BIOMETRICS_PASSWORD_ENTRY, '../../Setting/Biometrics/BiometricsPage'],
  [NavEntryKey.USERS_ACCOUNT_ENTRY, '../../Setting/UserSettings/UsersAccountsPage'],
  [NavEntryKey.USER_SETTING_ENTRY, '../../Setting/UserSettings/UserSettingsPage'],
  [NavEntryKey.INNER_SCREEN_FINGERPRINT_ENROLL_ENTRY,
    '../../Setting/Biometrics/Fingerprint/InnerScreenFingerprintEnrollPage'],
  [NavEntryKey.EXTERNAL_SCREEN_FINGERPRINT_ENROLL_ENTRY,
    '../../Setting/Biometrics/Fingerprint/ExternalScreenFingerprintEnrollPage'],
  [NavEntryKey.MULTI_FINGERPRINT_INTRO_ENTRY, '../../Setting/Biometrics/Fingerprint/MultiFingerprintIntroPage'],
  [NavEntryKey.PRIVACY_ENTRY, '../../Setting/Privacy/PrivacyPage'],
  [NavEntryKey.PHONE_MOUSE_SETTINGS, '../../Setting/Mouse/MousePage'],
  [NavEntryKey.PAD_PRINTER_SETTINGS_ENTRY, '../../Setting/Print/PrintPage'],
  [NavEntryKey.PAD_KEYBOARD_SETTINGS_ENTRY, '../../Setting/Keyboard/KeyboardPage'],
  [NavEntryKey.PAD_TOUCHPAD_SETTINGS_ENTRY, '../../Setting/Touchpad/TouchpadPage'],
  [NavEntryKey.PAD_KEYBOARD_FIRMWARE_UPGRADE, '../../Setting/Keyboard/KeyBoardFirmwareUpgrade'],
  [NavEntryKey.PAD_KEYBOARD_INFORMATION, '../../Setting/Keyboard/KeyBoardInformationSettings'],
  [NavEntryKey.RING_TONE_ENTRY, '../../Setting/Volume/RingToneSettingsPage'],
  [NavEntryKey.NOTIFICATION_TONE_ENTRY, '../../Setting/Volume/NotificationToneSettingsPage'],
  [NavEntryKey.MESSAGING_TONE_ENTRY, '../../Setting/Volume/MessageToneSettingsPage'],
  [NavEntryKey.DARK_SETTINGS, '../../Setting/Display/DarkModeSettingPage'],
  [NavEntryKey.SCREEN_ZOOM, '../../Setting/Display/ScreenZoomSettingPage'],
  // 情景模式
  [NavEntryKey.INTELLIGENT_SCENE_SETTINGS_ENTRY, '../../Setting/IntelligentScene/IntelligentScenePage'],

  [NavEntryKey.TOUCH_DISABLE_MODE_ENTRY, '../../Setting/System/SystemPage'],
  [NavEntryKey.SYSTEM_NAVIGATION, '../../Setting/System/SystemNavigationPage'],
  [NavEntryKey.LANGUAGE_REGION_ENTRY, '../../Setting/System/LanguageRegionPage'],
  [NavEntryKey.DATA_TIME_ENTRY, '../../Setting/System/DateAndTimePage'],
  [NavEntryKey.FONT_MANAGE, '../../Setting/System/AppFontsManage/AppFontsManagePage'],
  [NavEntryKey.INPUT_ENTRY, '../../Setting/System/InputPage'],
  [NavEntryKey.SMART_MULTI_WINDOW_ENTRY, '../../Setting/System/SmartMultiWindowPage'],
  [NavEntryKey.MULTI_WINDOW_FORCE_SWITCH_ENTRY, '../../Setting/System/SmartMultiWindow/MultiWindowForceSwitchPage'],
  [NavEntryKey.MULTI_WINDOW_LINKAGE_SCENE_PRIVACY_ENTRY, '../../Setting/System/SmartMultiWindow/MultiWindowLinkageScenePrivacyPage'],
  [NavEntryKey.RESET_ENTRY, '../../Setting/System/ResetPage'],
  [NavEntryKey.RESET_NET, '../../Setting/System/Reset/ResetNetPage'],
  [NavEntryKey.RESET_FACTORY, '../../Setting/System/Reset/ResetFactoryPage'],
  [NavEntryKey.SCHEDULED_POWER_ON_OFF, '../../Setting/System/ScheduledPowerOnOffPage'],
  [NavEntryKey.DEVELOP_OPTION_ENTRY, '../../Setting/System/DevelopOptionPage'],
  [NavEntryKey.SOS_EMERGENCY_HELP_ENTRY, '../../Setting/System/SOSEmergencyHelpPage.ets'],
  [NavEntryKey.DEVICE_AND_APPLICATION_ENTRY, '../../Setting/System/DeviceAndApplicationPage'],
  ['Setting.Home', '../../Setting/Home/HomePage'],
  [NavEntryKey.BLUETOOTH_BONDED_ENTRY, '../../Setting/Bluetooth/BluetoothBondedDevicePage'],
  // [NavEntryKey.BLUETOOTH_ENTRY, '../../Setting/Fusion/FusionPage'],
  [NavEntryKey.BLUETOOTH_ENTRY, '../../Setting/Bluetooth/BluetoothPage'],
  [NavEntryKey.FUSION_BONDED_ENTRY, '../../Setting/Fusion/FusionBondedDevicePage'],
  [NavEntryKey.POWER_CONSUMPTION_ENTRY, '../../Setting/Battery/PowerConsumptionPage'],
  [NavEntryKey.APPLICATION_INFO_ENTRY, '../../Setting/Application/AppDetailPage'],
  [NavEntryKey.DEFAULT_BROWSER_ENTRY, '../../Setting/Application/DefaultBrowserPage'],
  [NavEntryKey.DEFAULT_MAIL_ENTRY, '../../Setting/Application/DefaultMailPage'],
  [NavEntryKey.APPLICATION_PERMISSION_SETTINGS_ENTRY, '../../Setting/Application/ApplicationPermissionSettings'],
  [NavEntryKey.MORE_APPLICATION_ENTRY, '../../Setting/Application/MoreApplicationPage'],
  [NavEntryKey.APPLICATION_RESTORE_ENTRY, '../../Setting/Application/ApplicationRestorePage'],
  [NavEntryKey.APPLICATION_NETWORKING_ENTRY, '../../Setting/Application/AppNetworkPage'],
  [NavEntryKey.LANDSCAPE_STARTUP_ENTRY, '../../Setting/Display/LandscapeStartSettingPage'],
  [NavEntryKey.UNIVERSAL_DRAG_ENTRY, '../../Setting/System/UniversalDragPage'],
  [NavEntryKey.NOT_DISTURB_ENTRY, '../../Setting/Volume/NotDisturbSettingsPage'],
  [NavEntryKey.TIME_PERIOD_ENTRY, '../../Setting/Volume/TimerPeriodEditPage'],
  [NavEntryKey.INCOMING_CALL_ENTRY, '../../Setting/Volume/IncomingCallSettingPage'],
  [NavEntryKey.STORAGE_APP_ITEM, '../../Setting/Storage/AppItemPage'],
  [NavEntryKey.VPN_SETTINGS_ENTRY, '../../Setting/MoreConnection/VpnHomePage'],
  [NavEntryKey.LOCAL_BACKUP_DATA, '../../Setting/Storage/LocalBackupDataPage'],
  [NavEntryKey.UPGRADING_DATA, '../../Setting/Storage/UpgradingDataPage'],
  [NavEntryKey.STORAGE_MORE_CARD, '../../Setting/Storage/MoreCardPage'],
  [NavEntryKey.STORAGE_UNINSTALL, '../../Setting/Storage/UninstallAppPage'],

  // 蓝牙半模态页面配置
  [NavEntryKey.OPEN_BLUETOOTH_INFO_ENTRY, '../../Setting/Bluetooth/OppBluetoothPage'],

  // 外部跳转UIExtension通用界面
  [NavEntryKey.COMMON_PAGE, '../../Setting/Storage/CommonUIExtensionPage'],

  // item跳转外部UIExtension通用界面
  [NavEntryKey.COMMON_ITEM_PAGE, '../../Setting/Storage/ItemUIExtensionPage'],

  // 更多推荐
  [NavEntryKey.HOMEPAGE_SUGGESTION_MORE_PAGE, '../../Setting/Suggestion/SuggestionMorePage'],
]);

const DFX_PAGE_KEY_MAP: Map<string, string> = new Map<string, string>([
  [NavEntryKey.BATTERY_ENTRY, HiSysBatteryEventGroup.ENTER_BATTERY],
  [NavEntryKey.SYSTEM_UPDATE_ENTRY, HiSysAboutSystemSettingsEventGroup.ENTER_SYSTEM_UPDATE_ENTRY],
  [NavEntryKey.NETWORK_INFO_SETTING, HiSysAboutDeviceEventGroup.ENTER_NETWORK_INFO_SETTING],
  [NavEntryKey.DARK_SETTINGS, HiSysDisplayBrightnessEventGroup.DARK_MODE_ENTRY],
  [NavEntryKey.SCREEN_ZOOM, HiSysDisplayBrightnessEventGroup.FONT_SIZE_WEIGHT_ENTRY],
  [NavEntryKey.LANDSCAPE_STARTUP_ENTRY, HiSysDisplayBrightnessEventGroup.LANDSCAPE_STARTUP_ENTRY],
  [NavEntryKey.PAYMENT_APPLICATION, HiSysNFCEventGroup.ENTER_DEFAULT_PAY_APPLICATION],
  [NavEntryKey.MORE_COLLABORATION_SETTINGS_ENTRY, HiSysMoreConnectionEventGroup.ENTER_ADVANCED_SETTINGS],
  [NavEntryKey.WIRELESS_PROJECTION_ENTRY, HiSysMoreConnectionGroup.ENTER_WIRELESS_PROJECTION],
  [NavEntryKey.APPLICATION_SERVICE_ENTRY, HiSysApplicationsAndServicesEventGroup.APPLICATIONS_AND_SERVICES_ENTRY],
  [NavEntryKey.MORE_APPLICATION_ENTRY, HiSysApplicationsAndServicesEventGroup.MORE_APPS_ENTRY],
  [NavEntryKey.SYSTEM_NAVIGATION, HiSysAboutSystemSettingsEventGroup.SYSTEM_NAVIGATION_ENTRY],
  [NavEntryKey.OUC_PARAM_VERSION, HiSysAboutDeviceEventGroup.PARAMETER_VERSION_SETTING_ENTRY],
  [NavEntryKey.APP_OPEN_SOURCE_STATEMENT_ENTRY, HiSysAboutDeviceEventGroup.OPEN_SOURCE_STATEMENT_ENTRY],

  [NavEntryKey.RESET_ENTRY, HiSysSystemAndUpdatesEventGroup.ENTER_RESET],
  [NavEntryKey.GRIP_POSTURE_FOLLOW_ENTRY, HiSysAboutSystemSettingsEventGroup.ENTER_GRIP_FOLLOW_ENTRY],

  [NavEntryKey.EID_DETAIL_ENTRY, HiSysAboutDeviceEventGroup.ESIM_ID_ENTRY],
]);

export class PageRouteController {
  private static instance: PageRouteController | undefined = undefined;

  public static getInstance(): PageRouteController {
    if (PageRouteController.instance === undefined) {
      PageRouteController.instance = new PageRouteController();
    }
    return PageRouteController.instance;
  }

  public isHomeEntryPage(pageEntryKey: string): boolean {
    return PHONE_SETTING_HOME_MENU_KEYS.has(pageEntryKey);
  }

  public isPageAdapted(pageEntryKey: string): boolean {
    return PAGE_PATH_MAP.has(pageEntryKey);
  }

  public getPageUrl(pageEntryKey: string): string | undefined {
    return PAGE_PATH_MAP.get(pageEntryKey);
  }

  public getDfxKey(pageEntryKey: string): string | undefined {
    return DFX_PAGE_KEY_MAP.get(pageEntryKey);
  }
}
