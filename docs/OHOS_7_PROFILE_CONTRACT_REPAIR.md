# 7.0 画像收紧与首包验证记录

## 统一 Release 构建入口进展（2026-10-06，尚未交付六包）

当前完整 M144 使用固定 TPC Release 清单的 156 个项目目录。R1 实际 native
构建在 PGO 输入处失败：`arkweb.profdata` 是 LFS 指针，而非真实 profile。已从
同一固定源码的官方 LFS 获取 262100672 字节对象，SHA-256
`c98db0441494ecd018d7decbd2aa9b37ec61fd3e960b56e7e81eb19e0afceb1b`。
仓库新增构建前 LFS 缓存/安装/校验，拒绝指针、错误哈希、未知改动和路径别名。
R2 已重新进入实际编译，原 PGO 错误未重现。验证仓库Docker依赖镜像后，
主动中断本次owned Ninja，把 jobs4 调度为 R3 jobs8；保留 R2 的 exit2/
interrupted 证据和已完成对象，不把主动中断误记为源码编译缺陷或成功。
R3 实际编译在 ANGLE `ohos_util.cpp` 失败：固定扩展的头文件相对路径越过
真实 Release 源码目录。独立 `m144_angle_includes` 仅修五个现有扩展文件的
七条 include；不改 ANGLE、WebGL、Vulkan 功能选择或 bridge/API。
真实固定 Git blob 全量补丁检查第 06 次为 37 文件、0 缺失、0 待复核；
live 重复应用和 reverse-check 通过。R4 jobs10 已续编，原失败证据保留；
路径和编译问题仍须完整五库、HAP 和 guest 验收，不能据局部检查关闭。
五个完整内核 SO、签名 HAP 和
新镜像运行验收仍未完成。保留 R1 失败证据，不把 R2 的中途编译计为通过。

新增 `core_hap_source` 独立部件，把主系统 `ohos_nweb/BUILD.gn` 的三个 ABI
分别指向源码 HAP；x86_64 不再回退 ARM64。实际固定 webview
`d421b6b549fa3038ad01cf34589b959286137be9` 的原始 Git blob 在 scratch 中
重复打补丁及 reverse-check 通过，记录为
`main-core-abi-selection-source-evidence-01.json`；不是原位改动或运行通过。
安装前验证全量 Release graph、API26 SDK、native/HAP 冻结补丁、真实 ELF/
资源和签名校验记录；系统归档将携带证据，并校验其实际内置 HAP 的哈希。
官方预编译 HAP 保留，不允许后续 LFS 恢复覆盖受管源码输入。

六包入口已串联源码/SDK bootstrap、单 ABI 完整依赖、首包实际行为门槛、
其余架构依赖和两画像构建；没有通过首包时不会启动其余五个系统包。
过期依赖和非当前冻结脚本/补丁的旧包不可直接复用。实际六包运行尚未执行。
独立 JSVM 的 GN 原来关闭 Intl，现开启并内嵌 ICU/startup 数据，校验实际
args.gn 与来源哈希。ohos-native-bindings 增加数字/UTC闰日/非法参数/独立VM
回归，尚未新包运行。两个画像补丁入口也调用完整构建器的同一份有序计划。
主系统新增精确的 519 项 Release project lock，实际全部 Git HEAD 核对通过；
保留原 remote/upstream 提示，并在 sync 前安装 commit 覆盖层。
两画像共享完整补丁顺序；2in1 Serial 固定源码缓存自动准备。
普通应用验证 runner 已实测旧 R6 的 I18n 八项通过，仅证明自动化链路，
不是新包证据。其余五包也强制各自 archive-bound runtime evidence，复用不能绕过。
最新完整主机回归 `host-regression-capability-47.log` 为 469 项通过；这些
不等价于 HAP、boot、API 或六包运行验收。诊断 R9 ARM64 phone 仍在构建，
使用的是此前官方 ARM64 HAP/旧依赖，不能满足当前统一源码内核的最终首包门槛。

首包门槛保持 **false**；其余五包未启动；不能声称所有缺口已经修复。

## R6 历史运行状态（2026-10-06）

已启动实际重包 R6（ARM64 phone，SHA-256
`502b08384576945bab9183281f8c4fe1475d836316354f3b15819962ece6a155`）。
普通应用 user-ID 13 项、I18n 8 项和 ohos-native-bindings JSVM/QoS/vibrator
11/5/2 项实测通过；不扩展为全部 API 或其他架构通过。
Vulkan 的提交/销毁重建执行但可见内容失败；AudioRenderer 两轮没有 PCM 回调，
新 AudioPolicy route 缺 pipe；ArkWeb 首次 renderer 在 SetUserId100 时 EPERM，页面未运行。
详细命令、结果与新鲜运行身份见首包证据及 Native/ArkTS 缺失清单最新段。
诊断环境使用包外 keepalive，不声明无人值守启动合格。
最新完整主机回归为 423 项通过（`host-regression-capability-36.log`），设备画像测试通过；
尚不解除首包门槛，其余五包未启动。下面保留旧首包/R6 冻结前历史，不能当当前结果。

7.0 AudioPolicy 新部件现已在 profile 生成/遍历前补既有 pipe 的 flag 和 stream
supportDevices，固定源码重复 apply/真实 ext4 读回通过。full-source 包验证强制检查
chip_prod 的优先 XML，不仅看 ALSA 文件存在。正常应用 PCM 回调仍必须新首包验证。
图形内部 IPC 回复与 nwebspawn 最小服务身份权限已获明确确认并落实独立部件补丁。
后者的真实 Linux 6.6 AccessToken driver 对象已在 ARMv7a/ARM64/x86_64 三 ABI
编译通过；主机边界测试验证 UID 3081 只获得当前任务的账号 ID 设置入口，不获得
token/bitmap 设置权限，最终 renderer UID 仍不能自行重设账号。仍须新包实际 renderer 验证。

Issue #20 新增实际空 C main 的链接顺序/退出回归。R6 ARM64 phone 的
`-lavplayer -ludmf` 三次均 exit 139；原始 UDMF+Pasteboard 两个顺序在这个 ARM64
环境未触发，不能据此认定报告中的 x64 已修复。Native LLDB 实测来自
`libsync_fence.z.so` 与 `libsurface.z.so` 的两个退出 callback 析构同一个
`SyncFence::INVALID_FENCE` 对象。真实生成的 libsurface link graph 同时引入 shared
和 static fence；FrameReport 的传递 static 依赖是重复实现来源。新部件仅改该
GN 依赖为已有 shared provider，不改 musl、ArkJS 清理、UDMF API 或 fence FD 语义。
新打包器强制验证实际 ELF 的单一 global owner、DT_NEEDED 和 Native Fence 导出，
已准确拒绝 R6 的重复实现。真实 fresh GN 与正常 Ninja 的 ARM64 Surface/fence
link、重复 link 已通过，实际 ELF 保持单一 owner，Surface 的 11 个 SyncFence
导入都由 shared fence 导出。RenderService ARM64 两个真实对象此前编译通过；
三 ABI 的联合辅助验证尚缺生成依赖，不能声称三 ABI 全部服务端对象通过。
尚无新包退出回归通过记录。

旧 R6 的隔离候选库诊断没有通过：Pixelmap 导入 InvalidFence，却没有保留直接
DT_NEEDED fence，原来由包含重复实现的 Surface 满足。仅替换私有 Surface/fence
触发真实 loader exit 127，不是退出回归通过，也不能据此关闭 Issue #20。
正常新 GN 的 Pixelmap link 已含 shared fence；完整重链接必须保留该依赖。
新 image guard 增加 Pixelmap 的真实 ABI/导入/直接 provider 检查，不改 namespace
策略、不用 LD_PRELOAD 强行通过、不恢复 static duplication。
实际完整系统构建已重链接 Pixelmap：其 SHA-256
`33a3dd64e3c473c7d8869845659bc782010d485f70345136b3b718790cef25a9`，
明确保留 DT_NEEDED libsync_fence.z.so 且 InvalidFence 导入解析到 shared provider。
`production-surface-fence-pixelmap-link-01.json` 为实际 ELF 检查通过，不是已归档镜像
或 guest 退出通过证据。

Issue #19 另设完整 ArkWebCore HAP 的实际 ELF ABI/资源检查，不再把 JSVM V8
校验称为 ArkWeb 内核验证。固定 7.0 x64 装配指向 ARM64 HAP 的缺陷已确认，新
检查会拒绝该包。M144 完整内核的新构建图已通过；仅修 OHOS 未声明的 ANGLE
测试聚合边，不关闭 WebGL/Vulkan/原有 ArkWeb feature。官方 prepare/CEF translator
和完整 native 目标的本地 Docker 构建仍在推进。已修复两个实际编译缺口：
私有 WindowAdapter 副本漏掉既有 SetWindowNodeIdAndRSHandle 方法；OHOS base 的
Blankless 扩展未声明 robolectric_buildflags 生成头依赖。前者只同步已有方法，
后者只补 GN 依赖，两处失败对象都重新编译通过；未手改生成 bridge、关闭 feature
或制造头文件。随后真实编译发现 WebRTC 的 OHOS thread-ID 落入 pthread_t 整数
reinterpret_cast 的错误 fallback；新独立部件使用既有 gettid，不改 pthread ref、
命名、调度或 WebRTC feature。真实固定源码在 Clang22 的三个 OHOS ABI 中均先
复现原缺陷、再编译候选通过；API26 native probes 编译、真实源码 host 及 R6 ARM64
root 诊断各完成 16 轮 × 16 线程、2176 项线程身份检查。记录
`webrtc-thread-id-three-abi-02/evidence.json` 与 `r6-webrtc-thread-id-evidence-02.json`，
都不是 ArkWeb session、新包或其余架构运行验收。native R7 中原失败对象也已通过。

私有接口对照进一步发现：BufferRequestConfig 多了公共接口没有的 GetTimestamp；
帧监听器私有 OnFrameAvailableListener 与公共 GetContext/GetOnFrameAvailableCb
虚函数契约不同；HiTrace 中间插入 StartTraceEx，改变后续虚函数槽。图形 canonical
TPC 头与当前固定 7.0 系统头一致，因此不能只依靠“能编译”宣称 bridge 兼容。
native R7 已精确中断本次 owned Ninja，以免继续构建已知未核实的 ABI；这是主动
停止，不是新编译错误。用户确认后，独立 `m144_private_contract` 部件已同步私有
请求/帧回调契约：时间戳取已有 flush config；共享回调 registry 保留旧失败注册，
清除新失败注册，成功 unset/SDK destroy 后释放引用，in-flight callback 仍保活。
HiTrace 本地 StartTraceEx 保留为 nonvirtual NDK 转发，不插入 release vtable。
公开 API、权限、renderer/backend 均未改变，没有手改生成桥接。
`private-contract-three-abi-evidence-08.json` 记录真实 Clang22/SDK26 的三个 CPP、
三 ABI 共九个 thin-LTO 对象；使用真实 GN flags 和各架构真实生成 allocator flags，
不是三架构完整 GN/link。主机实际 CPP + 真实 SDK 声明 + 单独 release-header 调用方
ASAN/UBSAN 测试通过，覆盖失败/替换/unset、并发回调保活、100 次 destroy、迟到回调、
空 context/空 function 和四个 64-bit timestamp 边界。主机只 mock SDK/日志/raw_ptr
依赖，不能据此宣称 GPU、页面、服务或新包通过；先前辅助工具失败证据全部保留。
完整 M144 ARM64 native R8 已恢复，本地 Docker jobs=4，输入冻结于
`/workspace/qemu-core-build-20261006-r8/arm64/frozen-build-inputs`，tree SHA-256
`c42e28ae14f4189cc50a215bbf991df311a607cd84bf6d2f0f3ceb83137c59ad`。
原生构建记录 source pins/真实 tracked diffs、SDK 和冻结补丁输入；HAP 复用并验证同一
冻结输入，不从后来变动的 `/work` 重取补丁。完整五库和源码 HAP 尚未产出。
该 native R8 已退出 1：真实 `network_change_notifier` 引用缺失的扩展源文件，
QUIC 的 `GetServerHostForQuicBroken` 缺少 visitor 声明。只读核对发现当前 Chromium
4ae5 / ArkWeb eff888 各为不同时点 master 快照，QUIC 901d 是 Chromium DEPS 的
upstream 版本，不能仅凭 milestone 144 称为完整配套源码。Github 的既有 ArkWeb
144.0.7559.59 tag 提供前者真实源文件；尚未据此擅自改依赖、制造空文件或关闭网络
feature。随后用户批准统一固定 M144 发布基线的依赖调整，旧源码、完整失败、输入和
之前三 ABI 边界证据全部保留。后续五库/source HAP 必须绑定修正后的实际输入。
追加只读 `audit_m144_source_includes.py`：结合真实 native GN 的 `gen` 搜索路径，
原先 1166 个生成头引用已正确解析，不能误报为缺失源码。
`m144-source-include-audit-evidence-03.json` 剩余 349 条未解析引用中，291 条属于
未启用的 `ohos_nweb_ex`；另有 56 条 chromium_ext 引用及两个其他目录引用。
这只是带源码 SHA/上下文/仓库 pin 的待核查清单，不把所有引用都判为当前目标错误，
也不把没有缺失 include 当作 ABI/运行通过。真实已触发的 network/QUIC 编译失败
曾阻塞完整内核。现已从 TPC 官方 `OpenHarmony-7.0-Release` manifest
`79739ee5ae8ee71c8ef90b63e7a658ef639c5980` 解析并固定 156 个项目目录，
保存于 `scripts/m144_release_source_lock.json`；构建不解析 moving branch，也不再
用 Google upstream DEPS 覆盖 OHOS QUIC 等分叉依赖。GitHub 缺少发布 commit 时才
回退官方 GitCode 的同一 commit，不回退 master。完整缓存（155 个独立仓库）及实际
Linux checkout 已通过 pin 检查；实际 `chrome/VERSION` 为 144.0.7559.59。
新的 Chromium/ArkWeb/CEF/V8 pins 分别为 `a8168622`/`f3d90443`/`6153d21e`/
`bb352490`，OHOS QUIC `dd5f8314` 已含实际 visitor 声明，原缺失网络扩展源也存在。
过时的 presubmit、第三方 OHOS target 和 Window slot 添加补丁已移除；保留真实
Window slot 保护检查。其余补丁先对实际 locked Git blob 核验，再进入完整原生构建。
旧三 ABI 实测仍是旧输入的历史证据，不能代替新基线的重新编译或 guest 验证。
完整 host 回归当前为 428 项；新完整 ARM64 native R1 本地 Docker jobs=4 正在构建，
输出 `/Volumes/PSSD/qemu/artifacts/arkweb-core-release-20261006-r1/arm64/`，不是已完成 HAP。
首包 R9 也正在构建，仅用于先确认系统修复；仍未满足新源码 HAP 和真实行为门槛。
六包入口已强制先打代表包并检查真实运行证据与归档 SHA、冻结输入、命令和环境绑定。
没有该证据、旧包、外部 keepalive、缺失行为/边界回归或失败结果均不得进入剩余矩阵。
API26/Hvigor 单次失败传播/原签名 profile 期限修复已完成固定源码重复 apply 和实际
SDK26 sign-profile/verify-profile；不是完整 HAP 签名或 BMS/页面验收。
源码构建 HAP、完整签名、bridge 兼容及新包真实页面行为尚未验收。详细证据位于
`/Volumes/PSSD/qemu/validation/first-20261005/issue-20-20261006/`。

### 当前代表包重建 R8（已发现构建失败，尚未归档/启动）

R7 在编译阶段主动停止，以纳入新确认的 Camera JPEG 修复；不是编译错误，
不保留为可交付产物。RotJpegImg 明确初始化完整 marker copy/transform options，
拒绝 workspace 时释放 JPEG 对象且不预分配输出。固定源码完整 Camera CPP 在
ARMv7a、ARM64、x64 真实 GN 参数编译通过；真实 libjpeg 的像素/EXIF/ICC/COM、
非 MCU 边界及 400 次失败路径 ASAN/UBSAN 回归通过，未完成 guest 拍照验收。
证据为 `camera-jpeg-three-abi-evidence-04.json`。

R8 仅 ARM64 phone，在本地 Docker 编译，原目标包目录为
`/Volumes/PSSD/qemu/packages/first-capability-repair-20261006-r8/`。
冻结构建输入 `/Volumes/PSSD/qemu/build-inputs/phone-VHYWHa`，tree SHA-256
`53c7621f695ba1f0b08e62b98da071d39fd853b91f4a567ce3b17961e7b04fc5`。
重包纳入 kernel/RenderService/shared fence、AudioPolicy、Camera JPEG 等修复。
**这不是产物 checksum。** 包完成后仍须记录实际 archive SHA、启动绑定、测试环境、
命令及边界/回归结果。R8 冻结后的 Pixelmap guard 必须在实际新 system.img 额外执行；
后续构建使用最新冻结检查器。其余五包未启动；不得由主机回归、scratch link、
旧包根进程诊断或当前编译进度解除首包门槛。

本次完整构建在 CalendarData resource action 暴露真实错误：Stage `module.json5`
被 `ohos_resources` 送入旧资源链，restool 要求 FA `distro` 对象而拒绝。只读 inspector
使用相同真实输入/工具，独立 `/tmp/calendar-resources-diagnose-01` 输出重复失败，
记录 `calendar-resources-diagnose-01.log`。修正原 `0001`：保留真实 `ohos_app`/Hvigor
assembleHap、五个本地 HAR、平台签名/权限，把旧资源/JS metadata target 移出依赖。
这与固定版本 Contacts_DataAbility 的 Stage 构建方向一致，不把 Stage 改成 FA。
只迁移 SHA 为 `bc5f8c2631abe876725387d42311178f6d3d2d9d2854b9482d82729614c3eb77`
的本仓库旧 BUILD；未知改动/符号链接拒绝覆盖。9 项 CalendarData 回归通过，
新首包仍须重新冻结、正常 GN/Hvigor 编译、打包和 guest provider 行为验证。
当前 R8 内核任务仍在结束中，不修改活动生产源码、不把此失败构建作为可交付产物。

## 历史门槛状态（2026-10-05）

实际 ARM64 phone 新包已启动，不是只做归档或旧镜像测试。SHA-256
`c060979b682568ed747662b9cee7276befa6a06b9cf13b6b4905e8e7f5b2ef22`，完整路径、
checksum、guest/host、前台启动和 HDC 命令、各测试结果在
`/Volumes/PSSD/qemu/validation/first-20261005/first-package-evidence.json`。
首包门槛仍未通过：普通 HAP user-ID、renderer 恢复、Vulkan 可见窗口、Vibrator 与
I18n 的错误类型/参数边界以及普通应用 AudioRenderer 有实际失败。部分 JSVM/QoS/WebGL/
AudioSuite PCM/root 内核调用通过，
不得由这些结果推断全部 C++/ArkTS 1.1 已可用或其他五包通过。

SceneBoard 的 post-board 窄覆盖层现为 phone/2in1 联合开启统一渲染，避免 logical display
没有实际合成层。`graphics_features.py` 在当前 preload 后、编译前精确检查
SceneBoard+uni-render+OpenGL=true 与 Rosen Vulkan=false；后者不影响独立 CPU Vulkan ICD。
新开关触发较大 graphics 重编，保留已完成缓存；仍只打同一代表包。
同时纳入强 AppSpawn setter、安全 renderer PID-1 SIGTERM handler、有限计时 VDI、
I18n numeric BusinessError/类型校验和此前 PermissionManager 修复。

实时音频另有装配缺口：固定 ALSA 默认禁用 global config，`hw:0` 没有定义；
配置树也未装到库实际读取的 vendor 路径。R6 已同时启用两画像的 config feature，
按部件补丁安装上游 79 个文件，将产品本地空 ALSA 条目迁移到共享 board inherit，
并保留 local-shadow 拒绝检查。真实当前 preloader 配对检查通过，不等于音频回调通过。

完整主机回归最新 302 项通过（`host-regression-capability-20.log`），三产品 I18n/AppSpawn/loader/音频/AVC/DSP/Camera 探针等 scratch 编译单独记证据；
没有通过全六包实际验收，没有批量修改原始行为台账为通过。
下面保留各次冻结/失败的历史，不把主动停止重冻当作编译报错或已产出包。

AVC 新候选使用固定 M144 OpenH264 真实实现 wrapper ABI；三个 OHOS ABI 编译与
宿主机 96 帧真实编码/解码、520 项检查通过。依赖来源/实际 ELF/四个 notices 在构建前
强制检查，AVCodec 独立部件安装及 full-source system.img 检查均已接入。SDK 26
普通 HAP 三 ABI 编译，ARM64 Linux 签名验签通过，但尚无新包普通媒体 API 运行证明。
这些候选晚于 R6 冻结，后续仍要重建同一个首包，不能据此启动其余五包。
固定 AVC wrapper 的 EOS 复用 buffer 长度/PTS 残留及忽略 backend error 也已单独
补丁修正；三产品真实参数编译及五项结构/分支 sanitizer 回归通过，普通 HAP 必须
在新包验证真实 reuse/drain/error 行为，不能据上述编译关闭整项。

CalendarData 已另行准备真实固定源码 provider 构建和精确平台签名配套。Linux 实际
compile_app/app_sign 链编译签名成功，原有 ACL/权限边界保留，Editor 仍未实现。
这些补丁不在当前 R6 冻结中，不能把候选 HAP 的签名成功算成新 QEMU 包运行通过；
详细范围见 `OHOS_7_NATIVE_ARKTS11_GAPS.md` 的 CalendarData 记录。

本记录不是六包完成声明。只撤销已确认位于官方设备画像外、且没有可用实现的错误声明；
官方 SDK 画像及 phone 文档最小能力集内的问题仍需实现、打包和真实调用验证。

## 本轮边界

| 能力 | phone | 2in1 |
| --- | --- | --- |
| NetFirewall | 不再声明，关闭对应 feature | 保留，继续验证真实 firewall 栈 |
| VideoProcessingEngine | 不再声明 | 不再声明 |
| CloudSync Client/Config/Server、DFS CloudSync Core/Manager | 官方文档要求，不能撤销 | 不在官方 SDK 画像内，撤销依赖缺失 Provider 的五项声明 |
| AudioSuite | 官方 phone 文档要求，继续修复 | 本轮不增加声明 |
| Camera.Core | 官方 phone 要求，继续补真实后端 | 不在官方 SDK 画像内，撤销 rich 继承的错误声明，保留部件和库 |

产品生成逻辑在 `patches/phone/product_profile`、`patches/2in1/product_profile` 分开维护。
共享 `patches/lib/device_contract.py` 先检查 SDK 画像和固定文档契约，再生成最后加载的窄覆盖层。
hb 的部件继承不是深度合并；只在早期 full profile 内改 feature/SysCap 会被后续 board
画像覆盖。窄覆盖层复制相关部件最终 board 设置，再修改明确管理的 key，不挪动完整画像。
若产品本地部件会遮蔽覆盖层则直接失败，不静默打出错误声明。

phone 文档保护列表：`patches/phone/product_profile/official_documented_syscaps.json`，
来源为审计固定 7.0 文档提交 `9585fb12fa8f977accfd9435d9f5537b14734473`，共 231 项。
这是独立 API 文档证据，不改变构建 manifest 的固定提交。
此外强制保护用户明确要求的 JSVM、QoS、Vibrator、ArkWeb、WebGL1/2、Vulkan；
即便上游默认画像未列入，也禁止通过收紧画像撤销这七项需求。
2in1 CloudSync 的收紧已在实际源码上只读生成验证，但尚无新的 2in1 preloader 或运行证据。

AudioSuite 的进一步源码检查确认已有 upstream engine/pipeline，默认关闭的
`audio_framework_feature_audiosuite_support` 使 `ohaudiosuite` target 没有 sources。
phone 窄画像现准备开启该 feature 及 format-convert feature，保留现有 board 音频设置。
同时显式启用对应 SuiteEngine SysCap；bundle 默认值为 false，仅开 feature 不会自动恢复声明。
只读实际源码生成及后置继承回归测试通过，仍不是运行证明。
**这项修改晚于已失败的 phone-QFLnfo 输入快照，但已进入 2026-10-05 的 phone-f02tvm 重试**；
必须由该重试的新包启动验证，不得据旧候选包的图形测试进入其余五包。
`audio_suite_capabilities.xml` 还引用多个算法插件，当前缺失问题仍未解决；打开 engine
开关不能把算法、云下载和 realtime device nodes 标为全功能通过。

## 已执行检查

```sh
python3 ci/capability-audit/test_device_contract.py
python3 ci/capability-audit/test_build_input_snapshot.py
python3 ci/capability-audit/test_verify_device_contract.py
python3 ci/capability-audit/test_verify_web_results.py
python3 ci/capability-audit/test_ohos_present_copy.py
python3 ci/capability-audit/test_vulkan_loader_ohos_surface.py
bash ci/device-type/test.sh
git diff --check
```

2026-10-05：90 个 Python 回归测试通过，device-type 测试通过，diff 与 bash 语法检查通过。
新增的 13 项 AccessToken 内核 hunk/探针/结果验证器用例已进入完整 discover；不是仅计数新增文件。
包含网络两层开关、SceneBoard 两种画像及 source-built 证据、退休声明名约束，
以及 Vulkan 可见窗口结果验证器的坏像素、几何、超时、陈旧生命周期回归用例。
截屏测试依赖 `ci/capability-audit/requirements-test.txt`，在隔离 venv 中执行完整 discover。
覆盖官方能力不能误删、缺失契约证据拒绝执行、board 后置继承、幂等生成、不同画像切换、
冻结输入不受后续编辑影响、声明与参数双向不一致、空证据、Web 超时及仅有 context 没有绘制、
像素转换的 stride/溢出边界，以及 Vulkan loader 多 ICD 分发和部分失败清理等情况。
这些测试不是新镜像 E2E。

真实 ARM64 phone 源码 load-only 命令：

```sh
DEVICE_TYPE=phone PRODUCTS=arm64_virt \
PACKAGE_ROOT=/Volumes/PSSD/qemu/packages/arkweb-vulkan-first-20260925 \
QEMU_VULKAN_COMPONENT=1 SKIP_REPO_SYNC=1 SKIP_PREBUILTS=1 SKIP_GIT_LFS=1 \
BUILD_ONLY_LOAD=1 BUILD_JOBS=8 KERNEL_BUILD_JOBS=8 \
bash scripts/run_2in1_full_build_docker.sh
```

`phone_full_build_20260927T032910Z.log` 中 hb load 完成。该轮外层 shell 最后因构建期间
脚本被修改而出现 `o: command not found`，因此不把外层命令记为成功；这是引入只读输入快照的原因。
随后已从真实 source/out Docker volumes 读取并断言最终预加载结果：
NetFirewall/VPE 不在 SysCap JSON 中，两者 `const.*=true` 参数不存在，firewall feature 为 false。
完整重试也已再次通过同一断言。

打包时还会检查 feature、错误声明是否消失和 2in1 NetFirewall 是否保留；这些配置检查失败则不交付包。
运行后使用 guest 的实际 `syscap.json`、`param get` 输出检查一致性：

```sh
python3 ci/capability-audit/verify_device_contract.py --device phone \
  --syscap /path/to/guest-syscap.json --parameters /path/to/guest-syscap-params.txt \
  --profile /path/to/new-package/device-profile.json --output /path/to/contract-result.json
```

该检查明确只验证声明一致性，不将保留能力标为真实可用；还必须运行 ArkTS `canIUse()` 和相关 API。

## 官方声明正向复核

真实 source/out volumes 的 ARM64 phone preloader 中共声明 290 项 SysCap，
SDK default 与固定 phone 文档并集要求 242 个名称。以下九项是旧 preloader 的差异；
2026-10-05 已区分六个退休名称与三个仍有效的能力，不再把九项统称为缺失实现：

| SysCap | 本轮源码观察；不是运行结论 |
| --- | --- |
| FileManagement.File.DistributedFile | registry 明确 abandoned；dfs_service 保留，不能据退休名称判断行为通过 |
| HiviewDFX.HiDumper | registry 明确 abandoned；hidumper 保留 |
| Multimedia.AVSession.AVInputCast | 联合开启 SysCap 和 `av_session_enable_input_redistribute`；真实 MMI/Settings 白名单行为待测 |
| Multimedia.Audio.SuiteEngine | 联合开启声明与 engine/format-convert；core PCM 待测，算法插件未齐 |
| Security.DataTransitManager | registry 明确 abandoned；实际部件是 `base/security/dataclassification`，保留 |
| Security.DeviceAuth | registry 明确 abandoned；device_auth 保留 |
| Security.DeviceSecurityLevel | registry 明确 abandoned；device_security_level 保留 |
| UserIAM.UserAuth.PinAuth | registry 明确 abandoned；pin_auth 保留，认证行为待测 |
| Window.SessionManager | phone 启用实际 SceneBoard、HandsetSmartWindow 和非 PC 模式；真实 SessionManager 行为待测 |

这些声明问题必须分别确认实际实现，不能通过批量写 true 关闭台账。
使用新版 verifier 对真实 preloader 和待应用 phone policy 的只读比较，明确失败于九项
缺失声明及对应参数；诊断结果保存在
`/Volumes/PSSD/qemu/validation/first-20260927/phone-preloader-required-declarations.json`。
该文件明确标注 `actual_preloader_vs_pending_policy_not_packaged_or_booted`，不是新包验收结果。
画像元数据现在保留 `required_official_syscaps` 和 `enabled_required_syscaps`，打包和 guest
声明检查都正向要求官方能力及七项明确需求存在、参数为 true；不能只检查“未被撤销”。
六个退休名称只在固定 registry 明确 abandoned、SDK 画像不要求、实际 `.ts` 无引用且
对应部件仍存在时取得窄豁免；保存 registry 哈希和 `behavior_validated=false`。
原始 242 项列表保留，不允许借退休元数据排除任意有效 API 或七项用户需求。
此增强和三个有效能力配置已经进入 phone-f02tvm；新包行为尚未验证。
新增检查没有免除首包真实行为门槛；其余五包仍不得启动。

## 首包构建状态

固定 manifest：`OpenHarmony-7.0-Release @ f079c4ad9848f9cc4a9a4b3a3613ad8fbb142549`。
环境：macOS/OrbStack、`linux/amd64`、`ohos-qemu-build-env:7.0-release`；
source volume 为 `ohos-qemu-7_0-release-source`，out volume 为 `ohos-qemu-7_0-release-out`。

```sh
DEVICE_TYPE=phone PRODUCTS=arm64_virt \
PACKAGE_ROOT=/Volumes/PSSD/qemu/packages/first-capability-repair-20260927 \
QEMU_VULKAN_COMPONENT=1 \
QEMU_VULKAN_ARTIFACTS=/Volumes/PSSD/qemu/artifacts/swiftshader-wsi-candidate-20260927 \
SKIP_REPO_SYNC=1 SKIP_PREBUILTS=1 SKIP_GIT_LFS=1 \
OHOS_SKIP_KERNEL_REBUILD_IF_COMPLETE=0 BUILD_JOBS=8 KERNEL_BUILD_JOBS=4 \
bash scripts/run_2in1_full_build_docker.sh
```

已失败的日志：`/Volumes/PSSD/qemu/logs/phone_full_build_20260927T042342Z.log`。
只读输入快照：`/Volumes/PSSD/qemu/build-inputs/phone-QFLnfo`。
脚本/补丁内容树 SHA-256：`930c97914c1a370d641817156efec85b9d4d69e2304b2e891fc8eb602822adf5`。
快照含未提交修改，以逐文件哈希为准，不能只用 git revision 表示本次构建。
此轮已在遍历前应用 OHOS Vulkan loader 补丁，并安装 WSI candidate ICD；
安装日志确认 ICD SHA-256 为 `adde98235c76e199d3bfaf7773c28dab2072e72f89247b93f951a73823369d2a`。

前一轮 `phone_full_build_20260927T033426Z.log` 已编译出修复后的内核（Image SHA-256
`569ffbf89ac87321f0cae61d707d0c1dbefa4bce79a69e7f71a33356203e26ab`），
随后为纳入新 ICD 和 loader WSI 补丁而主动停止；不是该轮编译报错，也未产出新包。
该轮保留用户态缓存，并强制执行内核构建，避免把旧 Image 当作新包证据。

### 2026-10-05 链接失败复核

该轮在 `libnet_vpn_manager.z.so` 链接失败：
`NetsysController::ProcessVpnStage`、`NetsysController::UpdateVpnRules` 未定义。
实际源码检查确认二者由 `SUPPORT_SYSVPN` 保护；ext 的 sysvpn 已开启，但
`netmanager_base_enable_feature_sysvpn` 仍为 false。两层开关未配套，不是缺失源文件。
phone/2in1 最终窄覆盖层现在都显式开启 base/ext sysvpn；NetFirewall 同样两层联动，
phone 两层 false、2in1 两层 true。保留原有其他 board feature。
新增 `patches/lib/network_features.py`，在当前补丁的 hb preload 完成后、编译前检查四个
开关。不得使用上轮 preloader 代替；实际编译显式传 `--build-only-load=false` 防止参数泄漏。
三个专门回归测试及 device-type 画像切换测试通过，尚不代表 VPN 建链或首包运行成功。

2026-10-05 load-only 复核日志：
`/Volumes/PSSD/qemu/logs/phone_full_build_20261005T073154Z.log`。
只读输入 `/Volumes/PSSD/qemu/build-inputs/phone-fa1jrS`，树 SHA-256
`d2cb708b0f7642642e9bd2f6fb2152d2b84a3030b731f85f30226173c68306e7`。
该输入含 AudioSuite 开关和正向契约检查。该轮在 GN format 子进程发生 SIGILL，退出 1；
后续同一 GN 的 20 次 dry-run 未重现 SIGILL。未隐藏失败，也不将原因归为已修复。
下一轮 `phone_full_build_20261005T074337Z.log` 因 CEM patch 缺少尾部上下文，
无法在真实源码识别已应用状态而失败；已补上下文，真实源码 reverse-check 和 fixture 回归通过。

随后完整重试只构建 ARM64 phone：

```sh
DEVICE_TYPE=phone PRODUCTS=arm64_virt \
PACKAGE_ROOT=/Volumes/PSSD/qemu/packages/first-capability-repair-20261005 \
QEMU_VULKAN_COMPONENT=1 \
QEMU_VULKAN_ARTIFACTS=/Volumes/PSSD/qemu/artifacts/swiftshader-wsi-candidate-20260927 \
SKIP_REPO_SYNC=1 SKIP_PREBUILTS=1 SKIP_GIT_LFS=1 \
OHOS_SKIP_KERNEL_REBUILD_IF_COMPLETE=0 BUILD_JOBS=8 KERNEL_BUILD_JOBS=4 \
bash scripts/run_2in1_full_build_docker.sh
```

日志 `/Volumes/PSSD/qemu/logs/phone_full_build_20261005T074519Z.log`；
只读输入 `/Volumes/PSSD/qemu/build-inputs/phone-f02tvm`，树 SHA-256
`6ceac365841d2e62b35fb3144988a62abed53953eb0eebc87eb590100411b48a`。
已通过 SceneBoard 签名 HAP、当前 preload、base/ext feature 成对检查并进入编译。
phone 使用 HandsetSmartWindow/non-PC，2in1 保持 FreeFormMultiWindow/PC；共享源码 CEM
携带 userId，source-built init 在 boot_completed 发出解锁事件，不依赖手动替换程序。
打包将保存实际 CEM/config/HAP 哈希，并检查 source-built 路径；此记录不是运行通过。

稍后新增的 AudioSuite ABI 插件路径及 I18n 内置数据启动修复晚于此快照；
该轮在编译中主动停止以重新冻结，保留编译缓存，没有产出包，不是该轮编译错误。
最终首包必须纳入这两项补丁并重新验证后才能启动其余五包。

下一次冻结 `/Volumes/PSSD/qemu/build-inputs/phone-9EBq1x`，内容树 SHA-256
`7e466687f62518004544d87c11a5dba2ecdcf69093d6a534afce425293e77470`，
日志 `/Volumes/PSSD/qemu/logs/phone_full_build_20261005T081911Z.log`。
两项新部件补丁已经应用，当前 preload 检查通过并进入编译；该轮随后主动停止，
以纳入下一项 canonical-path 修复。没有产出包，不是该轮编译报错。
随后发现 QEMU `/system -> /usr/system`，AudioSuite 的 realpath 白名单也必须接受
对应 ABI 的 `/usr/system/lib[64]/`。追加独立 `0002` 修复；保留 realpath，不允许
从任意数据目录加载。这项追加晚于 phone-9EBq1x，已在下一轮重新冻结纳入。

上一轮冻结 `/Volumes/PSSD/qemu/build-inputs/phone-8fBzhQ`，内容树 SHA-256
`4ccf4aa97018880653b2b8d66a5073c537e49dfc16900fb23bf92ef08fe6b3e2`；
日志 `/Volumes/PSSD/qemu/logs/phone_full_build_20261005T083636Z.log`。
AudioSuite 的两个路径补丁、I18n 内置数据修复以及前述修复都已实际应用；
该轮 preload 和 feature 检查通过，ARM64 phone 进入编译；随后主动停止以纳入下述
AccessToken 真正处理逻辑。保留编译缓存，不是编译失败，尚无归档、启动或运行通过结果。
随后准备的 PC `target_platform` 参数及编译权限表校验晚于该快照；只修未来 2in1
默认误用 phone 平台的问题，当前首包 phone 的实际编译表已通过同一校验。

上一轮冻结 `/Volumes/PSSD/qemu/build-inputs/phone-p1TS26`，内容树 SHA-256
`909e21a5b8358ec6f1443616c3af52f8ed5c5821e82aed1c45fc0cc0fdf5e427`；
日志 `/Volumes/PSSD/qemu/logs/phone_full_build_20261005T091701Z.log`。
该输入纳入权限平台/编译表验证以及以下两个 AccessToken 部件；真实源码应用日志已确认。
该轮已主动停止，缓存保留，尚未打包、启动或验收。停止原因是下面确认的内核依赖缺口，
以及冻结后发现的 user ID/AppSpawn 修复需要纳入下一轮；不是该轮编译失败。

### 内核补丁未触发 Ninja 重建

实际 Linux 6.6 `build_kernel` action 只有顶层 `kernel_source_dir` 目录作为 source。
嵌套 C/config 文件变化不会更新顶层目录 mtime，因此即使设置
`OHOS_SKIP_KERNEL_REBUILD_IF_COMPLETE=0`，Ninja 不调用脚本时该变量仍然无效。
只读检查实际 source/out volumes：顶层目录 mtime 为 2026-09-08，Image 为
2026-09-27 04:09:31，`access_tokenid.c` 为 2026-10-05 09:18:14；
`ninja -w dupbuild=warn -n packages/phone/images/Image` 却输出 `no work to do`。
不能把上述候选构建或旧 Image 当作最新内核修复的证明。

新增独立 `common/device/qemu/kernel_build_dependencies` 部件：所有补丁应用完成后、
preload/遍历之前对实际 kernel、common_modules、配置及 HDF 等八组输入生成内容指纹；
GN 显式依赖该指纹。新 wrapper 只在真正执行并成功完成内核编译后生成 Image/12 个模块
的哈希证书，禁止给原来的“文件已存在”快捷路径出具证书。打包前重新核对当前源码、
Image、模块及证书；归档携带输入清单和证书，交付检查再次核对实际 Image。
七项回归覆盖嵌套变化、稳定输入 mtime、构建生成文件排除、错误架构/旧 Image/旧模块、
构建中输入变化、GN 相对输出路径及包内证据。此证书只证明来源，不能代替启动和行为测试。

纳入这些修改的冻结 `/Volumes/PSSD/qemu/build-inputs/phone-XyNwB2`，树 SHA-256
`7d11bd859abe272d8a39b257639a2f8335895465a0fe232b5e272d3391c300af`；
日志 `/Volumes/PSSD/qemu/logs/phone_full_build_20261005T100318Z.log`。
实际准备后 kernel 输入指纹 `a67b606baf7852004a417b6d07d7dbe537cb2aa72b6d9e8e07ff5d2467999f16`，
84863 个输入。完整主机回归 99 项、device-type 回归通过（截屏依赖使用隔离 venv）。
该轮在 load-only 的 `gn format .../security/dlp_permission_service/BUILD.gn` 遭遇 SIGILL，
退出 1，未进入内核编译、未产出包。实际 GN SHA-256
`aa76f11ec5ab820695fdd0973d644d205305b1a23fabcc43e230871f502230a7`，版本 `2026 (47b40ef4)`。
同一二进制/输入的 60 次 `format --stdin` 全部成功，没有复现 SIGILL；
40 次 `format --dry-run` 均退出 2（表示尚需格式化，不是 SIGILL），不能计为格式通过。
只能据此重试首包，不声称构建环境异常已修复。

相同内容树的重试冻结 `/Volumes/PSSD/qemu/build-inputs/phone-sbP33M`，
日志 `/Volumes/PSSD/qemu/logs/phone_full_build_20261005T100824Z.log`；当前只构建 ARM64 phone。
已通过 load-only、最新 feature/权限/画像检查，进入完整构建；尚无归档或启动结果。
后续已观察到内核 `out/kernel/OBJ/arm64_virt` 的真实 make/编译进程，不再是 Ninja
“no work to do”。但该冻结不含下述后发现的 AppSpawn 强实现、Vibrator 时间序列及
PermissionManager manual-settings UI 修复；
本轮只能用于新包诊断，不能当作最终修复包交付。启动检查发现的失败仍需在同一个
ARM64 phone 首包上重新冻结、编译、打包及复验，其他五包继续受门禁约束。

### AccessToken 处理逻辑复核

旧 inline 代码试图替换 5.10 风格 function table，而实际 Linux 6.6 使用 switch。
因此只改到 header，GET_ALL_PERMISSIONS 没有 handler；旧脚本还含不应保留的 SPM/refcount
直接成功占位分支（本次 6.6 源码并未匹配到这些 C 分支）。移除整个 inline ABI 修改，拆成：

- `common/kernel/linux/linux_6_6/access_token_abi`：只对已知旧 header SHA 做严格迁移，
  新增真实 GET_ALL 位图查询和 dispatcher；锁内复制，锁外 copy_to_user；未知 token/copy
  错误不返回成功。单项 GET_PERMISSION 先在锁内取值，避免并发删除后的 use-after-free。
- `common/base/security/access_token/kernel_spm_handshake`：仅 ioctl 成功且协议 v1 时启用 SPM；
  失败/零版本/未知版本保留上游 legacy 路径。不声称增强 SPM/refcount 协议已经实现。
- 最新 kernel 补丁还实现真实 `current->user_id` 的 SET/GET，写入仅限 root/ATM；
  `common/base/startup/appspawn/kernel_user_id` 将设置顺序移到降权前，并传播错误。
  这些修改晚于 phone-p1TS26，下一轮必须重新冻结、重编内核和 AppSpawn。

7 个回归验证真实 hunk 中函数的全部 2048 位、64-word 位图、更新/未知 token/坏指针/
opcode 溢出、解锁立即释放节点、SPM 错误及版本、幂等及 marker 漂移，以及 user ID
存储/权限/错误边界、AppSpawn 的设置顺序及失败传播。
ASan 负向回归能检出旧函数的 heap-use-after-free；新函数通过 ASan/UBSan。
从实际 source volume 复制到只读诊断容器 `/tmp/access-token-real-source.SlAny0` 后，
实际旧 header 迁移和两个部件重复应用/reverse-check 通过，补丁后 SHA-256：

| 文件 | SHA-256 |
| --- | --- |
| access_tokenid.c | `0f8ec1a28b66d5c919cf6cf15cd7e2f8cacf4748d355d45803ced468d9bd94bd` |
| access_tokenid.h | `17990a5fd71940b2cd43179aeda009eaf06c046e13baa452193b6b9c83afe273` |
| permission_kernel_utils.cpp | `48c309c1ec2443594ecd35ca0387b4ee5d1f536e609562d00e335a2c7bdf2912` |

上表是 phone-p1TS26 的位图版，不是最终 user ID 版。后续实际源码副本
`/tmp/access-token-userid.0JzPo3` 的旧位图版迁移、三个部件重复应用通过；新版 SHA-256：
`access_tokenid.c` 为 `ec40a8d18c56f8872d30d94d013fd3ed543e11cf33c7faacb8eef70360808606`，
header 为 `31e016948586c1e03691a9ade0bbc2e88be9edd8c924490ba706c219ad2dae18`，
`appspawn_common.c` 为 `8013c0c242d318c3cdd56480935338296d920ab1bcb6af23630d4de408867790`。
parent-HAP-token 查询仍没有实际 kernel handler，需要单独闭环，不能用当前 token 冒充父 token。

继续检查实际 ELF，发现 `libappspawn_common.z.so` 的 `SetUserId` 是 WEAK：
默认 `appspawn_custom_sandbox=false` 时只执行返回 0 的空函数；只移动调用顺序并没有
修复普通 QEMU 应用。新增该部件的 `0002`，在默认 common 模块实现真实校验/open/ioctl，
移除 custom_config 内重复定义，保留降权前调用和失败传播，不启用整套 custom sandbox。
实际 source volume 的只读副本 `/tmp/appspawn-userid-real.F1knyC` 应用及重复应用通过；
`appspawn_common.c` SHA-256 为
`96b7dd1ccbc5e53478c7ef753710711477814b2d2d967e3cda5cf89839ce140b`，
`appspawn_custom_config.cpp` 为
`84113b3e1526557343054e09f2a6038db2d76c1a00c49c7b8f62a3e60e557a59`。
新增真实函数 ASan/UBSan 回归覆盖 uint32 边界、非法字符串、设备打开/ioctl 失败及清理；
AccessToken 部件测试现为 8 项。`phone-sbP33M` 尚不含 `0002`，普通应用 HAP 必须验证
内核账号与账号服务一致，不能用 root 的 SET/GET 通过掩盖 AppSpawn 的空实现。

以上是源码/主机测试证据，不是新内核运行结果。新首包须重编 kernel，实际在 guest 执行
`access_token_kernel --privileged <32-hex-run-id>`；仅使用保留的非法 token，不修改任何有效
应用 token，测试 grant/revoke、2048 位一致性、删除/重建并发查询及错误边界，再删除测试记录。
普通应用 UID 的 `--unprivileged` 还需验证设备访问或权限写入/设置 token 被拒绝。
三种架构 raw 探针交叉编译通过，均未在新 guest 执行：

| 架构/路径（`validation/first-20261005/` 下） | 探针 SHA-256 |
| --- | --- |
| access-token-kernel-arm64/access_token_kernel | `e47d711aa1dafd4606489ce28b674bf080ee78547f0fb832849024e0050bce68` |
| access-token-kernel-armv7a/access_token_kernel | `dce19869f8c5ef7497fea74f16a84156e2617d51476b5d82a720574d3988c527` |
| access-token-kernel-x86_64/access_token_kernel | `4ac3fb8c9f0cea99278edea235255a5712c37012afdb4d067358976288555a8b` |

JSONL 验证器绑定实际归档 SHA、run ID、架构/位宽、真实 UID/角色和 guest 退出码，要求
完整边界/并发/清理用例；明确记录 enhanced_spm_implemented=false，不把 legacy 适配说成增强协议实现。
探针的主机 syscall mock 回归会实际执行 probe 的授权及并发/清理逻辑，并确认全零“成功”
位图会失败、root/ATM 不能冒充普通 UID；这些 mock 结果仍不算新 guest 运行证据。
探针同时覆盖 mmap/mprotect 只读输出缓冲区：合法读取输入后 copy_to_user 必须返回 EFAULT，
不能因锁内用户访问造成异常，也不能返回虚假成功。上述探针仍不覆盖 user ID 的新 guest
行为；必须追加验证，不能借位图通过声称全部 AccessToken API 已修复。

追加独立 `access_token_userid` 和普通 AppSpawn HAP：root 实际 roundtrip、fork 继承/子进程
隔离、坏指针/只读 copyout、恢复原 task 状态；HAP 查询账号服务结果，检查内核值一致，
普通 UID 改写拒绝并确认状态不变。冻结 host challenge 防止旧日志冒充新运行；不改变有效
应用 token 或给正常应用授权。5 项 actual-probe mock/严格结果验证回归通过。
三个 ELF 交叉编译、ARM64 普通 HAP 构建通过；均未在新 guest 执行。
HAP `/Volumes/PSSD/qemu/validation/first-20261005/userid-app/entry/build/default/outputs/default/entry-default-unsigned.hap`，
SHA-256 `b6ea30309b3d8b437ff99ab183298a2b15d5d8317e97f092462beb7e8bf722c7`，
host challenge `0731890507924f97a3192e84a85ec8d2`。当时完整主机回归 104 项、bindings 驱动 9 项通过，
这些不是 guest E2E。三架构 user ID 探针 SHA-256（同上目录）：
ARM64 `b06c382eae0fb4f741ac257c7406539183620091bcdd08e425e020d9025d4536`，
ARM32 `5c8177662a967550e1d232ad56f1d8497bd1fa0ca753375994367317948b3b20`，
x86_64 `1f2dd48bf7b77cea4bc79c50c460500fc438d924c766169a26561012065f3f46`。

同一普通 HAP 的 ARM32 / x86_64 未签名包也实际构建通过，分别位于
`validation/first-20261005/userid-app-armv7a/` 和 `userid-app-x86_64/`；SHA-256 分别为
`2ccd63043b827347fa4a00f9bd348b8f9784372fd693c382725d7d43a190126a`、
`8089f7a8a685d44890c06a6ab21a97b329fb55af808d8cbd130d697d22ba4413`。尚未在新 guest 安装。

### 测试假通过与自定义振动复核

bindings 的 Vibrator、ArkWeb 原用例把非空异常也当作通过；QoS smoke 只要求字符串非空。
现在要求 Native 调用不抛错、协议注册返回 true、QoS 精确等级及六次实际 set/get 输出。
ArkWeb 注册用例明确不证明页面执行；另外给测试宿主/示例的 WebviewController 设置真实
webTag（ArkUI 的 `.id()` 不等于 Native controller tag）。主机断言回归 4 项，架构驱动及
严格 Hypium 解析 9 项，共 13 项，不是 guest E2E。

严格用例暴露出另一处实际能力缺口：QEMU VDI 的 `isSupportTimeDelay=false` 导致 Custom
JSON API 在解码前返回 unsupported；即使只开标志，旧 composite 逻辑还拒绝上游
`TransformTime` 的零时长结束项，且重复累加 delay+duration。已修复为事件开始时间轴，
接受最后的 stop marker，溢出/非法序列保持原状态，只声明时间序列能力；不声明 HD、
primitive mapping、强度/频率调制。实际 decoder GN 目标存在且 custom feature 默认 true。
真实类的 4 项 ASan/UBSan 回归覆盖重叠/分片/结束项、精确到期、uint32 边界、设备 ID、
取消及未实现能力。当前完整仓库主机回归 109 项通过；新 guest 的 decoder→服务→HDI→VDI
闭环仍待验收。该修改也晚于 `phone-sbP33M`，不得写成已打包修复。

候选 VDI 使用三个产品的实际 Ninja compiler flags、musl/HDF 头文件均编译通过。
ARM32/x86_64 的旧输出缺 HDI 头文件，使用各产品的实际 IDL 工具从当前源码在 `/tmp`
重新生成；上游 IDL 工具要求输入 W_OK，故仅复制这三个 IDL 到 scratch，没有改变正在
构建的 source/out。编译器/生成头文件证据保存在验证目录；仍不等同于六包构建或运行。
VDI 源码 SHA-256 `cb8b733448b5b9175b2144c493431c70356bacc78bc63343c4f4f1d32f5606ee`；
ARM64 / ARM32 / x86_64 object SHA-256 分别为
`50127acb8f327562ec2f95478df3736e67e1cbb53392adf30901e256aa50ca0f`、
`ab55f2d353609b245a509afed84b8f54b8126b2b272f4d6d03df25a84a2752ee`、
`640e2804e0aed657503db7e14f9a779e9388b1d79f4bff65a5fccc8174312eb1`。

收紧断言/修正 controller tag 后，bindings 实际未签名 ohosTest HAP 构建通过，路径
`/Volumes/PSSD/code/ohos-rs/ohos-native-bindings/examples-ui/entry/build/default/outputs/ohosTest/entry-ohosTest-unsigned.hap`，
SHA-256 `a5cd485ba2b500ade2495f53550b9cba7c770821890846cd54dd5b368dad20f3`。
这是编译证据，尚未签入新 guest/执行 E2E。

### PermissionManager 独立手动授权入口

固定 AccessToken 使用 `com.ohos.permissionmanager.OpenSettingAbility` 和单项
`ohos.open.setting.permission` / `ohos.open.setting.result_code`。旧 PermissionStateSheet
使用权限数组和不同返回键，直接 alias 会造成错误协议或成功默认值。
固定 permission parser 的 manual_settings 仅四项 PC/tablet 权限；phone 的不支持路径
是设备约束，不给 phone 追加 PC 权限。

新增 `common/applications/standard/permission_manager/open_setting` 独立脚本、注册入口、
页面和模型，不改旧数组协议。AbilityManager 注入的 bundle/UID/token 必须匹配对应账号
的实际 BMS 记录和声明（包含 signed int32 token 转 uint32），只在明确 Allow 后重新
校验、调用真实 `grantPermission(..., PERMISSION_USER_SET)` 并再次查状态。Cancel/back/
卸载换 token/关闭中/重复点击不会自动授权；不支持、未声明及内部失败不是成功返回。
父窗口 modal 创建、加载失败明确报错，不降级为无归属授权窗口；销毁还原浮窗状态。

7 项真实 ArkTS 模型/组件回归覆盖上述边界，实际源副本
`/tmp/permission-open-setting-real.7zroo7` 应用/重复应用通过。第一次 compile-only 项目缺
buildOption，第二次真实 ArkTS 检查检出 4 个类型错误，均已修复；第三次语义编译及归档通过。
使用隔离 SDK overlay 的系统 API 来自实际 pinned checkout，未修改 DevEco SDK。
`validation/first-20261005/permission-settings-compile-03/compile-evidence.json` 记录完整结果；
未签名检查 HAP SHA-256 `7fffd8ddf74b5eac495fdf44212f689e2267e2b5c1211769c273447bbe584189`。
此检查 HAP 包名为 `org.harmonycontrib.permissioncompile`，**不可安装冒充 PermissionManager**。
新 2in1 包内签名、UI 启动、Allow/Cancel、实际 grant/revoke 及调用方边界仍待验收。
当前完整主机回归 116 项通过；其他五包仍未启动，以上新增候选都不算已交付修复。

进一步补齐 PermissionManager 生命周期边界：关闭 session 后失效旧请求；重复使用
extension 时重置关闭状态；拒绝并发新 session 后，它的销毁回调不得关闭原 session。
实际模型/组件回归已增至 8 项。第四次隔离系统 API 编译通过，证据为
`validation/first-20261005/permission-settings-compile-04/compile-evidence.json`，
未签名检查 HAP SHA-256 `0344595d852ca1a50fd8e4976d5c289ca34d41dce7782aff83177ebca8b186a0`，
Ability 源码 SHA-256 `dd04ee19a3c60a51108298e93e5064da75cfc75009b37f83cc26b199d1d4e635`。
这些仍是 compile-only，不能代替实际 2in1 系统 HAP 的签名/权限/UI 验证。

新增真实 HDI IPC 振动探针，覆盖 12 个有序场景：连接、仅时间序列能力、设备信息、
one-shot running/cancel/expiry、上游 stop marker、时间轴不重复累加、非法序列/设备
不改变原状态、未实现调制如实拒绝及清理。使用实际产品 system libc++ ABI 编译，
不借用 public NDK 的 ABI；探针 ELF 的依赖必须由新镜像自身提供，不随探针额外塞入库。
ARM64 ELF 路径 `validation/first-20261005/vibrator-hdi-arm64/vibrator_hdi`，
SHA-256 `18d4f72e1cd47c970b099cc6538285465ccd4a1bb07cd37f257bbc7594f2afb4`；
源码 SHA-256 `8d1e4ce20e8b40a3495f86232e96b9a4c23558ab6875628c08e2c4e61160677d`。
严格结果校验器的 3 项回归通过，但探针尚未在新 guest 运行。它只证明 root→HDI→VDI
路径，不替代普通应用 JSON decoder/权限及 bindings E2E。

最新完整主机回归 120 项通过（包含上述生命周期和 HDI 结果校验）；新包运行结论仍为空。

后续 effect 边界复核发现旧 VDI 把所有非空名称都报告为支持。现只支持固定 SDK 的
`haptic.clock.timer`（100 ms）；未知非空名称查询返回 false/0 ms，start 明确失败，
不修改已有 deadline；空名称继续返回 invalid。新增第 5 项真实类 sanitizer 回归通过。
HDI 探针增至 14 个场景，额外要求实际预置查询/运行及未知名称不改变原状态。
最新候选 VDI 源码 SHA-256 `34ac2964b2dcaf452e861672aaadf58383051a2e8d3085e6c82785964eaaa1d0`，
实际 ARM64 / ARM32 / x86_64 object SHA-256 分别为
`8d7b87eea6f451cb0e10e373ae35e558e61217f91474ab11876353dff31def67`、
`5bc4adf644687bb115558151df4bf45e5fb3cfa3faa842ce28a1a5dcf5daaeb3`、
`d6da1c23af46f7ee4ae2bc07f9f5287b9de75c1018ca6eba0aaf7d8f44c7210d`。
编译证据为 `validation/first-20261005/vibrator-compile-preset-{arch}.json`。
更新 HDI ELF 位于 `validation/first-20261005/vibrator-hdi-preset-arm64/vibrator_hdi`，
SHA-256 `3bb1d073151c79a828408f8c432290f64d40cbc3a77b83d2b67075f9f379a7be`，
源码 SHA-256 `105bdeeecbe83cf91ee9a94523c4ee05e25a105bb7fab77cfe36f89d1cfccb33`。
它替代上述 12 场景探针用于后续 guest 验收；当前冻结包仍未含 VDI 修复。

新内核实际编译结束，staging Image 更新时间为 2026-10-05 10:52:12 UTC，
Image SHA-256 `cea3357e720f36210bbeb0631839b845b38d3838af4c271c2a07441297e2f97b`；
10:52:49 UTC 已生成 `kernel-inputs.json`，输入树仍为
`a67b606baf7852004a417b6d07d7dbe537cb2aa72b6d9e8e07ff5d2467999f16`。
整包尚在 userspace 链接阶段；该 Image/certificate 不是已打包或已启动的证明。

后续打包清单新增 `validation`：capability flags 明确只代表 static packaging contract，
boot/behavior/first-artifact gate 均为 false，真实运行证据必须外置并绑定归档 SHA-256。
full-source 离线检查拒绝缺失、含混或伪造 true 的运行验证标志。2 项回归、真实打包/画像
脚本的 fixture 测试通过；该标注晚于当前冻结输入，不会将旧标志理解成新包运行通过。

导出复核保留原 SDK `411d28f767bd6cd2a6905e3c6b15f0992f55b81b`：原临时 worktree
已不存在，GitHub 精确 commit 归档返回 404，使用本地只读 Git object 的 `git archive`
恢复到独立 validation 目录，未改构建 checkout，也未降级到当前构建 SDK。
审计源码 tar SHA-256 `932f7de65b9caa2450800ddea0542f9b3ef4c1f1bff4730367e6742733011df1`。
AST 分类 4 项回归通过；每种设备原 14 个 const enum 误报移至编译调用契约，总计
16 项 `compiled_caller_not_verified` 保留，真实函数数量未变；新 guest 验证仍待执行。

截至 2026-10-05 11:14 UTC，最新完整主机回归 **127 项通过**（使用实际 SDK 26
TypeScript AST 与 Pillow venv）；`ci/device-type/test.sh`、shell syntax、diff whitespace
检查通过。这些测试只覆盖源候选/打包契约/结果校验器，不是新镜像的 E2E。
`phone-sbP33M` 已到 5819/7299，仍无实际归档；后补 AppSpawn common setter、Vibrator
时间轴/有限 preset、PermissionManager UI、manifest validation 标注均不在该冻结输入。
其他五包未启动，Camera/WiFi/Bluetooth/Telephony/软件编码器及余下 Provider 仍未完整实现。

进一步复核发现上表的六个旧名称（DistributedFile、HiDumper、DataTransitManager、
DeviceAuth、DeviceSecurityLevel、PinAuth）在固定源码
`developtools/syscap_codec/include/codec_config/syscap_define.h` 明确标为 `abandoned`，
固定 SDK 的 ArkTS `.d.ts` 中也没有引用它们。不能据旧文档名称缺失，直接断言六个部件没有实现。
其中 DataTransitManager 实际位于 `base/security/dataclassification`，产品已含此部件，
不是此前猜测的缺失 `data_transit_mgr` 仓库。仍需分别检查真实实现及运行行为；本发现不是
取消接口实现或批量补 true 声明的授权，也不算运行验收。

首包还未生成，所以尚无实际包路径、包校验和或启动验收结果；输出目录不能冒充产物。
其他五包未启动。首包产出后必须补记实际归档路径、SHA-256、隔离端口 5681 的新包启动环境、
完整测试命令与结果；失败则修复并重建首包，不进入六包矩阵。

后续检查更新：完整主机回归 **135 项通过**。新增 7 项 root 探针驱动回归覆盖错误 ABI、
非 root guest、错误画像、实际 guest exit marker、传输失败、探针 checksum 变化、超时及
旧结果拒绝；新增 1 项 SwiftShader Subzero POSIX 配置 apply/reverse/幂等回归。
`run_root_probe.py` 只传探针 ELF，不注入运行库，记录随机 run ID、真实 guest 退出码、
归档/探针 SHA-256、命令和日志；caller-selected archive 不是自动启动证明，full gate 始终 false。
它不替代普通 HAP/权限、JSON decoder 或可见 UI 验收。

ARM32/x86_64 Vulkan ICD 依赖已实际编译、检查 ELF/loader 入口，首个 ARM32 Subzero
编译失败及修复均已记录；没有构建其他 QEMU 包。bindings 的 ArkWeb 响应修复及同进程
live-page 验收已在 ARM64 实际编译主/测试 HAP，18 项相关主机回归通过。具体产物
SHA-256、输入快照和日志见 `OHOS_7_ARKWEB_VULKAN_REPAIR.md`。这些均不是新 guest 运行通过。
当前 `phone-sbP33M` 仍在 userspace 链接，输出目录尚无归档，仍保留此前注明的后补输入差异。

2in1 Camera 画像复核：实际 SDK `43e34facc58b9c0f15c58571554ddd7eaa004455` 的
`api/device-define/2in1.json` 不含 Camera.Core，SHA-256 为
`b2c3a0d1f2338819a53bd623134701ada26a025f6ac59b0f5eae97a19364bc7d`；rich.json 则继承
camera_framework，其 bundle 默认声明 Camera.Core，而 QEMU Camera VDI 缺失。
2in1 窄覆盖层仅撤销该错误声明，复制 rich owner 的原有设置，保留组件/库，不改 shared
bundle 或 phone 能力。只读实际 profile 生成、两个新增保护/幂等回归及 device-type
画像切换测试通过；未启动新的 2in1 preloader/guest，不据此把 Camera 实现标为完成。
未来固定 SDK 若要求 2in1 Camera，同一保护器会拒绝继续排除该能力。

加入上述 Camera 保护后，完整主机回归更新为 **137 项通过**；进一步包含 phone/2in1
切换时没有残留 Camera false 覆盖的 device-type fixture 测试也通过。
`compile_appspawn_userid.py` 使用实际三个产品的 Ninja clang 命令、system headers 和 flags，
仅在 scratch 应用后补 common-setter 补丁，ARM64/ARM32/x86_64 均编译通过，且真实
`llvm-nm` 要求 `SetUserId` 为强 `T` 符号。补丁 SHA-256 为
`708f829b1200659acd9dc43f0210e6d9c945452de56cabbbb0776a517eaaa94c`；候选 common.c
SHA-256 为 `96b7dd1ccbc5e53478c7ef753710711477814b2d2d967e3cda5cf89839ce140b`。
object SHA-256 依次为 `ed9d7414195b0e7f695f83cd6f9b849d1f91d5c91dce1a5b6702264a37ef86e8`、
`c1f9497f2b9ddf9bdfa1dee5a7720cfcde001aa3f7049c608e703a20f0ce569c`、
`9cbd7438355e276f34f6feb82dbc8b0f39583980abe422e4c8e2efa9532ee3e4`。
证据为 `validation/first-20261005/appspawn-userid-compile-{arch}.json`，均明确 compile-only。
source/out volumes 保持只读，当前冻结首包仍未含后补 setter；这不是普通 HAP 账户隔离证明。

## 已准备的实际调用测试

2026-10-05 首包验收脚本又修复两种误判：AccountMgr 必须在同一份最新快照中明确
显示用户 100 在前台，不能用其他账户的 foreground 或累计旧状态满足门槛；新增四项
解析回归后完整主机回归为 141 项通过，qemu-smoke shell 回归亦通过（含错账户、
前后两份状态拼接的拒绝案例）。这仅验证验收工具，没有提前认定 guest 已通过。
另发现打包脚本直接写最终包名会让消费者读到压缩中的截断文件，已改为同目录唯一
临时文件，tar 成功后原子 rename；真实成功/失败回归要求保留旧完整包并清理临时文件。

首个 ARM64 phone 包的构建进程已退出 0，最终包为
`/Volumes/PSSD/qemu/packages/first-capability-repair-20261005/openharmony-qemu-arm64-arm64_virt-phone.tar.gz`，
大小 866941152 bytes，SHA-256 `c060979b682568ed747662b9cee7276befa6a06b9cf13b6b4905e8e7f5b2ef22`。
从该包重新解压完成，待实际启动验收；后补 setter/VDI 等没有进入其冻结输入，
因此该包只用于诊断，不能交付为全部缺口已修复。完整环境与命令记录在
`/Volumes/PSSD/qemu/validation/first-20261005/first-package-evidence.json`。

- `validation/first-20260927/native-strict`：Native 设备/音频/HUKS/GLES 探针已编译。
  GLES 不再始终返回 0；要求 GLES 2/3 context 和 RGBA 回读均正确。
- `validation/first-20260927/graphics`：Vulkan device/headless/extension 与 EGL 声明探针已编译。
  device 探针增加实际队列提交、设备填充、同步与 1024 个 word 回读检查。
- `validation/first-20260927/graphics-wsi`：OHOS NativeWindow buffer-queue 探针已编译。
  通过 Vulkan 清色和 present，要求消费者映射回读十帧共 1500 个像素，验证 resize 后旧
  swapchain 返回 OUT_OF_DATE 且不提交虚假帧。此探针不是屏幕 compositor 呈现证明。
- `validation/first-20260927/arkweb-strict-recovery`：未签名 Web HAP 已编译。
  使用本地 HTML，验证 JavaScript、DOM、Canvas 2D、WebGL 1/2 context、shader 编译/绘制/像素回读，
  并要求非法 shader 被拒绝、页面异常后继续执行、实际 JS/ArkTS 双向回调、刷新后保留
  ArkTS 状态，以及 renderer 终止/恢复后重新绘制 WebGL1/2。启动新包获得 UDID 后再签名安装。
  当前未签名 HAP SHA-256：`31acd9ba996b33f3e3158e4c614eb9ad10f3c2cf89c2852a6f37770f7abd8246`；
  这不是产物包的校验和，也不是运行验收记录。
- `validation/first-20260927/audio-suite/audio_suite`：使用固定源码中的 API 26 Linux native SDK
  编译真实 PCM 管线探针，要求两轮 engine/pipeline/node 创建、输入回调、3840 个非零
  样本回读、停止前后错误边界及释放。明确不覆盖算法插件、云下载和 realtime device nodes。
  探针 SHA-256：`82e2f6e435c8c38129471fae57769e13a7b3d2ca5a1b20e5c1b2226fe092f602`。
- `validation/first-20261005/vulkan-window`：实际 XComponent 回调提供 NativeWindow 的未签名 HAP，
  要求五帧 present、释放 Vulkan 资源、销毁并重建窗口，再用两张实际 compositor 截屏验色。
  未签名 HAP SHA-256 `2c2e9683045b77045dae25cf956d4040117d1faf264ff2cedea0d87483dd3328`。
  已通过 API 26 host SDK 编译，以及固定源码 Linux SDK 独立编译/链接；尚未运行。
- `validation/first-20261005/i18n-data`：普通应用实际检查时区偏移/DST、城市数据、E164/非法
  号码、区域名称、ICU 日期年份，以及 system-language setter 权限拒绝且语言不变。
  未签名 HAP SHA-256 `b4e2d0967eee489d0160f4b25a1e3a27f13dec1c90150c7d9ded0adcb67553b2`。
  使用公开 SDK 的 system setter 显式类型桥，未关闭权限或绕过签名；编译通过，尚未运行。
- ARM32 bindings 交叉编译目录 `validation/first-20261005/bindings-armv7a`；仅测试库，不是 QEMU 包。
  JSVM SHA-256 `117b836d9762a3a01298487ac8925a1900361130d8e39a40e9fe81406100fde1`；
  QoS `a281128bc9183788b243fe3ce5366a80d64039cf0259aca5deb20be0c38507cf`；
  Vibrator `92ad80c825ed05075738310ab9008f40d468a7ba003c82dc7ade401998a0369c`。
  实际 ELF32 ARM/EABI5；尚未在新 ARM32 guest 调用。驱动改动在 bindings 独立分支，未提交。
- `validation/first-20261005/permission-registry-arm64`：从固定源码 system innerkit 和
  system toolchain 编译只读探针，不用 public NDK 的不同 libc++ ABI 伪造跨 DSO 类型。
  要求实际查询全部 973 项定义、核对 APL/ACL/权限元数据和禁用项，以及不存在/非法/空名边界。
  新 run ID、完整 footer 和进程退出码同时检查，拒绝陈旧/不完整结果。
  探针 SHA-256 `a9b59a812bb2e5c7035dd71b700db7e36bc8ddbb2d7c9115cd17af1f41a94bf2`；
  源定义 SHA-256 `fae6948a3ad48070c9a55a423332c3c355397c2c36d991c4a3a5e3cbc106b70e`。
  已编译，尚未在新 guest 运行；它只验证注册元数据，不代表全部受权限控制 API 可用。

```sh
python3 ci/capability-audit/verify_web_results.py \
  --log /path/to/new-guest-web-results.log --output /path/to/web-result.json
```

全部仍待新包运行。Vulkan headless 成功不等于 OHOS NativeWindow WSI 成功；
ICD CPU 呈现桥及 loader 分发已实现候选版本并通过编译/边界测试，真实呈现尚未验收。
Camera/WiFi/Bluetooth/Telephony 等官方画像内后端，以及其他 C++/ArkTS 1.1 台账项仍未完整修复。
本轮画像收紧不会把这些问题从待修复范围移除。
