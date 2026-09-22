# OpenHarmony 7.0 phone / 2in1 系统能力审计

审计日期：2026-09-23

## 结论

当前 QEMU 产物不能把 `canIUse=true`、模块可加载、库存在或 System Ability 已注册解释为
“能力可用”。phone 和 2in1 都存在声明、权限、API 表面、服务配置、内核以及虚拟硬件后端
不一致的问题。

本轮修正了此前审计的三个根本缺口：

1. 旧解析器只为“方法段落自己重复写了 SysCap”的条目建账。OHOS 7 大量 Native 文档只在
   文件头声明一次 SysCap，例如 Camera 的几十个 C 函数，因此旧总数漏掉了数千个 API。
   新解析器从 API 标题出发，把文件/模块契约继承给每个方法。
2. 旧总账以 SysCap 为主，无法表示一个模块里的不同方法、权限和设备边界。现在增加了逐 API、
   逐设备台账，并保留没有 SysCap 标记的文档条目。
3. 旧审计停在 SysCap、动态库和 System Ability 层，遗漏了系统服务继续委托给预装 HAP 的链路。
   现在逐个核对 `/system/app` payload、`install_list.json`、签名能力白名单、BMS 实际注册状态、
   HAP 中的 Ability/UIExtension 入口，以及生产源码硬编码的目标包名。

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
| 系统 HAP Provider 规则 | 38 |
| 生产源码 bundle token（全部保留） | 468 |

逐 API 大文件可由脚本再生并被 Git 忽略；提交中保留
`api-usability-summary.json`、SysCap 总账和关键运行证据。

## 系统 HAP Provider 与镜像装配

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
| 设备合同内不可用的 Provider 流程 | 13 / 38 | 16 / 38 |

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
- **权限设置入口（两种设备）**：AccessToken 服务默认启动
  `com.ohos.permissionmanager.OpenSettingAbility`，但已启用的 PermissionManager HAP 没有声明
  该 Ability 或 Extension。授权弹窗的其他入口存在，不能据此推断“打开权限设置”的完整链路可用。
- **无障碍系统 Provider（两种设备）**：核心事件与虚拟输入 E2E 可以工作，但系统没有屏幕朗读器
  HAP；框架主要路径硬编码 `com.ohos.screenreader/AccessibilityExtAbility`，另一路安装监听又检查
  `com.ohos.hmos.screenreader`。字幕状态查询也能返回，但启用字幕助手会启动缺失的
  `com.ohos.vassistant/AiCaptionServiceExtAbility`。因此 Vision 与 Hearing 只能标为部分可用。
- **Photos（2in1）**：HAP 存在但未注册；证书指纹与能力白名单不一致，手工安装被 BMS
  拒绝。Photo Picker 返回空结果却没有可用选择界面。phone 的相同调用会真实启动
  `com.ohos.photos/PickerUIExtensionAbility`。
- **CalendarData、PrintSpooler、DLP（2in1）**：payload 均存在但未注册，且实际证书与
  `install_list_capability.json` 不一致；手工安装触发 signature/capability-list 或
  privileged-extension 校验失败。这解释了 Calendar 的 201、Print 的无扩展，以及 DLP
  能力无法激活。
- **Settings（2in1）**：SettingsData 查询可用，但 `com.ohos.settings` 本体未注册；其中的
  Wi-Fi、蓝牙、免打扰、密码、USB Debug 等系统 UIExtension/系统对话框不能据此视为可用。
- **SceneBoard 替代关系（2in1）**：Launcher、SystemUI 未注册是产品策略的一部分，SceneBoard
  提供桌面、通知和系统对话框入口；审计把这些作为候选 provider 处理，没有将这两项简单误报
  为缺失。FileManager 虽未注册，但 `com.ohos.filepicker` 已启用，因此基础文件选择仍可用。
- **EDM 与 Wallpaper（两种设备）**：基础服务查询分别可工作，但生产源码所需的
  `com.ohos.adminprovisioning` 和配置声明的 `com.ohos.wallpaper` payload 不存在，相关 UI/
  provisioning 子流程不完整。
- **USB 配置陈旧但实际 Provider 正常**：配置引用缺失的 `com.usb.function`，生产代码实际使用
  已启用的 `com.usb.right`，且 `UsbFunctionSwitchExtAbility` 存在。USB gadget 仍因没有 UDC
  后端而不可用，但不能把它误诊为 USB 对话框 HAP 缺失。

生产源码扫描覆盖 `base`、`foundation`、`applications` 的非测试实现，得到 2,843 次系统包
token、468 个唯一 token，其中 168 个直接出现在 `base` 或 `foundation`。报告现在保留并分类全部
468 个 token，不再先与已知镜像包求交集；否则“源码引用、镜像和配置均不存在”的 provider 会被
过滤掉。扫描同时按已安装包、源码 AppScope 声明和 Ability/Extension 后缀归一化，已发现
`com.ohos.mediacontroller`/`com.hmos.mediacontroller`、ScreenReader 前缀漂移以及存在 bundle 但缺
entrypoint 的问题。

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
| 已确认行为失败或部分失败 | 99 |
| 画像或打包失败 | 7 |
| 已验证行为子集 | 123 |
| 需要外部设备、云或账号 | 7 |
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
- **Vulkan**：`vkCreateInstance` 返回 `VK_ERROR_INCOMPATIBLE_DRIVER`。
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
| 已确认行为失败或部分失败 | 86 |
| 画像或打包失败 | 5 |
| 已验证行为子集 | 119 |
| 需要外部设备、云或账号 | 5 |
| 需要特权系统角色 | 2 |
| 需要交互 UI | 1 |
| 仅编译期契约 | 1 |
| 仅测试框架 | 2 |

### 2in1 新确认的重要问题

- **SelectionInput**：文档明确支持 PC/2in1，镜像也声明 true，但精确 2in1 SDK profile 反而
  漏掉该能力。SA 8500 存在，系统配置指向 `com.selection.selectionapplication`，镜像却没有安装
  这个 bundle；listener/content 调用分别返回 `33600003` 和 `33600001`。
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

修正动态/静态限定符后，phone 官方画像仍有 57 个模块缺运行导出，涉及 13 个公开函数和
35 个 system API 函数；2in1 为 48 个模块、15 个公开函数和 23 个 system API 函数。369 个
只属于静态 ArkTS 的导出不再被误报为动态 NAPI 缺失。

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
| 所属能力已验证子集、方法未单独执行 | 9,337 | 9,140 |
| 所属能力部分失败、方法未单独执行 | 19,929 | 18,715 |
| 已确认关联能力失败 | 4,395 | 4,286 |
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
- `ci/capability-audit/known-findings.json`

严格校验命令和再生顺序见 `ci/capability-audit/README.md`。
