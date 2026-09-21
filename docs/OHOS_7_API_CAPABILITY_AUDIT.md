# OpenHarmony 7.0 phone / 2in1 系统能力审计

审计日期：2026-09-22

## 结论

当前 QEMU 镜像不能把声明为 `true` 的能力整体视为可用。完整扫描已经覆盖 OHOS 7
公开集合中的 **327 个 SysCap**、**594 个 ArkTS 模块入口**（526 `@ohos.*`、20
`@system.*`、48 `@kit.*`）、API 26 公开 C ABI、
System Ability、init/HDF、内核接口和一批实际行为探针，并分别记录 phone 与 2in1。
`permissions.d.ts` 与 `arkts/builtin` 是权限/语言声明，不是 OHOS 运行模块，因此没有送入
`napi_load_module()`，也不计入 594 个模块入口。

本轮新增并确认的关键问题包括：

1. **API 26 的 ArkTS 运行导出面大面积不完整。** 镜像自报 API 26，但 phone 官方画像涉及的
   83 个模块缺少 474 个应存在的运行值，其中包含 189 个公开函数和 151 个 system API
   函数；2in1 为 74 个模块、364 个运行值、94 个公开函数和 145 个 system API 函数。
   模块本身可以 import，缺失函数却是 `undefined`。Sensor/Wi-Fi/Location/Display/Image 等
   多个基础能力均受影响。
2. **基础音频输出实际不可用。** phone 和 2in1 都能创建 audio manager、枚举 MIC/SPEAKER，
   也能创建 `OH_AudioRenderer`；但 `Start()` 返回
   `AUDIOSTREAM_ERROR_ILLEGAL_STATE`，状态停在 `PREPARED`，帧数与写回调均为 0。两种设备
   启动时都报 `AudioSeekCpuDaiDevice: daiController is empty`。此前只验证 manager 的结论是
   假阳性。打包启动命令没有添加任何 QEMU audio device，内核还关闭了
   `CONFIG_SND_VIRTIO`，属于明确的镜像/虚拟硬件实现缺口。
3. **Audio Suite 是空壳。** 两种镜像内的 `libohaudiosuite.so` 只有 5176 字节，只导出
   `_init/_fini`，缺少 API 26 的全部 48 个公开符号。phone 发布文档要求此能力，但
   `canIUse()` 为 false。
4. **phone 存在 9 个契约能力不可发现，2in1 存在 3 个。** 这不是不同系统的合理默认值，
   而是当前镜像与 OHOS 7 SDK/发布文档不一致。
5. **镜像仍大面积多报。** 相对最新 SDK 画像，phone 多声明 61 项，2in1 多声明 75 项。
   其中已经证明 Wi-Fi、Bluetooth、Vulkan、部分 MSDP/硬件和内核能力会出现失败或假成功。
6. **2in1 的官方可调用模块有两个不能加载：** `@ohos.busManager.serial` 和
   `@ohos.net.netFirewall`。phone 的官方可调用模块加载失败数为 0，但这只证明入口存在，
   不代表行为正确。

因此，当前产物不能得出“基本没影响”或“只是不同系统配置不同”的结论。画像差异可以是
合法差异；当能力属于目标设备契约却返回 false，或声明为 true 但后端/行为失败时，就是
实现或打包问题。

## 审计基线

本轮没有继续使用滞后的本地文档快照，而是固定到远端 `OpenHarmony-7.0-Release` 最新提交：

| 来源 | 提交 |
| --- | --- |
| `openharmony/docs` | `9585fb12fa8f977accfd9435d9f5537b14734473` |
| `openharmony/interface_sdk-js` | `411d28f767bd6cd2a6905e3c6b15f0992f55b81b` |
| API | 26.0.0 |

本地旧快照分别为 docs `37cf961...`、interface/sdk-js `de6fe2a...`。最新 2in1 SDK
画像已经移除了 `SoftBus.Core` 和六项 Driver/USB extension 能力；继续使用旧快照会把
镜像差集算错。

运行代表包：

- ARM64 phone：`window-manager-2in1-20260917/openharmony-qemu-arm64-arm64_virt-phone.tar.gz`
- ARM64 2in1：`window-manager-2in1-20260917/openharmony-qemu-arm64-arm64_virt-2in1.tar.gz`

两者均从原始归档重新解包到临时目录后启动，未直接修改归档。完整基线记录在
`docs/capability-audit/source-baseline.json`。

## 审计模型

每个 SysCap 分别检查五层：

```text
OHOS 7 文档和 SDK 设备画像
  -> 镜像 SysCap / part / feature
  -> ArkTS 模块和 Native C ABI
  -> init / System Ability / HDF / 内核或虚拟设备后端
  -> 普通 HAP 或原生进程中的真实调用与返回语义
```

其中：

- `canIUse=true` 只表示镜像声明该能力；
- 模块可加载只表示入口存在；
- SA、库或设备节点存在只表示静态表面存在；
- 必须观察到 API 的真实结果、副作用、回调或状态变化，才能把相应行为标为已验证；
- 没有硬件时返回“无设备”可以是正确行为，例如 IR 和 USB 枚举；
- 返回成功但状态不变化、数据恒为 0、consumer/driver 不存在属于假成功或部分失败。

## 全量覆盖结果

### 公开集合

| 项目 | 数量 |
| --- | ---: |
| OHOS 7 公开 SysCap 总账 | 327 |
| 镜像声明或目标契约涉及的 SysCap | 304 |
| 文档 API 条目 | 32,043 |
| 文档可调用条目 | 21,899 |
| ArkTS 注解涉及的 SysCap | 266 |
| C API 注解涉及的 SysCap | 107 |
| XTS 源码涉及的 SysCap | 272 |
| 显式设备行为边界 | 1,071 |

327 项均已进入 `capability-coverage-ledger.json/csv`；两种设备的 327 项均执行了
`canIUse()`，594 个公开模块入口均执行了加载/入口类型探针。总账不会再因为某项未被人工点名而
漏掉该项。

### phone

| 指标 | 结果 |
| --- | ---: |
| 最新 SDK default 画像 | 232 |
| 最新 phone 文档最小画像 | 231 |
| 两个来源的联合契约 | 242 |
| 当前镜像声明 | 292 |
| 327 项中 `canIUse=true` | 292 |
| 联合契约中 `canIUse=true` | 233 |
| 联合契约中 `canIUse=false` | 9 |
| 超出最新 SDK 画像的声明 | 61 |
| ArkTS 运行模块加载 | 496 / 594 |
| 官方可调用模块加载失败 | 0 |

phone 的 9 个契约缺口：

| SysCap | 契约来源 | 当前结果 |
| --- | --- | --- |
| `FileManagement.File.DistributedFile` | phone 文档 | false；HMDFS 已挂载，但能力不可发现且未做双设备闭环 |
| `HiviewDFX.HiDumper` | phone 文档 | false；命令/SA 有部分实现，声明与契约不一致 |
| `Multimedia.AVSession.AVInputCast` | SDK default | false；镜像漏配 |
| `Multimedia.Audio.SuiteEngine` | phone 文档 | false；48/48 C 符号缺失 |
| `Security.DataTransitManager` | phone 文档 | false；DSLM 后端未闭合 |
| `Security.DeviceAuth` | phone 文档 | false；存在部分服务，双设备流程未闭环 |
| `Security.DeviceSecurityLevel` | phone 文档 | false；`/proc/dsmm/dsl` 缺失 |
| `UserIAM.UserAuth.PinAuth` | phone 文档 | false；init 报 `pin_auth_host` 配置错误 |
| `Window.SessionManager` | phone 文档 | false；相关窗口实现存在但 profile 漏配 |

phone 文档还包含 `SoftBus.Core`。最新 SDK default 已移除它，但当前镜像仍声明为 true，
所以它没有计入上述 9 个 false；其跨设备行为仍需真实对端验证。

### 2in1

| 指标 | 结果 |
| --- | ---: |
| 最新 SDK 2in1 画像 | 221 |
| Tablet 文档参考画像 | 223 |
| 当前镜像声明 | 293 |
| 327 项中 `canIUse=true` | 293 |
| SDK 契约中 `canIUse=true` | 218 |
| SDK 契约中 `canIUse=false` | 3 |
| 超出最新 SDK 画像的声明 | 75 |
| ArkTS 运行模块加载 | 496 / 594 |
| 官方可调用模块加载失败 | 2 |

2in1 的 3 个确定契约缺口：

| SysCap | `canIUse` | 模块/行为 |
| --- | --- | --- |
| `BusManager.Serial` | false | `@ohos.busManager.serial` 加载失败，NAPI status 10 |
| `Communication.NetManager.Eap` | false | `@ohos.net.eap` 可加载，但能力漏声明 |
| `Multimedia.Audio.DeviceEnhance` | false | manager 可创建，但 enhanced routing 返回不支持 |

此外，Tablet 参考画像和大量 PC/2in1 方法文档包含 `Window.SessionManager`，但最新 2in1
SDK 与镜像都省略它，`canIUse()` 为 false。它是**文档与 SDK 的上游契约冲突，同时也是
当前 2in1 功能发现缺口**，不能仅依据 SDK JSON 忽略。

## 文档与 SDK 自身不一致

### phone：10 项文档有、SDK default 无

`SoftBus.Core`、`DistributedFile`、`HiDumper`、`Audio.SuiteEngine`、`ImageEffect.Core`、
`DataTransitManager`、`DeviceAuth`、`DeviceSecurityLevel`、`PinAuth`、`Window.SessionManager`。

### phone：11 项 SDK default 有、文档最小表无

`IntelligentScene`、`ArkUI.Circle`、`FolderAuthorization`、`FolderSelection`、
`HyperGraphicManager`、`HiRetrieval`、`AVInputCast`、`SystemLoad`、
`BackgroundProcessManager`、`Security.Cipher`、`Test.PerfTest`。

### 2in1：Tablet 参考有、SDK 2in1 无

共 23 项，主要是分布式文件/CloudSync、Location/GNSS、Camera、Sensor、ImageEffect、IR、
Audio Suite、安全设备能力和 `Window.SessionManager`。

### 2in1：SDK 2in1 有、Tablet 参考无

共 21 项，主要是 `BusManager.Serial`、EAP、NetFirewall、DistributedHardware、
AVInputCast、Audio.DeviceEnhance、Input.Cooperator、Print、DLP 和 USB Serial 等。

因此 2in1 不能直接用 Tablet 文档替代精确 SDK 画像，但 Tablet/PC 方法文档也不能被完全
丢弃。总账同时保留 exact SDK 与 reference profile 两列。

## ArkTS 与 Native ABI

### ArkTS 594 模块入口

两种设备均为 496 个加载成功、98 个 `napi_load_module()` 失败。98 个失败不能全部算作系统故障：

- 48 个 `@kit.*` 是编译期聚合/re-export 入口，不是独立 NAPI 模块；
- 另有 30 个接口、类型、ExtensionContext 等编译期声明，不是应由 `napi_load_module()`
  加载的运行模块；
- 20 个 legacy `@system.*` 模块在两种设备上全部加载成功；
- phone 有 20 个可调用失败模块，全部位于 phone 精确 SDK 画像之外；
- 2in1 有 18 个画像外可调用失败模块；
- 2in1 另有 2 个官方画像内失败：Serial 与 NetFirewall。

这也修正了把 `BackupExtensionContext` 一类类型声明误报为模块缺失的问题。

模块加载仍不足以证明 API 表面完整。本轮继续用 TypeScript AST 排除 interface/type 等纯
编译期声明，再把 API 26 的 function/class/enum/namespace/variable 与运行对象的 own
properties 逐项比较：

| 指标 | phone | 2in1 |
| --- | ---: | ---: |
| 成功加载且导出枚举完成 | 496 | 496 |
| 整个导出对象为空 | 0 | 0 |
| 官方画像内存在缺失导出的模块 | 83 | 74 |
| 官方画像内缺失运行值 | 474 | 364 |
| 其中公开函数 | 189 | 94 |
| 其中 system API 函数 | 151 | 145 |

两种镜像的完整运行对象实际均缺少 787 个 API 26 运行值；profile 过滤后数量不同。为了排除
`napi_load_module()` 绕过新桥接层造成的误判，又用最新接口声明直接编译普通 ArkTS HAP。
两种设备上的十个代表项仍全部为 `undefined`：

- Sensor `onAccelerometerChange`；
- Location `getCurrentDistrict`；
- Ethernet `enableEthernetInterface`；
- Image `createIncrementalSource`；
- Matrix4 `combine`；
- Display `onAdd`；
- Emitter `onEventData`；
- Telephony observer `onNetworkStateChange`；
- Wi-Fi `onWifiStateChange`；
- ErrorManager `onUnhandledRejection`。

这不是单纯的旧 SDK 编译问题：HAP 已用最新 `OpenHarmony-7.0-Release` 声明编译，运行镜像
也自报 `OpenHarmony-7.0.0.39 / API 26`。镜像内甚至存在 `sensor_abc.abc`、
`libsensor_taihe_native.z.so` 等新桥接产物及对应符号，但普通动态 ArkTS HAP 得到的模块对象
没有这些属性。故障位于生成桥接产物的装配、模块路由或注册链路；只把库/ABC 放入镜像还
不够。逐模块、逐导出明细保存在 `arkts-export-surface-latest.json`。

### C/NDK ABI

API 26 header 共形成 105 个 SysCap、128 个库契约。运行镜像的主要结果：

- phone 精确 SDK 画像内没有 C ABI 库/符号缺口；
- 2in1 精确 SDK 画像内缺少 NetFirewall 对应库；
- 两种镜像的 `libohaudiosuite.so` 均缺少 48 个公开符号；
- 由于 Audio Suite 属于 phone 文档最小画像而非 SDK default，若只统计 SDK JSON 会把这个
  严重问题漏掉。

### System Ability 与服务面

运行时逐个调用了已注册 SA 的 dump 入口：phone 97 个、2in1 98 个，均无超时或非零退出。
Form、Notification、InputMethod、Selection 等 dump 需要额外参数，CommonEvent 没有默认输出，
所以这些结果只证明 SA 已注册且 IPC 入口可达。它们不会把相应能力自动升级为“可用”；
Audio、Wi-Fi、Bluetooth、Camera 等反例已经证明 SA 存在仍可能没有数据后端。

## 已确认的行为失败

| 能力/链路 | phone | 2in1 | 证据 |
| --- | --- | --- | --- |
| Audio Core / Renderer | 失败 | 失败 | HAP renderer `Start=2`，0 frame/0 callback；DAI controller 为空；启动器无 audio device，`CONFIG_SND_VIRTIO` 关闭 |
| Audio Suite | 失败 | Tablet 参考不完整 | 空壳 so，48/48 符号缺失 |
| Bluetooth Core | 失败 | 失败 | enable 假成功后回到 OFF；`libbt_vendor.z.so` 缺失 |
| Wi-Fi Core / STA | 失败 | 失败 | enable 假成功；linked-info/scan 失败；AP6275S HDF driver 不存在 |
| Camera Core | 失败 | 画像外误报 | phone 返回 7400101/count 0，camera host 不存在 |
| Vulkan | 失败 | 失败 | loader 存在，`vkCreateInstance=-9`，无 ICD |
| AccessToken API 26 | 部分失败 | 部分失败 | `GET_ALL_PERMISSIONS`、`GET_SPM_VERSION` 返回 ENOTSUP |
| XPM / CodeSign | 部分失败 | 部分失败 | API 26 ioctl 不被内核识别，部分用户态路径吞掉错误 |
| QoS | 失败 | 失败 | authority backend 缺失，内核拒绝未授权 PID |
| NetFirewall | 画像外误报 | 失败 | feature/模块/client/service/SA 8300 均缺失 |
| FusionConnectivity | 失败 | 失败 | init 用户/组缺失，服务配置解析失败 |
| MSDP DeviceStatus | 画像外误报 | 画像外误报 | client 库缺失，服务使用 mock backend |
| Storage quota | 部分失败 | 部分失败 | F2FS quota 初始化失败，统计/限额可假成功 |
| NetManager eBPF | 部分失败 | 部分失败 | BPF syscall 返回 ENOSYS |
| HiTrace ARM64 | 失败 | 失败 | `CONFIG_FTRACE` 关闭 |
| HiDebug 图形内存 | 假成功 | 假成功 | 缺 DMABUF_PROCESS_INFO，返回 success/0 KiB |
| BackgroundProcessManager | phone 方法边界错误 | 2in1 后端断链 | phone native child 未返回文档要求的 801；2in1 event 134 无 consumer |
| PSI/freezer | ARM64/x86_64 失败 | ARM64/x86_64 失败 | 内存压力源和真实 freezer cgroup 缺失 |
| Thermal | 部分失败 | 部分失败 | API 返回 level 0，但 service zones 为 0，gpu thermal 读取失败 |

`SELinux=Permissive` 还是全局风险：当前大量 AVC 被放行，现有成功结果不能证明切换到
Enforcing 后仍成立。

## 已验证的可用子集与正确的“无设备”行为

| 能力 | phone | 2in1 | 范围 |
| --- | --- | --- | --- |
| Settings / DataShare | 可用子集 | 可用子集 | HAP 同步/异步读取 brightness=255，URI 正确 |
| ImageEffect | 可用子集 | 画像外但实现可调用 | create、brightness filter、count、release 成功 |
| Sensor | 模拟数据可用 | 画像外模拟实现 | `sensor_test` accelerometer 在 2 秒收到 9 次回调 |
| Battery / Display / Window Core | 可用子集 | 可用子集 | 状态、800×500、75 Hz 和 manager 查询成功 |
| Native Child Process | 设备边界错误 | 可用子集 | 2in1 21 项回归通过；phone 应返回 801 |
| Infrared | 正确无设备 | 画像外 | `hasIrEmitter=false`，频率列表为空 |
| USB manager | 正确无设备 | 正确无设备 | 返回空设备/附件列表，不等于 USB 透传已验证 |
| Location | 入口可用 | 画像外 | phone start/stop 成功，10 秒无定位回调，provider 未验证 |

2in1 启动早期 HOME/OOBE 曾出现 DataShare 15700010，但系统 UI 随后批量读取成功，HAP
稳定后同步/异步读取也成功。它应归类为启动 readiness/retry 缺陷，而不是整个 DataShare
能力不可用。

## 画像污染：声明不等于支持

当前产品把 `rich.json` 与目标设备画像做并集合并，目标画像不能删除 rich 已加入的 part。
这导致 phone/2in1 分别多声明 61/75 个 SysCap。典型污染包括：

- phone：外设 DDK/HID/SCSI/USB Serial、MSDP、ImageEffect、MIDI、Print、DLP、
  Companion/FaceAuth、IntelligentVoice 等；
- 2in1：Camera、Location/GNSS、Sensors、Telephony/eSIM、Battery 以及多种实体硬件能力；
- 两种设备：Wi-Fi、Bluetooth、Vulkan、部分安全/资源调度能力虽被声明，但真实后端失败。

修复时应以目标 phone/2in1 画像为唯一基线，仅显式增加 QEMU 已实现且通过行为验证的
能力。打包门禁还要维护 forbidden part/SysCap 差集，禁止 rich 的新增项再次自动进入。

## 方法级设备边界

OHOS 7 文档扫描得到 1,071 个显式设备边界块。自动分类结果：

| 分类 | phone | 2in1 |
| --- | ---: | ---: |
| supported | 599 | 681 |
| unsupported | 269 | 183 |
| conditional hardware | 6 | 6 |
| conditional mode | 72 | 72 |
| conditional policy | 67 | 67 |
| review required | 58 | 62 |

这说明“模块支持”不能替代方法级判断。Native Child Process 就属于同一 Ability Runtime
SysCap 下 phone 与 2in1 返回语义不同的公开方法。所有待人工判断项保存在
`method-device-boundaries.json/csv`，没有从总账中删除。

## 当前总账状态

总账为每个 SysCap、每种设备保留：来源画像、镜像声明、`canIUse`、ArkTS 模块加载、C ABI、
镜像组件、已知行为证据和后续验证环境。

联合契约内当前状态：

| 状态 | phone（242） | 2in1（221） |
| --- | ---: | ---: |
| 已确认行为失败/部分失败 | 15 | 14 |
| profile 或打包失败 | 8 | 3 |
| ArkTS 导出面失败，尚未逐项调用 | 55 | 46 |
| 已验证可用子集且导出面完整 | 6 | 4 |
| 方法设备边界失败 | 1 | 0 |
| 行为仍需端到端验证 | 157 | 154 |

这里的“仍需验证”不是漏项：这些条目已经完成 profile、`canIUse`、模块、导出面和 ABI 层扫描，
但没有足够证据把上万个 API 的实际语义判成可用。把它们仅凭模块/SA 存在批量标为可用，
会重现此前漏掉 Audio、Wi-Fi、Bluetooth、quota 和 QoS 的错误。

## 修复顺序

### 第一阶段：让声明可信

1. 停止 `rich.json` 并集合并，按最新 SDK 画像重新生成 phone/2in1 part 与 SysCap。
2. 处理 phone 的 9 个契约缺口和 2in1 的 3 个缺口；每项选择完整实现或按官方契约修正画像。
3. 对 `Window.SessionManager` 明确解决文档/SDK 冲突，并确保 PC/2in1 方法可发现。
4. 模块、库、SA、init 用户、HDF/内核后端任一缺失时禁止声明能力为 true。

### 第二阶段：修复公共基础能力

1. 修复 API 23-26 Taihe/ANI/ABC 与动态 ArkTS 模块对象之间的装配和注册链路；以最新
   interface-sdk-js 自动生成逐导出门禁，任何目标画像内运行声明为 `undefined` 都阻止发布。
2. 为启动器添加匹配的虚拟声卡，启用对应内核驱动并补齐 OHOS HDF audio DAI/PCM adapter，
   先让真实 renderer 产生回调和帧；
   Audio Suite 必须换成导出完整 API 26 符号的实现或关闭能力。
3. 为 Wi-Fi、Bluetooth、Camera、Location 等能力实现虚拟/宿主 provider；没有 provider 时
   从对应设备画像中关闭。
4. 补齐 AccessToken、XPM、CodeSign、BPF、FTRACE、PSI、freezer、quota、DMABUF 等匹配
   API 26 的内核能力，删除用户态假成功兼容。
5. 修复 QoS 授权、BackgroundProcessManager consumer/AppNap、Fusion 账号、SceneBoard 权限，
   并在 SELinux Enforcing 下重跑。

### 第三阶段：分布式、账号、云与外设

SoftBus、DistributedFile、DeviceAuth、DataTransit、CloudSync 等必须使用真实第二设备或
可控 peer 验证发现、连接、读写、断连和重连。USB/Serial/NFC/NearLink/生物认证需要真实
透传或模拟后端，不以“空列表”证明完整能力可用。

## 打包门禁

每项能力至少记录：declaration、product feature、module/ABI、service、dispatch、backend、
smoke、device boundary 八层。以下情况阻止发布：

- 目标契约能力 `canIUse=false`；
- `canIUse=true` 但公开模块、C 符号、SA/init 或固定后端缺失；
- API 返回成功但没有状态变化、数据、回调或副作用；
- 目标画像排除的 part 被 rich 重新引入；
- 内核 syscall/ioctl 返回 `ENOSYS`/`ENOTSUP`；
- 物理设备能力没有虚拟/宿主 provider，却仍声明为 true；
- 文档规定的不支持设备没有返回指定错误码；
- SELinux 不是 Enforcing，或成功路径依赖未解释的 AVC；
- 代表包未先完成启动与本轮行为验证。

多产物打包继续执行项目已记录的固定顺序：**先构建一个 ARM64 代表产物，启动并验证本轮
全部修复；方向确认后，再构建其余架构/设备产物，并逐包保存日志和校验和。**

## 复现

生成全量矩阵：

```bash
python3 ci/capability-audit/build_matrix.py \
  --ohos-root /Volumes/PSSD/qemu/openharmony \
  --docs-root /private/tmp/ohos-docs-7-latest-9585fb1 \
  --sdk-js-root /private/tmp/ohos-sdk-js-7-latest-411d28f \
  --phone-syscap /path/to/phone-syscap.json \
  --two-in-one-syscap /path/to/2in1-syscap.json \
  --findings ci/capability-audit/known-findings.json \
  --output-dir docs/capability-audit
```

构建 HAP 探针后，在 phone/2in1 各运行一次，再分析全量 SysCap 与模块：

```bash
python3 ci/capability-audit/analyze_syscap_runtime.py \
  --matrix docs/capability-audit/all-capability-matrix.json \
  --device phone \
  --probe-log /path/to/results.log \
  --output /path/to/syscap-runtime.json

python3 ci/capability-audit/analyze_arkts_modules.py \
  --sdk /Applications/DevEco-Studio.app/Contents/sdk/default/openharmony \
  --api-dir /private/tmp/ohos-sdk-js-7-latest-411d28f/api \
  --kits-dir /private/tmp/ohos-sdk-js-7-latest-411d28f/kits \
  --profile phone \
  --probe-log /path/to/results.log \
  --output /path/to/arkts-module-load-latest.json

node ci/capability-audit/analyze_arkts_exports.js \
  --typescript /path/to/typescript/lib/typescript.js \
  --api-dir /private/tmp/ohos-sdk-js-7-latest-411d28f/api \
  --kits-dir /private/tmp/ohos-sdk-js-7-latest-411d28f/kits \
  --runtime /path/to/arkts-module-load-latest.json \
  --output /path/to/arkts-export-surface-latest.json
```

合并总账：

```bash
python3 ci/capability-audit/build_coverage_ledger.py \
  --matrix docs/capability-audit/all-capability-matrix.json \
  --runtime-root docs/capability-audit/runtime \
  --output docs/capability-audit/capability-coverage-ledger.json

python3 ci/capability-audit/verify_results.py \
  --matrix docs/capability-audit/all-capability-matrix.json \
  --runtime-root docs/capability-audit/runtime \
  --ledger docs/capability-audit/capability-coverage-ledger.json \
  --api-dir /private/tmp/ohos-sdk-js-7-latest-411d28f/api \
  --kits-dir /private/tmp/ohos-sdk-js-7-latest-411d28f/kits
```

## 主要证据文件

- `docs/capability-audit/capability-coverage-ledger.json/csv`：327 项 phone/2in1 总账
- `docs/capability-audit/all-capability-matrix.json`：公开能力来源、画像、组件与 finding
- `docs/capability-audit/method-device-boundaries.json/csv`：1,071 个方法设备边界
- `docs/capability-audit/runtime/arm64-{phone,2in1}/syscap-runtime.json`：327 项 `canIUse`
- `docs/capability-audit/runtime/arm64-{phone,2in1}/arkts-module-load-latest.json`：594 模块入口
- `docs/capability-audit/runtime/arm64-{phone,2in1}/arkts-export-surface-latest.json`：API 26
  逐模块、逐运行导出差集
- `docs/capability-audit/runtime/arm64-{phone,2in1}/c-api-abi.json`：API 26 C ABI
- `docs/capability-audit/runtime/arm64-{phone,2in1}/hap-probe/results-ohos7-latest.log`：HAP 原始结果
- `docs/capability-audit/runtime/arm64-{phone,2in1}/native-probes/audio_stream.txt`：音频流失败
- `docs/capability-audit/runtime/audio-boot-serial.txt`：两种设备的 HDF DAI 启动错误
- `docs/capability-audit/runtime/audio-packaging.txt`：启动器与内核的虚拟音频缺口
- `docs/capability-audit/runtime/audio-suite-elf.txt`：Audio Suite 空壳导出
- `docs/capability-audit/runtime/api26-export-dispatch.txt`：API 身份、十项直接 HAP 验证和
  Taihe/ABC 装配证据

## 审计边界

这次已经建立“不依赖人工点名”的完整能力清单，并对全部 327 项完成画像、声明和运行时
发现性检查，对全部 594 个公开 ArkTS 模块入口完成加载、类型和逐导出检查。ARM64 上已确认的失败可以直接用于修复
和发布门禁。仍有 157 个 phone 契约能力、154 个 2in1 契约能力缺少端到端行为证据；分布式、
云、账号、支付和实体硬件类还需要专用环境。它们在总账中明确保留为待验证，不能被报告为
“可用”。armv7a 与 x86_64 目前只有既有静态一致性证据，修复后仍必须按“ARM64 先验证、
再产出其余包”的流程完成架构级运行回归。
