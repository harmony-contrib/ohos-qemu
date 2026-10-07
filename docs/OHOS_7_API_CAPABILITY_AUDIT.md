# OpenHarmony 7.0 phone / 2in1 系统能力审计

审计日期：2026-09-23

## 结论

当前 QEMU 产物不能把 `canIUse=true`、模块可加载、库存在或 System Ability 已注册解释为
“能力可用”。phone 和 2in1 都存在声明、权限、API 表面、服务配置、内核以及虚拟硬件后端
不一致的问题。

特别是 ArkWeb 不能因页面加载或 Native JSVM 用例通过就判为整体可用。后续分段探针
已在旧 ARM64 phone 包上证实页面 JS、DOM 和 Canvas 2D 可执行，而 WebGL1/2 超时，
并定位到 EGL wrapper 错误广告 backend 不支持的 robustness 扩展。Vulkan ICD 缺失是
**独立问题**，不能作为 ArkWeb WebGL 的解释。修复与各架构验收门槛见
`docs/OHOS_7_ARKWEB_VULKAN_REPAIR.md`。

本轮修正了此前审计的七个根本缺口：

1. 旧解析器只为“方法段落自己重复写了 SysCap”的条目建账。OHOS 7 大量 Native 文档只在
   文件头声明一次 SysCap，例如 Camera 的几十个 C 函数，因此旧总数漏掉了数千个 API。
   新解析器从 API 标题出发，把文件/模块契约继承给每个方法。
2. 旧总账以 SysCap 为主，无法表示一个模块里的不同方法、权限和设备边界。现在增加了逐 API、
   逐设备台账，并保留没有 SysCap 标记的文档条目。
3. 旧审计停在 SysCap、动态库和 System Ability 层，遗漏了系统服务继续委托给预装 HAP 的链路。
   现在逐个核对 `/system/app` payload、`install_list.json`、签名能力白名单、BMS 实际注册状态、
   HAP 中的 Ability/UIExtension 入口，以及生产源码硬编码的目标包名。
4. 旧 provider 扫描先按镜像已有包过滤，并且 ArkTS/TS/JS 只识别 `bundleName` 位于
   `abilityName` 前面的对象。这会同时漏掉“源码目标与镜像都不存在”的包和字段反序的 Want。现在
   全量保留 bundle token，按同一对象作用域解析 JS 目标，并单列无法静态求值的 C++ 与 JS 调用点、
   运行时参数目标和 DataShare URI authority。
5. 旧审计把隐式 Want 只当作字符串，没有检查启用的 HAP skill 是否同时满足 action、entity、
   URI/UTD 和 domainVerify 条件。现在保留完整 skill 约束；只有无约束且已启用的 handler 才直接
   标为可解析，只有 action 证据的约束路由继续标为需要匹配。
6. 旧审计只确认 DataShare 服务和 HAP 存在，没有核对 API 实际选择的 authority。现在从生产源码
   枚举 URI，并与每个启用 Extension 的声明连接，能够识别 `calendardata_whole` 这类分支缺口。
7. 旧审计没有反查框架的运行时插件，而且源码边界只含 `base/foundation/applications/domains`，
   会整个漏掉 Driver Kit、Ark 运行时、公共工具库和设备侧 DFX。现在同时覆盖 `drivers`、
   `arkcompiler`、`commonlibrary`、`developtools`，枚举生产 `dlopen()` 调用、解析同文件常量、连接
   完整文件清单，并保留所有无法静态求值的调用点。

修正后，完整清单包含 **325 个公开 SysCap、37,920 个文档 API 条目、32,280 个可调用
条目、594 个动态 ArkTS 模块入口、484 个静态 ArkTS 模块入口、6,768 个有头文件依据的
Native C 函数**。325 个 SysCap 在 phone 和 2in1 上均已有明确分类，设备契约内不再存在
`behavior_validation_pending`、`surface_failure_unclassified` 或 `permission_registry_gap`。
严格校验器状态为 `complete_capability_classification_method_sampling_full_provider_inventory`。

分类区分已验证子集、已确认失败、画像/打包失败、外部设备或云依赖、系统角色限制、交互 UI、
测试框架和纯编译期契约。它回答每个 OHOS SysCap 在模拟器上的可用条件；逐 API 台账仍明确标出
没有单独执行的方法，避免把一个成功样例扩展成整个 SysCap 的所有 37,920 个 API 都已通过。

## 审计基线

| 来源 | 版本 |
| --- | --- |
| OpenHarmony 文档 | `OpenHarmony-7.0-Release` / `9585fb12fa8f977accfd9435d9f5537b14734473` |
| interface_sdk-js | `OpenHarmony-7.0-Release` / `411d28f767bd6cd2a6905e3c6b15f0992f55b81b` |
| 运行系统 | `OpenHarmony-7.0.0.39` / API 26 |
| 代表产物 | ARM64 phone 与 ARM64 2in1 |

phone 和 2in1 的 `image-syscap.json` 均直接从本轮运行的 guest
`/system/etc/syscap.json` 提取，不再使用重建或推测文件。完整来源记录见
`docs/capability-audit/source-baseline.json`。

## 覆盖范围

| 层级 | 覆盖 |
| --- | ---: |
| OHOS 7 公开 SysCap | 325 |
| 文档 API 条目 | 37,920 |
| 其中 callable | 32,280 |
| system API 条目 | 4,847 |
| 权限受控条目 | 2,278 |
| 继承或显式设备边界条目 | 1,822 |
| 文档没有 SysCap 契约的条目 | 182 |
| 动态 ArkTS 模块入口 | 594 |
| 静态 ArkTS 声明文件 / 模块入口 | 914 / 484 |
| Native C manifest / 函数 / 库 | 134 / 6,768 / 130 |
| API 权限名 | 394 |
| 打包的 System Ability profile | 164 |
| 有直接证据的关键运行后端 | 71 / device |
| Provider/URI/Want/运行时插件规则 | 71 |
| 生产源码 provider 候选 token | 540 |
| 生产源码 DataShare URI / 引用 | 43 / 953 |
| 生产源码隐式 Want action / 引用 | 48 / 482 |
| 生产 `dlopen()` 库候选 / 调用点 | 329 / 795 |

逐 API 大文件可由脚本再生并被 Git 忽略；提交中保留
`api-usability-summary.json`、SysCap 总账和关键运行证据。

## Provider、URI、隐式 Want、运行时插件与镜像装配

这一层是此前审计仍然“不全”的主要原因。服务进程和 NAPI 可以正常加载，调用也可能先返回成功，
但最后需要启动的系统 HAP 没有被 BMS 注册、签名不符合白名单，或框架写错了包名/Ability 名，
最终能力仍不可用。

| 项目 | phone | 2in1 |
| --- | ---: | ---: |
| `/system/app` HAP / bundle | 58 / 47 | 76 / 61 |
| 未列入预装清单的 HAP / bundle | 5 / 5 | 19 / 18 |
| 清单有路径但 payload 缺失 | 11 | 11 |
| 清单 payload 存在但 BMS 未启用 | 1 | 11 |
| HAP 证书与能力白名单不匹配 | 5 | 9 |
| JSON 配置引用但 BMS 缺失的 bundle | 10 | 19 |
| 设备合同内不可用的 Provider 流程 | 44 / 71 | 39 / 71 |

关键结论如下：

- **Share Picker（两种设备）**：`install_list.json` 和 AbilityManagerService 都引用
  `com.ohos.sharepickerdialog`，但镜像没有 payload。`startAbilityByType('share')` 的 Promise 先
  返回成功，回调随后报 `16000050`。
- **Distributed Hardware UI（两种设备）**：实际 payload 位于
  `/system/app/DHardware_UI/DHardware_UI.hap`，清单却写
  `/system/app/com.ohos.dhardwareui`。HAP 可手工安装，说明根因是预装路径错误。
- **Media Controller（两种设备）**：phone 完全没有 provider；2in1 有
  `com.hmos.mediacontroller`，但它未进入预装清单且 BMS 未注册。更严重的是
  `AVCastPickerHelper` 的 JS NAPI 与 ANI/Taihe 实现硬编码
  `com.ohos.mediacontroller`。手工安装真实 HAP 后仍找错包，`select()` 仍返回
  `success:true` 且没有 UIExtension 启动。2in1 HAP 还缺源码要求的
  `AVInputCastPickerAbility` 和音频隐私链路要求的 `DialogExtension`。
- **AVSession 桌面歌词（两种设备）**：实现仅按设备类型就对 phone/2in1 报告支持，实际启动
  `com.ohos.mediacontroller/DesktopLyricAbility`。phone 没有 provider；2in1 只有未注册且包名前缀不同的
  `com.hmos.mediacontroller`，其中也没有该入口。
- **通知设置（两种设备）**：订阅设置 API 需要 SceneBoard 的
  `NotificationAccessGrantUIExtensionAbility`，phone 没有 SceneBoard，2in1 的 SceneBoard 没有入口。
  `notificationManager.openNotificationSettings*()` 另需 `NotificationManangerUIExtensionAbility`；2in1
  具备该入口，phone 仍缺 provider。
- **Camera Picker（phone）**：非 TV 路径硬编码 `com.ohos.camera/PickerAbility`；phone Camera HAP
  只有 MainAbility 和 TV 使用的 ExtensionPickerAbility，因此公开 `cameraPicker.pick()` 缺目标入口。
- **AVScreenCapture 隐私窗（2in1）**：运行时参数仍把授权 UI 指向
  `com.ohos.systemui/com.ohos.systemui.dialog`。该 SystemUI payload 在 2in1 未注册，SceneBoard 不能替代
  这个精确的参数目标；phone 的相同目标已启用。
- **UserAuth 应用模态路径（2in1）**：文档限定 2in1 的 `WidgetParam.uiContext` 路径启动
  `UserAuthModalUIAbility`，但 AuthWidget HAP 只声明小写的 `userauthuiextensionability`。
- **权限设置入口（两种设备）**：AccessToken 服务默认启动
  `com.ohos.permissionmanager.OpenSettingAbility`，但已启用的 PermissionManager HAP 没有声明
  该 Ability 或 Extension。授权弹窗的其他入口存在，不能据此推断“打开权限设置”的完整链路可用。
- **无障碍系统 Provider（两种设备）**：核心事件与虚拟输入 E2E 可以工作，但系统没有屏幕朗读器
  HAP；框架主要路径硬编码 `com.ohos.screenreader/AccessibilityExtAbility`，另一路安装监听又检查
  `com.ohos.hmos.screenreader`。字幕状态查询也能返回，但启用字幕助手会启动缺失的
  `com.ohos.vassistant/AiCaptionServiceExtAbility`。因此 Vision 与 Hearing 只能标为部分可用。
- **Photos（两种设备）**：2in1 HAP 存在但未注册；证书指纹与能力白名单不一致，手工安装被
  BMS 拒绝。phone 的基础 Photo Picker 能启动，但 OHOS 7 的 `RecentPhotoComponent`、
  `getRecentPhotoInfo()` 和 `getPhotoPickerComponentDefaultAlbumName()` 分别需要
  `RecentUIExtensionAbility`、`RecentPhotoInfoAbility` 和 `DefaultAlbumNameUIExtensionAbility`，phone
  HAP 三个入口都没有。
- **CalendarData、PrintSpooler、DLP（2in1）**：payload 均存在但未注册，且实际证书与
  `install_list_capability.json` 不一致；手工安装触发 signature/capability-list 或
  privileged-extension 校验失败。这解释了 Calendar 的 201、Print 的无扩展，以及 DLP
  能力无法激活。 Calendar 的 phone CRUD 虽通过，phone HAP 仍缺事件编辑
  `EditorUIExtensionAbility`、提醒回调 `ReminderCallbackExtAbility`，并且没有接收提醒跳转的
  `com.ohos.calendar/MainAbility`。DLP 还依赖不存在的
  `com.huawei.hmos.dlpcredmgr/DlpPermServiceAbility`；Print 的远端发现还依赖不存在的
  `com.ohos.remotesvc/RemoteServiceExtAbility`。
- **Settings（2in1）**：SettingsData 查询可用，但 `com.ohos.settings` 本体未注册；其中的
  Wi-Fi、蓝牙、免打扰、密码、USB Debug 等系统 UIExtension/系统对话框不能据此视为可用。
- **Settings 页面跳转（两种设备）**：`@ohos.settings` 的 `openNetworkManagerSettings()`、输入法
  页面和 API 24/26 的 `open*SettingsPage()` 实现均指向不存在的 `com.huawei.hmos.settings`。phone
  虽启用了 `com.ohos.settings`，但包名前缀不匹配，且缺两个目标 UIExtension；2in1 的同名 payload
  未注册，并且入口也不完整。SettingsData 读写成功不能证明这些公开跳转 API 可用。
- **Contacts Picker（phone）**：联系人增删查生命周期已通过，但六个公开
  `selectContact/selectContacts` 重载都启动 `com.ohos.contacts/ContactUiExtentionAbility`；phone 的
  Contacts HAP 没有该入口。2in1 HAP 有入口，但 Contacts 超出精确 2in1 SDK 画像。
- **ArkUI 系统文本能力（两种设备）**：OHOS 7 的 `TextMenuItemId` 明确提供搜索、分享、翻译、
  URL、邮件、电话、地址和日历跳转。两个镜像都缺
  `/system/lib64/expanded_menu/libexpanded_menu.z.so`，因此无法取得实体到应用的映射；还同时缺
  分享、翻译和实体识别所加载的 `libsystemshare_innerkits.z.so`、
  `libai_text_translation_innerapi.z.so`、`libai_text_analyzer_innerapi.z.so`。源码 fallback 分别返回
  `-1`、unsupported 或空操作。镜像也没有 Browser、Calendar、Maps、SuperDevice 等映射目标，
  `search`、`appdetail`、`sendData` action 没有启用的 handler。
- **AppDomainVerify（phone 合同内，2in1 也错误声明）**：查询接口可以返回，但两个镜像均缺
  `libapp_domain_verify_extension.z.so`。进一步源码复核纠正此前推断：该库是可选 extension，
  `E_EXTENSIONS_LIB_NOT_FOUND` 会触发内置 VerifyTask/VerifyHttpTask，验证及刷新并非直接失败。
  但 Want conversion 的 fallback 返回空 TargetInfo；真实 HTTP/HTTPS 验证、刷新、签名校验和
  路由仍需运行测试，不能把缺可选库或查询成功单独作为失败/通过证明。
- **Audio Vivid 元数据（两种设备）**：API 26 在 `libnative_media_core.so` 中公开
  `OH_AudioVividMetaBuilder_*`，两个镜像却都没有 `libAudioVividMetaBuilder.z.so`。源码和单元测试
  明确显示 `Create`/`CreateEmptyBuilder` 在该库缺失时返回 `AV_ERR_UNSUPPORT`；因此
  `SystemCapability.Multimedia.Media.Core` 只能标为部分可用。
- **SelectionExtensionAbility（重点影响 2in1）**：SA 8500 存在并不能完成选择面板能力。配置的
  `com.selection.selectionapplication` 未安装，API 26 扩展运行时还会加载缺失的
  `libselection_extension_ani.z.so`，所以 Selection Extension 无法实例化。phone 本就不在文档设备
  范围内，但其镜像仍错误声明该 SysCap。
- **视频编码的传递失败（两种设备）**：此前只把两个广告的 OMX.rk AVC/HEVC 编码器创建失败记到
  `VideoEncoder`。实际 `AVTranscoder` 的视频转码和 `AVScreenCapture` 的视频录制也依赖该路径；
  对象创建/释放成功只能证明生命周期，不能证明转码或录屏输出可用，因此两项均降为部分失败。
- **Calendar 全量权限分支（两种设备）**：API 21+ 在调用方拥有 `READ_WHOLE_CALENDAR` 或
  `WRITE_WHOLE_CALENDAR` 时改用 `datashare:///calendardata_whole`。phone 启用的 CalendarData HAP
  只声明 `calendardata`；2in1 payload 虽声明 whole authority，但未注册，所以该特权分支均不可用。
- **CloudSync（两种设备）**：CloudData、RDB `cloudSync/cloudSyncEx` 与 File CloudSync 最终固定连接
  `com.example.cloudsync/ServiceExtAbility`。两个产品都没有这个示例 provider，也没有参数或配置把
  它替换为真实服务；这不是单纯缺账号或外网。
- **phone 的 MTP 与 Photos FA Card**：MTP 动态库存在，但已启用的 MediaLibrary HAP 没有
  `MtpService`；Photos 的 FA Card/云变化路径又硬编码缺失的 `com.huawei.hmos.photos`，phone 的
  `com.ohos.photos` 也没有 `FACardServiceAbility`。基础照片选择成功不能覆盖这两个子流程。
- **隐式分享、电话反骚扰与 2in1 打印 AI 动作**：两个镜像都没有启用的
  `ohos.want.action.sendData` handler；phone CallManager 的 spam/HSDR 路径分别缺
  `com.spamshield/SpamShieldServiceExtAbility` 与 `com.hmos.hsdr/HSDRService`；2in1 打印通知动作缺
  `com.ohos.vassistant/VoicePcServiceExtAbility`。
- **SceneBoard 替代关系（2in1）**：Launcher、SystemUI 未注册是产品策略的一部分，SceneBoard
  提供桌面、通知和系统对话框入口；审计把这些作为候选 provider 处理，没有将这两项简单误报
  为缺失。FileManager 虽未注册，但 `com.ohos.filepicker` 已启用，因此基础文件选择仍可用。
- **EDM 与 Wallpaper（两种设备）**：基础服务查询分别可工作，但生产源码所需的
  `com.ohos.adminprovisioning` 和配置声明的 `com.ohos.wallpaper` payload 不存在，相关 UI/
  provisioning 子流程不完整。 WallpaperService 的 Launcher fallback 也不可用：phone Launcher 没有
  `WallpaperExtAbility`，2in1 Launcher payload 未注册。
- **网络与电话 UI（phone 为主）**：VPN 服务硬编码缺失的 `com.huawei.hmos.vpndialog`，而镜像实际
  启用 `com.ohos.vpndialog`；`showAppNetPolicySettings()`、网络用量通知和
  `showSystemApnSettings()` 分别指向缺失的 Huawei CommunicationSetting、Settings 和 CallSetting。
  CallManager 的号码标记刷新还依赖不存在的 `com.numberidentity/NumberIdentityServiceExtAbility`。
- **Wi-Fi 与定位 UI（两种设备）**：`WifiServiceAbility`、`HotSpotServiceAbility`、Captive Portal 和
  LocationDialog 只存在于未注册 payload；定位详情页进一步指向缺失的 Huawei Location provider。
  这些装配问题与无线电、GNSS 硬件后端缺失相互独立。
- **USB 配置陈旧但实际 Provider 正常**：配置引用缺失的 `com.usb.function`，生产代码实际使用
  已启用的 `com.usb.right`，且 `UsbFunctionSwitchExtAbility` 存在。USB gadget 仍因没有 UDC
  后端而不可用，但不能把它误诊为 USB 对话框 HAP 缺失。

provider/URI/Want 扫描覆盖 `base`、`foundation`、`applications`、`domains`、`drivers`、
`arkcompiler`、`commonlibrary` 的非测试实现，`dlopen()` 扫描还覆盖设备侧 `developtools` 实现。
扫描得到 3,040 次 provider 候选引用、540 个唯一 token，其中 236 个直接出现在框架、服务、
Driver 或 runtime 实现。报告保留
不存在、非本地命名空间和无法解析的候选，不再先与镜像已有包求交集。

语义扫描另外得到 185 个可解析的 bundle/entrypoint 目标，其中 69 个来自框架或服务；504 个 C++
Element 调用点中解析 151 个、保留 353 个动态调用点；418 个 ArkTS/TS/JS 同对象目标中解析 231 个、
保留 187 个动态对象。两个屏幕录制运行时参数目标、43 个 DataShare authority（953 次引用）和
48 个隐式 Want action（482 次引用）也进入同一报告。HAP skill 记录 action 之外的 entity、URI/UTD
和 domainVerify 条件；两个设备都只有 5 个 action 能由已启用且无额外约束的 handler 直接解析，
其余 43 个缺 handler 或仍需要路由级约束匹配。

动态库扫描覆盖 795 个生产 `dlopen()` 调用点，解析 504 个并归并成 329 个库候选，291 个动态
表达式原样保留。phone 和 2in1 各有 171 个候选库不在文件清单；其中既有产品可选扩展，也有
公开能力的必需实现，后者通过规则与源码 fallback 单独判定，不能把 171 项全部直接算成 API 失败。

## phone 结果

### 设备契约

| 项目 | 数量 |
| --- | ---: |
| SDK default 画像 | 232 |
| phone 文档最小画像 | 231 |
| 两者联合契约 | 242 |
| 镜像声明 | 292 |
| 联合契约中 `canIUse=true` | 233 |
| 联合契约中 `canIUse=false` | 9 |
| 超出 SDK 画像的声明 | 61 |

9 个契约不可发现项为：DistributedFile、HiDumper、AVInputCast、Audio Suite、
DataTransitManager、DeviceAuth、DeviceSecurityLevel、PinAuth、Window SessionManager。
其中 Audio Suite、PIN/安全设备、SessionManager 已有额外实现或打包失败证据，不能归因于正常的
设备差异。

### SysCap 级覆盖状态

| 状态 | 联合契约内数量 |
| --- | ---: |
| 已确认行为失败或部分失败 | 112 |
| 画像或打包失败 | 7 |
| 已验证行为子集 | 114 |
| 需要外部设备、云或账号 | 3 |
| 需要特权系统角色 | 2 |
| 需要交互 UI | 1 |
| 仅编译期契约 | 1 |
| 仅测试框架 | 2 |

### phone 关键失败

- **Wi-Fi**：镜像声明 STA/AP/P2P/Core，但 guest 只有 `virtio_net` 的 `eth0`；HDF 找不到
  AP6275S，`cfg80211/mac80211/iwlwifi/iwlmvm` 也没有打包。
- **Bluetooth**：没有可用控制器和 vendor radio 数据路径，状态无法完成开启闭环。
- **Camera**：无 `/dev/video*` 和 camera host；Camera Manager 能创建，但枚举返回
  `7400101`、设备数 0。
- **Audio**：`/dev/snd` 只有 timer，没有 PCM；Renderer `Start()` 返回 2，状态停在
  PREPARED，0 frame、0 callback。Audio Capturer、通话、录音、SoundPool 和依赖音频的数据链路
  同样不可用。
- **Audio Suite**：`libohaudiosuite.so` 是占位库，API 26 的 65 个公开符号全部缺失。
- **Location**：没有 GNSS/location provider；定位回调为 0。
- **Telephony**：没有 modem、SIM 或 radio transport；查询框架存在，但电话、短信和蜂窝数据
  无法完成。
- **Vulkan**：旧包无可用 ICD，`vkCreateInstance` 返回 `VK_ERROR_INCOMPATIBLE_DRIVER`；
  OHOS swapchain implicit layer 还要求 `VK_OHOS_native_buffer`。临时注入的 M144
  SwiftShader 在 ARM64 phone 上通过 core/headless WSI 探针，但新包及 OHOS
  native-window WSI 尚未验收，详见独立修复记录。
- **ArkGraphics3D**：模块和 3D 库完整打包，但 `Scene.load()` 返回
  `Creating scene manager failed`，因此不能因模块可加载而标为可用。
- **VideoEncoder**：运行时枚举出 `OMX.rk.video_encoder.avc` 与
  `OMX.rk.video_encoder.hevc`，两个实例均无法创建；解码、音频编解码、Muxer 和 Demuxer 可创建。
- **Ads**：`ad_service_config.json` 指向未安装的 `com.samples.AdsServiceDemo`，广告加载链路不可用；
  OAID 本地标识链路是另一项能力，已单独验证。
- **IntelligentScene**：两个 DND 查询均返回内部错误 `35200001`；phone 镜像同时缺少
  `com.ohos.intelligentscene` bundle。
- **ShortKey**：`ability_launch_config.json` 的 Shortkeys/Sequences 为空，RepeatKeys 又指向缺失的
  `com.ohos.emergencycommunication`；`setKeyDownDuration()` 返回 401。
- **DeviceAttest**：OEM adapter 的 product ID/key 为空，查询返回 `DEVATTEST_INIT (-2)`。
- **CertificateManager**：`getAllAppPrivateCertificates()` 在无证书时解析为 `undefined`，与 OHOS 7
  声明的 `Promise<CMResult>` 不一致。
- **Network statistics/policy**：BPF syscall 返回 `ENOSYS`，依赖 eBPF 的 UID 统计和策略后端
  不完整。
- **SelectionInput**：OHOS 7 文档限定为 PC/2in1，phone 却声明 true，属于错误继承。
- **分布式/SoftBus/AVCast**：默认启动器使用 QEMU user-mode NAT，guest 之间不能完成对端发现；
  需要 bridge 和第二设备才能使用。
- **系统 UI Provider**：Share Picker 缺包；DHardware UI 预装路径错误；Media Controller 缺包或
  包名错误；PermissionManager 缺 OpenSettingAbility；ScreenReader 与字幕助手缺包；
  PrivacyCenter、LocationDialog、Bluetooth UI payload 未进入预装清单。它们和无线/定位硬件后端
  失败是相互独立的问题。

## 2in1 结果

### 设备契约

| 项目 | 数量 |
| --- | ---: |
| 精确 2in1 SDK 画像 | 221 |
| Tablet 参考画像 | 223 |
| 镜像声明 | 293 |
| SDK 契约中 `canIUse=true` | 218 |
| SDK 契约中 `canIUse=false` | 3 |
| 超出 SDK 画像的声明 | 75 |

3 个 SDK 契约缺口是 BusManager.Serial、NetManager.Eap 和 Audio.DeviceEnhance。
`@ohos.busManager.serial` 与 `@ohos.net.netFirewall` 也是 2in1 官方可调用模块中的两个加载失败项。

### SysCap 级覆盖状态

| 状态 | SDK 契约内数量 |
| --- | ---: |
| 已确认行为失败或部分失败 | 92 |
| 画像或打包失败 | 5 |
| 已验证行为子集 | 113 |
| 需要外部设备、云或账号 | 5 |
| 需要特权系统角色 | 2 |
| 需要交互 UI | 1 |
| 仅编译期契约 | 1 |
| 仅测试框架 | 2 |

### 2in1 新确认的重要问题

- **SelectionInput**：文档明确支持 PC/2in1，镜像也声明 true，但精确 2in1 SDK profile 反而
  漏掉该能力。SA 8500 存在，系统配置指向 `com.selection.selectionapplication`，镜像却没有安装
  这个 bundle；listener/content 调用分别返回 `33600003` 和 `33600001`，API 26
  `SelectionExtensionAbility` 还缺实例化所需的 `libselection_extension_ani.z.so`。
- **Print**：这是 2in1 官方能力。PrintService 可以按需启动，但没有 PrintExtension，vendor
  driver `dlopen` 和 CUPS 资源初始化失败，发现打印机返回 `13100004`
  (`E_PRINT_INVALID_EXTENSION`)。
- **Window SessionManager**：文档包含 PC/2in1 能力，SDK/image 却未声明；PiP 返回 enabled，
  FloatingBall 与 FloatView 返回 disabled，属于部分实现和 profile 不一致。
- **WindowManager Native**：完整 ARM64 native 套件在不授予屏幕捕获权限时为 1/4；授予
  `CUSTOM_SCREEN_CAPTURE` 后，active window、完整 API 26 matrix、异步回调均通过，为 3/4。
  剩余一项只因测试固定期待 2 个 visible layouts，而当前非全新 guest 合法返回 3 个；它是测试
  fixture 假设，不是 API 错误。
- **Wi-Fi、Bluetooth、Audio、Vulkan、eBPF、FTrace、USB gadget、quota** 与 phone 使用相同
  基础镜像和后端，因此同样失败或部分失败。
- **ArkGraphics3D、VideoEncoder、Ads、IntelligentScene、ShortKey、DeviceAttest 和
  CertificateManager** 与 phone 得到相同的失败结果。2in1 的 CA 证书对话框支持查询返回 true，
  phone 返回 false。
- **CalendarData**：相同的 v13 CRUD HAP 在 phone 通过，在 2in1 即使授予日历权限仍返回 201。
- **预装 Provider**：Photos、CalendarData、PrintSpooler、DLP 的 HAP 存在，但签名白名单不匹配
  且未注册；MediaController、FileManager、PrivacyCenter、IntelligentScene 等属于 18 个未列入
  清单的 bundle。Settings HAP 也存在但未启用，造成基础 DataShare 可用而设置 UI 子流程不可用。
- **AVCast Picker 假成功**：真实 provider 是 `com.hmos.mediacontroller`，NAPI/ANI 却写成
  `com.ohos.mediacontroller`。手工安装真实 HAP 后调用仍返回成功但没有 UI 启动，证明它不是
  单纯的预装遗漏。
- **Camera、Location、Telephony、Sensor 等大量能力**来自共同的 `rich.json` 继承，超出 2in1
  精确画像。它们不应继续对 2in1 宣告可用。

## ArkTS、静态 ArkTS 和 Native ABI

### 动态 ArkTS

两种设备均完成 594 个入口加载，496 成功、98 失败。98 项中包含 48 个 `@kit.*` 聚合入口和
30 个纯声明入口；需要运行模块的失败已按设备画像单独计算。

修正动态/静态限定符及 const enum 分类后，phone 官方画像仍有 54 个模块存在运行导出
不匹配，涉及 13 个公开函数和 35 个 system API 函数；2in1 为 45 个可加载模块（另外
2 个整体缺失）、15 个公开函数和 23 个 system API 函数。369 个只属于静态 ArkTS 的
导出不再被误报为动态 NAPI 缺失。16 项 const enum 契约单列为编译调用待验证，未宣告
通过。无公开 constructor 的数据类还需验证实际工厂返回值，不能把所有表面不匹配都
直接理解为 API 不可调用。

### 静态 ArkTS

静态 SDK 共扫描 914 个 `.d.ets` 文件、484 个模块入口和 3,711 个顶层函数；镜像有 99 个
ANI so 和 480 个 framework ABC。当前 DevEco API 26 包缺少静态构建 driver
`ets/static/build-tools/driver/build-system/dist/entry.js`，因此只能确认表面与运行产物，不能把
静态 ArkTS 行为标为通过。该项保持 `static_hap_probe_required`。

### Native C ABI

最新 interface_sdk_c manifest 提供 134 个契约、130 个库、11,429 个 manifest 名称；结合
头文件后得到 6,768 个可调用函数和 107 个 SysCap。确认的官方缺口包括：

- phone：`OH_LocationInfo_IsFromMock` 缺失；
- 2in1：Net Traffic Filter 官方库缺失；
- 两种设备：Audio Suite 65 个函数全部缺失。

## 权限与服务层

API 26 声明使用 394 个权限名，guest 只注册其中 367 个，缺 27 个。按目标画像过滤后，phone
缺 11 个官方 public 权限和 3 个官方 system 权限；2in1 缺 13 个 public 和 3 个 system 权限。
影响范围包括 BundleManager、OsAccount、InputSimulator、Startup/SystemInfo、Window 屏幕录制，
以及 phone Sensor、2in1 DLP/Print/TrafficFilter。权限名未注册时，对应 API 无法通过普通授权
流程变成可用。

两种镜像均打包 164 个 SA profile、87 个 eager SA。行为探针后仍各有 8 个 eager profile 未注册；
SA 注册只证明 IPC 入口存在，Audio、Wi-Fi、Camera、Selection 和 Print 已证明其后端仍可缺失。

启动日志还持续出现 AccessToken ioctl 不支持、QoS 未授权、resource cgroup 路径缺失、secure
hardware 节点缺失、FTrace 路径缺失和 F2FS quota 损坏。它们已按错误族计数并关联到运行后端
总账。

## 已验证可用的代表能力

- DRM/virtio-gpu 显示、基础窗口和 active window；
- Ethernet、默认网络、外部 DNS、mDNS 启动；
- 模拟 accelerometer，2 秒收到 9 个回调；
- 模拟 vibrator；
- Battery、Display、I18n 基础查询；
- AppAccount、RDB、KVStore、Preferences、Asset、Contacts，以及 phone Calendar CRUD；
- AES/HMAC/PBKDF2、RSA 签名校验、X25519、HUKS key lifecycle 和 PKIX validator 创建；
- AVSession、AVPlayer/VideoPlayer、AVImageGenerator、AVTranscoder、AVScreenCapture 对象生命周期；
- 音频编解码器、视频解码器、MP4 Muxer、WAV source/demuxer；
- FileAccess/UserFileManager、FileTransferAgent、HTTP 上传下载、后台任务查询；
- Libuv 1.52、FFRT、HiCollie、HiRetrieval、FaultLogger、LogLibrary；
- ArkUI router、ColorSpace、无障碍字幕管理器、Pointer/InputConsumer/InputMonitor；
- 使用 `--a11y` 虚拟多点触控时，phone 和 2in1 Accessibility E2E 通过；
- 2in1 native Hypium 全套中 32/33 模块零失败，总计 96 pass / 3 fail；3 个失败都在未授予
  screen-capture 权限的 WindowManager，授权后只剩可见窗口数量 fixture 问题。

这些结果只提升被实际覆盖的方法，不会把同一 SysCap 下未调用的方法整体标为通过。

## 方法级验证边界

SysCap 级分类已经收口。逐 API 台账保留方法粒度，下面两类表示所属能力已有运行证据或失败证据，
但该方法没有被单独调用；不能把它们改写成“方法通过”。

| 状态 | phone | 2in1 |
| --- | ---: | ---: |
| 所属能力已验证子集、方法未单独执行 | 8,192 | 8,002 |
| 所属能力部分失败、方法未单独执行 | 20,982 | 19,831 |
| 已确认关联能力失败 | 4,683 | 4,308 |
| API 表面缺失 | 306 | 239 |
| profile/打包失败 | 1,885 | 3,836 |
| 权限注册失败 | 44 | 56 |
| 文档明确不支持该设备 | 753 | 578 |
| 文档缺 SysCap 契约 | 179 | 180 |

当前结论可以用于判断 325 个公开 OHOS SysCap 在 ARM64 phone/2in1 模拟器上的可用状态与前置
条件。它不代表每个重载、枚举、回调和错误分支都通过；这类方法级覆盖仍需按风险继续补充真实
HAP、Native 或 XTS 用例，并在修改产物后遵循“先验证一个 ARM64 代表包，再构建其他架构”的规则。

## 主要产物

- `docs/capability-audit/capability-coverage-ledger.json`
- `docs/capability-audit/api-usability-summary.json`
- `docs/capability-audit/runtime-backend-audit.json`
- `docs/capability-audit/system-bundle-provider-audit.json`
- `docs/capability-audit/summary.json`
- `docs/capability-audit/runtime/arm64-phone/preinstalled-hap-audit.json`
- `docs/capability-audit/runtime/arm64-2in1/preinstalled-hap-audit.json`
- `docs/capability-audit/runtime/arm64-phone/permission-audit.json`
- `docs/capability-audit/runtime/arm64-2in1/permission-audit.json`
- `docs/capability-audit/runtime/arm64-2in1/native-ohostest-summary.json`
- `docs/capability-audit/native-arkts11-gap-ledger.json`
- `ci/capability-audit/known-findings.json`

严格校验命令和再生顺序见 `ci/capability-audit/README.md`。
