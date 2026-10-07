# OpenHarmony 7.0 QEMU: ArkWeb 与 Vulkan 独立修复记录

固定基线：`OpenHarmony-7.0-Release` manifest
`f079c4ad9848f9cc4a9a4b3a3613ad8fbb142549`。范围为 phone/2in1 ×
armv7a/arm64/x86_64。ArkTS Static 不在本次范围内。以下的“已验证”仅指实际运行过的
测试环境，不能由一个架构推断六个包都通过。

## 当前续修（2026-10-07）：统一对象编码候选，尚未通过新包门槛

以下 R6 是历史失败记录，相关最小权限、回复协议及内核异步 PID 修复均已获用户
批准并实现。用户另批准 RS 两类 sptr 改用标准 Binder 编码，以及普通延迟副本和
ashmem 大事务持有真实对象引用；该候选已纳入部件补丁 0009，主机边界测试通过，
真实三 ABI 的30个 RS 编译单元已经全部通过；按图形仓库要求的九类57规则稳定性审查已完成，
未检出确定新增缺陷，报告为 `report/report_rs_object_encoding_20261007_093932.md`。
首包另已接入18项调用真实产品 RS/IPC 库的边界测试（非跨进程/UI替代）。权限、异步协议、
token/节点归属检查不放宽，新包不兼容旧错误私有编码。
正式配套 M144 依赖的原生内核和官方 HAP 已通过构建及转换校验，V8/SwiftShader/
AVC 仍在继续。详细证据见 `OHOS_7_NATIVE_ARKTS11_GAPS.md`。不能以候选实现、
编译或历史旧包结果认定 ArkWeb/Vulkan 已修复；仍须新代表包真实 Web 恢复及
独立 Vulkan compositor 像素验收，首包门槛 false。

## 历史 R6 实际验收（2026-10-06）：两个能力均有失败

新解压 ARM64 phone / HVF 的包 SHA-256 为
`502b08384576945bab9183281f8c4fe1475d836316354f3b15819962ece6a155`，
实际路径及诊断环境见 `OHOS_7_NATIVE_ARKTS11_GAPS.md` 最新段和首包证据索引。
ArkWeb 的严格恢复 HAP 在首次页面前就失败：renderer 子进程 4910 的
`SetUserId(100)` 返回 EPERM，AppSpawn 返回失败、StartRenderProcess=22，
收到 unexpected renderer exit。不能只验证旧 SIGTERM 故障或把旧包 WebGL PASS 沿用。
身份初始化必须同时兼容普通应用与 renderer 的隔离流程，不能放开 kernel setter 权限。

Vulkan 的两个 XComponent generation 各完成五帧并清理，实际 UI 点击销毁重建已运行；
但 QMP PNG 与系统内部 JPEG 都显示白底紫色启动图，测试区像素是白色而非目标 RGBA。
`r6-hvf-vulkan-result-01.json` 明确失败，RS tree 仍保留 starting-window canvas。
HVF 锁屏可见、RS/SceneBoard 稳定，因此不是“所有 softpipe 均不可用”的证据；
TCG freeze shader 栈另行保留。应用第一帧/渲染连接仍需定位，禁止以离屏或队列成功替代上屏。
首包门槛 false，未构建剩余五包。

继续只读定位确认内部 `CreateRenderConnection` 的服务端未写客户端期待的成功 bool，
且两条成功分支都返回 INVALID_TOKEN_MASK_ID=0。实际 guest 同时记录 hasRemoteObj
错误，客户端未得到有效连接；证据 `render-process-ipc-source-01.log` 固定提交
`81cc9ca9509bccd86c435064136fe45591d29eeb`。拟将两个服务端点对齐现有客户端协议，
新建返回实际请求 token、重复连接返回已存 token，不改变公开 API 或后端。
该轮涉及内部 IPC，当时按 graphic_2d AGENTS 等待用户明确确认；当时未完成修复/new guest
可见像素闭环，不将此源码不一致当成所有图形问题的唯一根因。
ArkWeb 另需最小授权 UID3081 的账号 setter，现有 seccomp 禁止服务切回 root；
无需也不应放开普通应用或最终 renderer 权限。该权限决策在该轮同样待明确确认。

## 历史实际验收（2026-10-05）

新 ARM64 phone 包 SHA-256
`c060979b682568ed747662b9cee7276befa6a06b9cf13b6b4905e8e7f5b2ef22`，
实际包路径、HVF/QEMU/账号/启动命令见 `OHOS_7_NATIVE_ARKTS11_GAPS.md` 和
`/Volumes/PSSD/qemu/validation/first-20261005/first-package-evidence.json`。

bindings live-page 两轮 custom 文档、JS/DOM/Canvas/WebGL1/2 的真实 RGBA 像素、
Rust proxy/native refresh/lifecycle 已通过；五项 Hypium 边界也通过。
修正测试适配器把当前请求 URL 误写为响应 redirect URL 导致的 20 次重定向，
并在引擎导航前安装 Native 生命周期/协议状态，在 controller attach 时只挂 proxy。
当前 ARM64 Native 库 SHA-256
`3dceaf02704e7712fe74ffec1fb31151381fcbbc37cebcf16e70f81c7913c544`。
真实结果 `bindings-arkweb-e2e-07/arkweb-live/67d9853961cbc76132214c309e21df4d/result.json`。
这不包括 renderer crash recovery，不能把后者关闭。

独立 Web 探针的初始图形、无效 shader、异常后继续执行、proxy/刷新均通过，
但 `terminateRenderProcess()` 虽返回 true，renderer 并未退出：其 namespace 内 PID=1，
M144 CEF 使用默认 SIGTERM。新增 AppSpawn `render_pid_namespace` 部件仅给该 renderer
安装 async-signal-safe `_exit` handler，保留已有显式 handler、seccomp、UID 和隔离；
6 项 sanitizer 回归及三产品实际编译通过，**待重包运行验证**。

Vulkan 使用包内 ICD 自动发现，无替换系统 DSO：device/queue/1024-word 回读及
OHOS NativeWindow 十帧/1500 consumer pixels、resize OUT_OF_DATE 通过。
真实 XComponent 则完成 generation 1 → destroy → generation 2，每轮五帧，却实际
compositor PNG 与 QMP monitor 全黑；`vulkan-compositor-01-result.json` 明确失败。
屏幕 AWAKE/ON，不是休眠或只截屏失败。RenderService empty-layer/-3 与始终未 prepare 的
SceneBoard screen tree，定位到 `graphic_2d_feature_rs_enable_uni_render=false`。
phone/2in1 已补配套统一渲染开关及编译前检查，当前 preload 为 true；保持 OpenGL
softpipe，不把启用 Rosen Vulkan 与 Native ICD 混为一谈。可见像素仍须新包复验。

因此首包门槛未通过，只重打同一 ARM64 phone，没有构建其余五包。
下文历史“待测”是当时状态；最新局部通过以本节的精确范围为准。

## ArkWeb：EGL/WebGL 路径

旧 ARM64 phone 镜像的分段 WebView 探针已经得到页面 JS 算术值 `2`、DOM 标题
`Example Domain` 和 Canvas 2D 成功值；WebGL1/2 均超时。EGL 探针发现公共
`libEGL.so` wrapper 广告 `EGL_EXT_create_context_robustness`，但其 QEMU Mesa backend
没有该扩展。ArkWeb 按 wrapper 广告请求 robust context，Mesa 返回
`EGL_BAD_ATTRIBUTE`，共享上下文建立失败。这条链与 Vulkan loader/ICD 无关。
同一旧镜像的 GLES2 对照调用显示：wrapper 与 backend 的普通 context 均成功
(`EGL_SUCCESS`)，请求 robust attribute 均失败 (`EGL_BAD_ATTRIBUTE`)。这进一步把
失败定位到错误扩展广告/属性选择，而不是 GLES2 context 全面不可创建。

修复位于 `patches/common/standard_vpn/components/graphic_2d_egl/`：wrapper 仅在实际
backend 同时支持时广告 robustness。补丁在共享部件层生效，由实际 backend 决定扩展是否
保留，适用于三个架构及 phone/2in1；不能直接假设各架构 Mesa backend 行为一致。

| 架构 | phone | 2in1 | 必须完成的验收 |
| --- | --- | --- | --- |
| arm64 | 旧包已定位 WebGL 失败；新包待测 | 旧复合探针失败；新包待测 | JS、DOM、Canvas 2D、WebGL1/2 各自返回明确结果；EGL 扩展与 backend 一致 |
| armv7a | 待测 | 待测 | 同上，并确认源码构建的 Mesa kms_swrast 路径 |
| x86_64 | 待测 | 待测 | 同上，并确认预编译 Mesa backend 路径 |

已加入 JS proxy 双向调用、页面捕获异常后继续执行、刷新保持状态及 renderer 终止恢复后
重新绘制 WebGL1/2 的独立用例；尚待新 guest 执行。修正扩展广告是已定位
`EGL_BAD_ATTRIBUTE` 的针对性修复，WebGL 是否能完整渲染必须由新包启动后验证。

2026-10-05，bindings 另补真实同进程页面验收：原 Hypium 进程没有主应用的 Web 实例，
不能把注册函数返回或不存在的 WebTag 调用当作页面通过。新 `ArkWebTestAbility` 在创建
Web 引擎前注册 custom scheme，并在真实 Web attach 后安装 Rust proxy、生命周期及协议处理器。
协议处理器原来只有 `receive_data`，现补齐真实 response header 与 `finish`。
主应用以随机 run ID 写自己的结果文件，要求正常应用 UID、两轮实际 custom 页面请求、
JS/DOM/Canvas/WebGL1/2 像素、页面异常后继续执行、JS→Rust 回调及 Native refresh 均成功。
Hypium 保留非法参数/陈旧 refresh 边界，driver 必须先通过 live-page 阶段，不能用边界测试
替代真实页面。新增结果校验器 5 项、其他相关驱动 13 项主机回归通过；不是 guest E2E。

- ARM64 main HAP SHA-256：`bf1af98ac399d79302e3ef7eec1f28ee5b4b70958773aa22aaf890ae9a0c08ca`
- ARM64 ohosTest HAP SHA-256：`2a1fc84b114d86734b5a81a227f12490949ad87477cfd00876a4353056c7ed26`
- ARM64 Rust `.so` SHA-256：`c5273928b7c20a05673c293a44f2d76dbd0d67d9f34282f19c20abb350af96f1`
- 实际 SDK 26 编译日志：`validation/first-20261005/bindings-arkweb-live-{main,test}-build-03.log`

以上 HAP 已顺序编译通过，仍未签名到新 guest 或运行。此 bindings 阶段也不覆盖
renderer crash recovery 或 Vulkan；这两项继续使用独立严格探针。
同一 Rust live-page 路径还已交叉编译为 ELF32 ARM 和 ELF64 x86-64，未覆盖 ARM64
主/测试 HAP 的库；SHA-256 分别为
`5b34b122d2405f13d706181f0b9ffddfbdfd24de7f422cc3a6c3b02442c457a9` 和
`be164ae495d6047e8e83b736091a5ff6c9529ed47e1ea17c24a16e12c01b2322`。
独立输出目录 `validation/first-20261005/bindings-arkweb-live-extra`，两架构仍待对应 HAP
编译、签名及新 guest 运行，交叉编译不是页面通过证明。

## Vulkan：ICD、loader、layer 与 WSI

旧 ARM64 phone 镜像的 Vulkan loader 存在，但无可用 ICD；`vkCreateInstance` 返回
`VK_ERROR_INCOMPATIBLE_DRIVER`。从固定的 ArkWeb/Chromium M144 源码构建的
SwiftShader ICD，在旧镜像的临时目录中可创建 instance、物理/逻辑设备、host-visible
buffer，并可创建 headless surface/swapchain。这是 Native Vulkan 的独立修复路线，
**不会**修复 ArkWeb WebGL。

OHOS loader 通过系统 parameter store 读取 `VK_DRIVER_FILES`，不是只读取进程环境变量。
生产镜像应把正确架构的 ICD JSON 放入 `/system/etc/vulkan/icd.d/`、库放入
`/system/lib[64]/`，由 loader 自动发现；运行时不应要求手动 `param set`。

旧镜像还有两个独立 layer 障碍：OHOS swapchain implicit layer 在 ICD 不提供
`VK_OHOS_native_buffer` 时拒绝所有 `vkCreateDevice`；Trace3D implicit layer 清单引用的
二进制没有导出 loader 所需入口。QEMU 产品补丁仅停止安装这两个不兼容的隐式清单，
不移除其他产品的 layer。SwiftShader 链接 `NODELETE` 以避免 OHOS musl 卸载 ICD 后，
退出回调指向已卸载代码而崩溃。

| 架构 | ICD 产物 | loader/implicit-layer 方案 | phone/2in1 新包 |
| --- | --- | --- | --- |
| arm64 | M144 已构建；临时目录运行通过 core 与 headless WSI | 共享产品补丁，64 位 JSON/库 | 均待启动验证 |
| armv7a | 固定 M144 ARM32 GN 输出已构建；ELF32 ARM/EABI5 | 共享产品补丁，32 位 JSON/库；校验 ELF machine | 均待启动验证 |
| x86_64 | 固定 M144 x64 GN 输出已构建；ELF64 x86-64 | 共享产品补丁，64 位 JSON/库；校验 ELF machine | 均待启动验证 |

`scripts/build_m144_swiftshader.sh` 负责从固定 M144 源码、补丁和已有 GN 输出构建各架构
ICD；`patches/common/standard_vpn/components/qemu_vulkan/apply.sh` 在修改标准源码前
验证 ELF 架构与 `NODELETE`，再安装产品依赖、库及清单。

### OHOS native-window WSI 候选实现（尚未运行验收）

SwiftShader 提供 `VK_EXT_headless_surface`、`VK_KHR_surface` 和 `VK_KHR_swapchain`，
旧版本不提供 `VK_OHOS_surface` 的呈现实现。现已在 SwiftShader ICD 本身增加
`0004-present-vulkan-to-ohos-native-window.patch`，不重新启用不兼容的 implicit layer：
动态解析实际 NativeWindow/NativeBuffer API，成功后才广告扩展；保存窗口引用；
request buffer、等待并关闭 fence、map、按 stride 进行 BGRA→RGBA CPU 拷贝、unmap、flush。
尺寸变化返回 OUT_OF_DATE，映射/同步失败中止 buffer，而不是返回虚假成功。
没有广告 `VK_OHOS_native_buffer`，也不声称支持外部内存的硬件零拷贝导入。

另外定位到固定 Vulkan loader `2a3e35b84a405e5f66102a16b978baed268953e3`
的 OHOS surface terminator 只返回平台结构，未调用 ICD 的 CreateSurfaceOHOS，也未建立
现代 swapchain 使用的 surface index/每 ICD handle。新增独立部件
`patches/common/third_party/vulkan-loader/ohos_surface_dispatch`，使用现有 loader 的
分配/清理路径补齐分发，并覆盖多 ICD、分配失败和部分创建失败。

ARM64 candidate ICD 已从固定 M144 源码实际编译：

- 路径：`/Volumes/PSSD/qemu/artifacts/swiftshader-wsi-candidate-20260927/arm64/libvk_swiftshader.so`
- SHA-256：`adde98235c76e199d3bfaf7773c28dab2072e72f89247b93f951a73823369d2a`
- 该组件构建输入：`/Volumes/PSSD/qemu/build-inputs/swiftshader-LwGPKD`
- 输入内容树 SHA-256：`feadf88eb6febee015a81bf647dbe00e5ebf052e98d8bb08fe6ef926110e0fac`

loader 补丁使用实际 ARM64 phone 编译命令、只读源码副本编译通过，证据为
`/Volumes/PSSD/qemu/validation/first-20260927/vulkan-loader-compile-arm64.json`。
两项 ASan/UBSan 单元测试验证实际补丁中的像素转换代码及 loader 分发函数；它们不是 guest E2E。
2026-10-05 又以三个产品的真实 Ninja clang 参数完成 loader wsi.c 的 scratch 编译，
保留真实 system/product headers，source/out volumes 没有写入；已应用补丁的 checkout
必须通过 exact reverse-check，不静默忽略 hunk 不匹配。ARM64 / ARM32 / x86_64 object
SHA-256 分别为 `b40ff3e9d0592a0d9b4a0549094d1f52fa59cd3e588e36552a2dbe7ced3da3d0`、
`16b3f0e2201c7b47229f1dfb17bddef629e4640caa3c06746637495fb1a27e95` 和
`3077bac5fd934dd5e576cb7bfdfc85879c33bcef76619460433707a10ea71a56`。
实际证据为 `validation/first-20261005/vulkan-loader-compile-{arch}.json`；仍不是 guest WSI 通过。
`vulkan_ohos_surface_probe.c` 已编译，要求真实清色/present、十帧像素回读及 resize 的
OUT_OF_DATE/无虚假提交边界；它只覆盖 NativeWindow buffer queue。

2026-10-05 新增 `vulkan_window_probe.c` 与 HAP `--vulkan-window-only`：从真实 ArkUI
XComponent 的 surface 回调取得窗口，呈现五帧清色并释放 Vulkan/窗口引用；按钮销毁窗口，
随后重建并再次呈现。`verify_vulkan_window.py` 要求精确的三条有序生命周期记录，
两张实际 compositor 截屏的窗口几何须等于 NativeWindow 几何，除五像素边缘外逐像素
验证 RGBA `[51,102,153,255]`（容差 1）。编译成功或 fixture 截屏不算实际上屏通过。

- ARM64 未签名 HAP：`/Volumes/PSSD/qemu/validation/first-20261005/vulkan-window/entry/build/default/outputs/default/entry-default-unsigned.hap`
- HAP SHA-256：`2c2e9683045b77045dae25cf956d4040117d1faf264ff2cedea0d87483dd3328`
- 固定源码 API 26 Linux SDK 独立链接 ELF AArch64；该 `.so` SHA-256：
  `7fc7fc8506542342387bcf3b297664f6a0cee0a622923cace73fe9a355dfea31`

尚待新包 UDID 签名、安装和运行。后台/前台、实际 compositor resize 仍需额外验证，
不能拿此测试的销毁重建或 consumer resize 覆盖代替。

2026-10-05 ARM32 构建首先在 Subzero 缺失 `llvm/Config/llvm-config.h` 时失败：
固定 GN 仅给 Linux/ChromeOS 添加 POSIX LLVM config headers，没有包含 OHOS。
新增 `0005-configure-subzero-posix-headers-on-ohos.patch`，保留 ARM32 实际 Subzero JIT
与 ARM32 backend，仅补 OHOS 的 POSIX include/config 分支，不关闭 JIT 或使用空 header。
真实 apply/reverse/幂等回归通过；重试 ARM32 和 x86_64 ICD 均链接成功。

- 产物根：`/Volumes/PSSD/qemu/artifacts/swiftshader-wsi-extra-20261005`
- ARM32 `arm/libvk_swiftshader.so` SHA-256：
  `d5055c7e01d9b2da94c432671fc1a5c1a465b9cf93f25ab23e1036449eab3b20`
- x86_64 `x86_64/libvk_swiftshader.so` SHA-256：
  `ae78ee51998210003358358720087f7c41fa1bbffb22ff82e15f4e97f0ff0e73`
- 冻结输入：`/Volumes/PSSD/qemu/build-inputs/swiftshader-GoZn3M`；树 SHA-256：
  `7b5a2d81a356e4ccdda49fc29695c81d05d66dbb67107f30c1cb0c0e51008ed6`
- 首次失败日志：`/Volumes/PSSD/qemu/logs/swiftshader_extra_build_20261005.log`
- 两架构成功重试日志：`/Volumes/PSSD/qemu/logs/swiftshader_extra_build_retry_20261005.log`

两份库实际 `readelf` 检查仅依赖 `libc.so`，包含 `NOW NODELETE` 与两个 ICD loader 入口；
运行时扩展从 ICD proc table 分发，不以动态符号表中是否直接导出 OHOS surface 函数判定。
随后也以同一套五补丁重新完成 ARM64 依赖构建，并归入上述独立根；其
`arm64/libvk_swiftshader.so` SHA-256 为 `adde98235c76e199d3bfaf7773c28dab2072e72f89247b93f951a73823369d2a`，
日志为 `/Volumes/PSSD/qemu/logs/swiftshader_arm64_subzero_set_20261005.log`。该根 manifest
现包含三个架构和同一冻结补丁集，没有覆盖当前 ARM64 首包的冻结依赖。
这里只构建依赖，不是另两个 QEMU 产物，也没有启动其他五包矩阵。
ARM64 phone 首包已完成打包，正在从该新包启动；ARM32 JIT、各架构 OHOS WSI
及实际屏幕呈现仍待 guest 验收，以上候选实现均不得记为运行已修复。

## 首包门槛

首先仅构建 ARM64 phone。打包后记录路径、SHA-256、构建日志与镜像 manifest，再从
**新包**启动 QEMU，执行分段 WebView 探针、EGL 探针、Vulkan core/device/buffer 与
headless-swapchain、OHOS NativeWindow 消费回读及 XComponent 可见呈现探针，
并覆盖扩展广告、无手动参数、退出稳定性等边界。
首包失败则修复并重打同一包；通过之前不启动六包矩阵。通过后使用已编译的各架构
ICD，逐架构、逐设备形态打包和验证。实际首包结果在完成后补记，不以旧镜像临时目录
测试代替。
