# OpenHarmony 7.0 phone / 2in1 系统能力审计

审计日期：2026-09-22

## 结论

当前 QEMU 产物不能把 `canIUse=true`、模块可加载、库存在或 System Ability 已注册解释为
“能力可用”。phone 和 2in1 都存在声明、权限、API 表面、服务配置、内核以及虚拟硬件后端
不一致的问题。

本轮修正了此前审计的两个根本缺口：

1. 旧解析器只为“方法段落自己重复写了 SysCap”的条目建账。OHOS 7 大量 Native 文档只在
   文件头声明一次 SysCap，例如 Camera 的几十个 C 函数，因此旧总数漏掉了数千个 API。
   新解析器从 API 标题出发，把文件/模块契约继承给每个方法。
2. 旧总账以 SysCap 为主，无法表示一个模块里的不同方法、权限和设备边界。现在增加了逐 API、
   逐设备台账，并保留没有 SysCap 标记的文档条目。

修正后，完整表面清单包含 **325 个公开 SysCap、37,920 个文档 API 条目、32,280 个可调用
条目、594 个动态 ArkTS 模块入口、484 个静态 ArkTS 模块入口、6,768 个有头文件依据的
Native C 函数**。所有条目都有 phone 和 2in1 两个结果；严格校验器已通过，状态为
`complete_surface_inventory_behavior_pending`。

这表示“能力表面没有再被静默漏掉”，不表示 37,920 个 API 都已真实调用。当前仍有 phone
27,161 条、2in1 27,735 条方法级行为待验证。总账明确保留这些 pending，避免用模块或 SysCap
级成功覆盖未调用的方法。

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
| 有直接证据的关键运行后端 | 26 / device |

逐 API 大文件可由脚本再生并被 Git 忽略；提交中保留
`api-usability-summary.json`、SysCap 总账和关键运行证据。

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
| 已确认行为失败 | 49 |
| 画像或打包失败 | 8 |
| 权限注册缺口 | 6 |
| API 表面失败且尚未归因 | 25 |
| 已验证行为子集 | 7 |
| 方法设备边界失败 | 1 |
| 行为待验证 | 146 |

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
- **Network statistics/policy**：BPF syscall 返回 `ENOSYS`，依赖 eBPF 的 UID 统计和策略后端
  不完整。
- **SelectionInput**：OHOS 7 文档限定为 PC/2in1，phone 却声明 true，属于错误继承。
- **分布式/SoftBus/AVCast**：默认启动器使用 QEMU user-mode NAT，guest 之间不能完成对端发现；
  需要 bridge 和第二设备才能使用。

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
| 已确认行为失败 | 37 |
| 画像或打包失败 | 5 |
| 权限注册缺口 | 6 |
| API 表面失败且尚未归因 | 24 |
| 已验证行为子集 | 4 |
| 行为待验证 | 145 |

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
- 使用 `--a11y` 虚拟多点触控时，phone 和 2in1 Accessibility E2E 通过；
- 2in1 native Hypium 全套中 32/33 模块零失败，总计 96 pass / 3 fail；3 个失败都在未授予
  screen-capture 权限的 WindowManager，授权后只剩可见窗口数量 fixture 问题。

这些结果只提升被实际覆盖的方法，不会把同一 SysCap 下未调用的方法整体标为通过。

## 尚未完成的行为验证

逐 API 台账当前仍有：

| 状态 | phone | 2in1 |
| --- | ---: | ---: |
| 行为待验证 | 27,161 | 27,735 |
| 已确认关联能力失败 | 2,985 | 1,845 |
| 部分失败、方法待细分 | 4,003 | 3,018 |
| API 表面缺失 | 306 | 239 |
| profile/打包失败 | 1,870 | 3,695 |
| 权限注册失败 | 44 | 56 |
| 文档明确不支持该设备 | 753 | 578 |
| 文档缺 SysCap 契约 | 179 | 180 |

因此不能宣称“所有 OHOS API 已经可用性验证完成”。当前完成的是可再生的全表面清单、双设备
分类和已知后端失败传播；剩余工作必须继续按未验证队列运行真实 HAP/Native/XTS 行为测试，
并在 ARM64 代表包验证后覆盖 armv7a 和 x86_64。

## 主要产物

- `docs/capability-audit/capability-coverage-ledger.json`
- `docs/capability-audit/api-usability-summary.json`
- `docs/capability-audit/runtime-backend-audit.json`
- `docs/capability-audit/summary.json`
- `docs/capability-audit/runtime/arm64-phone/permission-audit.json`
- `docs/capability-audit/runtime/arm64-2in1/permission-audit.json`
- `docs/capability-audit/runtime/arm64-2in1/native-ohostest-summary.json`
- `ci/capability-audit/known-findings.json`

严格校验命令和再生顺序见 `ci/capability-audit/README.md`。
