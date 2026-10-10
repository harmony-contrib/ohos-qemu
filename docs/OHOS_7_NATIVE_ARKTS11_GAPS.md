# OpenHarmony 7.0 Native / ArkTS 1.1 缺失清单

## 2026-10-10 HiDebug 普通应用实测新增失败

在未替换内核或库的 R30 归档上，新增 C++/ArkTS 普通、零权限 HAP 试验，
准备依次分配两个 2048×2048 RGBA DMA 缓冲并释放，比较每阶段两套公开接口的
真实统计，同时保留 `/proc/process_dmabuf_info`。三 ABI 调用者均完成实际 API26
SDK 构建：`graphics-memory-{arm64,armv7a,x86_64}-build-r31-04`。

实测在第一个统计结果便失败，尚未进入缓冲分配：
`r30-graphics-memory-runtime-01/graphics-memory/actual-results.log` 报告
`cannot serialize a BigInt`，boot `5ebd5e7a-0b8a-4acd-a5b0-c2798518c376`。
结果 SHA-256 `e4915f047a730cee1d7207c2805c14923aba65a0149c720c0fb5acf1989044cc`，
诊断 SHA-256 `8e40b989115aa87112fbca1c6f14e3a4c03bab22e17e3e4197d22f664b85daaa`。
固定源码 `GraphicsMemorySummaryAsyncTask::Done` 将 `graph` 用
`napi_create_bigint_uint64` 编码，而 API26 `GraphicsMemorySummary.graph` 明确为
`number`；内部 `gl`、`graph` 均为 `uint32_t`，其中 `gl` 还错误地转为有符号数。

新增独立部件 `common/developtools/profiler/hidebug/graphics_memory_types`，
两字段统一用 `napi_create_uint32`，保持真实数值、缓存、统计后端及错误路径不变。
不在应用端偷偷转型以掩盖错误公开类型。源树 patch check、幂等/漂移测试及
0、INT32_MAX、INT32_MAX+1、UINT32_MAX 编码边界通过；共享构建入口已接入。
该修复不在正在构建的 R31 冻结输入中，必须由后续新归档复验。

失败客体已恢复电源策略并关闭，证据与失败镜像保留；不更新缺口闭环数。
新增图形内存结果验证器严格拒绝固定零值、无分配变化、泄漏、身份改变和错误类型；
其结果仍为 `closed=[]`，不冒充完整 HiDebug 或内核 inode 归属闭环。
此前新增调用者/验证器主机回归运行 1375 项、整体成功，其中 1 项跳过，205.905 秒，
`host-regression-graphics-memory-r31-01.log`；类型修复后的全量回归另行记录。

第二次独立实测 `r30-graphics-memory-runtime-02` 没有偷偷将 BigInt 转为合格数值：
记录真实 `typeof` 和诊断字符串，错误类型仍用 -1 标示并被验证器拒绝，但继续
分配/释放以观察独立底层路径。boot `48245a03-fa17-4023-bf82-1e6a5b659adf`，
普通 PID 2585、UID 20010038。NDK 实际 graph KiB 序列为
**0 → 16384 → 32768 → 16384 → 0**，两次释放均验证保留的数据及成功返回；
C++ 空指针边界返回 401。ArkTS `graph` 五次仍是 BigInt，故整体明确失败，
并非后端固定零值冒充成功。原始内核记录随每次轮询保存。
结果 SHA-256 `64c08abd2522a888d07bd9048d2cae329a898ae7e2838b6fb44d69077a2c0f71`，
诊断 SHA-256 `d8a0aa1ccafd99a1e31d7548897f058b20ddb00fc422bed982aa5dffad84b904`。
经逐日志 SHA 与客体成功状态核验，真实内核 inode 25、26 各 16777216 字节，
持有序列 0 → 1 → 2 → 1 → 0，与 NDK 计数和释放顺序对应；此窄范围复核仍为 `closed=[]`。
增强后的调用者三 ABI 构建均通过（`graphics-memory-*-build-r31-05`）。
两次失败证据都保留；必须在修复后的新归档上让原类型检查和真实计数检查同时通过。
最终主机回归 `host-regression-hidebug-types-r31-03.log`：运行 1384 项、整体成功，
其中 1 项跳过，207.827 秒。包含内核 inode 生命周期检查，但不替代新实包运行。

随后把 `graphics-memory` 接入完整套件与六组合共用首包门禁：必须在同一真实
验收客体上，重放编译/普通签名负载、C++/ArkTS 数字类型及数值、两次分配/释放、
内核 inode/字节数/普通进程 UID，以及电源策略恢复。只有全通过才允许登记
`behavior:hidebug-dmabuf-kernel`，不登记所有 HiDebug API。签名负载校验与 HiTrace
共用一个只读验证器；既有 R30 HiTrace 原始证据重放仍通过。
`host-regression-graphics-gate-r31-01.log`：运行 1390 项、整体成功，其中 1 项跳过，
208.292 秒。**新图形内存门禁尚无通过的新归档实测，当前账本不减少未闭环数。**

## 2026-10-10 图形内存统计解析修复（待新实包）

固定 Hiview `graphic_memory.cpp::CreateDmaInfo` 有两个独立缺陷：

- `%llu` 的 64 位目标与 `uint32_t pid` 不匹配，且只检查扫描结果等于 0，
  导致截断行、表头和部分解析失败仍可能进入 inode 去重表。
- 更新去重 inode 的归属 PID 时没有同步归属进程名。若先看到 composer、再看到
  普通应用、最后看到 RS，旧的 composer 名称会使 RS 覆盖应用 PID；统计依赖枚举顺序。

新增独立部件 `common/base/hiviewdfx/hiview/dmabuf_parser`，两个独立补丁分别
按真实 32/64 位宽解析十进制字段并拒绝无效行，以及同步去重所有者的名称与 PID。
不改变图形缓冲分配、公开接口、权限或内核统计来源；不生成虚构内存计数。
共享 Docker 构建入口已接入，适用六种组合；正在运行的 R31 冻结包不含此修复。

只读源文件 SHA-256 `9e730cafb54435d0141d931c55f071343a302db76ad509596f25c391aaed04a8`。
`hiview-dmabuf-parser-compile-r31-03/evidence.json` 保存实际源码摘取的解析器、
ASan/UBSan 边界运行及三 ABI SDK 目标对象编译证据；包括完整/截断记录、负数、
溢出、64 位 inode、重复 FD，以及 composer/RS/应用六种枚举顺序。
该结果不等于 HiDebug 公共接口实测成功，`behavior:hidebug-dmabuf-kernel` 仍未闭环；
后续必须在新归档普通 HAP 上验证真实分配/释放前后的 C++/ArkTS 统计及内核记录。
`host-regression-dmabuf-r31-01.log`：运行 1370 项、整体成功，其中 1 项跳过，206.841 秒；
最终枚举顺序边界又以独立实源码编译运行和定向主机测试复核通过。

## 2026-10-10 同客体验证接入（R31 构建期间）

R30 原始归档未替换内核、库或系统镜像，补充验证得到：

- `r30-router-observer-runtime-02/diagnostic.json` 通过，证据 SHA-256
  `4534769f28eb1a2ba7b1774e4fb83a5245770388f312b0999362f64b4ca52201`。
  修正 UIContext 引用相等的错误断言后，两轮真实页面生命周期及两种退订均通过；
  不据此声称构造器导出、density 或 breakpoint 可用。
- `r30-hitrace-enclosing-runtime-01/hitrace/diagnostic.json` 通过，boot
  `6977d6bf-8f33-4d20-b5e6-06a54bef7879`，证据 SHA-256
  `509d761079cb66e23e9dfeed6d7d790a0ab8b820be1642f06aac381592dc674b`。
  C++/ArkTS 公共调用匹配 36 条真实内核记录；子检查复用拥有者客体，不重启、
  不关闭客体、不改变拥有者的电源策略，并恢复 trace 配置。

证据根目录与下节相同；环境仍为 macOS arm64/HVF、API26 Release SDK，
精确构建、签名及客体命令在上述报告及 `r30-hitrace-enclosing-deferred-01.json`。
新增重放校验覆盖实际签名 HAP 与编译负载、普通应用 UID/PID/TID、内核原始记录、
同次启动身份及策略恢复；只登记原审计的 `behavior:hitrace-arm64-kernel` 后端缺口，
不代表 HiTrace 全 API 或其他架构已验证。当前脚本将该检查接入完整套件和首包门禁。
`host-regression-hitrace-gate-r31-01.log`：运行 1366 项、整体成功，其中 1 项跳过，218.395 秒；
重放上述实际客体证据也通过。主机夹具测试不替代新归档完整验收。

正在构建的 R31 使用冻结输入 `phone-PGsn0J`、commit `0fd9517`，包含 display
content rect 初始化及 Meta+I 保留表修复；冻结主机回归 1354 项通过、1 项跳过。
**本节新增的同客体 HiTrace 门禁不在 R31 冻结输入中**，后续最终冻结必须包含它。
首包完整验收尚未通过，剩余五包未启动；完整账本仍维持 R28 的 149 闭环、132 未闭环，
不把补充单项结果写成全量验收成功。

## 2026-10-10 R30 实包验证与下一轮修复

代表归档为
`/Volumes/PSSD/qemu/packages/first-wpa-events-7.0-release-20261010-r30/openharmony-qemu-arm64-arm64_virt-phone.tar.gz`，
SHA-256 `ea00649ce4088a545035fe047658520607f01053a30a638b3c4ac71ad2e01ceb`。
冻结输入 `phone-waHkww`，commit `4820675bd3adba68ac3cf8b897db23ed560468b3`。
本地 Docker 构建完成；实际 Ninja 命令核验五个 Wi-Fi/WPA 编译开关。
以下证据均位于 `/Volumes/PSSD/qemu/validation/first-20261005/issue-20-20261006`。

- `r30-wifi-runtime-01/diagnostic.json` 通过，两轮 radio 启停、四次真实扫描、
  频段查询、legacy 数字错误码 201 均通过；boot
  `f4a33d1a-a5b9-4a77-b12e-3386fc1af777`，普通 UID 20010038。
  证据 SHA-256 `dd084a97874bcc3e3a27a1ede5edb137954c943a0d137b4194ebd81a8a5d3e44`。
  不代表 association/AP/P2P 已验证。
- `r30-hitrace-runtime-01/diagnostic.json` 通过，C++/ArkTS 两轮公共调用对应
  36 条真实内核记录，含交错异步结束及有符号 64 位边界。boot
  `8a5a80cb-fedd-4345-a74e-06a8b3935ea9`，PID/TID 2634。
  证据 SHA-256 `792025406b933cdc89986f047b2d1a892698e321b181695b21b3120eb6f1045d`，
  原始 trace SHA-256 `e60013a111a3db17b56fa85b6294a3689ec670b808a2326c559dac06bf58599b`。
  两项测试均恢复测试策略并关闭客体，成功测试的展开镜像已清理，归档与原始证据保留。

首包总门禁**仍未通过**，其余五包未启动。R30 全量回归尚未执行，最新完整
缺口账本仍是 R28 的 149/281 闭环、132 未闭环，不用上述单项结果改写总账。
运行环境为 macOS arm64、QEMU HVF、4 核/4 GiB、独立 HDC server，
API26 Release SDK；精确命令及结果见 `r30-build-then-validation-01.json`、
`r30-hitrace-deferred-01.json` 及各诊断报告。

新失败及对应修复方向：

1. 1920×1080 测试完成普通解锁后，UITest 截图失败。
   `r30-refresh-1920x1080-runtime-01/boot/019-refresh-failure-hilog.log`
   明确显示 RS 把 display content rect 当作 **64×65535**，不是分辨率
   查询失败或 HDC 丢失。`RSLogicalDisplayRenderNode` 的私有 `Rect contentRect_`
   未初始化，构造函数未赋值；`surface_type.h` 的 Rect 是无默认成员值的聚合。
   截图及渲染参数同步直接读取该成员，且尺寸为正时覆盖实际屏幕尺寸。
   `display_content_init` 独立补丁仅零初始化该成员，与同组件
   `RSLogicalDisplayRenderParams` 的既有初始化一致；不改结构布局、公开 API、
   IPC 编码、权限或显式 SetDisplayContentRect 行为。真实源树 patch check
   通过，四项幂等/漂移/构建接入测试通过，**仍需重建实包复验**。
2. Meta+I 三次实测未启动 Settings；第三次实际 `hidumper -s 3101 -a "-k"`
   给出 `ShortcutKey: count = 0`，虚拟键盘已被 MMI 枚举。
   源码 `KeyConfigParser::ParseShortcutKeys` 调用 `RegisterSystemKey`，后者拒绝
   不在 `SystemKeys` 中的组合；原补丁只增加 launch 配置，漏掉保留表。
   新增 `0002-reserve-qemu-settings-shortcut.patch`，仅保留 Meta+I；不绕过
   注册检查，不改应用权限。主机测试验证原有保留项不变和标记后的漂移拒绝。
   诊断新增实际注册数量核验、键后原始日志留存，**等待新包两轮真实按键验证**。
3. Router observer 已实际收到完整两轮页面生命周期与 off 行为，但测试错误地
   要求 `info.context === this.getUIContext()`。固定源码
   `jsUIContext.js::__getUIContext__` 每次返回 `new UIContext(instanceId)`，
   该引用相等断言不属于接口承诺。测试改为读取回调上下文的真实 host 应用身份、
   filesDir 及可用 router；保留所有生命周期、页面 ID、订阅移除校验。
   原失败记录不覆盖，三种 ABI 的 API26 编译通过，后续 R30 第二次实测通过（见上节）。

`host-regression-display-init-r31-01.log`：1353 项通过、1 项平台夹具跳过，
201.903 秒（后续 reservation/context 调整另行补回归）。稳定性工具 registry
最新 0.1.1 已在隔离临时目录检查，其 CLI 是 skill 安装器，不是自动扫描器；
没有把安装成功算作完整 57 规则检视。当前完成初始化数据流与布局的人工窄范围
检查，完整专项检视未声称通过，也未 push。

## 2026-10-10 扫描诊断收尾日志无损采集

复核发现 R30 冻结的 `run_wifi_scan_diagnostic.py` 在成功收尾与失败诊断
仍通过严格文本接口读取 hilog；R29 已出现过非法 UTF-8 字节，因此不能
只修普通 HAP 失败日志的读取。当前仓库改为仅这两个 hilog 调用保存原始
stdout/stderr 二进制及哈希，替换解码文本明确标注为诊断用途；HDC 失败
仍报错，真实扫描结果、频段、权限错误码和同一次启动核验均保持严格。

新增三项边界测试：非法字节完整保留、传输失败不冒充成功、不能把诊断
读取器用于应用结果。整仓 `host-regression-wifi-hilog-r30-01.log` 为
1349 项通过，203.511 秒，macOS 跳过同一 Linux 专用夹具。没有修改
正在构建的 R30 冻结目录；如原冻结诊断遇到此问题，应保留失败记录，
再对同一原归档使用修正后的诊断复验，不覆盖失败、不替换客体库。

## 2026-10-10 HiTrace 普通应用到真实内核的补充验证

现有三产品实际 `.config` 都已开启 FTRACE/TRACING/EVENT_TRACING，不能
继续仅引用原审计的 ARM64 关闭配置断言当前仍不可用；但静态配置也不是
运行证据。新增 `build_hitrace_app_probe.py`，从真实 API26 Release SDK
构建无权限普通 HAP，同时调用 C++ NDK 和 ArkTS 公共 HiTrace API。
两轮覆盖嵌套同步事件、相同名字不同 task ID 的交错异步完成，以及
`-2147483649 / 0 / 2147483648` 计数边界；不直接写 trace_marker。

`hitrace-typed-{arm64,armv7a,x86_64}-r30-02` 三 ABI 编译通过。
实际 R29 原归档（SHA-256
`ab720999e6fc6224b88fd780654116b4043562a7eec12347238f2a85ee58c601`）
独立诊断 `r29-hitrace-runtime-03` 通过，boot
`d1a8f6e8-7f35-4072-ac35-34aeee426560`，普通 UID 20010038，
PID/TID 2589，共 36 条精确内核记录；核对真实 `/proc/PID/task/TID/status`，
不是把返回 void 或 enabled=true 当作追踪成功。启停使用系统 hitrace
调试工具，不改变应用身份、权限、trace_marker 访问模式或镜像库。

证据 `diagnostic.json` SHA-256
`4d79bdd6cd74d05e2653eee6b360cc8fbbc58c8d52c958bddd3ceb1a39ab17fa`，
实际内核记录 SHA-256
`25f5d7cab3d5ff65ea7fa37a997b348563ae4c099ee5c6758297cf9538edd7b5`，
严格解析器 SHA-256
`23e0970d8f81913d6915b3d9da0801bb884afc0258546fdae5ffcdd503e77f80`。
追踪开关、tracer、clock、tags、PID 和原请求容量均已恢复，电源设置
恢复后关闭客体。Linux 6.6 采用页负载长度向上取整，原请求 1408 KiB
在 4096 字节页、4080 字节负载下显示 1410 KiB；验证器精确核对源码
公式及实际页大小，不将任意容量差异视为恢复成功。

保留两次采集器失败：01 未识别内核懒分配的 `7 (expanded: 1408)`；
02 未识别 trace 的 `(-------)` TGID 占位和缓冲区页取整。02 原始内核
数据经修正解析器独立回放通过，但原失败报告没有改写。03 才是重新启动、
完整测试与恢复全部成功。三个已关闭测试客体的展开镜像已回收，保留
原归档、原始追踪、普通应用身份、HAP、命令及失败/成功记录；测试
userdata 的临时安装状态不保留。

**这是原 R29 的补充验证，非 R30 首包或三架构运行通过。** 解析器仍返回
`closed=[]`，尚未接入统一交付门禁；不关闭完整 HiTrace API、disabled
过滤、链路/监听接口或剩余矩阵的缺口。四个旧打包目录 R24–R27 的
pristine images 另经原归档逐文件哈希复核后回收，记录
`retired-pristine-packages-cleanup-r30-01.json`，回收 7,867,584,512 字节，
其原归档和全部测试证据仍保留。
最终整仓主机回归 `host-regression-hitrace-caller-r30-03.log`：1343 项通过，
199.965 秒，macOS 跳过同一 Linux 专用夹具。

已进一步整理为仓库脚本 `ci/capability-audit/run_hitrace_diagnostic.py`，
接受单个 archive/output/sdk/hdc，独占 HDC transport，正常执行原有归档
冻结输入校验、真实桌面、普通应用签名安装、内核采集与状态恢复；不构建
其余镜像，不放宽权限。第四次客体验证 `r29-hitrace-repo-runtime-04`
也通过（boot `cfee0e78-a0e2-407a-841a-60f5a0d30828`，PID/TID 2550，
36 条内核记录），通过外层实验入口加载原 R29 冻结启动验证器，复验
当前仓库脚本；没有把旧归档伪装成匹配当前工作树。脚本现在在判定应用
结果之前保存真实内核记录，失败时也不会丢失关键记录。
`host-regression-hitrace-runner-r30-01.log`：1346 项通过，200.569 秒，
同一 Linux 专用夹具跳过。仍未将旧包补充结果直接用于新包缺口关闭。

## 2026-10-10 路由观察者真实回调测试（尚待客体验证）

`RouterPageInfo` 在固定源码
`foundation/arkui/ace_engine/interfaces/napi/kits/observer/ui_observer_listener.cpp:1587`
由 `CreateRouterPageInfoObj` 创建并通过真实路由回调传给应用；不能只因
模块没有独立构造器而认定此类完全不可用。已按 ace_engine 的 KB-first
规则查询 observer/router、阅读范式说明并核对实际 NAPI 与 PagePattern，
没有修改 SDK、引擎源码或放宽审计基线。

新增普通、无权限的 `router-observer` persona，用实际 SDK 类型接收
两个真实路由页面产生的回调，重复注册两个监听、仅移除其中一个、再
移除全部监听；核验生命周期、页面 ID、上下文身份、计数及取消订阅后
静默。测试不构造替代对象，也不把 DensityInfo/断点观察能力算作通过。
结果验证器目前返回 `closed=[]`，尚未接入缺口关闭条件。

三个 ABI 的真实 API26 HAP 编译通过，记录
`router-observer-typed-{arm64,armv7a,x86_64}-r30-01`；整仓主机回归
`host-regression-router-observer-r30-01.log`：1338 项通过，202.316 秒，
同一 Linux 专用夹具在 macOS 跳过。首次使用不含 Pillow 的系统 Python
运行独立测试遇到依赖导入失败，改用已有验证虚拟环境后 5 项独立测试
和整仓测试通过；没有修改测试以跳过图像依赖。

`after-r30-router-observer-01.py` 等待 R30 已安排的首包测试与键盘诊断
结束，随后仅启动同一归档的独立普通应用诊断，使用归档原冻结启动验证器，
不修改运行中的冻结构建输入、不运行其余五包。当前仍无此 persona 的
客体通过证据，完整缺口计数不变。

磁盘回收记录 `retired-r29-packaging-images-cleanup-01.json`：只移除逐项
SHA-256 核对通过的 R29 打包 images 副本，回收 1,973,633,024 字节；
保留原归档、SHA256SUMS、构建记录及全部失败证据，删除内容可从归档恢复。

## 2026-10-10 R30 代表包重建与快捷键输入诊断

R30 仅重建 ARM64 phone，冻结输入 `build-inputs/phone-waHkww`，提交
`4820675bd3adba68ac3cf8b897db23ed560468b3`，输入树 SHA-256
`24edda868c8fc47710a9066fde66bc80eb0473502e30b3189c1924d726d53814`。
冻结目录本身运行 1330 项主机回归通过（202.782 秒，macOS 跳过 1 项
Linux 专用夹具），记录 `host-regression-r30-frozen-01.log`。
产物目标 `packages/first-wpa-events-7.0-release-20261010-r30`；
`after-build-r30-01.py` 只等待此包，并增加对实际 `events.c`/`scan.c`
编译命令中 `CONFIG_QEMU_WPA_SCAN_EVENTS` 的核验，然后依次跑扫描、
1920×1080 模式切换和完整套件。不启动六包矩阵，当前尚无 R30 归档通过证据。

另外新增 `run_shortkey_keyboard_diagnostic.py`，从实际归档启动，在真实
桌面上验证左 Meta+I 短按取消、Ctrl+I 不触发、长按出现 Settings 的可见
标题和实际合成器像素，以及普通 Back 返回桌面，两轮重复。测试仅使用
本次客体的 QMP 及真实键盘输入，保留有限电源设置/恢复；不直接启动
Settings，不修改镜像快捷键配置，也不冒充 privileged duration API 验收。
本机 QEMU 的实际 QMP schema 已确认 send-key、hold-time、meta_l 支持。
新诊断尚未运行于客体，也不包含在冻结 R30 中；整仓主机回归
`host-regression-shortkey-diagnostic-r30-01.log` 为 1333 项通过（203.922 秒，
同一 Linux 专用夹具跳过），不能据此关闭快捷键完整缺口。

## 2026-10-10 R29 首包发现的扫描事件与错误码缺陷

R29 首包在普通 Wi-Fi 扫描门禁失败，后续屏幕/完整套件和其余五包均未启动。
实际启用无线、2.4/5 GHz 查询正常，但普通应用收到失败回调；不能以服务
已启动或空扫描列表作为成功。独立同归档复现 `r29-wifi-runtime-03`，
boot `1d2e273f-9447-47d2-8292-78e93249afa4`，记录真实 WPA 于
16:38:02.767 收到扫描结果（0 BSS），上层 16:38:03.002 仍等到超时。
对应固定 WPA 源码的普通扫描和 scan-only 两条完成路径，均只在
`IsUpdaterMode()` 时发送 HDI `WPA_EVENT_RECV_SCAN_RESULT`；正常系统
因此收不到真实完成事件。

新增独立 `third_party/wpa_supplicant/scan_events` 候选：仅三个 QEMU 产品
在真实 libwpa GN 目标开启事件路由，保留非 QEMU 的 updater/chip 原行为，
保留事件产生位置、scan ID、HDI 接口、调用者权限与真实扫描数据。
四个完成分支（两条路径各含有/无 ID）仅调整路由条件，不制造完成回调。
新包还必须验证实际 GN 选择，隔离编译显式宏不算产品选择证据。

同时确认普通应用收到的同步权限错误码是字符串 `"201"`，而不是 SDK
要求的数字。独立 `wifi/business_error` 候选改用源码已有的
`napi_throw_business_error`，不改变错误码映射、消息、成功路径或权限拒绝。
四个 NAPI 变体 × 三 ABI 的真实完整 TU 编译均通过：
`wifi-business-error-r29-01.json` SHA-256
`38605455a6d6c8861841a19282e3997a454ec7719ebac107f69daf153547fae5`。
两条 WPA 路径 × 原/QEMU 分支 × 三 ABI 共 12 个完整 TU 编译通过：
`wpa-scan-events-r29-01.json` SHA-256
`1b76ae75e1dfbf3dec09580a3c9dc6d54779dd6c757a4305f3a2a85941c40724`。

首次失败诊断还暴露 hilog 含非 UTF-8 字节导致采集器解码中断。已只对
失败日志增加无损 stdout/stderr 二进制保存，替换解码文本仅供诊断，
不用于行为判定。03 实际原始 stdout SHA-256
`686285ddf61e6f84ad8ed71f22cee53190a6d47622cf9b992c96e3f36478614d`。
02 保留因错误使用当前工作树 boot verifier 而在启动前拒绝的记录；03
使用归档原冻结 boot verifier，未绕过输入绑定，外层仅使用新版诊断采集器。
01/03 均恢复电源及无线状态后关闭客体，失败结果没有覆盖成 pass。
以上生产候选尚未进入新包验收，不关闭完整 WLAN 缺口。
整仓主机回归 `host-regression-wpa-events-r29-01.log`：1330 项通过，
200.120 秒，macOS 跳过 1 项已另在 Docker 验证的 Linux 专用夹具。

## 2026-10-10 QEMU 全局快捷键配置候选

固定 MMI 源码 `64a0e42f22c9c6739651bf79b33746c500788322` 中，
`setKeyDownDuration` 只接受已在配置注册的 businessId；SDK 明确要求
调用前查询真实 ID。因此原审计直接传入字面值 `businessId` 返回 401，
不能单独认定接口实现错误。但产品的 Shortkeys 确实为空，仍没有可用实例。

独立 `input/shortkey_profile` 部件新增 `qemu.settings`，左 Meta + I
按住 500 ms 打开已预装 `com.ohos.settings.MainAbility`，两个画像共享
同一真实配置，保留原 Sequences/RepeatKeys；不修改 NAPI、系统应用限制、
参数校验、输入分发或应用启动权限。构建入口在源码准备阶段应用补丁，
且即便旧 marker 存在，也重验实际目标配置，避免把已漂移的配置当作成功。

已读取 MMI 的仓库约束、输入流水线与板侧验证说明。固定源码只读
`git apply --check`、shell 语法检查及四项主机配置边界测试通过。
整仓回归 `host-regression-shortkey-profile-r29-01.log`：1324 项通过，
202.731 秒，macOS 跳过 1 项已另在 Docker 验证的 Linux 专用夹具。
**尚未构建进 R29；尚未取得新包按键触发、取消、延时设置、重启持久化、
普通应用拒绝的运行证据，不关闭 `shortkey-empty-launch-config`。**

## 2026-10-10 普通应用真实网络计量验证

新增 `network-accounting` 普通 HAP persona，只申请 INTERNET，不申请
GET_NETWORK_STATS、ACL 或系统应用身份。受控本机 HTTP 服务校验随机
nonce 和每个字节，普通应用分别收发 128 KiB、256 KiB，使用 Promise
读取之前计数、callback 读取之后计数，并验证查询 UID 0 返回 201。
验证器绑定归档、编译输入、真实应用 UID、HTTP 服务记录与实现哈希；
失败时也关闭本次独占的回环监听，不将网络策略控制算作通过。

R28 原归档 SHA-256
`9e7ee9bd842402265665793b1462d0ab174365a1d21d9caf617926a7b6e0efc9`
上实际普通 UID 20010038 验证通过，两代 Rx/Tx 增量分别为
135516/132630、270388/264022 字节；两次越权查询均返回 201。
证据目录 `r28-network-accounting-runtime-01`，`ordinary/evidence.json`
SHA-256 `59407f7e24809de74facaa18f3a895bd7cbebcad4da3cfc22680ad671d2b0d0e`；
验证器 SHA-256
`29f2872af7c761f6ddf7463255620516789ff8838a9c33fda4d984822f3bdeca`。
`diagnostic.json` 记录同包启动、测试命令、电源策略恢复和客体关闭。
这证明自 UID 统计后端可用，不关闭仍缺策略变化验证的完整网络缺口。

API26 SDK 三 ABI typed HAP 编译记录为
`network-accounting-typed-{arm64,armv7a,x86_64}-r29-01`。
整仓主机回归 `host-regression-network-accounting-r29-02.log`：
1312 项通过，204.986 秒，macOS 跳过 1 项已另在 Docker 验证的 Linux
夹具。01 保留两处旧测试 fixture 缺新增 flag 的错误，02 只补 fixture
后重跑，没有降低权限断言。新测试尚未包含在冻结 R29 构建输入中，
上述 R28 验证也不替代 R29 首包门禁；完整账本仍为 149 闭环/132 未闭环。

后续统一套件和交付门禁已把 `network-accounting` 设为两个设备画像的必验项，
新增证据重放会重新验证原始数据、HTTP 三次交换、真实身份、编译输入和哈希，
不信任单独的 pass 字段。R28 原始证据重放通过，记录
`network-accounting-evidence-replay-r29-01.log`；整仓主机回归
`host-regression-network-gate-r29-01.log` 为 1320 项通过（204.350 秒，
同一 Linux 专用夹具在 macOS 跳过）。这些门禁更新没有改写冻结 R29 输入。

## 2026-10-10 NetManager eBPF 统计表只读诊断

新增 `build_bpf_netstats_readback.py` 和实际 C 调用者，固定读取
`/sys/fs/bpf/netsys/maps/app_uid_stats_map`，以 `BPF_F_RDONLY` 打开，
核验实际 HASH/8 字节 UID/32 字节计数 ABI，区分缺失 UID 和已有零值，
以十进制字符串保留完整 uint64 计数。不创建/修改 map、不挂载、不附加
程序或改变策略，也不将存在统计表等同于真实流量计数/公开 API 验收。

API26 SDK 三 ABI 编译记录 `bpf-netstats-readback-build-r29-01/build.json`；
ARM64 二进制 SHA-256
`8e1aceef3f8d2073472da1b34c35235c1b3919df3fd0e3476cd225dafa7e9576`。
Linux Docker 中直接包含实际 C 源码的 syscall 边界夹具验证只读打开、
错误 map ABI、缺失 UID、系统调用失败、参数溢出/非法 nonce、普通 UID
拒绝、uint64 无损输出、描述符关闭失败；不以夹具替代客体内核。
记录 `bpf-netstats-readback-host-r29-01.log`，可运行：

```sh
python3 -m unittest discover -s ci/capability-audit -p test_bpf_netstats_readback.py -v
```

整仓宿主测试 `host-regression-bpf-readback-r29-01.log`：1303 项，
254.595 秒，1 项 Linux 专用夹具在 macOS 跳过（已在上述 Docker 独立通过）。
R28 root/HDC 命名空间读回固定路径为 ENOENT；**这尚不能证明 netsysnative
服务未加载**，还需核对服务自己的挂载命名空间和实际流量。
这些诊断新增文件不在冻结 R29 中，不修改 R29 生产输入，不关闭网络统计缺口。

后续 R28 同归档的新 boot `23ba4969-4b60-4ed2-9e65-a9d8511d1743` 已确认
这确实是挂载命名空间差异：netsysnative（实际 UID 1098）自己的 bpffs/
cgroup2 挂载存在。只对独立的只读诊断子进程使用已有 `nsenter -m`，
不改变服务、init 配置或任何权限后，读到 map ID 2，UID 0 的计数为
Rx 209 包/28996 字节、Tx 159 包/34924 字节；实际进程退出 0。
root 观察者的同一路径仍为 ENOENT，两个事实不冲突。

`r28-netstats-readonly-runtime-02/boot/032-actual-netsys-mount-namespace.log`
SHA-256 `aecdc8dcd80aa367b1fe1166cbfc28e2d2755aeb7095541408762a5b1152ffa0`；
`033-service-namespace-map-readback.log` SHA-256
`3cc6413c86031a527663bc7a746286d5ebd125e4e76602846ed411fb2b366cb9`。
采集器新增同时记录观察者与服务挂载命名空间、真实服务身份、服务根目录下
的统计表路径；仅做只读观察，4 项采集器回归通过。该非零快照仍不代替
受控流量增量、公开 API 返回值、权限拒绝及策略变化的端到端验证。
命名空间采集修正后的整仓主机回归为 1304 项（220.141 秒，macOS 跳过
1 项已在 Docker 验证的 Linux 专用夹具），记录
`host-regression-netstats-namespace-r29-01.log`。

## 2026-10-10 R28 全套运行结果与 R29 单包构建

R28 独立完整运行已结束，实际归档 SHA-256
`9e7ee9bd842402265665793b1462d0ab174365a1d21d9caf617926a7b6e0efc9`，
boot ID `539fabbf-5840-460e-9284-9d2df5e5190b`。
`ohos-native-bindings` 的全部 32 个当前测试模块为 **102 pass / 0 fail**。
同包严格缺口账本为 **281 项应验、149 项闭环、132 项未闭环**；
完整门禁仍为失败，不能以 native-bindings 通过代替系统全部能力验收。
相较 R23 新闭环 CompletionHandler 导出、FA ErrorCode、温控真实读回与
回调、项目配额及普通应用存储计量；未闭环项不等同于全部尚未实现。

证据均位于 `validation/first-20261005/issue-20-20261006`：
`r28-independent-full-runtime-01.json` SHA-256
`a3121c31532b90849a74f22d70b62cb75b76e2bf9723a8e4a7fb752a85c8584f`；
`openharmony-qemu-arm64-arm64_virt-phone-runtime-49f7h05t/cxx-arkts11-gaps.json`
SHA-256 `0a2cac365fdc0de18883591fc7145a5100322c9fecd8aa82b9b39b566ec0d1b0`。
该次成功的普通运行/休眠测试不消除此前 R28 1920×1080 测试中唤醒约两秒后
重新进入 s2idle、HDC 连接失败的独立记录；仍需定位其根因。

R29 仅构建 ARM64 phone，包含 WPA 扫描/生命周期/软件 PNO/实时信道及
签名监管数据库修复。冻结目录 `build-inputs/phone-enur20`，源码提交
`963d0a7622834eab2ea4df0b4a53f5b2e4a7fedf`，输入树 SHA-256
`6a7f8b2046da8568d09044260be6626116e0df2da4e9ee20648f18e1bd926108`。
冻结主机测试 1302 项通过（217.116 秒）。计划产物目录
`packages/first-wpa-backend-7.0-release-20261010-r29`；
`after-build-r29-01.py` 仅等待这一包，随后核验真实 GN 宏选择、两轮无线
启停/普通应用扫描、1920×1080 模式切换及完整运行套件。
R29 于 16:28 CST 完成归档，路径
`/Volumes/PSSD/qemu/packages/first-wpa-backend-7.0-release-20261010-r29/openharmony-qemu-arm64-arm64_virt-phone.tar.gz`，
SHA-256 `ab720999e6fc6224b88fd780654116b4043562a7eec12347238f2a85ee58c601`。
源码系统编译耗时 55 分 03 秒。真实 Ninja 编译命令核验 channel helper、
scan state machine 含 `WIFI_SOFTWARE_SCAN_BACKEND`，STA HAL 含
`HDI_WPA_INTERFACE_SUPPORT` 且不含 chip 分支；三份原始命令记录为
`r29-real-gn-{channels,pno,sta}-01.log`。单包 watcher 已开始从该归档启动
`run_wifi_scan_diagnostic.py`，使用 API26 Release SDK、macOS ARM64/HVF
和独占 HDC 连接；路径、命令和结果持续写入
`r29-build-then-validation-01.json` 及 `r29-wifi-runtime-01`。
**R29 实际扫描门禁失败；原因和修复候选见本文开头，其余五包未启动。**

## 2026-10-10 WPA 实时频段查询候选与可重复首包诊断

`wpa_scan` 第二份补丁补齐实际 GET_CAPABILITY freq 解析和 non-chip HAL
路由，依据 R27 原始读回格式，保留 B/G 去重、空模式块、DFS 分类和 NO_IR
监管限制；不把 6/60 GHz 混入 5 GHz。无效频段、错误/截断回复不覆盖原输出。
配套 `wpa_channels` 读取真实 WPA 信道表，失败清除旧表、拒绝空频段转成
全频扫描；getter 加锁前刷新，覆盖单例早于 WPA 启动及异步监管更新的情况。
原 chip 路由保留，未调整公开权限、国家码或内核监管检查。

`wpa-frequency-compile-r28-01.json` 为四个完整 TU × 三架构 12 个对象通过，
SHA-256 `6e16e29a24619e1d3aa1332c3c36f054c99f45ebd7d42ecaae24e6cba16f557d`。
`wpa-channels-compile-r28-02.json` 为刷新修复后的完整 TU、软件候选/原分支
× 三架构六个对象通过，SHA-256
`9cbad3b05baeb31a478fa1a2414e9ff876c36ff33565670775bdb603d5230326`。
后者宏为隔离候选，真实 GN 选择仍须在新包构建核验。实际补丁函数体的
ASan/UBSan 测试覆盖六类频段、重复、NO_IR/DFS、空表、错误回复、超长、
越界和失败后再次成功；不是射频、关联、后台 PNO 或 AP/P2P 验收。

普通应用 wifi-scan persona 新增实际 2.4/5 GHz 支持查询，仍只请求原有
GET_WIFI_INFO/SET_WIFI_INFO，不降低旧 scan 缺定位权限时应有的 201 拒绝。
`wifi-bands-typed-{arm64,armv7a,x86_64}-r28-02` 三 ABI API26 typed HAP
编译通过；01 保留命令 nonce 长度校验拒绝记录，没有跳过 nonce 检查。
`host-regression-wpa-frequencies-r28-02.log` 为 1301 项通过（200.281 秒）。

仓库新增 `run_wifi_scan_diagnostic.py`，用于后续冻结代表包：验证真实预装
监管文件哈希/加载路径、两轮启停、每轮普通应用真实频段和两次扫描回调、
只读 WPA 原始频率表、同一 boot ID 以及无线/电源状态恢复。该诊断明确
不关闭完整 WLAN，不替代受控 SSID、关联与传输、AP/P2P/PNO 的验证。
加入诊断后的整仓 `host-regression-wpa-frequencies-r28-03.log` 1302 项通过
（211.289 秒）。
这些修复均不在 R28 归档中，尚未启动其余五包。

## 2026-10-10 R28 温控首包与 WPA 信道表读回

R28 新包 `first-thermal-backend-7.0-release-20261010-r28/openharmony-qemu-arm64-arm64_virt-phone.tar.gz`
SHA-256 `9e7ee9bd842402265665793b1462d0ab174365a1d21d9caf617926a7b6e0efc9`，
使用冻结脚本 `phone-Z6yzih/ci/capability-audit/run_thermal_diagnostic.py`，
API26 Release SDK、macOS ARM64/HVF 和独立 HDC，实际启动
`0533fdb0-4283-433e-a1a3-b3fd668800be`。`r28-thermal-runtime-01/diagnostic.json`
记录命令、配置和普通应用证据：内核 battery 与 SA 3303 均读回 2600，
普通应用现代/旧接口各两代初始回调通过，恢复电源策略并关闭客体。
这是原归档的低温路径验证，不证明高温状态转换或完整首包门禁；后续屏幕和
完整回归仍需通过。R28 不含后续 Wi-Fi 修复，不能据此启动余下五包。

R27 原归档的独立启动 `1514f2e6-a01d-41d4-9f0c-14320d3ebe4c`，通过新增
只读 `wpa_frequency_readback.c` 查询真实 WPA `GET_CAPABILITY freq`，没有
替换镜像库或配置。结果 1184 字节，包含 B/G 重复、空 Mode[A] 块、
2.4/5 GHz、NO_IR 和 DFS 标记；当前实际结果可放入现有 2048 字节 HDI 缓冲区。
`r27-wpa-capabilities-runtime-01/actual-wpa-frequency-capabilities.txt` SHA-256
`a7ddc07a3719c7937b31dc1b6cc858872b52dd0b5e07e8445cb5940d72f0da5a`。
诊断已关闭客体并恢复电源策略；它不是普通应用扫描或 WLAN 验收。
`build_wpa_frequency_readback.py` 用固定 API26 Release SDK 重现三架构只读
调用者，`wpa-frequency-readback-build-r28-02/build.json` 保存输入和命令，
与实际运行的 01 构建逐字节一致。

同时确认内核启动报 regulatory.db 缺失。固定 manifest 的 unisoc 源码中
已有数据库与签名，二进制 CMS 校验通过；仍需校验签名者与内核内置信任键、
补齐打包及加载路径，并在新包验证。不得关闭签名检查、硬编码放开信道，
也不能把服务层国家码当作内核监管域已生效。

后续 `wlan_regulatory` 候选部件已接入公共构建：复用固定源树的数据库和
签名，验证固定哈希、二进制 CMS 及签名者 DER 与 Linux 6.6 内置 wens
证书完全一致，三架构继续强制签名校验。数据库安装在 system/lib/firmware，
独立 vendor pre-init 配置在 boot 加载 cfg80211 前选择该固件目录。
私有副本两次应用和损坏数据库拒绝检查通过，
`wlan-regulatory-check-r28-01/check.json` SHA-256
`523b16d6573dad2953ee6f8cd69f107aa1ffb995d89cc0d42e67c6fde5820df3`。
整仓宿主回归 `host-regression-regdb-r28-01.log` 1296 项通过（200.390 秒）。
尚未进入新包运行，不能据此关闭监管数据库或 WLAN 行为缺口。

R28 后续 1920×1080 检查在 UI 用例开始前失败：串口显示 GPIO 唤醒后约
2 秒又进入 s2idle，HDC reconnect 明确失败；独立 HDC 服务本身仍在运行。
保留 `r28-refresh-1920x1080-runtime-01/boot` 和专属 transport 证据，
没有忽略连接失败、循环保活或启动其余五包。正在独立诊断实际电源事件。

## 2026-10-10 扫描生命周期与软件 PNO 补充修复

扫描路由接通后的生命周期检查发现两个独立问题：ScanService 先注册回调，
再设置回调所用状态机指针；后续初始化失败会直接析构 ScanMonitor，原析构
不注销回调。新 `wpa_scan_lifecycle` 部件将指针设置移到注册前，析构时先
注销回调再销毁状态机；记录自身是否成功注册，防止失败初始化、重复 UnInit
或已退休对象析构时注销新对象的回调。未改变权限、公开 API 或消息队列协议。

真实补丁 ScanMonitor 方法的隔离宿主 fixture 覆盖立即到达事件、注册失败、
无显式 UnInit 的销毁、重复注销、旧对象不影响新对象，以及 100 轮创建/销毁；
ASan/UBSan 通过。`wpa-scan-monitor-boundaries-r28-02.json` SHA-256
`83b0b4a4b38d4f0e20b9ef582b5c2e45ba5c4bc88db3472be1f83a3aa5ba097b`。
两个实际完整 TU × 三架构编译通过，`wpa-scan-lifecycle-compile-r28-02.json`
SHA-256 `a973c845657b063f5fabf82700ac3694c926e17952290a30e5a20c9d7c2aad1b`。
01 曾被候选头文件依赖检查拒绝：未修改的 scan_service.h 用引号包含同目录
旧 scan_monitor.h，普通 -I 无法覆盖。现用精确 Clang VFS 文件映射，六个
对象均确认实际消费补丁头文件；没有放宽依赖断言或把旧布局算作通过。
整仓 `host-regression-wpa-lifecycle-r28-01.log` 1290 项通过（204.089 秒）。

另确认默认配置 `supportHwPnoFlag=true` 会选中 QEMU 没有的芯片 PNO 卸载，
WPA HDI 本身没有对应卸载实现。`wpa_software_pno` 在关闭 chip HDI 的标准
产品选择已有的定时软件 PNO 状态机；芯片产品继续遵循原配置。软件扫描仍
经过真实 WPA/内核扫描及结果查询，不伪造结果，也不声称硬件节能卸载可用。
`wpa-software-pno-compile-r28-01.json` 记录三架构、软件候选/原分支共六个
完整 TU 编译，SHA-256 `5e6594d6af45fca42713999c83efb8b5a07c1778ee39fe13e2d0b1f9da622e3b`。
软件分支为显式隔离候选宏，**尚不证明新包真实 GN 选择或后台扫描行为**；
需要下一代表包核验宏、保存网络后的周期扫描/重连、停止与失败分支。
`host-regression-wpa-pno-r28-01.log` 整仓 1293 项通过（208.558 秒），含
软件分支不读取硬件配置、原分支保持 true/false 配置的 ASan/UBSan 检查。

三个独立 Wi-Fi 部件都已接入公共打包脚本，但都不在仍在构建的 R28 冻结包内。
进一步源码检查仍有未闭环项：非 chip 的信道表查询为空，会影响分频段扫描；
非默认扫描调度样式、关联与数据链路、AP/P2P 仍待适配/实测。不能用开关、
空列表、软件候选编译或上述宿主生命周期检查关闭完整 WLAN 缺口。

## 2026-10-10 Wi-Fi：真实 WPA 启动后，扫描服务仍被芯片条件编译截断

R27 原归档的新启动 `e9f08aa5-4cab-4567-9c25-e1421d6c02af` 使用预装
`svc wifi enable/disable`：SA 1120 从 inactive 变为 activated，再回到 inactive；
真实 `wpa_host` / nl80211 初始化成功。但 `RegisterSupplicantEventCallback`
只在 `HDI_CHIP_INTERFACE_SUPPORT` 下注册，QEMU 实际配置关闭 chip HDI、
启用 WPA HDI，因此 `ScanMonitor` 注册失败、扫描服务初始化失败。
`WifiStaHalInterface::Scan/QueryScanInfos` 也只有 chip 路径。
不能将开关命令成功或“activated”作为扫描、连接、AP/P2P 已可用的证据。

证据 `r27-wlan-service-runtime-01/diagnostic.json` SHA-256
`d29062020450d27e940cfd41ff70587dc71f468a2c0dff7d35591d837e8bf5da`；
实际 hilog SHA-256 `7bcfa9833cdbd0d3f548c6421b53d0966956a6e5c9192ef1dc889224794b50c7`。
测试未替换客体库、配置或内核；恢复电源策略后关闭客体及专属 HDC。
镜像没有 `ip` 命令，相关 shell 输出不能作为 link 状态读回，后续改用 sysfs。

独立候选部件 `common/foundation/communication/wifi/wpa_scan` 固定 Wi-Fi
`367605c52dfaf5f09bd690f16d9ee9a301cfc98a`，保留 chip 路由，补 non-chip
WPA 扫描/结果路由及回调注册。WPA 完成回调改用已有同步派发方法，与注销
共享锁，避免直接读取可并发清空的回调引用。扫描参数经有界十进制频率和
十六进制 SSID 编码送入现有 `GetWpaStaData` 请求/回复通道；不把不支持
SCAN 的 `STA_SHELL` 当通用执行器，不忽略 HDI 失败或 WPA `FAIL-BUSY`。
现阶段非默认扫描调度样式明确返回 NOT_SUPPORT，不能据此关闭低功耗/PNO
或完整 WLAN 缺口。接口名必须匹配实际主 STA，不能默默扫描另一网卡。

四个宿主单元检查通过，包含真实补丁函数体的 ASan/UBSan 参数/回复边界。
`wpa-callback-boundaries-r28-02.json` 的四种宏配置及注销并发检查通过，
SHA-256 `293ddd7e26b2df18d637062b62856889186bd4e87d437609ad7cbfa3624dff6b`。
它们使用明确隔离的宿主 fixture，不是 HDI IPC 或客体行为验收。
`wpa-scan-compile-r28-04.json` 记录三架构四个完整 TU、共 12 个对象编译通过，
均核验真实产品启用 WPA、未启用 chip。生成头文件由各产品真实 HDI action
在私有目录生成；不改正在构建的源卷，也不借用其他架构的生成头文件。
01 保留缺失生成头文件、02 保留历史构建绝对根目录不匹配、03 保留候选
验证脚本变更触发完整性拒绝的记录；04 使用稳定输入重新执行全部检查。
独立部件已接入公共打包脚本，适用于两个画像、三个架构。
普通应用新增 `wifi-scan` 诊断 persona，仅申请 GET_WIFI_INFO/SET_WIFI_INFO，
要求实际启用状态、缺少定位权限时旧 scan 的数字 201 拒绝、两次真实扫描
完成回调及注销后无回调；不修改服务状态或代授权限。
`wifi-scan-typed-{arm64,armv7a,x86_64}-r28-01` 的 API26 typed HAP 均编译通过。
六项 verifier/构建权限边界检查明确拒绝旧 nonce、字符串错误码、回调失败、
重复/漏行及特权调用者。空列表与非空数量均不证明目标 SSID、关联或 AP/P2P；
该诊断的 `closed` 始终为空，尚未运行新包实测，也未纳入完整 WLAN 闭环。
整仓宿主回归 `host-regression-wpa-r28-03.log` 为 1287 项通过（201.057 秒）。
02 保留新增 persona 后两处旧测试 namespace 缺新 flag 的失败；只补 fixture
默认 false，仍保留纯调用者零权限断言，并新增 Wi-Fi 的精确两权限断言。
此候选不在 R28 冻结构建中，仍需新包的真实扫描结果、关联/数据传输及
权限/重复开关验证；没有减少完整缺口计数，余下五包尚未启动。

## 2026-10-10 图片元数据：真实读取成功，但错误类型仍不符合 SDK

R27 原始归档的新启动 `1e80acc1-66c6-4531-aba8-b1ba6d4ddee6`，普通 UID
`20010038` 使用 API26 typed HAP 读取固定 image_framework
`711db218c8d1c4d6546b28d8cf466059644dfa77` 的三份原始测试资源。
DNG 返回版本 `[1,4,0,0]` 和 fixture 模型 `FakeCamera ModelX`；TIFF 返回
实际压缩/色彩/方向/分辨率；AVIS 返回 90 帧及首、中、末帧 100 ms 延时。
它们是解析固定文件的工厂结果，不是伪造公有构造类或物理相机数据。

严格诊断仍然失败：负索引和边界索引抛出 `code: "7700204"` 字符串，
而公开 `BusinessError.code` 声明是 number。探针没有 Number/parseInt 转换，
失败后再次读取仍成功。直接原因是 `ReadImageMetadataByType` 参数失败分支
调用 `ThrowExceptionError` 时沿用 `codeAsNumber=false`，进入 `napi_throw_error`；
同一工具已有数值 BusinessError 路径。尚未修改该公开绑定；按框架维护规则
请求仅此参数分支的最小类型修复，保留数值、解析器和其他 API。

`r27-image-metadata-runtime-01` / `diagnostic.json` SHA-256
`22a7d74e1e6aaa266345aae0232b919f468afcb36845643a782dbaf173218fca`；
原始 results SHA-256 `88dc9eb06c157e684ca47c6cdaa31b20f4e0ef24de90130eb186b6e2786e1f57`。
客体使用 R27 冻结启动 helper，新增 caller 单独标识，原镜像未替换文件；
电源策略已恢复、客体与专属 HDC 已关闭。不关闭三项 metadata 缺口，不纳入
R28 冻结套件，也不声称完整图片格式/XTS/硬件验证。新增探针的三个 ABI
typed HAP 编译通过，记录在 `image-metadata-typed*-build-r28-01.log`。
完整宿主回归 1277 项通过（208.590 秒），见
`host-regression-image-metadata-r28-02.log`。01 保留新模式缺参数检查先于
互斥检查导致的单项失败；只调整检查顺序，未修改测试断言。
XTS 已定位 `test/xts/acts` 固定 `12ed38d7aec9c680ed1510a77a96efcc7b101489`
的 `image_exif_get_modify_hap` / `ActsImageExifGetModifyTest`，其中
`SUB_MULTIMEDIA_IMAGE_READIMAGEMETADATABYTYPE_PROMISE_ERROR_0100/0200`
覆盖负索引/越界，但 `handleError` 使用 `==`，不能发现字符串与数字差异。
尚未执行该完整 XTS HAP；本仓测试明确拒绝字符串错误码及隐式类型转换。

## 2026-10-10 R28：重建温控代表包，尚未完成客体验收

仅构建 ARM64 phone，输入提交 `31ed764`，冻结目录
`/Volumes/PSSD/qemu/build-inputs/phone-Z6yzih`，树 SHA-256
`b230fd3d21b99787f0f584c632ca6d7a0c83cb92869fda88134bc98f766c8299`。
本地容器 `6e14d2afd4261c5c88c4be8f37e4017ee078e45ded9c1e1e7986a49da354c978`，
产物目标目录 `first-thermal-backend-7.0-release-20261010-r28`；
7.0 Release manifest、M144 依赖版本与源卷不变。
正常部件脚本已将 thermal XML 精确升级为
`31231293c6e337a0e2942584742d1808acae66e2f97c8289ae4e265432d833a8`，
无客体临时配置或库替换。构建日志 `first-thermal-backend-arm64-phone-build-r28-01.log`。

`host-regression-r28-frozen-03.log` 记录冻结输入 1271 项检查通过（202.369 秒）。
此前 frozen-01 使用了 macOS 不支持的 C.UTF-8 以及较旧的系统 clang，
frozen-02 仅纠正 locale，故都保留为环境错误失败记录；03 明确使用
`LC_ALL=LC_CTYPE=LANG=en_US.UTF-8`、`/opt/homebrew/opt/llvm/bin` 优先的 PATH，
没有删除测试或放宽断言。旧的两名等待器仅停止其 docker wait 客户端，不中断构建。
有效等待器 `after-build-r28-03.py` / `r28-build-then-validation-03.json` 只处理
上述精确容器和单一代表包，依次运行专属 HDC 下的温控新包诊断、1920×1080
真实模式切换、完整统一套件；失败则保留证据，不启动余下五包。

另清理两份已关闭 R27 构造类/配额诊断的展开 images，回收 10076704768 字节；
原归档与全部证据保留，见 `retired-diagnostic-images-cleanup-r28-01.json`。

## 2026-10-10 R27 完整回归中断：宿主 HDC 握手，不是枚举结果

同一 R27 原始归档的完整启动 `f6a9d000-59c4-4b3f-9af8-2a9a7a913e7f`
在 `ordinary-const-enum` 的首条身份命令中得到 stderr `Connect server failed`，
HDC 却返回 0。原始日志 SHA-256
`239db9cb0f1555fed2e9ec0672eb764d0514d2c8af1804f8d462c6d782f5e360`。
枚举 HAP 尚未编译或执行，不能认定枚举失败，也不能将部分成功当作完整验收。
套件已恢复电源策略并关闭客体；完整缺口统计仍为上次 R23，未合并不同启动结果。

固定源码 `developtools/hdc/src/host/client.cpp` 的 `CommandWorker` 在等待
host server handshake 超时后打印该错误；这不证明客体接口失败，也尚不能证明
宿主为何短时未响应。现修正 boot/ordinary runner 对 stdout 与 stderr 的错误检测，
不会重试应用命令或忽略失败。统一 `validate_packaged_qemu.sh` 改用专属前台
HDC：随机回环端口及独立 TMPDIR（HDC 单实例 PID 锁不随端口变化），继承到
整个套件；只关闭自己创建的进程，不重启共享服务器。保留 `.hdc/transport.json`、
服务日志和私有临时目录用于诊断，记录与客体能力证明分开。

`owned-hdc-smoke-r28-01`、`owned-hdc-stress-r28-01` 实际执行 SDK HDC，
100 次四并发连接通过；`owned-hdc-child-failure-r28-01` 保留真实子进程退出 7，
均确认专属服务关闭。11 项宿主边界检查覆盖 stderr/退出 0、未知锁归属、
失败传递和只清理自有进程。它们仅证明测试连接隔离实现，不替代新包完整回归。

## 2026-10-10 温控实测发现配置错配，待下一代表包验证

R26 原始归档 SHA-256 `f21bb14194ae781485780b4722a9e613261e524c142bab02c7326bdd4d5be8fd`
的新启动 `515bc728-36ef-4112-a82e-092ca1b16df0` 实测发现：内核
`thermal_zone0` 的类型为 `battery`、原始读数 `2600`；打包 HDI 配置却查找
`test_battery`，`hidumper -s 3303 -a "-t"` 没有任何温度记录。因此该缺口
仍是真实故障，不能以 `thermal.getLevel()` 返回 0 判定通过。
`r26-thermal-readonly-runtime-04` 使用 R26 冻结启动 helper 和原始镜像，
无客体库或内核替换；真实桌面解锁后才设置本测试的有限超时，最后恢复并关闭。
诊断 SHA-256 `990bd302be842ab061b466583d5dd0feaa4f9d3343a25f1f68004de771e475dd`；
内核观察 `c6bc911cc3f5befbdab6b225bb4b8f426edb91f95a5d33dc85a1b3f55f37f090`；
服务观察 `b954cea97b478a319f9bcac70ef45ffef261930d9dcd552c27d5c240f4f21f51`。

三个架构的实际 kernel 构建树均由共同 `power.patch` 将供应器和温度区改名为
`battery`，见 `thermal-three-kernel-source-names-r27-01.log`。新增独立
`qemu_backend/0003-match-the-packaged-kernel-battery-zone.patch` 与精确旧状态升级；
只改 HDI 对真实节点的匹配，不模拟读数、不改阈值或权限。
`thermal-backend-exact-r27-01.json` 的七次应用/升级/幂等/未知改动/部分状态/
符号链接边界检查通过；这是只读源码加私有 scratch 验证，不是新包运行证明。

新增公开 SDK 编译的普通应用探针，要求两轮新回调及两轮旧回调的真实首次通知、
退订回调、可选 undefined、旧订阅不再回调和等级一致。单独的回调成功仍不关闭
缺口：统一 suite/交付门禁还必须重放同次启动前后的非零内核/服务读数、
实际配置、普通 UID、签名 HAP、SDK/源码输入、随机挑战和全部原始文件哈希。
只允许关闭 `behavior:thermal-backend-zero-data`，不声称高温状态转换或真实物理温度。
API26 Release SDK 实际编译通过；旧包在后端读回阶段失败，未执行这些应用回调。
新增 18 项温控解析/门禁/关闭边界检查通过，完整宿主回归 1260 项通过，
记录于 `host-regression-thermal-gate-r27-03.log`；均不替代新镜像测试。
本修复及新增门禁不在已经冻结的 R27 输入中，必须重建代表包后验证。

初次诊断 01 被 frozen-input 校验拒绝；02 因锁屏持有超时策略主动拒绝，
03 被桌面测试的非 acceptance 启动检查拒绝，均保留失败记录而未放宽门禁。
01–03 的关闭/未启动临时 images 已清理，归档和所有证据保留，
详见 `retired-thermal-images-cleanup-r26-01.json`。

## 2026-10-10 R27：截图预算及回调类首包已打包，运行验证中

仍仅 ARM64 phone。输入冻结为 `ac556ca`、目录
`/Volumes/PSSD/qemu/build-inputs/phone-9WIVCw`，树 SHA-256
`ec212de64a68e4b5fa1d827f19f6f142d554e8f3af4017ec6292199d4346cfdd`。
本地 Docker 容器
`d7ccefaa1d685a17480b76281dfb4d3dad8003e336b87ceee4d502250126ce1e`，
目标目录 `first-capture-completion-7.0-release-20261010-r27`。
固定 7.0 Release manifest 和依赖不变，先应用全部部件补丁再执行配置遍历；
实际日志已确认 `capture_budget` 与 `completion_handler` 整体精确状态通过。
冻结输入的 1242 项宿主检查通过（`host-regression-r27-frozen-01.log`）。
本地编译成功，编译阶段耗时 46 分 53 秒；容器退出 0，归档完成：
`/Volumes/PSSD/qemu/packages/first-capture-completion-7.0-release-20261010-r27/openharmony-qemu-arm64-arm64_virt-phone.tar.gz`，
SHA-256 `ea64ca3c5ed95a705f343ae33809238f20e5c88bd248e20ce9fb896da0edcd62`。
离线最终镜像完整 Native 缺口 ABI 检查、画像和权限装配检查通过；
实际 GN 已选择 `WM_QEMU_SOFTWARE_CAPTURE` 并链接 `libscreen_session_manager.z.so`，
实际只读 screen caller 也已编译通过。现开始新归档运行验证，不声明行为修复通过。
温控修复不在此归档内，仍须下一代表包；不能把 R27 当作最终交付包。

同一 R27 归档的两次独立新启动已通过显示窄诊断：1280×800 boot
`fcb60270-1a5a-4114-b8b6-0557abc5f38b`、1920×1080 boot
`de14d38f-04fe-4328-9c54-4e9f5c09b968`。后者首次桌面截图成功，实际
Settings UI 选择刷新率后，内核 DRM CRTC 33 / connector 34 读回
75 Hz → 50 Hz → 75 Hz（像素时钟 217140 → 148500 → 217140 kHz），
不是只检查 DMS 缓存；普通应用直接设置的 202 拒绝与返回也通过。
前者只有真实 75 Hz 选项，不声称完成切换。两份 `diagnostic.json` SHA-256
分别 `14b23fb3abd090d071c61744e52d24dd01d2e78a4448e04ab34ec2200f5556a6`、
`9aa07ac60c243d5888f0a358f2e23094bbef305a55c1409cfb8e6227b7634ac7`。

`r27-completion-handler-runtime-01` 新 boot
`9e3449cc-fb11-4c85-acfa-3ce8c4ce9705` 的真实普通 UID `20010038`
通过 API26 typed HAP 构造/字段契约：8 条有序观察、67 个实例，覆盖可选字段、
回调参数、隔离、清空、继承与既有错误码。它证明旧包缺失的命名类现在可用，
不证明组件启动服务回调或 IPC。诊断 SHA-256
`76d35bc24ce14f36b156740a63d949647fa4b7115ec7c3e4650262c29435d2bb`。
以上三个测试均恢复原电源策略并关闭客体；仍不是同次启动完整总门禁。
两份显示诊断与 R26 thermal-04 的临时 images 已清理，原始归档、截图和所有
证据保留，可重新解包；回收 15112335360 字节，见
`retired-diagnostic-images-cleanup-r27-01.json`。

`first-capture-completion-arm64-phone-build-r27-01.log` 记录构建；
`r27-build-then-validation-01.json` 的等待器只在精确容器退出 0、归档完成及
空间检查通过后，顺序执行该归档的 1280×800、1920×1080 实际模式切换、
普通 ArkTS 构造类、无能力项目配额和完整回归。构造类窄诊断也只使用冻结
脚本，完整 suite 另在同一次启动执行 Storage 和该类的原始证据强制校验。
任何失败即保留失败并停止该序列，不启动其他五个产物。

## 2026-10-10 R26 代表包：低分辨率验证通过，高分辨率首次截图失败

仅启动 ARM64 phone，输入冻结为提交 `c9de875`、目录
`/Volumes/PSSD/qemu/build-inputs/phone-9x1nCX`，树
`cb28e1fb7f7683fd5b69a4751ceca390a897477377846a5006214997d203b5ca`。
本地 Docker 容器 ID
`d5fec5c264876954d078359d225485bb6eb0b96f74dec2f9e44e6b62b14e17ce`，
目标目录 `first-display-modes-7.0-release-20261010-r26`；本地容器正常退出 0，
归档 `openharmony-qemu-arm64-arm64_virt-phone.tar.gz` 已完成，SHA-256：
`f21bb14194ae781485780b4722a9e613261e524c142bab02c7326bdd4d5be8fd`。
只读模式探针编译通过。1280×800 新 boot
`f2f26b46-5fe5-4d72-a69f-ee481810ac9d` 的 Settings 页面、26 个真实模式、
内核 75 Hz 读回、普通应用 202 拒绝与返回验证通过；该分辨率没有真实备用
刷新率，因此不声明切换成功。1920×1080 新 boot
`7bbd61cb-5759-4065-910d-f17d7508621c` 在首次桌面截图明确返回
`Failed to get display pixelMap`，尚未进入刷新率切换。两个客体均已关闭。
等待器保持 fail，未执行后续配额和完整回归；显示模式切换方向仍须新包验证，
不能把低分辨率成功或归档生成作为首包总门禁通过。
构建与顺序验证记录位于既有 evidence 根目录的
`first-display-modes-arm64-phone-build-r26-01.log`、
`r26-build-then-validation-01.json`。冻结版本宿主 1208 项检查通过。
等待器仅验证该包：1280×800 页面、1920×1080 切换及真实内核 DRM 读回、
无能力子进程项目配额、完整回归；失败即停止，不启动其余五包。

当前工作树另将 `storage-stats` 纳入两个画像的统一 suite 和强制交付门禁，
重放原始文件增长/回收、202 拒绝、普通 UID、编译输入及逐文件哈希。
该新增门禁不在已冻结 R26 输入中，不能把 R26 等待器的结果解释为已经执行它；
需用对应最终冻结脚本重新验证。13 项 Storage 宿主边界检查通过，均非客体证据。
完整回归 `host-regression-storage-gate-r26-02.log` 首次因两处写死旧 persona
列表的测试断言失败；补上 Storage 列表项后，`-03.log` 的 1215 项全部通过，
没有改动原有行为断言或覆盖失败记录。
R25 独立截图耗时采样 6 次均成功（约 0.27–0.75 秒），但只说明部分调用正常，
此前首次截图超时依然未关闭，不能以重试成功代替修复。

后续工作树也将 `project-quota` 纳入两个画像的统一 suite 和强制交付门禁：
使用实际架构 SDK 编译探针，只接受有完整归档清单、真实宿主 QEMU 进程和
boot ID 绑定的临时客体；读取 `/proc/mounts` 验证安全挂载及三类 quota，
验证实际进程退出码、无能力写入 EDQUOT、恢复与清理。该项与普通 Storage
同一次启动执行，但各自仍返回 `closed: []`，不冒充所有特权 Storage API。
`host-regression-quota-gate-r26-04.log` 1219 项通过；新增入口本身尚待客体实测，
同样不属于已冻结的 R26 构建输入。R25 已关闭的 quota-04、storage-02、
1280×800 refresh-01 展开 images 已移除，回收 15,113,461,760 字节；
保留原始归档、manifest、截图、探针和全部证明，临时 userdata 不保留，
详见 `retired-positive-images-cleanup-r25-03.json`。

新增入口在 R25 的同一新启动 `d74fc16a-c339-49e1-b3dd-f44f2cb81601`
实测通过：`r25-storage-quota-unified-runtime-03` 保留内核真实 EDQUOT/恢复、
普通应用两轮文件统计/回收与 202 拒绝；电源策略恢复、客体关闭。
外层复用冻结启动 helper 时导入缓存仍是旧门禁，故另外用独立新进程执行
当前严格门禁，`strict-current-gate-replay.json` 通过；不把旧 helper 的泛化
状态检查当作当前门禁。新关闭规则同时重放两类原始证据、绑定实际编译的
无能力配额探针、ABI/归档/boot，才关闭 `behavior:storage-quota-not-mounted`。
窄诊断的 `quota-only-gap-closure.json` 仅关闭这一项，其余 280 项没有在这次
窄诊断中运行，因此报告整体仍失败，不与 R23 不同 boot 的结果拼接成全量成功。
新增 5 项关闭规则边界独立通过，完整 1224 项回归通过；独立运行测试时补充
显式 scripts 搜索路径，避免依赖其他测试导入顺序，修正后单独 5 项通过。

截图只读异步探针由真实产品头文件/库编译，位于
`capture-latency-r26-01`；只传输可执行文件，不替换系统库。
`r25-direct-capture-latency-runtime-01` 新启动
`f8d6d4d5-fb33-4732-8375-e6cd3724e2b9` 的 1920×1080 首次回调 1,958,803 微秒，
后续五次约 117–119 毫秒，均得到真实尺寸像素图；同期有 R26 构建和宿主检查，
不是空载性能基准。该结果显示冷调用接近 2 秒上限，但仍不证明历史超时已修复，
报告保持 `observations_collected_NOT_pass`，继续独立新启动复测。

后续独立启动保留所有失败：`r25-direct-capture-latency-runtime-02` 被默认
10 秒电源休眠中断，不能推断回调丢失；`-03` 恢复有限测试电源策略后首回调
525,039 微秒。`-04` 启动真实 Settings 后三个公共 DMS 截图均约 2.08 秒失败，
晚到 PixelMap 日志约在请求后 3.53/2.75 秒出现；后续暖调用成功没有覆盖失败。
`-05` 原始 hilog 含非法 UTF-8 导致诊断收集器失败，未执行后续公共截图。
`-06` 改为按原始字节保存日志，新 boot
`27569011-9a3f-4d33-9ae7-18cb21e3919f` 的真实异步 RS 回调实测
4,489,856 微秒、单次回调且真实 1920×1080 像素图，明确超过 DMS 2 秒预算。
两者均为原始 R25 库，不替换系统库、不改变异步协议，报告仍是观察而非修复通过。

因此另准备 `window_manager/capture_budget` 候选，仅三个 QEMU 产品设置
有界 10 秒预算，硬件产品保持 2 秒，不重试、不绕过权限、不接受空图。
实际 Future/DropLock 的延迟、空值、错误、HDR、释放全局锁及有限超时边界，
真实 GN 条件的三个 QEMU/三个非 QEMU 选择，以及补丁状态保护检查已通过。
记录 `screen-capture-budget-r26-01.3FFokm/boundaries-01.json`；这些宿主检查
不代表 IPC/新包通过。首次三架构编译在 ARMv7a 的旧
`/openharmony` 绝对路径处失败，保留失败输出；改用双只读路径挂载继续检查，
不更改现有源码/out，也不通过伪造生成头文件规避错误。
第二次在 x86_64 的另一原始路径处失败；按各架构原始路径分别只读挂载后，
`armv7a-compile-03.json` 与 `arm64-x86-compile-03.json` 三个完整 DMS
源文件编译全部通过，实际生成缺失 IDL 头而非替身。1224 项宿主回归通过
（`host-regression-capture-budget-r26-06.log`）。随后接入两个画像的共同
打包前补丁序列，不改变已经冻结的 R26；仍需下一版新归档冷启动验证，
不能把三架构对象编译或现有归档暖调用成功算作新包修复完成。
接入后 `host-regression-capture-wired-r26-07.log` 的 1225 项检查全部通过。

已关闭的 latency-01/02、同 boot Storage/quota-03 展开 images，以及
latency-03/04/05 展开 images 分两批删除，保留归档、日志、探针和全部证明。
记录 `retired-latency-images-cleanup-r25-04.json`、`-05.json`；临时 userdata
不保留，基础 images 可从原归档恢复。其余五包仍未启动。

### CompletionHandler 命名类导出

已确认 `@ohos.app.ability.CompletionHandlerForAbilityStartCallback` 的 SDK
公开类缺失：固定源码模块只注册 `AbilityStartFailureCode`。候选补齐真实
NAPI 构造函数，两个可选回调保持普通实例字段，不引入原生所有权或服务身份；
不改变已有枚举、启动/生命周期、权限和 IPC。已阅读 ability_runtime 的
AGENTS/CLAUDE、公共错误码边界和模块注册/现有回调消费实现，修改范围仅为
该缺失绑定。`JsUIExtensionCallback` 仍按原有字段读取两个回调。

证据目录 `completion-handler-r26-01.1hYP0l`：三个实际产品完整模块源文件
编译通过（`three-abi-compile-02.json`）；宿主真实 Node N-API 执行原样
构造函数，覆盖 new-only、可选字段、实例隔离、继承及 10,000 次分配/回收
（`host-napi-01.json`）；17 项宿主错误路径、原始结果、归档/boot/普通身份、
篡改拒绝及窄关闭规则检查通过（`host-boundaries-03.log`）。首次补丁 hunk
行数错误在应用前被拒绝，修正后重新检查；不作为生产源码编译错误隐藏。
`typed-caller-build-01.log` 记录真实 API26 Release ArkTS 调用者编译成功。

同一调用者在原 R25 新 boot `b0cddb51-fa5f-40e0-ac50-6c419d4ae363`
复现真实导入失败：普通 UID 20010038 的应用崩溃记录明确指出请求模块没有
`CompletionHandlerForAbilityStartCallback` 命名导出。记录位于
`r25-completion-handler-baseline-01/actual-own-app-jscrash.log`，没有替换系统库。
该失败保留，不把成功编译或宿主 Node 测试算作 ArkTS 客体通过。

工作树已将候选接入共同打包前补丁和两个画像的普通 HAP suite/强制门禁。
关闭规则只能在同一新归档、真实 acceptance boot、ABI、普通 UID 和实际
编译输入均匹配且原始八组观察重新校验通过时关闭这一项导出；明确不声明
真实组件启动回调送达或服务 IPC 已由该构造测试证明。当前冻结 R26 不含该
候选，下一代表包仍须真实启动验证；其余五包不能提前开始。
最终补丁上下文整理后 `three-abi-compile-03.json` 再次三架构通过，生成源码
SHA-256 不变；`host-regression-completion-final-r26-09.log` 1242 项全部通过。
旧包基线诊断最终保持 fail（未完成应用观察），其真实缺失导出崩溃单独留存
并绑定 `missing-export-proof.json`；测试电源策略恢复、客体关闭。
latency-06 与该基线已关闭的展开 images 回收约 9.96 GB，基础镜像仍可从
原 R25 归档恢复，临时 userdata 丢弃，其余证据不删；记录
`retired-diagnostics-images-cleanup-r25-06.json`。

## 2026-10-10 R25 代表包与 AppMgr 登记顺序候选

仅 ARM64 phone 代表包已完成本地 Docker 构建与打包，冻结提交 `3824311`，输入
`/Volumes/PSSD/qemu/build-inputs/phone-ILPEK6`，树
`51d2d9e41864dd855e5680c8ac9c8f948f4de593ea0a5d17805f6c1c09fdb64b`。
目标归档：
`/Volumes/PSSD/qemu/packages/first-refresh-quota-7.0-release-20261010-r25/openharmony-qemu-arm64-arm64_virt-phone.tar.gz`。
构建容器与等待命令均正常退出 0，归档 SHA-256：
`297c213658bc270cc55f3f40251ab092b150fd24f09102a55b86cea7774e8895`。
新归档的独立内核配额与普通应用存储统计实测通过（详见下文），
1280×800 Settings 刷新率页面通过，但 1920×1080 截图/模式切换失败；
完整行为门禁未通过，其余五包未开始。
该冻结输入包含 Settings 动态页面/模式索引与 F2FS 项目配额修复，
**不包含**本节后述的 AppMgr 候选。

自动验证记录 `r25-build-then-validation-02.json`：等待精确构建容器退出，
再执行独立新包配额、1280×800 与 1920×1080 刷新率 UI 诊断，全部通过后
才执行同归档完整回归。原等待器在产包前因选错不含 Pillow 的宿主 Python
被替换；保留 `r25-build-then-validation.json` 的 superseded 原因，不伪造测试
结果。新等待器使用已验证 Pillow 12.3.0 的现有虚拟环境。

等待器实际停止在 `r25-quota-runtime-01` 的失败，未执行后续测试，也未覆盖为成功。
`-02` 增加失败阶段，`-03` 确认测试子进程 UID 已为 65534，但 effective/permitted
仍为 `1ff:ffffffff`：OHOS init 的 securebits 保留能力，旧测试错误假设 setuid
自动清空。仅修改一次性测试子进程，显式 capset 清空后 capget 检查三组能力，
同时核验 UID/GID/补充组；不改 init/HDC 权限，也不放宽限额断言。
`r25-quota-runtime-04` 在同一新归档的独立 boot
`4dbeab46-9d41-479d-8b14-6363ac8010f1`（macOS ARM64/HVF、phone）通过：
真实限额 2,097,152 字节、无特权 EDQUOT、删除回收、恢复不限额后统计
4,198,400 字节（4 MiB 文件及目录），清理通过；探针 SHA-256
`f4b94736cfd6193d4f74234f94312280ad562a3d6cfb33ce7071021150731fca`。
三 ABI 探针编译及配额宿主 10 项检查通过，后续仅补充诊断变量初始化，
不将该窄项视为普通 Storage API 或完整缺口闭环。所有命令、实际挂载、
归档/探针校验和与环境保存在上述 diagnostic.json 及构建报告。
失败客体 01–03 已停止，其展开 `images` 删除回收约 14 GiB；原归档、
日志和报告保留，临时 userdata 不保留，记录
`retired-quota-images-cleanup-r25-01.json`。
只读屏幕探针构建 `screen-modes-readback-build-r25-01` 通过。
`r25-refresh-1280x800-runtime-01`（boot `d122abc1-73d9-4868-860a-d3e15ac30e58`）
实际动态页面、75 Hz 选中状态、合成器截图、返回及 normal 调用者 202 通过。
该分辨率只有一个真实选项，不声称覆盖切换。

`r25-refresh-1920x1080-runtime-01` 在截图处失败，DMS 等待 RS 像素图 2000 ms
超时；`-02` 保持同样断言，仅增加关闭前延后采集，仍出现截图超时，并在页面
实际请求 50 Hz 后定位独立缺陷：JS 正确传入索引 12，RS 正确转换为模式 ID 13，
但 QEMU `DrmCrtc::SetActivieMode` 硬编码拒绝非 0，composer 报错，真实模式仍为
75 Hz。不把后续截图成功抹去首次超时；两次失败都保留，完整回归没有开始。
两客体均恢复电源设置并关闭。额外只读 DRM 采集尝试发生在客体退出之后，
返回 Device not found，不作为任何成功证据。

新增 `device/qemu/display_modes`，仅允许连接器公布的非负有效模式，拒绝溢出/
未知 ID；原子模式请求使用 RAII，分配/属性/blob/提交失败保留失败及重试状态。
接入下一代表包的统一预构建补丁阶段，**不在 R25 内，也尚无新包成功证据**。
`display-modes-r25-01/host-boundaries-03.log`：真实函数提取的 ASan/UBSan
300 次切换、重复设置、非法 ID、空对象与 7 类 DRM 失败边界通过，原版负对照
确认拒绝有效非零模式，正向/重复应用和未知/部分状态保留检查通过。
`three-abi-compile-03.json`：3 个完整生产 TU × 3 ABI 共 9 个对象通过；01/02
的缺失 HDI 头文件失败保留，使用各产品实际 GN IDL 命令在隔离目录生成，
没有替代声明、修改系统源码/out 或注入运行库。仍需新包 UI 与内核实际模式读回。
该补丁不修复独立截图超时。
补丁空白上下文格式整理后再次通过正反应用；三份最终生产文件 SHA-256
未改变。新增内核 DRM 读回要求：只有 active/enabled CRTC 及其连接器的实际
分辨率/刷新率与显示服务一致才接受页面状态，不把缓存模式 ID 变化视为硬件成功。
3 项解析器边界通过，实际 R25 `r25-drm-readback-runtime-01` 中读取的内核状态
也通过解析（1920×1080、75 Hz、217140 kHz）；该客体随后桌面截图再次超时，
整体诊断仍为失败，未执行延迟采样。`-02` 单独调查截图耗时，不改变截图超时、
权限或任何验收结果；原失败保留。清理三个已停止失败客体的展开 images
回收约 14 GiB，原归档/日志/报告保留，临时 userdata 删除，见
`retired-diagnostic-images-cleanup-r25-02.json`。

普通 Storage `r25-storage-stats-runtime-01` 被错误测试口径拒绝：固定 Installd
源码的 LOCAL 是 UID quota 总量，cache 单独统计为其子集，`dataSize` 不排除
cache；[官方 API 说明](https://developer.huawei.com/consumer/cn/doc/doccenter-capabilities/api/js-apis-file-storage-statistics)
也只排除安装文件。修正测试，要求 data 增长等于 data 文件加 cache 文件，
保留增长/回收上界；新增遗漏/双计缓存拒绝检查，6 项通过，不修改系统 API。
重新构建并在独立 boot `a9151c28-65b3-4400-9060-9735f575e757` 执行
`r25-storage-stats-runtime-02` 通过，两轮实际文件、Promise/callback、删除恢复
和普通应用跨 bundle 202 均验证。01 失败未覆盖；两个 runner 源码分别保存，
SHA-256 与各报告一致（第二次执行命令仍使用当时的 01 路径，执行源码归档为 02）。
这只是独立诊断，`closed` 仍为空，不放行完整矩阵。

截至加入显示驱动候选和 Storage 口径修正**之前**，完整宿主回归
`host-regression-r25-06.log`：1204 项通过（217.703 秒）。
随后 `host-regression-r25-07.log` 完整 1205 项通过（206.012 秒），新内核读回
检查在其后加入，并另跑屏幕与刷新率相邻检查；不把宿主通过当成新包通过。

新增 `render_attach_registration` **未接入打包的候选组件**：可信 PID 的绑定
查询等待 nwebspawn 返回与 RenderRecord 登记完成；timeout 先登记再允许绑定
取消，释放互斥锁后才进行 observer/renderer 回调，不变更 SDK、IPC、身份、
沙箱、权限或 UID 分配。源码可证明存在先绑定后登记的顺序缺陷，但不能据此
认定它就是 R23 间歇 Web 退出回调丢失的原因；原失败仍未关闭。

`render-registration-r25-01/host-order-check-06.log`：提取真实原版与候选关键
代码，ASan/UBSan 宿主调度替身各运行 400 个确定性竞争场景（成功/失败、
renderer/GPU），旧版丢失早到绑定、候选阻塞到登记完成；覆盖无 scheduler、
无 manager/app/record、无 event handler、无效 PID 与失败后锁释放，保留原版
完整 observer enqueue/timeout 尾部，确认旧版遗留超时与候选及时取消的区别。
正向及重复应用、未知修改和部分应用状态保留检查通过。补丁文件仅统一 diff
空行格式，最终两个生产源文件 SHA-256 与上述实际编译输入完全相同；格式整理
中的一次 hunk 计数错误在检查时被拒绝并修正，未进入系统源卷或构建。
这是关键区测试，**不是** FFRT/Binder/AppMgr 单测或新包 Web 通过证据。
实际三 ABI 完整 AppMgr TU 均编译通过，依赖文件确认实际消费候选头文件：
`two-arm-abi-compile-05.json`（ARM64/ARMv7，SHA-256
`0fce848329f5e516915ae610b4cb3c813668fcd04b3bb55b328e35f38a548f7a`）与
`x86-abi-compile-06.json`（x86_64，SHA-256
`0c7045f1e07a61462659913c383a48bf3efa0e28c2d2841b449e22da921a6193`）。
两份记录各自明确仅覆盖指定架构，不把任一单份视为三架构门禁。
此前 01–04 检查中的缺失生成文件、历史 GN 绝对路径与只读输入失败记录均保留。
未完成完整 libappms 链接、AppMgr 相关单测及新包客体回归，候选仍不接入打包。
检查中缺失的头文件由真实 IDL
生成器生成到独立目录。固定版本工具要求输入具备 W_OK，因此复制原始 IDL
及导入同目录声明到独立目录并记录哈希，不放开系统源卷写权限或编造头文件。

`host-regression-r25-02.log`：1197 项通过（326.458 秒）；后续新增 IDL 隔离
边界 2 项单独通过，随后 `host-regression-r25-03.log` 完整 1199 项通过
（342.320 秒）。为后续验证释放空间，仅删除 R23 完整重跑、R23 四十轮
Web 与 R24 刷新率失败这三个已停止客体的 `boot/extract/.../images`，约 14 GiB。
对应 R23/R24 原归档 SHA-256 重新核对一致，全部日志、报告、冻结输入保留；
原始镜像可从归档恢复，临时 userdata 改动不保留。清理记录
`retired-runtime-images-cleanup-r25-01.json`；复查依赖镜像的旧报告时须先恢复
对应原始文件，不将清理或重试当作新验收。

补充普通应用 `storage-stats` 诊断（不在 R25 冻结输入内，尚未新包运行）：
两轮实际私有 data/cache 文件写入、fsync、大小检查与删除，分别经 promise/
callback 查询公开 `getCurrentBundleStats`，核对增长/回收而不是零值成功；
同一无权限 normal 应用查询其他 bundle 必须保持 202，清理仅限 nonce 私有文件。
`storage-stats-hap-compile-r25-01` 已用真实 API 26 Release SDK 编译 unsigned HAP，
SHA-256 `fa6224e7668476157b892a8cb58f7ba70a4bbdcda961b75132d3d379c5285b44`；
5 项宿主校验边界通过。该诊断的 `closed` 明确为空，不凭编译或统计 API 窄项
代替内核限额执行、特权 Storage API 或完整缺口验收。
`host-regression-r25-04.log` 的两个失败是既有测试写死 persona 列表、遗漏新增
模式；补齐仍要求全部隔离/互斥成员的断言，保留失败记录。随后
`host-regression-r25-05.log` 完整 **1204 项通过（302.829 秒）**。

## 2026-10-10 R24 归档验证恢复

代表包已生成：
`/Volumes/PSSD/qemu/packages/first-screen-modes-7.0-release-20261010-r24/openharmony-qemu-arm64-arm64_virt-phone.tar.gz`。
SHA-256：`bb161601d6a033605a35580ae737d2a6e9c4228dd76d132732e06b69a917a369`。
`gzip -t` 通过，包内冻结输入树仍为
`c986d923040a75607e0e73c86988d496e4cc39eb0562096b678beed5fe5c8782`。
原宿主构建日志与等待器未记录最终退出状态，构建容器已移除，原等待器也不再运行；
不补造成功退出码。`recover-validation-r24-02.py` 从已有归档恢复校验，保留旧报告，
新证据写入 `r24-recovered-validation-02.json`，先执行真实屏幕读回及两种分辨率的
Settings UI 诊断，然后才运行同归档完整回归。归档存在/完整不等于首包行为门禁通过；
其余五包仍未启动。R24 不包含后续提交的项目配额修复。

R24 新包 `r24-refresh-1280x800-runtime-01` 未通过：普通调用者实际发送了
`screen_refresh_rate_entry`，Settings 尝试动态导入，但 HAP 的 ABC 中只有路径
字符串，没有新页面/控制器代码。根因是遗漏 phone 构建配置的
`arkOptions.runtimeOnly.sources`，而非导航调用成功就可视为页面已实现。
同时实际读回 26 种模式，`activeModeIndex=25` 对应数组第 26 项（ID 0，
1280×800/75 Hz），原候选及其宿主夹具错误地把索引当作模式 ID。按 SDK 与
真实 Screen 实现修正页面、原生读回校验、UI 驱动及宿主边界；新增稀疏/逆序
模式 ID 与旧候选精确升级测试。诊断失败后恢复电源策略并关闭客体，未继续
1920×1080、完整回归或剩余五包。保留失败证据，不覆盖为成功。

修正后的独立 Settings HAP 编译使用只读系统源码副本，冻结输入
`settings-refresh-candidate-inputs-r25-01`，树
`e4b1bc582c094c8246f4fd6127cfb2fdd1c475ce2c9b1b579d161f10dd2d1cec`。
系统源码/out 和 R24 归档未修改；仍须重新打包启动验证。
本轮完整宿主回归 `host-regression-r25-01.log`：1197 项通过（213.325 秒）；
随后刷新率/读回相关 17 项再次通过。独立 HAP 编译退出 0（5 分 14 秒），
`settings-refresh-hap-compile-r25-01/.../phone-default-unsigned.hap` SHA-256 为
`02908d960797935ed2bd2a978b35893f71757a19659cbcbe6cd5d753635551e9`。
其 `ets/modules.abc` 现在包含页面与控制器的真实模块记录及索引检查代码，
而不再仅有动态导入路径字符串。此结果只证明新页面已编入 HAP，尚不能证明
新镜像的 UI/实际模式切换成功。

## 2026-10-10 R23 完整回归结果与项目配额候选

R23 再次完整回归 `r23-full-web-observed-02`（boot
`a8e73dfd-e667-4d67-bb27-ea39bfdfcc35`）已结束。此次 Web/窗口 Vulkan/Settings/
Camera/媒体等既有窄项通过，ohos-native-bindings **32 模块、102 项通过，0 失败**。
完整首包门禁仍失败在 `complete-Cxx-ArkTS11-gap-closure`：281 项要求中
145 项有注册闭环，136 项未闭环。未用重试成功删除原 Web 间歇失败记录。

R24 仅 ARM64 phone 代表包已开始本地 Docker 构建，输入 `phone-teUjOr`，
提交 `d8546c1`，树 `c986d923040a75607e0e73c86988d496e4cc39eb0562096b678beed5fe5c8782`，
输出 `first-screen-modes-7.0-release-20261010-r24`。该冻结树的宿主回归
`host-regression-r24-03.log`：1184 项通过（206.887 秒）。产包后仅继续本代表包的
实际刷新率读回/UI/权限与完整回归；没有安排其余五包。

另在 R23 新诊断客体进行只读 `quotactl`：用户/组 Q_GETFMT=4，Q_GETQUOTA
返回真实非零数据，但项目配额 Q_GETFMT/Q_GETQUOTA 均为 ESRCH。证据
`r23-web-lifecycle-stress-04/readonly-actual-quota.txt`。实际源码确认：QEMU 的
userdata 格式遗漏 `--prjquota`；F2FS 仅凭 quota inode 自动启用统计，限额执行
还需要 usrquota/grpquota/prjquota 挂载选项。不能把用户配额查询成功扩展成
项目统计或限额执行成功。

新增后续候选 `vendor/ohemu/f2fs_quota` 及统一 launcher/镜像特征位校验，
保持 nosuid/nodev/noatime、权限与实际服务不变。该候选**不在 R24 冻结树中**，
未应用到运行客体，也未重写旧镜像；仍须后续新包真实配额与 Storage API 验证。
候选宿主回归 `host-regression-quota-r24-01.log`：1190 项通过（230.115 秒），
包含格式特征位拒绝、三个设备磁盘名的启动参数、补丁顺序与重复应用检查。
仓库新增独立新包配额诊断入口，限于新建目录与未使用项目 ID，由无能力的
UID 65534 写入，验证 EDQUOT、删除后的统计下降、解除限额后 4 MiB 写入恢复
及清理。`project-quota-three-abi-r24-02` 三 ABI 真实 SDK 编译/ELF 校验通过，
解析器边界与真实挂载参数检查 4 项通过；**尚无该候选新镜像运行成功证据**，
也不以此关闭 Storage 应用 API 缺口。
新增测试后的完整宿主回归 `host-regression-quota-r24-02.log`：1194 项通过
（212.683 秒）；测试原生源码的三 ABI 编译证据单独保存，不混作客体行为结果。
旧 R23 归档负对照 `r23-quota-negative-control-02`：使用其原冻结启动器，新开
boot `9d3a37f0-31c1-4949-a191-ca80f5411930`（macOS ARM64/HVF、phone），
如预期在真实 `/proc/mounts` 检查拒绝缺失限额挂载选项，尚未执行配额修改，
随后关闭独占客体。`negative-control.json` 保存校验器输入哈希，
`expected_failure_observed=true` **不是修复包通过**。首次负对照 `-01` 被冻结
输入一致性检查更早拒绝，未启动客体；该记录同样保留，不混作挂载结果。

## 2026-10-10 刷新率新包验证入口

新增仓库 `run_settings_refresh_diagnostic.py`：自行启动指定新归档，构建普通
Settings 调用器，经公开导航打开真实预装页面。页面标签、单选状态与实际显示
服务的模式 ID/刷新率逐项对应，并保存合成器截图；有真实同分辨率备选模式时
通过页面切换、读回和恢复，再验证 Back 及普通调用者得到 202。原生诊断程序
仅只读查询，不从 root 设置模式或给普通应用授权。
`--require-mode-change` 在无真实备选模式时明确失败，不把单模式显示算作切换
覆盖。五项宿主选择/权限记录边界测试通过，尚未在新代表包执行；不能关闭缺口。
此前完整宿主回归 `host-regression-r24-02.log` 1179 项通过（209.156 秒）。

## 2026-10-10 R23 Web 间歇恢复失败仍保留

`r23-web-lifecycle-stress-03` 在同一新启动 R23 客体上顺序构建、签名、安装
十个全新普通 Web 调用器，十轮均通过页面/JS/Canvas/WebGL/reload/renderer
退出恢复；电源设置已恢复，VM 已关闭。原完整序列的再次运行
`r23-full-web-observed-02` 也已通过 Web，其他测试仍在执行。
这两项重试不抵消原始失败，尚未确认具体根因，也未放行剩余五包。

原失败要等待总计 300 秒才采集系统日志，而渲染恢复自身 60 秒即判超时，
使 AppMgr 核心日志可能提前滚出缓冲。后续 runner 在每次 Web 轮询时只读
保存 AppMgr 域日志，并在已判失败的 reload/恢复超时标记出现时立即失败。
不延长超时、不删失败、不重试掩盖错误，也不以诊断输出判断成功。
16 项普通 HAP runner 主机测试通过；这不是生产恢复缺陷修复。

## 2026-10-10 显示模式读回纳入后续首包门禁

共用本地验收脚本新增 `screen-modes` 必测项：从实际产品头文件与 libdm/libutils
构建只读调用器，绑定新归档及原始启动证据执行，并在最终门禁重新解析实际
进程输出、退出码与哈希。空屏幕、空模式、无效活动模式不再能通过首包验收。
此项不代表普通应用获得系统显示权限，也不代表 Settings 页面已实际呈现。
宿主回归 `host-regression-r24-01.log` 1177 项通过（199.768 秒）；运行中的
R23 仍使用原冻结输入，未混入这个新增门禁。后续新代表包须通过该项。

## 2026-10-10 R23 新包 FA 正向实测与显示模式修复候选

R23 本地 Docker 构建成功，代表归档：
`/Volumes/PSSD/qemu/packages/first-fa-settings-7.0-release-20261010-r23/openharmony-qemu-arm64-arm64_virt-phone.tar.gz`，
SHA-256 `f58c5346d6db78422c8ce85eec595f712be988f0e8da92958dcf05609b32961d`。
`r23-settings-fa-positive-runtime-01` 的新包 boot
`f7fe9125-6ddb-452e-bcd3-eb6f0d55e9ff` 已通过两轮 Settings 输入导航，以及
仓库 FA runner 新建的普通 FA HAP（nonce `0c1118e67e7e0bb49e05790e56aba4c2`）。
实际 page/service PID 3519/3706、普通 UID 20010039，五项常量/context/既有调用
均通过；当前严格 `verify_evidence` 对原始证据独立复核通过。有限电源设置恢复、
诊断 VM 关闭。同归档完整回归在 boot
`8f480ad7-01db-40bf-9884-79a49792f4ce` 未通过：普通 Web 的页面、JS、Canvas、
WebGL 与 reload 通过，但 terminateRenderProcess 后未观察到退出回调，恢复
超时。最终进程表中原 renderer 4490 已不存在，因此不能把原因直接归为
SIGTERM 未生效。失败证据保留在代表包目录的
`openharmony-qemu-arm64-arm64_virt-phone-runtime-tz422104/web/evidence.json`；
后续 Stage/native 全套未执行，完整首包门禁未放行，剩余五包没有开始。
此次归档不含后来新增的刷新率和显示模式修复候选。

缺口闭环校验新增严格 FA + 同包同 boot 普通 Stage 导航联合条件，仅允许关闭
`particleAbility:ErrorCode`，不推导全部 FA 生命周期或 Stage API 已通过。
单独 FA、另一 boot 的 Stage、缺失原始启动证据均不能关闭该项。此登记不改变
当前已完成全套证据的缺口统计。此前宿主回归 1174 项通过（192.746 秒）。
加入联合闭环拒绝测试后的全量宿主回归 `host-regression-r23-06.log`：
1175 项通过（198.503 秒）。独立 Web 诊断
`r23-web-lifecycle-runtime-01`（boot `b2be3ad7-1677-4f53-8228-3ca14bab7b4e`）
在同一未修改 R23 归档中通过退出恢复；这不是间歇失败已修复的证据，原完整
测试序列正在重现，失败记录与首包阻断状态保留。

`r21-display-service-diagnostic-02` 确认根因：客体 DRM 和 RenderService 均报告
26 个真实模式，主屏模式 ID 0 为 1280x800/75 Hz；ScreenInfo 只接受最多 20 个，
故服务端序列化失败，而 SceneBoard stub/proxy 没有正确传播此错误。此前诊断
01 的 3308 是显示电源服务；02 改为真实 DMS 4607，原失败诊断保留。

新增独立 `window_manager/screen_modes` 部件，将上限有限扩展为 256，编码前
拒绝过量或空对象，解码前同时检查上限与剩余数据长度；服务端传播编码失败，
客户端只发布完整解码结果，保留已有业务错误。不删真实模式、不硬编码刷新率、
不改 API/权限/身份/后端。五项宿主测试覆盖精确补丁、实际序列化算法和代理
错误路径（ASan/UBSan）；九个真实翻译单元（三文件 × 三 ABI）编译通过，
证据 `screen-mode-three-abi-r23-01/evidence.json`，原 source/out 只读且未更改。
这些不是客体修复证明，仍须下一完整代表包读回、上屏和权限回归。

## 2026-10-10 显示模式读回新增阻断证据

新增只读 `screen_modes_readback.cpp`，使用真实产品 ScreenManager 头文件、
Ninja 编译参数及 libdm/libutils 链接，不设置模式、不向普通应用授权。ARM64
实际编译链接通过：`screen-modes-readback-build-r23-01/build.json`。
ARMv7a / x86_64 的尝试因现有 out 缺少对应实际产品库而明确失败，保留各自
`screen-modes-readback-build-r23-{armv7a,x86_64}-01`；不能算三 ABI 构建通过。

新 R21 客体 `r21-settings-screen-boundary-runtime-01`，boot
`d27077ab-6677-4bc0-9c5a-cfaa40652c90`，测试输入树
`aa998d42b6c49183338f7717423458f5e64404134d8a711493ce0aa266b53a3f`：
原输入 Settings 导航通过；零权限普通调用者 `screen.getAllScreens()` 实际
返回 202，权限负向边界通过。但独立 root 只读 GetAllScreens 返回 DM_OK 和
空列表，诊断整体为失败。正在进一步核对真实显示服务、模式与 IPC 数据链路，
尚不能认定具体原因，更不能把刷新率页面候选或刷新率能力算作修复完成。
电源有限测试设置已恢复，诊断 VM 已关闭，失败原始证据保留。

新增模式读回解析的四项主机边界测试通过，只允许实际主屏、实际模式 ID 和
当前分辨率，不推导 UI 呈现或普通应用权限。此前全量主机回归
`host-regression-r23-04.log` 的 1165 项通过（199.403 秒）。

## 2026-10-10 FA 原始证据复核与正式门禁候选

新增 `verify_fa_particle_results.verify_evidence`，重新核对同包/同 boot/架构、
普通 FA 应用身份与 page/service UID、原始调用记录、nonce、实际编译的 FA
HAP/源码/签名包和命令日志哈希；不接受已改写的成功汇总。正式本地验收脚本
增加必需的 `fa-particle` 检查，并保留同一包的原 Stage/native 全部测试。
官方 hvigor/Node 可通过 `QEMU_TEST_HVIGOR_HOME` / `QEMU_TEST_NODE_HOME`
指定；默认使用本机 DevEco 工具。不会向测试应用授予额外权限。

16 项 FA 测试及 7 项首包门禁测试通过；这些是宿主拒绝路径测试，不是客体
证明。之前完整回归 `host-regression-r23-03.log` 的 1159 项通过
（196.198 秒）。R23 仍在构建，此门禁变更不在其冻结树内；其已排定的新包
FA 诊断保持独立测试输入和证据，不追溯修改构建输入或提前启动剩余五包。

## 2026-10-10 Settings 2in1 输入页路由候选

固定 Settings 源码的 `supportedPageForPCList` 缺少两个公开输入法页面，
导致 2in1 在参数校验之前静默返回，不会拉起已打包的真实 Settings Provider。
独立部件 `settings/input_2in1_navigation` 仅增加 `set_input` 和
`other_input_detail_settings`，接入两个画像共用构建脚本；不伪造设备类型、
改变权限、打开其他设备路由或替换页面为占位实现。

3 项主机测试通过：完整源哈希、重复应用、未知编辑拒绝且保持原样，以及
编译执行实际 C++ 路由表，逐项比较 6 种设备标识 × 13 个页面标识，确认仅
2in1 的上述两项由拒绝变为允许。测试 fixture 仅比原始源码多一个末尾换行，
测试重建原始无换行字节后先核对固定 SHA-256，不能借规范化接受未知源码。
仍需真实 2in1 新包的 Settings 导航门禁；phone 或主机测试不是该运行证明。
此候选不在正在构建的 R22 `phone-SymNve` 冻结输入内，不追溯修改 R22 证据。

Settings 必测项加入后，全量主机回归 `host-regression-r22-02.log` 中两处
旧测试仍匹配旧 persona 列表而失败；仅更新对应列表断言后，
`host-regression-r22-03.log` 的 1147 项全部通过。失败记录保留，不能计为
镜像运行问题或直接改写为通过。加入三项新路由测试后，完整回归
`host-regression-r22-04.log` 共 1150 项通过（194.647 秒）。

R22 构建未产包：GN 父子进程多次观察 CPU 时间不再增长，子进程所有线程
均等待 futex，未进入 Ninja。保存 `r22-gn-stall-process-evidence.log` 后只停止
本次构建容器，exit=143，自动验证入口正确记录失败且没有启动客体测试。
这是宿主工具停滞，尚未证明具体根因；不记为系统编译或 FA 修复验证通过。
下一次仅重试代表包，使用新的冻结输入和输出目录，保留失败日志与旧输入。

R23 代表包重试使用 `phone-mdDSOe`，冻结树
`9bcd3f05ba09834a8d186c7f49ffe1c24e5cea141ce462c026ec27e5ec3af27f`，
输出 `first-fa-settings-7.0-release-20261010-r23`，日志
`first-fa-settings-arm64-phone-build-r23-01.log`。自动继续入口
`r23-validation-scripts/after-build.py` 仅等待此次容器，成功产包后验证 FA 与
Settings，再对同一归档运行完整 Stage/native 回归；无六包矩阵启动权限。

额外 R21 复测 `r21-settings-network-display-runtime-01` 在输入页前置验证失败：
第四次 UI 树已出现真实 Provider，但紧随截图仍为调用者页面。前三张截图已
显示实际设置页；第四张没有，因此原验证正确拒绝，而不是将 void 返回计为通过。
保留失败结果和四张原图。测试入口新增最多 60 秒的实际绘制等待，每次重读
Provider/UI 树并重新截图，不重复点击、不调整权限或放宽最终像素检查；
持续空白仍失败。新增延迟绘制/持续空白边界，17 项 Settings 测试通过；
这不是对失败旧结果的修订，也不证明新的等待已通过客体验证。

新增仓库 `run_fa_particle_probe.py` 候选入口，从官方 hvigor 构建新 nonce 的
零权限 FA HAP、按 FA 模型签名、核对普通应用及真实 page/service UID，检查
常量与已有 Promise/callback/context 调用。独立检查 archive/boot 绑定；
不授予权限、不替换 guest 库、不将 FA 单测当作 Stage 回归。10 项 FA 结果及
进程边界测试通过，实际新包验证和正式门禁接入仍待完成。上述后续测试入口
变更不在 R23 冻结输入中。

绘制等待修复已在另一个全新 R21 客体上通过仓库入口及独立复核：
`r21-settings-network-display-runtime-02`，boot
`8ea9a738-5ebb-4d5c-9e93-1a42e5803af7`；8 条调用记录、四次输入页呈现及返回
均通过。另实测显示设置与网络设置页面，保留实际截图、AMS 身份及调用结果；
网络关闭后 Promise 返回 true。未操作网络开关、密码或其他系统设置。
对应冻结测试树 `011b6a27974f0835300258a4d5e6193604f7f164cc56e746ab764904de0a14c6`，
完整主机回归 `host-regression-r23-01.log` 1156 项通过（231.822 秒）。

进一步扩展普通调用器，`r21-settings-all-pages-runtime-01`（boot
`f0caa56b-e0ef-45de-af4e-49e2e4deb3bf`，测试树
`7b6bf7047c4bfdbb145e49727ceadbedf78d69eada1af08e8cc562bf7f923228`）实测：
移动网络、声音和振动、生物识别和密码、关于本机、调用者自身应用详情均显示
真实页面并返回；仅验证页面导航，不声称完成蜂窝通信、生物识别录入等后端。
刷新率接口却返回 void 成功并打开空白目的页：固定 Settings native 路由存在，
`PageRouteController` 没有对应页面注册，已确认不能将此接口算作可用。
NFC 调用保持调用方页面，native 另有真实 NFC SysCap/不支持标记检查，未据此
声称 NFC 导航或硬件已修复，也未删除检查来强行打开页面。

新增独立 `settings/refresh_rate_page` 候选：使用原 Settings PageLoader 路由和
真实 `screen.getAllScreens()`，仅呈现实际主屏报告的模式，只允许同分辨率下
的刷新率选择，调用原显示服务并读回 activeModeIndex；拒绝未知模式、并发请求、
服务失败或未生效结果，不编造 90/120 Hz、不新增权限或改变显示后端。
3 项主机测试通过，覆盖完整源哈希/幂等/未知与部分编辑拒绝，以及实际控制器
的服务边界。独立只读 source 的 Docker 副本正在编译完整 Settings HAP：
`settings-refresh-hap-compile-r23-01.log`，冻结候选树
`8223b7f6eb02c027494f7dea8087a4374971a22329ce6465e98be3db64359ebb`。
原系统构建 source/out 与 R23 冻结输入未修改；此候选仍需后续新包实际启动、
页面/模式读回与权限回归，通过之前不关闭缺口。

该独立 Docker 完整 HAP 编译已成功（5 分 25 秒），未签名产物
`settings-refresh-hap-compile-r23-01/source/applications/standard/settings/product/phone/build/default/outputs/default/phone-default-unsigned.hap`，
SHA-256 `d9c61490db28837de3851a982ef7c951ce21eba3d8c5413ac40b3b0c5db88af5`。
包含 ARMv7a、ARM64、x86_64 的实际 native 依赖；这仍是编译证明，不是三架构
客体行为证明。`host-regression-r23-02.log` 全量 1159 项通过（222.076 秒）。
之后普通调用器另加 `screen.getAllScreens()` 的 202 拒绝分支按钮并绑定该 SDK
声明哈希，17 项 Settings 测试通过；该权限分支还未在客体执行，不能记为通过。
R23 产包后 FA 自动步骤已改用冻结树 `011b6a...14c6` 的仓库入口，构建全新
nonce 调用器；没有替换 R23 镜像或在其冻结输入中混入后续刷新率页面。

## 2026-10-09 用户确认的交付范围调整

用户明确答复 CloudSync 与 imageGeneration「这两个不用实现」。两项标记为
`excluded_by_user_not_fixed_not_validated`，不计为已修复或已验证。
原始 `native-arkts11-gap-ledger.json` 保持不变，SHA-256
`ac9426982dff3d7cb80050a6815eae92afb8f77c027b2d4319bc8d9423d6e93c`。

`ci/capability-audit/release_scope.py` 列出精确排除项：两画像的8个imageGeneration
导出契约及cloud-provider行为项，另有phone的cloudExtension.Flag。
phone排除10项，2in1排除9项；不排除整个ArkUI、分布式存储、其他Provider或
包含多个子系统的 `api26-runtime-export-mismatches-phone` 行为契约。
闭环报告保留原始总数、实际交付范围总数、精确排除列表及策略校验值，首包门禁
独立重算并核对；缺失其他任何契约、扩大排除或把排除项计入修复均拒绝通过。
这不是运行验收证明，也不追溯修改旧归档/旧测试的失败记录。

## 2026-10-09 R14 实测与下一首包候选

### 已批准的 particleAbility 最小常量补齐（客体验证待完成）

新增独立部件 `foundation/ability/ability_runtime/particle_error_code`，接入两个画像
共用构建入口。仅导出API26 SDK明确声明的FA常量
`ErrorCode.INVALID_PARAMETER = -1`，不复制featureAbility的其他常量，不修改
已有错误值、Stage的401、生命周期、权限、IPC或服务实现。NAPI分配/属性注册
失败时返回失败，不发布半成品对象。已完整阅读组件维护规则及兼容性头文件，
用户已明确批准修改FA兼容代码。

实际固定源码副本重复打补丁通过；三ABI真实注册翻译单元编译通过，原source/out
只读且源哈希未变，证据 `particle-registration-three-abi-r21-01/evidence.json`。
新增3项主机测试覆盖LF/CRLF、重复应用、既有初始化保留、全部4处NAPI失败、
128轮ASan/UBSan注册边界；完整1126项通过，`host-regression-r21-05.log`。
这些不等同于完整链接或FA运行时证明；R21冻结输入没有混入这个后续修改。

普通FA调用器已通过本机官方hvigor的legacyAppTasks/legacyHapTasks实际编译：
`fa-particle-caller-r21-05`，使用API26 SDK、兼容API8、零额外权限。保留此前
工具入口/目录配置失败记录，不用Stage构建冒充FA。尚待后续新镜像真实启动，
验证常量、FA上下文和既有调用，并执行Stage回归；此缺口仍未关闭。

已整理独立仓库入口 `ci/capability-audit/build_fa_particle_probe.py --output <新目录>
--sdk <API26 SDK> --hvigor-home <官方hvigor目录> --node-home <Node目录>`。
该入口实际编译 `fa-particle-caller-r21-06` 成功，unsigned HAP SHA-256
`6acb70629fb717c68249b42097430eb27601d6891c99332906a3f15daf8fb888`；
确认打包的是FA的config.json且无额外权限，并记录源码、SDK、构建器及产物校验值。
新增5项验证器边界与相邻3项注册测试均通过，
`fa-particle-host-boundaries-r21-01.log`。验证器要求真实上下文与既有调用身份一致，
不接受最终complete掩盖前序失败；单独FA通过也不自动关闭缺口或代替Stage回归。
完整1131项主机回归通过，`host-regression-r21-06.log`。

FA调用器随后按官方XTS的ServiceAbility模型调整为普通page启动自身service；
保留`r20-fa-negative-control-01`至`06`全部失败记录。实测page直接调用
particle上下文不成立；shell直接启动service被正常拒绝；普通page启动自身
service成功，但page和service实际使用同UID的两个PID，不能只读取page日志。
`06/fa-system-hilog.log`已看到service的真实`onStart`及缺失常量null。
另一个测试误用了未在公开particle SDK声明的
`particleAbility.getContext().getAbilityInfo()`组合，固定源码对此走PAGE类型
检查并返回-105；不修改类型检查，也不把这个失败记录改写为通过。
调用器改为检查上下文对象非null、既有particle直接getAbilityInfo的Promise/
callback两条路径与getAbilityName一致，完整新镜像验证仍待完成。

`fa-particle-caller-r21-09`经官方legacy构建成功，实际包含page与service两个
非空ABC，unsigned HAP SHA-256
`7d20f1dd42d3b3f8525f4641f94ccad317d3f8cabec24ea0b200d5946f42cf6d`。
这仍是测试调用器构建证据，不是常量修复通过。运行采集改为逐个验证实际同UID
进程并读取其日志，避免遗漏service，也不使用其他应用输出补齐观察。

签名工具对FA不产生Stage专用permission-sign块（固定源码SignProvider明确
按module.json判断）。测试签名入口新增显式`--fa-no-permissions`，仅接受
上述固定bundle、零请求权限、一个page与一个service的FA包；拒绝Stage、其他
bundle、重复配置/ZIP成员，且仍要求真实code-sign、digest、证书链、profile
和verify-app成功。普通Stage校验仍要求原4项marker，未改变镜像签名策略。
实际FA签名、normal非system安装在`04`至`06`通过；主机1134/1135项回归分别
见`host-regression-r21-07.log`/`08.log`/`09.log`，最后的调用器上下文调整后
6项FA验证器与5项签名边界测试通过，尚不宣称最新全量回归或客体门禁通过。

### 2026-10-10 R21首包已打包，运行验收未放行

归档 `/Volumes/PSSD/qemu/packages/first-settings-source-7.0-release-20261009-r21/openharmony-qemu-arm64-arm64_virt-phone.tar.gz`，
SHA-256 `30b448fa8376eb42234150efdb1c77073d18733df71b24c799ac66fd7cc06389`。
冻结输入`phone-1n55Zn`（5dd98d1，tree
`893f0a4302e4bca5e56147fbeebf0c044203279be3dcac89c4a94893a8239a6c`），
本地Docker实际构建退出0，约1小时36分；镜像内Settings源码/ABI/签名检查通过。
**R21没有后续FA常量补丁，不是该补丁的正向验收包。**

首次实际启动为macOS ARM64/HVF、arm64_virt phone，boot ID
`339d6ccc-7c27-4a3c-8570-8f999fff624f`、HDC `127.0.0.1:52028`。
运行`python /tmp/ohos-settings-r21-validation-8nHjf3/run-settings-r21.py`，
脚本副本、每条实际命令、参数、校验值与结果保存于
`r21-settings-navigation-runtime-01/`。默认稳定性和桌面验证通过，Settings实际
以system_basic预装；零额外权限调用器的已安装IME查询与两个非法参数拒绝通过。
输入法页面真实生成，但UITest把嵌入的UIExtension节点归入调用方窗口，原先按
独立Settings bundle查找的断言超时；该次诊断保留fail，不能作为首包通过。

新增独立测试验证器要求实际可见的UIExtension子树标题，并同时核对AMS中的
Settings扩展、正常调用方、互相引用的PID、各自真实UID及前台状态；不能用
调用方自己的同名文本代替provider。3项主机边界覆盖错UID/宿主/状态、重复
provider以及伪造在扩展外的标题，均通过。仍须重新启动同一归档实测。

FA对照已确认Service真实上下文和Promise getAbilityInfo可用、常量缺失；
旧FA callback以`{code:0}`表示成功，测试适配这个既有协议并继续严格核对
回调结果，不修改系统错误码。调用器`fa-particle-caller-r21-10`实际编译通过，
SHA-256 `2b0c9db848390c1b7aaa4ddc9b0fc73dd1a0cbe178258a41040fa9ffd472bb26`。
完整1135项主机回归`host-regression-r21-10.log`通过（此后新增的3项单测另计）。

`02.log`/`03.log`记录主机临时venv文件缺失导致的导入失败，两次均未启动guest。
保留失败环境与日志，另建证据目录下的`host-validation-venv-r21-01`，实际安装
相同Pillow 12.3.0后执行`04`复验；不修改归档、权限或既有断言来规避环境故障。
其余五包仍未开始，完整首包能力门禁尚未通过。

`r21-settings-navigation-runtime-04/diagnostic.json`随后真实通过：同一R21归档
全新启动，boot ID `afc0c19d-3241-45fa-badb-1fafef054d85`、HDC
`127.0.0.1:50889`。输入法列表/已安装IME详情各2轮，共4次实际provider上屏、
4次Back回到调用方和8条应用观察全部通过，系统记录的Settings UID 20010011
与普通调用方UID 20010038及双向PID关系一致；保留4张合成器截图并实际检查
输入法列表和kikaInput详情画面。有限测试电源覆盖已恢复，私有VM已关闭。
这是输入法导航子集通过，不等同于全部Settings或完整首包门禁。

同一guest内FA负对照也真实通过其预期：5条观察中仅常量为null，既有上下文、
Promise/callback getAbilityInfo和getAbilityName全部正常；两个进程同属普通
应用UID，独立于Settings进程。证据`04/fa-baseline.json`，状态明确为
`expected_missing_constant_confirmed_in_real_FA`，不计为FA常量修复成功。
在保留R21不变的前提下，下一代表包纳入已批准的常量补丁再做正向及Stage回归；
不会由这个负对照直接放行剩余五包。

### R22构建与仓库Settings验收入口统一

已启动单一R22 ARM64 phone本地Docker构建，加入批准的FA常量补丁。
输入`phone-SymNve`（3b07b4f），tree
`351d163eeff7d6280b97f5ef8fb3295ca299561200cc62d4a45bf91e22a062e3`；
构建记录`first-fa-constant-arm64-phone-build-r22-01.log`，计划归档目录
`/Volumes/PSSD/qemu/packages/first-fa-constant-7.0-release-20261010-r22/`。
后续只对该归档启动FA正向/Settings复验，再执行同归档的完整Stage/native回归；
链路状态`r22-build-then-validation.json`，没有启动剩余五包。
最新1138项主机回归已通过，`host-regression-r21-11.log`。

新增仓库入口`run_normal_hap_probe.py --persona settings-navigation`，复用统一
新调用器构建、普通签名、独立安装、boot ID校验与原始证据记录。输入法列表与
真实已安装IME详情各执行2轮，参数拒绝、8条观察、实际可见标题、4次Back返回、
Settings/宿主双向PID与UID、合成器标题区域均单独断言；离线验证器重新读取
原始文件并校验hash，不接受仅返回void或外层pass。

`r21-settings-repository-runtime-01`在启动前因使用不同冻结脚本被拒绝，保留fail；
没有放宽启动门禁。`02`改用R21原冻结启动器，另外记录测试入口的冻结输入
`settings-runner-inputs-r22-01`，tree
`5aee2a77a1852f5c2e23f97b81089b24793480108bba2792610437e7e691761f`。
新guest boot ID `1eaafa08-1613-40a9-9178-1f2d63b9f5ec`、HDC
`127.0.0.1:52044`、新调用器nonce `7e457d04c4f51d142f5a56654c5fb084`；
真实运行和独立原始证据复核均通过，电源设置恢复，VM关闭。
首包与归档SHA仍为上面的R21值；这证明统一测试入口，不将旧包算作FA正向修复。

据此把Settings输入法导航加入两个画像的完整suite和独立首包必测集合。
15项相关边界测试及10项首包门禁测试通过；此前1143项全量主机回归见
`host-regression-r22-01.log`（后续新增的截图/门禁测试另计）。
新增测试明确拒绝相同标题出现在非扩展子树、后台/错UID/不互相绑定的进程、
重复或缺失观察、篡改/空白标题截图。该子集仍`closed: []`，不关闭整个Settings
缺口，也不宣称network/display或输入法开关操作已验收。
正在构建的R22冻结输入早于此次测试入口提升，不追改其构建记录；最终六包
仍必须来自包含最新必测项的统一仓库脚本并通过各自验收。

### R20完整回归结果与R21准备（未通过完整交付门禁）

R20新归档：
`/Volumes/PSSD/qemu/packages/first-fusion-tts-7.0-release-20261009-r20/openharmony-qemu-arm64-arm64_virt-phone.tar.gz`，
SHA-256 `5dc605b8e1a80574aef082e5e9ba9fa2ec71d2488fbad315a2278cb8a89e37d6`。
冻结构建输入 `phone-SvX3p0`，tree
`045ac45c432f9cab63831482440ebeb1406651bbbb88a9ad7f2cd52ed7150648`。
以原冻结 `scripts/validate_packaged_qemu.sh --package-archive <上述归档>
--package-directory <同名目录> --evidence-output <包根目录>/first-artifact-runtime.json`
执行完整回归；macOS/HVF ARM64 phone、API26 SDK、真实guest
`127.0.0.1:59508`、boot ID `9be504b8-e4d9-4d00-a4ab-638be84c8045`。
原始环境、每条命令、返回值、原始观察和校验值均在该报告与
`openharmony-qemu-arm64-arm64_virt-phone-runtime-qh4s4u9t` 内。

真实通过项目包含首启/桌面/默认休眠唤醒、RS对象、ArkWeb、UDMF相关issue20、
Vulkan设备/headless/OHOS窗口、完整权限注册表、Fusion启动及实际参数权限、
TTS真实导出、严格Camera与已有音视频回归。
**原仓库bindings全部32模块、102用例通过**，源码和依赖锁未改。
最终有限测试电源覆盖已恢复，私有VM已关闭。
但是完整台账门禁仍失败：原范围291个phone契约只有147个获得登记的完整证明，
144个未闭环；故 `first_artifact_behavior_gate_passed=false`，没有开始其余五包。

使用新批准范围另行重验同一份原始证据，报告
`issue-20-20261006/r20-approved-scope-gap-closure-01.json`：原始291、明确排除10、
范围内281、已证实145、未闭环136。两个被排除项目已有表面契约证明也不再计入
交付修复数量。这是诊断重验，不覆盖原失败报告，不作为当前脚本的首包门禁。
“未闭环”包含尚缺真实行为证明的项目，不能直接等同于136个尚未实现的独立功能。

Settings实际普通调用候选新增 `build_hap_probe.py --settings-navigation-only`，零额外权限，
使用真实安装IME身份、空参数错误16900010、输入法列表/详情、网络和显示设置公开API。
void返回明确不是上屏证明，仍须单独验证实际Settings页面、用户返回及重复生命周期。
API26实际编译产物 `issue-20-20261006/settings-navigation-caller-r21-01/entry/build/default/outputs/default/entry-default-unsigned.hap`，
SHA-256 `b144d77d565f939480a7cdb765c39f2b886fd30c9432be50124bcff090206748`。
其SDK、源码、模块与nonce记录于同项目inputs文件；未加入闭环验证器或全量门禁。
新增CLI互斥检查保留所有旧模式，完整1112项主机回归通过，`host-regression-r21-01.log`。
R21只构建ARM64 phone代表包，Settings修复须在其新归档上验证后才能宣称修复。

本轮还删除已结束R18的Rust中间缓存2,754,760,704字节，已复核并保留32个实际测试库，
可按保留的源快照/锁/命令重建；删除R11/R13/R14的22个精确归档镜像副本
10,183,475,200字节，均可从保留归档恢复。原始日志、userdata和不同于归档的可写镜像
均保留；完整删除/校验记录为 `cleanup-r18-rust-intermediates-20261009.json` 与
`cleanup-r11-r13-r14-duplicates-20261009.json`，未触及用户其他VM或仓库。

### Settings 最小授权获批并接入下一首包构建

用户已批准仅对 `com.ohos.settings` 与固定OS应用签名
`8E93863FC32EE238060BF69A9B37E2608FFFB21F93C862DD511CBAC9F30024B5`
启用 `allowAppUsePrivilegeExtension`。主脚本在部件遍历之前应用真实源码构建、
受限输入法UI入口及依赖准备，移除旧 `Settings.hap` 预编译目标，并同步该应用
原有GET_INSTALLED_BUNDLE_LIST授权的签名；不增加该权限、不改变其他应用配置。
`Launcher_Settings.hap`、SettingsData及其他Settings相关包保留。
未修改BMS、`system_basic`、原始ACL、服务权限或全局扩展授权规则。

新增 `verify_settings_provider_image.py` 在实际system.img中核对唯一Settings HAP、
43个扩展、三个ABI的6个ELF、真实签名与嵌入profile、两个实际预装策略文件。
profile校验从固定源码原始CMS重建允许差异，只接受OS证书与既定有限到期时间变更；
原ACL/权限/APL及profile签发者必须保持一致。
SettingsExtService/IgnoreRepeatClickExtService仍要求ACCESS_SYSTEM_SETTINGS，
输入法外部扩展保持独立instance会话。

隔离源码实际签名候选
`issue-20-20261006/settings-external-input-candidate-r20/Settings-external-input-signed.hap`，
SHA-256 `ae71d84a3cc0647443e09b23f4cd71d59583a98f0e1610c9ddeb51c62d64725c`。
实际运行 `verify_settings_provider_image.py --hap ... --source-root ... --arch arm64` 通过，
证据为同目录 `settings-provider-evidence.json`。对实际预装配置副本重复应用两次通过；
39项Settings主机回归通过，包含未知签名/额外权限/符号链接拒绝及服务权限、会话、
profile不变性检查。以上均非guest验收，不关闭Settings行为缺口。
正在验证的R20归档仍使用此前冻结输入，不包含这一批Settings改动；须重打下一首包
并从归档启动验证BMS安装、真实页面、取消及权限拒绝路径后才能认定修复。

### Photos 真实资产回读流程纳入仓库独立测试候选

后续R20新启动验证仍保留失败，不计为通过：`r20-photos-asset-runtime-01`
使用了不匹配的启动脚本快照，被原冻结输入校验拒绝；改为原R20启动脚本加独立冻结
新探针后，`...-02`在picker窗口切换时收到UITest精确的窗口节点未就绪错误。
新增错误分类，只对该精确命令返回值进行30秒内的观察等待；权限、传输、缺失退出
nonce、JSON错误均立即失败，且必须取得原有真实控件和完整授权/选择证明。
新增5项边界回归，完整1117项主机测试通过，`host-regression-r21-02.log`。

`...-03`通过窗口观察后又遇到真实DMS截图2秒超时，仍按失败记录，未调大生产超时、
未跳过截图或像素断言。随后隔离并发R21构建的CPU/IO竞争重测；单次成功不能证明
此前超时完全由资源竞争引起，也不代表完整Photos已经闭环。失败现场、userdata及
不同于归档的可写镜像保留。
另清理01/02中12个与保留R20归档精确相同的镜像副本5,656,403,968字节，可重新
解包恢复；记录 `cleanup-r20-photos-failed-run-duplicates-20261009.json`。

`r20-photos-asset-runtime-04` 从同一R20归档新启动通过完整19项真实观察，boot ID
`ac00195e-bdd6-4d46-adc1-e269752b16b6`：取消不选资产、真实授权保存、唯一recent
identifier `2854538`、预选并返回同一URI、64×64 JPEG回读RGBA `(37,149,212,255)`。
六个真实界面动作及三个compositor截图均经严格复核。原R20冻结启动脚本未更换，
新测试单独冻结为 `58d7c28ed968b6fea76433c2ad3dbe1c24e7859ac5ba4a2d11bc21403faa7505`；
有限电源覆盖恢复、私有VM关闭，R21构建容器也已恢复运行。
主机隔离记录 `r20-photos-build-isolation-04.json` 不改变guest或截图服务超时。

由此将 `photos-asset` 纳入phone/2in1所有架构共用首包/交付测试，并加入独立交付门禁：
必须重新读取原始19项观察、普通应用身份、固定源码/SDK、六个动作、截图、HAP和
校验值，重算同一资产及像素断言；泛化的pass、旧boot/架构、改动的截图或仅重算外层
checksum不能通过。新增6项门禁边界测试。旧04报告是实施方向的实测，不改写为新
验证器的报告或全量首包成功，仍不关闭完整图库/FA卡等Photos缺口。
完整1123项主机回归通过，`host-regression-r21-04.log`；此前03轮仅因旧套件
成员断言未包含新persona失败，修正测试期望后完整重跑，不放宽运行时验收。

后续磁盘清理保留归档与所有原始验证证据：R20已结束的Rust中间缓存
2,753,974,272字节可重新编译恢复；03/04、R20首轮运行及打包暂存目录中22个
与保留归档逐文件核对一致的镜像副本10,252,664,832字节可重新解包恢复。
userdata及不同于归档的镜像未删；分别记录
`cleanup-r20-rust-intermediates-20261009.json`、
`cleanup-r20-photos-completed-run-duplicates-20261009.json`。
另复核RS R7/R8两轮各32个已保留测试库及通过记录后，删除已结束的Rust中间
缓存各2,753,900,544字节；源码、锁、签名HAP与运行证据不变。记录
`cleanup-rs-r7-rust-intermediates-20261009.json` 和
`cleanup-rs-r8-rust-intermediates-20261009.json`，可按原构建命令恢复。

将R18已实测的普通应用流程整理为 `run_normal_hap_probe.py --persona photos-asset`：
新nonce、零额外权限、真实取消选择器、确认只保存一张测试JPEG、查询唯一标题对应的
recent identifier、预选同一URI后确认选择、打开返回URI并解码64×64 RGBA。
真实源像素格式显式为RGBA；三通道容差仍为8，不放宽原检查。
UI驱动只点击实际唯一可见且可用控件，验证授权提示、选择计数、控件所属bundle及
Button祖先；保存布局、截图及校验值，验证器重新读取原始观察和UI文件。

ARM64 API26实际编译产物 `issue-20-20261006/photos-asset-formal-compile-r20-01/entry/build/default/outputs/default/entry-default-unsigned.hap`，
SHA-256 `cedd006aad4353a90f2cf0536e27a9525f8bbaa26188bbe75e481218e6aa610f`。
12项专用主机单测覆盖失败/旧nonce/乱序、不同资产、错误像素、假成功、权限身份、
UI归属/禁用/歧义、布局或截图篡改，以及新探针与旧探针的CLI互斥。
完整1084项主机回归通过，`host-regression-r20-09.log`；前一轮保留两个旧硬编码
探针列表未包含新模式的测试失败，更新列表后重跑，不移除互斥或权限断言。

新验证器还能重验R18保留的19项实际观察和三个真实弹窗布局，记录
`photos-asset-verifier-replay-r18-r20.json`，明确不是R20运行证明。
当前仅增加独立测试模式，尚未将其加入完整首包编排，须先在新归档上验证此模式。
不据此关闭完整Photos、无预选图库、FA卡或CloudSync缺口；原始台账和metadata测试保留。

### Settings 输入法公开入口候选（未激活预装）

进一步确认固定 Settings 源码包含真实 `InputSettings`、`OtherInputDetailSettings`
及其输入法服务调用，但未声明 NAPI 指向的 `ExternalCommonUIExtensionAbility`。
新增独立 `settings/external_input` 部件，只允许 `set_input` 与
`other_input_detail_settings` 两种外部路由。详情参数按现有 NAPI 的
`pushParam` / `isParamJsonObject` 协议解析，检查大小、类型及实际已安装的输入法身份，
仅复制核验后的身份和服务返回的标题，不接收任意 Settings 页面或配置。
页面复用原有三个输入法组件和控制器；入口本身不启用、切换输入法或放开权限。
每个 instance 的内容使用会话 LocalStorage，拒绝并行替换，结束/加载失败释放 context。

实际扩展源码经 SDK TypeScript 转译后通过31项隔离请求/会话边界测试；它不是guest证明。
实际源项目经API26工具链完整编译成功，最终第二轮59秒，无新增页面的编译警告。
原上游 ResetFactoryController 跨模块引用警告等仍保留，不以编译成功关闭其行为缺口。
未签名候选 `issue-20-20261006/settings-external-input-candidate-r20/Settings-external-input-unsigned.hap`
SHA-256 `c1f9fe4c0230dd272401192230a8c98f5ed5907015e5b4ae386648107d501603`。
静态复核43个扩展、三ABI共6个真实ELF；旧42个扩展、应用身份与请求权限完全保留。
编译记录 `settings-external-input-compile-r20-02.log`，候选目录保存边界测试和静态复核结果。

该部件与 `source_provider` 一样尚未接入主构建：Settings 精确证书绑定的最小预装
扩展授权仍待用户确认，未改BMS、APL、ACL或其他应用权限。必须另行重新签名、装配并
从新归档启动验证实际页面与取消/错误路径；不能把候选计入已闭环项。
当前R20只包含已经提交的Camera、Fusion参数和TTS修复；首包自动继续脚本仅运行
`phone-SvX3p0/scripts/validate_packaged_qemu.sh`，不启动其余五包。

### R19 新归档相机严格三轮复测通过

代表包 `/Volumes/PSSD/qemu/packages/first-camera-publication-7.0-release-20261009-r19/openharmony-qemu-arm64-arm64_virt-phone.tar.gz`，
SHA-256 `d3c224bcb7f0323168a461186029d8922e3ad89381d9c586e1aa9d29033fce79`。
冻结输入 `phone-MerpQo` / `d543b63`，树SHA
`dbf87f1522fc399626332ab01d05d7828c8e63ac9f497a472d9cd8f844d65a5a`。
本地 Docker 编译成功（1小时19分06秒），实际镜像检查和归档成功。

macOS ARM64、QEMU HVF、4核4GiB、1280×800，从该归档重新解包启动；boot ID
`4b452c6e-a848-465e-aaaf-75e6f41216b1`，HDC `127.0.0.1:57973`。
连续运行冻结脚本 `ci/capability-audit/run_normal_hap_probe.py --persona camera` 三次，
每次均使用独立新输出、原始未放宽的 Camera 探针、API26 SDK 和普通应用身份。
原1000ms结束事件检查、JPEG内容及NDK生命周期检查均由原验证器保留；三次退出码均0，
三个 evidence.json 均为pass。测试电源超时覆盖已恢复，私有VM已关闭。

记录 `issue-20-20261006/r19-camera-publication-runtime-01/diagnostic.json`，含归档校验值、
环境、精确命令、探针源哈希、子结果与状态恢复。原始Camera失败证据没有删除或改写。
这里只确认相机请求发布顺序修复的方向，不是全部229项或六包完成；
`first_artifact_behavior_gate_passed` 仍为false。R19不含之后提交的Fusion参数权限及
Settings TTS修复，因此下一轮仍重建ARM64 phone代表包，不启动余下五包。

### R18 新归档与真实 Photos 正向验证

归档 `/Volumes/PSSD/qemu/packages/first-boot-assets-7.0-release-20261009-r18/openharmony-qemu-arm64-arm64_virt-phone.tar.gz`，
SHA-256 `4fa58c2be20a0c52736d045ec18f7b428c249b6bf931e9eed5b4d0de5f722298`。
冻结输入 `phone-IExnAy` / `d796783`，树SHA
`99734737af271779123fa14c80bd7637783a9c16fa5bb419e3ebcdb160211461`。
本地Docker完整编译成功（43分40秒），实际镜像Photos两份预装策略、14个字体及
2个配置、两项开机资源、Native ABI静态门禁均通过。额外只读扫描18373个装配文件及
82个ZIP/HAP中的25886个条目，未发现LFS占位文本；不是运行时能力证明。

在macOS/ARM64 QEMU中新解包启动该归档，使用API26 SDK和普通应用UID 20010037，执行
`photos-positive-probe-r18/run-runtime.py --output <新的证据目录> --archive <上述归档> --frozen-root /Volumes/PSSD/qemu/build-inputs/phone-IExnAy`。
真实系统保存弹窗确认、写入图片、查询对应最近照片、选择器确认返回同一URI、重新打开
并解码64×64 JPEG均已通过：中心RGBA为37/149/212/255（断言目标37/149/211/255，
JPEG误差界限保持8）。省略RecentPhotoOptions、保持输入对象不变、非法选择数401、
真实取消选择器也通过。新保存弹窗截图中文字已正常显示。证据
`issue-20-20261006/r18-photos-asset-diagnostic-03/`，19项观察全通过，超时覆盖已恢复。

01为首次检查真实完成控件而主动停止，未标为成功；02保留失败：探针给RGBA字节但未设
srcPixelFormat，而SDK声明源格式默认BGRA。03仅显式设置源RGBA格式，像素断言未放宽，
系统归档未改变。private探针、实际编译源及unsigned HAP已归档到`photos-positive-probe-r18/`。
以上仍不证明无预选图库浏览、FA卡、云设置或完整Photos能力；未关闭原始整项缺口。
完整首包验收 `scripts/validate_packaged_qemu.sh` 已在Camera第二轮预览结束处失败，记录
`first-boot-assets-arm64-phone-runtime-r18-01.log`；在完整门槛通过前不开始余下五包。

### R18 Camera失败与R19提交顺序候选

失败证据位于R18包目录的`openharmony-qemu-arm64-arm64_virt-phone-runtime-d0l763bs/camera/`。
第二轮ArkTS预览`session.stop()`后原有1000ms窗口内`preview_frame_end=0`；
四张JPEG内容和61项NDK检查仍通过。完整门禁为失败，不以这两个子结果替代。
实际hilog显示18:47:59.262缓冲区已加入pool，59.272返回INVALID并被归还，
而pipeline Capture与inTransit请求登记直到59.290才发生。请求留下没有对应缓冲区的
待完成记录，取消后无法发出结束事件；释放流时的迟到事件不能满足原验收。

新增独立`camera/capture_publication`部件：先取得但不发布缓冲区，在取消/停止检查后
登记待完成请求，准备pipeline和开始通知，最后才AddBuffer。配置失败回滚当前请求和
未发布缓冲区，不删除更早的在途请求；取缓冲区期间不占用请求锁。
原`capture_end`部件仅识别这套精确完整组合，未知修改和部分组合仍拒绝应用。
主机测试使用实际Capture/HandleResult/OnFrame/CancelRequest方法复现旧版遗漏，
并覆盖即时跨线程返回、连续100帧、单拍、取buffer期间取消/停止、配置失败及旧请求保留。
ASan/UBSan检查不等于新包验证；ArkTS原有等待和断言未修改，仍需R19重新打包启动验收。

`d543b63`已提交该候选，1037项主机回归通过；R19继续只构建ARM64 phone。
R18独立诊断`r18-native-bindings-diagnostic-01/`中的原生Vulkan device、headless、
OHOS surface三个探针均通过；完整native-bindings E2E的32模块、102用例全部通过，
包含ArkWeb、UDMF、JSVM、QoS、vibrator。原始测试仓库和依赖锁均未改变。
此轮boot ID为`a687fb95-ea5a-4660-98c8-a11d9205d65c`，最终测试超时覆盖已由嵌套用例
恢复并经外层复核。归档、测试环境、命令、完整原始结果保存在同一诊断目录。
这不是R19或六包验收。R18原完整运行的部分证据重放结果为291个展开的phone契约中
133个有完整登记证明，158个尚无；原始台账不变，不等同于158个均未实现。
记录`r18-partial-gap-closure-01.json`，仍为fail。

Fusion诊断01保留测试休眠超时；02使用既有有限开发超时并恢复后，两轮实际SAMGR
加载均成功，但验收错误地在内核串口寻找SAFWK的HiLog消息。现分开捕获两种日志：
必须同时有专属UID的init启动、同PID的exec、SAMGR动态启动和SA注册，以及来自同一
实际服务PID的HiLog发布成功事件，仍保留两轮真实LoadSystemAbility调用。
新验证器在`r18-native-bindings-diagnostic-01/service-init-contracts/`通过完整镜像、
账号、目录ownership和实际启动检查；错PID、错SA、失败返回或缺任一日志均被拒绝。
另外发现PartnerDeviceAgent生命周期参数的SELinux set拒绝（当前eng模式仅记录），
已补`fusion_partner_parameter`独立候选部件，仅为该完整参数名添加系统内部标签，
允许PartnerAgent和负责装载默认值的init写入；SAMGR仅可读，应用和FusionRanging不可写。
未开放整个persist域，未添加检查豁免或修改neverallow。普通/开发策略、上下文及完整
SELinux检查通过，记录`fusion-partner-contexts-and-policy-check-r20-04.log`，实际编译结果
保存在`fusion-partner-policy-r20/`。前三次诊断保留工具工作目录/输出目录末尾斜杠错误，
未改动检查器来通过。

另补实际产品链接的只读内核AV探针，ARM64编译通过；它读取实际allowed位，不接受
permissive包装器返回成功作为授权证明，不切换进程标签/全局执行模式或写参数。
新的正式init验收要求镜像中精确标签、两个允许写入角色和五个拒绝角色、同PID发布及
无该参数的真实MAC拒绝。R18的旧init正向证据仍保留为当时的较窄结果，不满足新增检查。
R19已冻结构建输入，尚不含此后新增参数候选；相机方向确认后须再重建代表包验证该策略。

### Settings TTS 标准入口候选（尚未新包运行验收）

固定 Settings 提交 `0aba461c750fda71977c2f5186ca0e756ecfc6ca` 的 NAPI 把
四个文本转语音设置键导出为小写 `tts`，API26 SDK 则声明大写 `settings.TTS`。
新增独立 `settings/tts_namespace` 部件，将标准入口指向原来的同一对象，保留小写入口；
没有创建模拟语音引擎，也不把设置键可读声称为语音合成后端可用。
补丁保留原始 CRLF，仅接受完整固定源或完整修复后的源，在公共打包脚本遍历前应用。

原始文件 SHA-256 `82395ff1aa9bf6d6cb32cdaf971d7c75bc0c029c81aef1f8b81501cd8b641567`，
修复后 `44225247789f4e6db3f1612cd13a71eb3ea4f78164ab4d40c8927be3f412e32f`。
真实 ARM64 产品编译参数下的独立翻译单元编译通过，证据
`issue-20-20261006/settings-tts-compile-r20-01/`；未修改正在构建的 source/out。
普通应用实际导出探针新增四个 own-property 字符串值和新旧入口严格同一对象的读取，
三个架构的 SDK 原生探针均编译通过。验证器只在这些真实观察全部一致时接受该标准
namespace，不能用一个同名函数、空对象或错误常量关闭缺口。
本候选尚不在冻结的 R19 中，必须随下一代表包启动验收；未启动其他五包。

### Settings 完整源码应用候选（预装授权待确认，尚未启用）

同一固定提交还包含旧 phone 预编译 HAP 缺失的真实 Settings 扩展实现。
`settings/source_provider` 已准备独立源码构建补丁、三个 ABI、固定 HAR 依赖和签名配置
准备脚本；目前未接入公共构建配方，也未替换镜像中的旧 HAP。构建工具未使用的
fs-extra/execa 声明已移除（所有源码构建脚本无引用），不再触发用户 npmrc 配置错误。

本地 Docker 隔离编译通过（3分40秒），代码签名、摘要、权限签名和完整 HAP 验签通过。
候选保存在 `issue-20-20261006/settings-source-candidate-r20/Settings-source-candidate.hap`，
SHA-256 `b5de32dbec789a2b10245a01a3f3528d462c816f43f498a961284d06e65e44ae`。
`inspection.json` 检查三种 ABI 的六个 ELF 库及42个扩展入口；包括
SettingsExtService、IgnoreRepeatClickExtService、OpenNetworkUIExtensionAbility。
两个无障碍 service 的 ACCESS_SYSTEM_SETTINGS 调用权限未改。
来源、命令与编译结果见 `settings-source-provider-compile-r20-03.log`，验签结果见
`settings-source-signature-r20-01.log`；01保留OHPM TLS下载失败，02保留首次构建诊断。
依赖通过原版本官方 HAR 下载并固定 SHA-256，未使用任意最新版本。

原源码 profile 的 APL 为 system_basic。准备脚本只更新过期 profile 的 OS 证书和
有限有效期，不改变 bundle、APL、ACL、请求权限或添加特权；实际CMS和工具验签均通过，
再次准备保持相同结果。原有完整权限内容的比较保存在候选检查证据中。
但当前 QEMU 启用 USE_PRE_BUNDLE_PROFILE，且没有 Settings 的预装 capability 条目；
BMS 对 SERVICE 扩展要求 allowAppUsePrivilegeExtension。该最小、绑定具体 bundle 和
OS 证书的预装授权已单独请求确认，未提前启用。缺失的 ExternalCommonUIExtensionAbility、
页面实际运行、服务调用、回归与各设备画像仍需后续修复/验收，不能以该 HAP 编译和签名
结果关闭整个 Settings、无障碍、网络或全部缺口。

### 首包修复过程与保留失败

R17后续：`0e8aec4` 的1019项主机回归通过。全分区 staging 占位文件扫描又发现
`system/etc/graphic/bootpic.zip`、`bootvideo.mp4` 为LFS文本，已主动停止R17构建，
未生成归档。补齐固定graphic_2d提交`81cc9ca9509bccd86c435064136fe45591d29eeb`
两个精确对象，LFS清单增至81项。新增打包门禁检查全部staging普通文件的占位标识，
并从实际system.img提取两资源验证SHA/大小及ZIP完整性/MP4头。真实缓存对象检查
和8项新增回归通过，但不代表开机动画已播放或新首包行为门禁通过。继续单首包重建。

`d796783` 后完整1027项主机回归通过，记录 `ohos-capability-host-r18-01.log`。
R18首包输入冻结为 `phone-IExnAy`，仅构建ARM64 phone，尚不启动余下五包。
又清理两次已关闭Photos资产诊断中的10个归档精确副本，释放5,511,127,040字节，
保留userdata、日志和R14归档，可从归档恢复；记录
`cleanup-r14-closed-asset-duplicates-20261009.json`。

继续核对固定ace_engine提交 `e55e178228b9f6388b15d3024e8caf125fa293d7`：
`interfaces/napi/kits/intelligence/image_generation/js_image_generation.cpp` 只注册show/scale，
SDK26声明的close/hide/restore及四个NodeGraph操作没有对应导出；show成功分支仍resolve
undefined而非结果数组，省略options传入空napi句柄。`interfaces/run_rollup.py` 的creator
错误拒绝instanceId=0，并直接改写调用者options.content。
`image_generator_dialog_project/general/utils/AIGenerateImpl.js` 的默认文本路径仍生成
mockThink/mockResult，默认图片路径延迟返回输入图片；两个自定义模型setter在该组件中
没有调用点。不能把枚举导出、空结果或这些模拟路径计为生成能力闭环。
证据 `image-generation-fixed-release-source-audit-r18-01.log` 保存实际源码哈希及定位。
已询问真实默认模型和phone CloudSync服务来源；不擅自接入收费服务，也不将模拟结果作为修复。

R16后续记录：`b446c92` 的1008项主机回归通过，但完整构建在SELinux域清单检查处
失败，尚未生成归档。两个新增sadomain已通过真实策略/上下文编译，却未登记到
`domain_baseline.json`；现只补充这两个名字的分类登记，不修改独立权限豁免清单、
neverallow或检查器。使用固定Release实际策略及脚本重跑全部SELinux检查通过，
证据 `ohos-fusion-full-policy-check-r17-01.log`；仍需新包运行验证。

同时从R14真实保存弹窗截图发现缺字，直接提取system.img确认
`HarmonyOS_Sans_SC.ttf` 和 `HMOSColorEmojiCompat.ttf` 均为213字节LFS占位文本，
不是可加载字体。现补齐固定 `global_system_resources` 提交
`8cb84b3f3dd2142826e3f09cf2c171a421a06c14` 的两个精确对象（约20.6MB和16.8MB），
LFS清单由77项增至79项，SHA/大小核对通过。打包新增实际镜像字体目录、SFNT表边界、
两对象哈希校验；它已拒绝旧R14镜像。14个真实字体及2份配置的候选对象检查通过，
但不冒充新镜像文字渲染通过。字体证据保留在同一issue-20证据目录。

补充：`13c6c3e` 的1003项主机回归通过，Photos普通调用探针三ABI均通过实际API26
编译。R15候选在本地Docker进入GN后主动以SIGTERM停止（退出143），尚未生成包：
并行的R14真实保存诊断05发现预装权限文件仍使用旧Photos证书，用户点击允许后
MediaLibrary API10007因WRITE_IMAGEVIDEO缺失返回201，Photos错误返回空URI集合。
不能把确认弹窗出现或空相册结果视为成功。

已将 `photos_provider` 扩展为两个独立补丁：能力身份和预装权限均绑定实际源码HAP
证书 `8E93863FC32EE238060BF69A9B37E2608FFFB21F93C862DD511CBAC9F30024B5`。
六项已有预装权限及userCancellable值完全不变，不给普通调用应用新增权限。
打包验证同时检查实际system.img内的两份策略，不再仅验证源码能力文件。
24项Photos策略/镜像边界测试通过；新的包与真实保存/读取结果仍待验证。
R14诊断04/05中的真实picker取消返回空列表通过，但不代表正向选择、保存、FA卡
或云服务能力闭环。额外清理20个已关闭诊断的归档精确副本（约10.3GiB），记录
`issue-20-20261006/cleanup-r14-closed-diagnostic-duplicates-20261009.json`；userdata保留。

R14 完整归档为
`/Volumes/PSSD/qemu/packages/first-camera-photos-source-7.0-release-20261009-r14/openharmony-qemu-arm64-arm64_virt-phone.tar.gz`，
SHA-256 `96a6cb1184febc91052aeae0fba553121c7149fc19bad5ec0559f770c55ae5ab`。
固定 manifest 仍为 `f079c4ad9848f9cc4a9a4b3a3613ad8fbb142549`；
构建输入 `phone-IqYr74`，树 SHA-256
`f492633e8b10a4f52479b0c5b9e120fedadaaa1549136dc9d40337cbbe46507d`。

在本地 macOS/ARM64 QEMU 新启动的 phone 镜像执行
`scripts/validate_packaged_qemu.sh --package-archive <上述归档> --package-directory <同名解包目录> --evidence-output <R14目录>/first-artifact-behavior.json`。
使用实际 API26 SDK `provider-sdk-26-full/26.0.0` 和普通签名应用。
原样 Camera 用例通过，包括两轮真实 JPEG/preview/capture-end；完整门槛仍失败，
未运行到 native-bindings 和完整缺口台账，不能报告全部修复或开始剩余五包。

失败及新增诊断证据位于
`/Volumes/PSSD/qemu/validation/first-20261005/issue-20-20261006/`：

- `first-camera-photos-source-arm64-phone-runtime-r14-01.log`：完整门槛停在 Fusion init。
- `r14-fusion-real-samgr-load-01/`：用实际产品 SAMGR API 请求 SA 8631，init 在
  `setcon(u:r:fusion_ranging:s0)` 返回 EINVAL 后、exec 前退出。两个服务配置引用的
  SELinux domain 均未定义。原探针的 Android 式 `ctl.start` 只写入惰性参数，
  已改为真实 `LoadSystemAbility`，保留 init 身份、token 和权限链。
- `r14-photos-source-diagnostic-03/`：默认相册名通过；省略 RecentPhotoOptions 返回401，
  显式 options 被修改，picker 非整数上限错误返回13900020。新增完整 JS 精确补丁修复
  默认参数/调用者对象保留、异步 RPC 连接所有权/期限、标准401与callback重载。
- `photos-recent-wrapper-arm64-r15-01/`：固定产品实际 es2abc 编译通过；
  主机完整 JS 130项边界通过，但均不是新镜像运行证明。统一门槛增加普通应用
  `photos-recent`，只验证元数据和参数契约，不把空图库当作正向资产、FA卡或云服务证明。
- `r14-photos-source-diagnostic-01/` 的截图超时保留为失败；02曾被中断，
  其错误的旧诊断pass已由同目录 `INVALIDATED.json` 明确作废，不能用于验收。

下一首包候选还加入独立 Fusion 服务 domain/SA 注册策略，没有放宽SELinux模式、
白名单、token或UID。需经过完整策略编译与新包启动验证后才能登记修复。
现有原始缺口清单保持不变；本节不更新未经完整重跑的剩余数量。

历史资源清理记录：`/Volumes/PSSD/qemu/validation/cleanup-duplicates-20261009.json`。
删除151个与保留归档逐字节一致且未打开的重复镜像，约63.8GiB已分配空间；
保留全部归档、诊断userdata、日志与元数据，可按证据记录从归档恢复。

## 当前续修状态（2026-10-07，首包门槛仍未通过）

用户已明确批准 RS 私有对象编码修复。`async_caller_identity` 统一栈新增
0009：两类 command `sptr` 使用标准 Binder 对象，普通延迟副本及 ashmem
sidecar 在请求返回前通过标准读写生成自持有 MessageParcel，不对共享字节中的
cookie/handle/PTR 调用对象读取或 AcquireObject。DBinder PTR/strong pair 校验
flags/长度/相邻 offset 后作为一个逻辑对象；对象重编码长度变化时重建后续字段。
FD/FDR、FD 0、部分写入失败和取消均保留单一资源归属。权限、真实内核 PID、
节点归属、异步调用及公开 API 不变；新六包同步重建，不兼容旧错误私有编码。
当前14文件 exact 栈在真实固定源码首次/重复应用通过，证据
`exact-component-stacks-object-05/evidence.json`；前两轮错误源哈希/补丁路径拒绝
保留，不改只读源码。7项实际新增 C++ 片段的主机 ASan/UBSan、OS FD 和引用
生命周期测试通过（6.624秒），`host-rs-object-encoding-03.log`；测试的 Parcel/
对象持有部分是具名 fixture，不是实际 Binder/guest。真实三 ABI 编译第18轮
发现头文件缺少 IRemoteObject 前置声明，失败证据保留；已修正，第19轮
10个真实编译单元×三 ABI全部通过。`rs-async-caller-three-abi-19.json` 及同名
`.logs/` 已保存；30个实际编译日志和component apply日志的复制SHA复核一致。
首包02已生成新归档；18项实际RS/IPC产品类边界已在该归档通过，见下文。
这不是完整跨进程、权限或全部图形能力闭环，不能仅据此登记全部对象编码修复完成。
另用真实三个产品命令补充编译完整 `rs_command_factory.cpp`，验证排除POD sptr
兜底后所有已注册绘制命令的模板仍可实例化；三ABI全部通过，证据
`rs-command-factory-three-abi-01.json` 及同名 `.logs/`。它明确标记为补充选择，
不冒充重复完整编译；与第19轮的component payload SHA完全一致，合计覆盖
11个真实TU×三ABI的33次编译，复制日志SHA已复核，仍不是链接或guest验收。

正式 M144 依赖 R18 的原生内核及官方 HAP/签名/五库转换复核通过：当前 recipe
`3c0d5cd7d3302a0fad81b2056f947299c8258897e23a1c2e338a40baefd8b350`，
ARM64 core manifest SHA-256
`388b2b1676883be667a51116237a20536fd8cd2fb68e2eaf148ee5a43fa7dfcc`，
HAP SHA-256 `c09e2f3e2dfd664b307015fee9c66634db2b376b3c1b19e9314001babb37db87`。
同一 R18 流水线的 ARM64 V8 已完成 4524 个 Ninja 步骤，并通过正式 JSVM artifact
校验。V8 manifest SHA-256 为
`af928e8b5c26def7c4e71d34c2c23313ed473cf6cbc0b4a631ea719dfbcabbee`，
实际 `libv8_shared.so` SHA-256 为
`c805d8d82fe4b128cb847fcfb35cfc2eb455bb8867dfd481fed014487fb110cc`，
宿主独立计算与 manifest 一致。SwiftShader 的1192步也已完成并通过正式校验，
manifest SHA-256 为 `b1ec03a25246b079dba732f0a3222bf243cbd154eb6c0a7b3ec9d77da5f06b0b`，
实际ICD SHA-256 为 `8284ae0540c98e7db1fa105d0844fe06692e50be4bb80af4e6fe9ae8cefd7591`。
AVC正式校验随后通过，manifest SHA-256 为
`94a07c8674931f4dcb7f64da9136458b01ae887a4c8c6a53c1d34d755aa7fe9a`；R18外层依赖命令
exit_code=0，完整日志为 `m144-dependency-arm64-r18-01.log`。以上不是新 QEMU 包、
JSVM执行、Vulkan上屏或AVC guest 验收。
2026-10-07 02:55:36 UTC 已经通过四类依赖的独立preflight并启动仅 ARM64 phone
首包构建，目标目录
`/Volumes/PSSD/qemu/packages/first-rs-objects-7.0-release-20261007`，冻结入口
`/Volumes/PSSD/qemu/build-inputs/phone-pdoJt7`，输入树SHA-256为
`23ee06099ac8e2123abfd6968cd2d0d899481754d8349bed4bbc29739dd8fce3`。
本地Docker使用 `ohos-qemu-build-env:7.0-release`、BUILD_JOBS=4、KERNEL_BUILD_JOBS=8，
只选择PRODUCTS=arm64_virt和DEVICE_TYPE=phone，manifest仍是固定7.0 Release commit。
构建日志为 `first-rs-objects-arm64-phone-build-01.log`。该次在HB LOAD调用原始
GN格式化 rust_atty/BUILD.gn 时以SIGILL失败，未进入系统编译、未生成新归档；
失败构建目录和输入冻结保留。只读复验相同GN和输入，原生及qemu-user各64次
格式化均成功、结果一致，因此目前仅将宿主翻译不稳定作为推断，不声称已经
定位具体非法指令，也不能将这些复验计作镜像行为通过。
新增 `common/build/host_gn_execution` 独立exact组件：两个Python调用点在显式
启用时使用qemu-x86_64-static -cpu max执行原来的固定GN，保留所有argv和失败
传播；非GN命令及GN二进制不变。ARM宿主的amd64 Docker入口自动选择此模式，
本地派生镜像安装执行工具，其他五包使用同一脚本路径。宿主工具修复须通过
新首包重试验证；02已完成归档及校验和，尚无boot/行为通过结果，
首包门槛仍为false，其余五包未启动。

宿主修复已用实际固定文件首次和重复应用验证；本地派生镜像
`ohos-qemu-build-env:7.0-release-gn-qemu-user`（镜像ID
`8f7a960c7dc515a597d43a510d6d8a5e634e5c94a55aa5d9e22bfbf6b0f42c55`）中
实际调用修复后的file_utils.write_file执行64次原始GN格式化，全部一致，错误
语法以exit=1传播，原始GN SHA保持不变。证据为
`gn-host-caller-runtime-01/evidence.json`和同名.log/.py，仍不是系统包验收。
第86轮全部763项主机回归通过（102.776秒），日志
`host-regression-capability-86.log`。2026-10-07 03:21 UTC开始仅ARM64 phone首包
重试，新的目标目录为
`/Volumes/PSSD/qemu/packages/first-rs-objects-7.0-release-20261007-r2`；命令保存在
`run-first-rs-objects-arm64-phone-02.sh`，build/runtime/gate分别使用02日志，
不覆盖失败的01目录。该命令在新归档完成后立即计算校验和、启动它进行全套
行为检查并执行严格首包门槛；不会启动剩余五包。
本次冻结入口 `/Volumes/PSSD/qemu/build-inputs/phone-edFWaW`，输入树SHA-256为
`8a11e14ea2ab569d08f31f090786ac9bbaca21b63a12fb94797da160f1d7fa36`；
宿主独立重算当前仓库、冻结树和manifest全部文件相等，证据
`first-rs-objects-build-inputs-host-validation-03.log`。此输入一致性不是行为验收。

2026-10-07 07:12:23 UTC，02完整ARM64 phone系统编译成功（3:44:01），
随后离线最终镜像检查和打包成功。首归档为
`/Volumes/PSSD/qemu/packages/first-rs-objects-7.0-release-20261007-r2/openharmony-qemu-arm64-arm64_virt-phone.tar.gz`，
864639459字节，SHA-256
`ee45c3fe022bb390426010f1a7a26910d0d24584551d8925b0a09c08dbf27c93`；
原始校验和记录 `first-rs-objects-arm64-phone-archive-02.sha256`。本地Docker环境
与命令仍为上述02脚本和派生镜像，API26 Release SDK来自
`provider-sdk-26-full/26.0.0`，Python环境 `/tmp/ohos-capability-tests-pvk51rjh`。
运行命令为 `scripts/validate_packaged_qemu.sh --package-archive <上述新归档>
--package-directory <同名目录> --evidence-output <r2目录>/first-artifact-behavior.json`，
随后执行 `scripts/verify_first_artifact_gate.py`（product=arm64_virt，device-type=phone）。
新归档已全新解压启动，实际运行工作目录
`openharmony-qemu-arm64-arm64_virt-phone-runtime-97vh58m0`。该次无外部keepalive
启动及两轮真实默认休眠/实体按键唤醒/合成器检查通过；boot ID为
`9f7887b9-df52-4d6d-8910-006a87d27cae`。全套随后因锁屏持有10000ms
PowerMgr override而拒绝覆盖，在应用测试准备阶段失败，保留原始
`first-artifact-behavior.json`及02 runtime日志。gate命令因set-e未执行；
不能将两个通过项当作完整验收。此时首包门槛仍为false，其他五包没有启动。

同一02归档另以原始内核、系统库和默认策略启动独立私有HVF诊断，boot ID
`c0016eb8-8f6e-45a5-abb7-713336e0c7ea`，target `127.0.0.1:60467`。
`lockscreen-new-package-02-01/boot.json`保存实际QEMU命令、进程及归档SHA。
普通UITest从真实锁屏节点向上滑动后，系统自行撤销10000ms override，
base=9000000ms不变，RenderService/Foundation PID及内核UUID未变；实际布局
从ScreenLockRootComponent切换为SCBDesktop_Flex_Desktop，截图经人工检查。
证据 `lockscreen-actual-gesture-01/evidence.json`，没有执行PowerMgr restore、
特权解锁或权限放行。默认套件现先执行此有界普通手势准备；未知override、
凭据/未知界面、错误节点和服务重启均失败，不兼容强行清除其他客户端状态。

该独立新包诊断的 `rs-objects-new-package-02-01/result.json`实际18项全部通过：
普通/ashmem、0/65536/900000字节payload、null、FD 0、跨线程消费/取消、
128轮生命周期及4种损坏sidecar拒绝；实际调用产品DSO，无系统库替换。
普通账号100新HAP的 `web-new-package-02-01/evidence.json`通过JavaScript/DOM、
Canvas2D、WebGL1/2全像素读回/错误shader、双向proxy、reload和renderer终止恢复。
不能仅用WebGL代替独立Vulkan或可见浏览器上屏测试。

独立原生Vulkan设备队列1024-word读回、headless swapchain及OHOS NativeWindow
10帧/1500像素/尺寸变化边界全部通过，证据
`vulkan-{device,headless,ohos-surface}-new-package-02-01/result.json`。
可见窗口第01次native提交/销毁/重建完成，但两张截图仍为启动图，严格像素验证
失败，原始失败保留。之后 `graphics-new-package-02-diagnosis-02/` 的系统截图
和QMP物理显示均已出现真正应用及预期色块，物理显示实际核对46110像素；
未替换库、重启服务或改变图形参数。同一归档的完整窗口复跑
`vulkan-window-new-package-02-02/verified-result.json`通过两代各46110像素及
真实销毁/重建。首次失败的精确延迟原因尚未证实，不宣称永久截图故障已修复。
验证入口现区分queue-present与真正合成器呈现，最多60秒等待实际完整像素，
保留每次失败截图，畸形布局/尺寸不符立即失败，不放宽颜色或以日志替代截图。
这些测试入口变更改变冻结输入，下一轮必须重打03新首包并重新执行完整套件；
02的独立通过不能拼成03完整首包门槛，也没有关闭全部C++/ArkTS1.1审计缺口。

上述入口及负例修正后，第87轮完整776项主机回归通过（106.134秒），证据
`host-regression-capability-87.log`；真实02归档的已解锁桌面准备也通过
`application-home-new-package-02-01/evidence.json`，没有新增手势或修改电源策略。
2026-10-07 08:03:32 UTC启动03代表包，命令
`run-first-rs-objects-arm64-phone-03.sh`，目标目录
`/Volumes/PSSD/qemu/packages/first-rs-objects-7.0-release-20261007-r3`。
新冻结入口 `phone-tJz4BX`，902个输入树SHA-256
`87a0d5d90822792b9f423167ce39caaddd75a68d98a22f21d0a9fba323845b18`，
宿主独立重算仓库/冻结树/manifest完全一致。M144 dependency recipe仍为上述
3c0d5cd7，系统源码、内核、图形实现和依赖不因测试准备时序变化而替换；
本轮仍只打包ARM64 phone，并自动启动新归档全套验收和严格首包门槛。
截至该启动记录尚无03归档/SHA/guest结果，其余五包没有启动。

03随后完成系统编译和离线镜像检查，生成新的代表归档
`/Volumes/PSSD/qemu/packages/first-rs-objects-7.0-release-20261007-r3/openharmony-qemu-arm64-arm64_virt-phone.tar.gz`，
864664435字节，SHA-256
`a81bfc82bc1a33262a6be56b7ab0a1f6e5b684f44c85237cf4328a95687196ce`。
原始记录为 `first-rs-objects-arm64-phone-archive-03.sha256`；实际新解压运行目录
`openharmony-qemu-arm64-arm64_virt-phone-runtime-blpl6kmj`，boot ID
`80320a10-ca90-4775-b20b-9b5916e6ebed`，本地macOS ARM64/HVF，API26 SDK、
Python环境及本地Docker构建命令沿用03脚本，未替换任何客体系统库。
截至2026-10-07 09:14 UTC，实际新包boot、默认休眠/唤醒、普通桌面准备、
Native ABI、内核bitmap/user-ID/BPF、Binder身份89项、RS对象18项、AudioSuite、
UDMF/Pasteboard/AVPlayer退出回归、证书两角色、普通ArkWeb，以及独立Vulkan
可见窗口销毁/重建的真实像素测试均通过。普通user-ID、i18n、matrix4、factory
和const enum契约也已通过；套件继续执行contact-sync-mode等后续用例。
这些结果只证明各自验证范围，不包含全部Provider/虚拟硬件闭环；当时没有
完整套件或严格首包门槛通过结论，其余五包仍未启动。

03完整套件于09:14:45 UTC在普通contact-sync-mode HAP处失败：安装、普通身份、
Ability启动均成功，但300秒内没有产生nonce绑定的结果文件；原始失败归档、
应用、157次结果轮询及enclosing报告保留，没有伪造枚举值或继续矩阵。
具体是哪个枚举或模块导致应用未完成尚待独立定位，不能凭源文件已打补丁
宣称这三个运行值已通过。另修复测试基础设施的独立清理问题：QemuGuest.start
在进入with主体前被KeyboardInterrupt等异常中断时也必须清理自己持有的进程，
即使写boot证据失败也执行cleanup；11项主机测试通过，证据
`host-boot-interrupt-cleanup-01.log`，这不是系统能力验收。

后续使用03原归档、原内核/系统库的新私有HVF诊断启动，boot ID
`df82c195-3349-4a8a-b2c6-52bce3a3aa66`，target `127.0.0.1:55087`。
`contact-enum-new-package-03-02/diagnostic-02`的真实应用崩溃记录确定为
公共`photoAccessHelper.FusionAssetType`未定义；原生001已提供numeric 0，
但固定源码`photoaccesshelperinf.js`没有转发。新增独立002只转发原生对象，
不补假枚举、不改存储/权限。原生CPP postimage不变，公共JS postimage SHA为
`b283d47255e633b5ed1b0f0ae27ef98ddc835d69ab60cdd2137e50da55ef1439`。
首次/重复/已知001前缀/未知修改的4项测试通过
`host-photo-public-wrapper-01.log`；真实产品Ninja命令生成新的
photoaccesshelper.abc（50532字节，SHA
`c9d280045d8a4f41861ae5314411752205a4745d2b35e2cbafa243b3a1db2b4b`），
证据`photo-public-wrapper-next.7lRPxO/product-01/evidence.json`。
以上不是新包中公共模块执行成功，必须重打代表包验证。

同一私有03启动的剩余persona诊断不能合并进正式03全套报告。
`remaining-personas-01`的ThreadWorker、PCM流、AVC编码和AudioSuite效果通过，
Legacy Worker在旧应用卸载/会话异步关闭时被AppMgr终止；增加只针对专用
审计bundle的`aa force-stop`及kernel PID/账号100 AA记录两次实际缺席检查后，
`remaining-personas-03/worker-legacy/evidence.json`通过。停止超时、未知回复、
错误dump或boot变化均失败，不修改Worker实现或权限，仍须新首包回归。

Camera诊断另发现两层问题。测试使用UIAbility模块context，结果位于
`haps/entry/files`，不是应用context的`files`；轮询和照片取回现使用同一真实
模块私有目录，不修改相机实现来掩盖测试路径错误。
`remaining-personas-05/camera`经过真实PermissionManager Allow后，NDK两轮
预览生命周期共61项检查通过；ArkTS实际photoProfiles却只有1003/1005的YUV
规格，没有JPEG=2000，因此拍照仍失败。新增`camera/jpeg_capture`四文件
组件仅在现有QEMU Vivid开关下广告实际枚举YUYV尺寸可软件编码的JPEG规格，
不广告JPEG预览/视频；BLOB输出不再无条件要求设备MJPEG输入，实际MJPEG
支持仍按真实查询选择。原有权限、节点过滤、非QEMU行为不变。
`camera-jpeg-profile-next.pOiLcA/three-abi-01/evidence.json`证明两个完整TU、
三个ABI、开关开/关的12次真实产品参数编译；显式候选define不冒充重生成GN。
同目录`component-source-01/evidence.json`证明固定实际源码首次、重复及前置
USB组件重复兼容，五个操作全部退出0；4项sanitizer/状态夹具通过
`host-camera-jpeg-capture-03.log`。它们不是新包拍照或完整Camera验收。
所有诊断均保留原失败、原包SHA、同一boot及有限测试电源override恢复证据；
未替换客体系统库或执行shell权限grant。当前六包门槛仍未通过，其余五包未启动。

2026-10-07 10:03:13 UTC启动04代表包，入口
`run-first-rs-objects-arm64-phone-04.sh`，仍仅ARM64 phone，目标目录
`/Volumes/PSSD/qemu/packages/first-rs-objects-7.0-release-20261007-r4`。
冻结输入`phone-Og7eZd`共914文件，树SHA-256
`42e7a890c5a1281c077cfaca24fb136152a956f331ab44f2571cd4011f92a24e`；
仓库、冻结副本和manifest独立重算一致。上述公共相册转发、相机JPEG以及
实际模块context/应用会话清理修正已进入此轮。第89轮完整788项主机回归通过
（145.703秒），证据`host-regression-capability-89.log`，不是guest能力通过。
本轮构建和验收期间保持scripts/patches/ci及门槛台账冻结，不启动其余五包。

03私有启动的当前bindings全集第01轮实际跑到全部32模块，Hypium原始结果
为102个通过用例；但完整driver退出1：XComponent的两个describe分别报告
`OHOS_REPORT_SUM: 3`和`1`，旧结果校验器只接受单一总数，尽管四个用例的
全局numtests、逐项成功和最终汇总一致。原失败报告保持fail。独立包外工具
`bindings-hypium-next-candidate-01/`现在按实际组边界核对各组完成数量，并
额外要求每个start/pass成对、原源码全部用例顺序及零skip/ignore，6项主机
回归通过；未修改用户bindings仓库或测试断言，也未修改04冻结验收输入。
其driver自己的电源cleanup已恢复override=None，外层重复`timeout -r`返回
failed，二层策略归属仍需正确整理，不能把这个整轮改写为通过。
更重要的是，该boot随后在第二轮应用重装期间发生真实
`render_service(pid 554) exit with signal : 11`（客体uptime 4049.847秒），
原boot证据已更新为fail，监控关闭了自己持有的VM。第二轮driver被明确中断，
记录`current-native-bindings-02/owned-abort-after-real-RS-crash.json`；不能拼接
前一轮用例成功成为稳定性/首包门槛通过。原userdata和串口保留用于崩溃取证。

WLAN独立诊断`radio-new-package-03-05/archived-hwsim/evidence.json`首次在真实
03归档模块上确认ARM64的额外根因：cfg80211装载时缺少rfkill_*内核符号；
该架构CONFIG_RFKILL=m，但GN/vendor模块安装没有携带rfkill.ko。
诊断仅向专属诊断VM装载原归档模块，实际cfg80211失败，未替换客体库或模块。
包外`wlan-next-candidate.A8nJvH/components-02`保留真实hwsim双radio启动，并
把ARM64 rfkill改为内建；ARMv7a/x86_64原配置已为y。
`rfkill-source-preflight-02/evidence.json`证明固定真实源码首次/重复应用及
未知、partial状态拒绝且保留源文件，仍不是内核链接、新包无线或STA/AP/P2P闭环。
随后仅在旧03归档的独立诊断VM中，从同一产品构建输出取出真实ARM64
`rfkill.ko`（SHA-256
`2f3fe5c16e30cdb9902325b2cacf1a123df6c72629eefd8127083749fa17d90e`）
并按实际SHA推入/加载，然后加载归档内原始四个无线模块；
`radio-new-package-03-11/archived-hwsim/evidence.json`记录boot ID
`f29968a6-4001-40fb-b35e-70e23bf2a1c7`，真实网络接口从`eth0,lo`
变为`eth0,hwsim0,lo,wlan0,wlan1`，两个wlan分别指向不同phy；Foundation
及RenderService PID前后不变，诊断通过。`/proc/net/wireless`旧WEXT表不存在，
并非nl80211/hwsim必备条件，诊断器现在只记录该边界。此验证主动修改了
旧包诊断客体模块状态，不证明04或后续包的自动启动，也没有覆盖Wi-Fi
STA/AP/P2P、鉴权关联、真实流量、应用权限或全部架构；首包门槛仍未通过。

热管理包外候选另外按API26可选callback契约接受显式undefined，且参数错误
或远端注销失败仍保留真实监听。`thermal-next-candidate.GP6SFz/optional-callback-01`
记录新CPP SHA `63da35b900b697d14dbc1f62b7073d47da074edb3b391ccf33111551d97f1dad`，
三ABI实际产品TU编译、四部件首次/重复八次应用通过；精确候选方法ASan/UBSan
具名夹具3435项断言通过，覆盖旧/新接口、排队取消、显式undefined与服务失败。
它们不是真实ArkVM/Binder/热后端验收，未纳入04，不复用旧CPP的DSO链接证明。

第85轮当前完整主机回归757项通过（148.001秒），证据
`issue-20-20261006/host-regression-capability-85.log`；第84轮754项（277.679秒）、
第83轮754项、第82轮752项及第81轮748项历史证据保留。
新包套件增加 `backend-inventory/inventory.json`：在同一真实新包 boot 的应用测试
设置之后只读记录热温区、实际热配置、网卡和蓝牙设备，原始文本绑定SHA，前后
核对kernel boot ID。其status明确为diagnostic，不注册任何能力闭环，不计入
行为通过项；3项host契约验证缺失设备不被误判为pass、boot变化及输出覆盖拒绝。
热管理源码补查确认：固定 `device/qemu` b017aee8 的 ARM64/x86_64 配置开启
CONFIG_TEST_POWER，而 ARMv7a 未开启；Linux 6.6 test_power 的温度属性返回26，
power_supply_core按0.1°C到m°C乘100，注册温区名为test_battery（即2600m°C）。
固定 thermal HDI 69094b77 的通用配置却选择sim_tz=1并创建9个初值0的模拟温度
文件，actual组仅寻找soc-thermal/gpu-thermal；热服务dbba4e1d同样使用lya配置。
这些是适配依据，不是新包运行结果：不能仅给模拟文件写常量作为能力修复，也
不能将当前ARM64温区的存在推断为其他架构已可用。当前thermal缺口仍未闭环。
首包02编译期间，在独立目录 `thermal-next-candidate.GP6SFz` 准备下一轮热配置，
没有修改当前仓库输入、只读源码卷或正在构建的首包。候选将已有内核
test_battery温区通过HDI的replace属性映射为battery，service使用现有sensor
cluster/thermallevel action，不伪造CPU/GPU等物理温度或宿主电池值。真实GN的
具名prebuilt模板fixture已在第03轮验证六种QEMU选择及两个非QEMU选择；
随后按真实模板的 `output` 属性补上原安装文件名约束，第04轮fixture因GN
非空列表覆盖而失败；只修正fixture为if/else，第05轮8项全部通过，最新证据
`thermal-next-candidate.GP6SFz/preflight-05/evidence.json`。它仍不是生产GN图或
实际安装结果，不将历史失败改写成通过。
三架构真实Kconfig parser在各自只读6.6.101准备树上规范化独立临时配置，
TEST_POWER/THERMAL/THERMAL_EMULATION/POWER_SUPPLY均为y，证据
`kernel-config-02/evidence.json`。早期fixture导入/unused变量失败及使用6.6.0
覆盖参数的配置01记录保留；只采用从真实Makefile读取版本的配置02结果。
候选仍需按部件整合、原生解析、内核编译和重新打包后的等级、迟滞、回调、
撤销/恢复等实测；不计入首包门槛或thermal闭环。
独立候选新增真实HDI/服务配置类及sensor-cluster调用探针，原生编译第04轮在
三种产品实际Ninja命令下全部通过，证据
`thermal-next-candidate.GP6SFz/native-three-abi-04/evidence.json`；probe SHA为
`e2fffed654753eadd999478c7a8f95ee96daf4319287fa4d203470db3f85898a`。
它使用真实HDI/SA/libxml生成输入，没有替代解析器或声明；只产生ThinLTO对象，
尚未链接或运行。01缺HDI头、02查询未选中的v1_0目标、03因实际IDL生成器
要求输入W_OK而被只读源卷拒绝，三次失败保留。04改用字节相同的独立输入
副本，真实源卷仍只读。当前首包输入仍为phone-edFWaW，候选未整合入包。
进一步比对实际API26声明和固定thermal NAPI，发现旧subscribe接口声明为
AsyncCallback(error,level)，实现却与新register共用单参数回调；unsubscribe
也先释放监听再校验可选回调参数。这两处需单独修契约和生命周期并用普通
HAP验证新旧入口、非法参数保留监听、排队事件、自注销、重注册及环境退出；
backend XML修正不能代替NAPI修复。WLAN补查也确认：三架构配置虽选中
mac80211_hwsim模块，当前init仅加载cfg80211/mac80211/iwl模块；芯片级HDI
尚未注册，默认vendor=hardware，default HAL的部分查询仍依赖实体私有ioctl。
因此不能只加载虚拟无线模块或打开feature就将完整STA/AP/P2P标记闭环。
热管理独立候选的两个NAPI文件随后通过三架构实际产品编译，证据
`thermal-next-candidate.GP6SFz/napi-three-abi-01/evidence.json`。同一文件哈希下，
精确提取候选方法的具名VM/Binder宿主fixture在ASan/UBSan下3388项断言通过，
覆盖新旧回调、事件值与顺序、非法参数不撤销监听、替换、自注销、环境清理、
引用/handle归还和四线程投递。证据为 `callback-host-03/evidence.json`；前两轮
因fixture错误地从工作线程取得thread_local监听对象失败，保留失败输入，修正为
投递实际已订阅对象后重测，未修改候选实现。它不是真实ArkVM、Binder或客体验收。
原生客户端另外六处订阅/撤销方法忽略远端返回、仅连接成功就返回true，独立候选
改为仅ERR_OK返回true，保留公开bool接口、原参数/连接检查和权限路径。三架构实际
编译通过，证据 `client-three-abi-01/evidence.json`；精确六方法的具名RPC返回fixture
通过，证据 `client-host-01/evidence.json`，仍不是真实IPC/权限拒绝实测。
普通ArkTS1.1热管理HAP无申请权限，三种架构构建选择均编译通过，证据
`hap-{arm64,armv7a,x86_64}-01/evidence.json`。这是纯字节码未签名HAP，不宣称
native ABI或安装运行通过。上述候选均位于包外，尚未整合、链接或新包验证，
当前首包输入与thermal未闭环状态不变。
后续独立热内核对象验证已通过三架构共12个真实ELF对象：test_power、
power_supply_core、thermal_sysfs与thermal_core。实际GCC、Make/Kconfig、
归一化配置和对象ABI/SHA记录于 `kernel-objects-three-abi-01.json`；只读源卷
未改动，使用已停止且有编译证据的内核头准备树，仅向本轮输出目录写入。
它不包含完整内核链接、打包或启动结果。另保留初版HAP，增加独立
`boundary-app/`：回调内重注册、不可变订阅编号及具名3500ms排队窗口，分别
检查原事件值、排队后撤销/替换；宿主必须另外证明真实provider转换发生在
窗口内，窗口起止本身不能算通过。三个构建选择通过且宿主重算HAP/source
哈希一致，证据 `hap-boundary-{arm64,armv7a,x86_64}-01/evidence.json`；仍未运行。
热候选现按HDI配置、服务策略、NAPI契约及客户端reply拆成四个部件，七个
源文件各自独立patch/apply入口，仅保存在包外 `components-02/`。固定两个
实际project HEAD及原文件SHA后，首次/重复共8次应用通过，结果与上述编译
候选完整文件哈希一致；未知修改负例被拒绝且所有文件保留，证据
`component-source-02/evidence.json`。首轮误把NAPI的构建目标目录当源码目录，
在复制预检即失败、没有执行任何patch，记录 `component-source-01/` 保留。
新增资产的None preimage支持目前也仅在包外helper副本中，9项具名宿主测试
覆盖不存在/空文件区分、partial状态、未知文件、symlink、越界patch及marker
不授权跳过，证据 `component-assets-host-01/evidence.json`；尚未改仓库helper。
另在只读生产source/out的独立已完成DSP树克隆中启动真实产品GN/两资产构建
验证，目录 `/tmp/thermal-product-GN-assets-01`。该轮四个热组件及host-GN组件
首次/重复共10次应用通过，但生产GN退出255（内层GN返回1），两资产构建未执行；
失败记录 `product-GN-assets-01.json/.log` 保留，不计为装配通过。直接用相同
GN/args在该独立副本重现时，父/子进程均等待futex；仅结束已核定身份/目录
的诊断进程，主构建未动。6分钟限时的单工作线程诊断也超时，证据
`direct-GN-single-worker-01/evidence.json`。原始同一GN二进制的未显式qemu
执行对照已返回1，证据 `direct-GN-original-native-01/evidence.json`；实际错误
是旧DSP验证副本缺少本轮新装入的 `foundation/multimedia/av_codec/qemu_avc`
目录，不能据此归因于thermal配置或QEMU工具。正在该独立副本中以只读生产
输入的字节一致副本补齐此目录后，原始GN成功生成完整产品图，实际Ninja
两个prebuilt目标成功安装原文件名，配置字节分别匹配4483da57与1ba15e29，
全部7个候选源码postimage保持不变；证据
`product-GN-assets-repaired-seed-02/evidence.json`。未改主构建，这仍不是新包
运行或thermal闭环。
当前首包898个
冻结输入已再次核对仍为8a11e14e，热候选与新增helper均未装入首包02。
新包套件另增加18项直接调用产品 RS/IPC DSO 的边界探针及严格 transcript verifier，
覆盖普通/ashmem、三种payload大小、空对象、FD 0、跨线程消费/取消、128轮生命周期
及四种损坏sidecar拒绝。只传可执行文件，不替换系统库；它是实际类边界，不能
替代 Web/Vulkan 的跨进程或UI测试。该项已作为首包独立必需检查；02归档的独立客体18项通过见上文。
首包02后段构建期间，该探针已用实际产品Ninja编译参数链接当前新建的
RS/IPC/utils库成功，证据 `rs-object-first-current-product-link-01/build.json`；
它记录三个产品库与调用程序哈希，不能替代新归档中的运行结果。
热候选另新增只读 `thermal_service_sample.cpp`：先发现实际SA并检查真实
GetThermalLevel/GetThermalSrvSensorInfo的IPC回复、battery类型，再读取实际
客户端查询值，记录nonce、boot ID与采样时间；不注入温度或注册假服务。
`service-sample-three-abi-01/evidence.json` 记录三架构实际产品参数编译及
ARM64当前真实产品client/registry/IPC/utils库链接成功。宿主控制器仍须核对
温区与实际转换，探针编译/链接或一次成功回复均不能关闭热后端缺口。
包外四项热组件链接预检 `product-component-links-arm64-01/evidence.json`
触发旧DSP out的13912个依赖动作，已仅结束核定argv/parent/PGID/out目录的
诊断Ninja组并保留-15失败记录；首个保护检查因实际cwd为Ninja的-C目录
而拒绝发信号，核定完整命令后才执行。主构建未动，候选完整链接仍待本轮
完整产品输出后验证，不计为通过。
随后在只读当前完整产品输出上补做两个候选TU的真实ARM64共享库链接，
`compiled-product-links-arm64-03/evidence.json`通过客户端与NAPI配套链接。
仅替换已经三ABI编译验证的候选object，响应参数来自实际Ninja的solink规则
及目标edge；NAPI链接到候选客户端，保留实际CFI、sysroot和其余依赖，
输出及LTO cache均在私有/tmp目录。前后图、实际输入及候选哈希未变；
客户端库SHA为22cd651fdbc04c2740cd847f31298162a52346f7bd9fa574a6077dbc6e4ca08b，
NAPI库SHA为a906eec444dbedeb76d5b9adffb7a2128046d0ab36b43e400eac5f9125588535，
复制证据和两库到宿主后重新核对一致。01的Python3.8 hash API错误、02未展开
response参数的拒绝仍保留；这些是预检工具失败，不隐去失败历史。
此通过仅为两个候选TU的真实产品命令链接，不是完整四组件Ninja构建、
三ABI链接或guest能力验收；没有替换任何客体库，03首包冻结输入仍为87a0d5d9。
包外 `run_thermal_backend_candidate.py` 现准备28个实际provider阈值/回差步骤，
先拒绝错误归档、外国QEMU/boot、未装入上述固定配置、未知vendor覆盖及
非默认test_battery温度，仅传递真实client-linked采样可执行文件。
每步独立核对内核温度和实际SA/client回复，要求跨两个1000ms轮询周期稳定，
保留非原子多次RPC在转换时的不同读数、不接受其为稳定通过；结束后写入零值
关闭Linux温度模拟，并复核2600m°C/level 0及服务PID不变。实际6.6内核的
emul_temp为DEVICE_ATTR_WO，脚本不声称读取初始或最终emul_temp状态。
7项主机计划/JSON/身份/类型/错误路径负例通过，记录
`backend-controller-host-01.log`；这是测试控制器预检，尚未执行客体测试，
不证明温区、HAP回调或thermal缺口闭环，也未装入03首包冻结输入。
另在包外 `wlan-next-candidate.A8nJvH` 准备virtual WLAN radio bootstrap：
固定QEMU b017aee8原始init的boot job只加载Intel模块，缺少已配置/打包的
mac80211_hwsim；候选保留原CRLF，以两个真实hwsim radio取代无对应设备的
Intel加载，不改权限、不将eth0重命名、不启用vendor chip false-success。
另用02归档准备两次独立无线bootstrap诊断，均未实际加载模块，不能计作
WLAN backend通过。第01次先遇到SDK HDC全局临时PID锁，独立端口并不自动
隔离该锁；在私有临时目录启动独立HDC后可正常checkserver，但客体未完成
连接，实际一次电源键输入仅记作辅助诊断，物理显示捕获不活跃。
中断启动上下文发现尚未进入with-body时不会自动关闭VM，已按精确原PID、
PGID、内核路径及QMP socket仅关闭该孤立客体，原始记录保留。
第02次在独立HDC就绪后以verbose诊断命令行成功连接root/API26/phone及
前台账号，但默认休眠后的60秒静默阶段没有自动唤醒，后续boot-ID查询超时；
实际串口确认sleep，失败boot.json保留，原脚本正常关闭该VM。
两次记录分别在`wlan-radio-new-package-02-01/`与`wlan-radio-new-package-02-02/`；
私有HDC也已关闭，用户原有HDC/QEMU未动。尚不能据此定位第01次的精确
客体离线原因或关闭Wi-Fi缺口；当前首包03正式套件已有独立真实GPIO唤醒验收。
真实只读源码字节副本上的首次/重复应用、未知状态拒绝保留全部文件、
三架构源Kconfig的cfg80211/mac80211/hwsim=m及实际init选项传递检查通过，
证据 `source-preflight-02/evidence.json`。01因checker假设post-fs而失败，实际
源job为boot，仅修正checker，原失败保留。此候选未进首包，实际PHY/WPA、
扫描/关联/数据、AP/P2P、MAC/能力协商和普通应用权限边界尚未通过，WLAN
缺口仍未闭环；不能把源配置m或init patch通过当作无线API可用。
探针本身已用第19轮真实 helper 的编译参数/完整生成输入完成三ABI编译，目录
`rs-object-probe-{arm64,armv7a,x86_64}-04/`；当前caller/builder及输出对象SHA
已独立复核。实际参数开启ThinLTO，输出是LLVM bitcode，不声称已获得三ABI ELF。
此模式不链接旧产品库，不作运行证据；
正常首包套件必须重新链接实际新产品DSO再传入新guest。
定向实际OHOS链接driver复核发现 `-fno-ident` 在object-only链接时会触发
`-Werror`；已筛选并保留实际ABI/toolchain/LTO参数，三ABI `-###` 选择真实
ld.lld、musl及目标架构复核通过。该复核不执行链接、不生成guest可执行文件。
探针随后按实际Parcel语义加固：损坏侧带仅修改自持有buffer中的字段，不调用会
截断object table的RewindWrite；失败后检查两个真实对象释放。FD 0 场景在复制、
ashmem解析及消费者执行期间保持stdin关闭，要求实际ReadFileDescriptor返回0，
检查关闭后再用RAII恢复原stdin，不能只测试会立即被writer复制成正数的输入0。
这些新边界尚未在实际guest运行。
源码要求的九分类57规则审查已完成，未检出确定新增问题；报告
`report/report_rs_object_encoding_20261007_093932.md` 和同名CSV绑定0009及六文件SHA。
主机回归、静态审查和编译均不是 guest 或新包验收。
已授权的异步调用身份修复另增加真实PID命名空间探针，保留原有58项，并增加
自己的CLONE_NEWPID子进程存活/退出两轮，共89项严格运行检查：命名空间PID=1，
原proc视图TGID及内核sender-info均必须等于宿主真实发送进程ID，异步wire PID
仍为0，伪造PID/UID不得被采用。探针不mount、不unshare调用者命名空间、不动
系统Binder上下文；只关闭自己的vndbinder manager并清理自己的正数clone PID。
三ABI真实C SDK编译及ELF/当前源文件SHA复核通过，证据
`binder-namespace-three-abi-01/`、`binder-namespace-three-abi-inputs-01.json`。
5项host verifier回归通过 `host-binder-namespace-verifier-01.log`；旧58项guest
结果不能被新verifier放行，当前89项尚未在新包运行。
相机已接入默认新包验收：正常账号100应用仅声明CAMERA，使用真实
PermissionManager 中针对专用audit应用的可见唯一Allow控件，不通过shell
直接授予权限。实际源码中的51种本地化文本及61个相关输入文件已绑定SHA，
证据 `camera-permission-labels-source-01.json`。两轮活跃ArkTS预览要求真实
UITest节点、同阶段原始日志及compositor PNG独立复核；另检查NDK的61项
边界/回调、两次重建和4张实际JPEG。生成页、SDK声明/头文件和native源文件
均绑定nonce。三ABI unsigned HAP实际SDK构建通过，目录
`camera-sdk-three-abi-02/{arm64,armv7a,x86_64}`，对应3个 `camera-sdk-*-02.log`，
但没有在guest运行。独立复核另外定位到UITest矩形tuple在JSON后变成list，
导致真实证据无法精确比较；节点现在返回JSON稳定的list，不改变边界、选择
或点击策略。新增8项契约复核通过 `host-camera-contract-03.log`。包级闭环只
对应 `camera-host-backend-missing`，不扩充为全部视频/高级相机API。
unsigned HAP内容复核发现x86_64库被ArkDown置于完整intermediates子目录，
并非正常 `libs/x86_64/lib*.so`；编译成功不等于该包可加载。共享测试签名入口
现调用 `qemu_test_hap_archive.py`，仅修正这个已确认的精确布局并清除ZIP64
extra，保持全部库字节、代码、资源及权限；未知嵌套、路径冲突、软链接及错误
ELF ABI直接失败。原始unsigned包不修改，native-bindings signer同样复用该入口。
实际修正输出/字节SHA证据为 `camera-hap-layout-x86_64-01.json`，5项host边界
回归通过 `host-hap-native-layout-01.log`。三ABI实际官方code-sign/digest/permission
验签通过 `camera-signature-{arm64,armv7a,x86_64}-01.log`，签名产物位于
`camera-signatures-three-abi-01/`，只绑定已记录旧诊断guest的真实UDID，未安装
或运行；后续新包会重新构建、签名并验证实际加载。生产ArkWeb HAP使用独立
官方Docker构建链，本修复不改变其打包语义。
签名后的三ABI另通过实际canonical库路径、ELF类型/架构、当前SDK/生成页契约、
CAMERA唯一权限及与本轮编译库一致的`.text`内容复核，证据
`camera-signed-inputs-three-abi-01.log`；仍不是guest加载或预览验收。
证书查询返回 `undefined` 的根因已经定位到三类 NAPI 数组转换将 count=0
当作错误；同时空列表 owner 因 child=null 未释放。新增独立
`base/security/certificate_manager/empty_lists` 部件，只修上述5处条件，
非空/null、分配失败和权限错误仍失败，非空字段/协议不变。严格完整文件
状态校验入口已统一接入 Docker patch plan，旧 marker 不掩盖未知源码。
三个真实产品 `cm_napi_common.o` 复核通过，证据
`certificate-empty-lists-three-abi-02.json` 及同名 `.logs/`；JSON 保留容器内
`/tmp/` 原始日志路径，宿主复制按同名文件对应，原始证据未改写。最终源文件
SHA-256 为 `ff3c3d31531600f836c64e0817532a24147a44e99e21237d961515fef6bb1c20`。
第03轮再次通过相同三个真实对象，证据 `certificate-empty-lists-three-abi-03.json`
及同名 `.logs/`，额外绑定验证脚本本身的 SHA，并拒绝覆盖已存在或软链接证据。
2048轮空/非空释放、重复释放、真实补丁函数转换及未知源码保护的3项 host
测试通过，不代表真实 NAPI 服务/权限或 guest 已通过。新包套件增加两个
限定身份 HAP：只有2项文档证书权限的 system_core 应用测试真实空数组、
promise/callback、自己的PKCS12导入/查询/精确URI删除、边界和64轮空查询；
无ACL普通应用测试拒绝，保持镜像权限表不变。不卸载全部凭据、不删除任何
其他证书；原始 `certificate-manager-undefined-result` 保留，只有同一新包
boot 的两身份完整真实结果才登记闭环。
当前完整证书调用页的两身份×三ABI unsigned HAP 实际SDK构建均通过，
目录 `certificate-sdk-three-abi-02/`，对应六个 `certificate-sdk-*-02.log`。
ARM64两身份的真实 code-sign、digest、permission及提取后的profile验签也
通过，证据 `certificate-signature-{system,normal}-01.log` 与
`certificate-signature-01/{system,normal}-signed.signing.json`。签名仅绑定
已记录旧诊断guest的UDID，没有安装或运行，不能作新包权限验收；新包测试
仍会重新生成nonce、证书、HAP，并绑定实际新guest身份。
新增 `factory-objects` 普通 HAP 在 API26 Release SDK 三 ABI 的 unsigned
构建全部通过，目录 `factory-sdk-three-abi-01/{arm64,armv7a,x86_64}`；
当前 SDK 声明与生成调用源码的独立校验也通过。它仅针对 ResourceManager
`Configuration`/`DeviceCapability` 及 TaskPool `TaskInfo`/`ThreadInfo`/`TaskPoolInfo`
五个无构造入口的返回数据类型，不制造假运行时 class。15行严格结果要求全部
资源字段的 sync/promise/callback 一致性、返回快照隔离，以及两轮四个真实任务
的匹配 ID/名称/状态/线程、计算结果和完成清理。默认新包套件已接入；只有同一
新归档和 boot 的实际结果才能将原始五项标记为 factory-return 契约闭环。
原始审计项未移除，其余 ResourceManager/TaskPool API 不由此放行。
三个 unsigned HAP SHA-256：ARM64
`d5c1e574e3b705efeee62d82b4bd3fd25af47467d2b81f68215cada15fbdebc5`，
ARMv7a/x86_64（纯 ArkTS，无 native ABI 声明）均为
`52b10bef211d6a65082858f2c68694d91e8d854b6db78505b13ed1aef2ab556a`。
编译与8项 synthetic host verifier 回归不是上述能力已在新包通过。

R9 ARM64 phone 已在本地 Docker 完成系统编译和实际打包，路径为
`/Volumes/PSSD/qemu/packages/first-capability-repair-20261006-r9/openharmony-qemu-arm64-arm64_virt-phone.tar.gz`，
SHA-256 `f23fa7aa29ab88402a0ad72ec44c025ef22764586b4a79b5398635474fd66aa4`。
它仍使用先前的 ArkWeb/JSVM/SwiftShader/AVC 依赖，仅作诊断，不是统一依赖后的交付包。
全新解压后 HVF 与 TCG 均曾达到 API26、账号100和 boot completed，随后无保活空闲
验证失败。verbose 内核证据确认进入 `s2idle`、冻结用户进程，而不是已证明
RenderService 重启或仅 HVF 特有问题。不得用外部定期输入把该问题计作通过。
命令、启动环境和失败证据保存在 `issue-20-20261006/boot-r9-*-diagnostic-*`。

进一步的第16轮有限 RTC 诊断已捕获真实第一次休眠：PowerMgr 在约33秒进入
`SLEEP Reason=TIMEOUT`，约34秒由 `base_host/OS_IPC_0_475` 写入内核休眠。
启动后的屏幕超时实际上被锁屏策略覆盖为10000ms；不能把早期 AWAKE 快照
推断成 HDI 在 AWAKE 状态非法休眠。三种 QEMU 内核配置另外都缺少真实
`/sys/power/wake_lock` 支持，ARM32 还关闭了 suspend 依赖。
新增独立 `device/qemu/power_wakelocks` 和 `kernel/linux/linux_6_6/qemu_power_button`
部件，均在画像配置和内核输入遍历之前应用。唤醒源仅限 `linux,dummy-virt`
平台现有 `poweroff/KEY_POWER` GPIO，不改 timeout、service 权限或其他板卡按键。
第一次实际唤醒另暴露 virtio GPU 的 fenced control queue 挂起：Linux 6.6 的该
驱动没有 freeze/restore 回调，而通用 virtio PCI 的 s2idle 恢复重置了 host 队列。
新独立 `kernel/linux/linux_6_6/qemu_virtio_gpu_s2idle` 只对实际 QEMU、GPU、s2idle
且驱动没有上述回调的组合保留队列；其他设备、S3、非 QEMU 和真正的
freeze/thaw/restore 路径不变。三 ABI 的配置及实际相关对象通过，证据
`power-kernel-three-abi-02.json`。独立完整 ARM64 Image05 链接通过，SHA-256
`a344933413de38c8fb5db596aaef24e6fb8b6080ab5fca311023060a46f1e887`，
证据 `power-linked-arm64-05.json`。所有失败尝试保留，不修改只读主源码/构建输出。
旧 R9 私有替换此候选内核的第19轮诊断已通过六阶段真实 sysfs wakelock 边界和
两次休眠唤醒；随后独立 compositor 诊断再次通过两个默认策略 s2idle/实体按键
唤醒周期。每次实际 UITest 窗口和 1280×800 compositor PNG 均有效，RS546、
Foundation489 和内核 UUID 不变；不改超时、不保活。证据分别为
`power-runtime-diagnostic-02/evidence.json` 和 `power-compositor-diagnostic-02/evidence.json`。
它们仍是旧 R9+候选内核诊断，不是新归档，不解除首包门槛；新包默认验证入口已
强制同样的默认策略休眠/唤醒/上屏闭环，再进行有限应用测试配置。

完整 M144 原生引擎 R7 编译暴露了 API26 SDK15 的 ARM64 静态运行库没有 BTI
属性。现从 SDK 编译器本身的固定 LLVM commit 重建 libunwind 和 compiler-rt
全部260个原有对象，保持 C ABI/成员列表、生成真实 BTI 指令；严格 BTI/fatal
linker warnings 下的真实 libffmpeg 链接通过。R8/R9/R10 的后续阻塞均已记录并
分别修补。R11完成大部分原生编译，但引擎最终链接失败：NDK wrapper仅在
libs声明adapter_ndk_stub，缺少GN目标依赖，stub未生成时先链接引擎。失败
日志和证据保留，仍无合格HAP或新首包运行证据。

HAP 打包前的独立复现另发现隔离 ABI checker 仅复制3个Python文件，而其
实际导入链还依赖 `verify_runtime_elf_contract.py`，会直接产生
ModuleNotFoundError。修复前失败 `m144-hap-python-closure-before-01.json`
保留，修复后宿主及实际Linux Docker隔离执行均通过
`m144-hap-python-closure-after{-linux,}-01.json`，相关71项主机回归通过
`host-m144-package-closure-01.log`；这不是 HAP 或 guest 通过。
打包器现在复制完整4文件闭包，默认M144配方同时纳入实际共享patch helpers、
snapshot、ELF/ALSA checker及AVC validator，避免这类依赖变化误复用旧cache。
当前冻结R11仍使用旧配方
`e0d78a3c7a4944938207d6b75c48dc8168f86a655b7c59e759e0dd436d88c0f5`，
没有修改其冻结输入或活动源码。HAP隔离导入闭包修正的中间配方为
`9ba1e06bf51e4db80086c50582fd70f48f8b60b921448ed0d6f7337c1db34528`。
0007新增wrapper对既有真实stub目标的GN依赖，不改stub/NDK语义、CFI/BTI
或fatal link检查；固定源码真实补丁预检和8项组件host测试通过。
R12以当时的统一配方
`2f566c66f2ec0cbc28d84d4e9d650421793bb189a751e59db8d58bb53360f320`
重新执行真实原生构建，冻结输入树SHA为
`82a336ea09c1db990f09771a078bdef69f245269260ee22b5a38b0ee939eaf8f`。
R12的实际完整GN再次通过29087个target/4222个文件；新Ninja图明确包含
engine到stub的TOC依赖，3个相关文件SHA保留在
`m144-stub-link-graph-r12-01.log`。实际stub先链接成功，R12随后完成五个
实际ARM64 ELF库，`native-build-evidence.json`的exit_code=0、
failures为空；engine SHA-256为
`7d2b080dcf817c5984c5b1d5fd28f8cd94ad6761548e934c12dd42b8f97d9c9c`。
这仅是native构建通过，不是签名HAP或guest通过。R12的HAP追加编译、最终
链接和官方kernelpermission步骤完成，但OHPM install失败：准备镜像中
`/root/.ohpm`指向容器内未挂载的`/Volumes/PSSD/qemu/home/.ohpm`。`/root`
本身存在，不是HOME目录被删除。该轮package-build-evidence exit_code=1，
失败日志和native/HAP证据均保留，未产出合格core-artifact或启动V8后续阶段。
仓库新增`prepare_m144_host_cache.py`并接入host准备和Dockerfile复制闭包，
仅创建所配置`.ohpm`缓存目标并检查可写；不重设HOME、不改链接、不清缓存、
不改SDK/源码/权限。4项host边界通过 `host-m144-ohpm-cache-02.log`，第01轮
macOS路径/循环链接fixture失败保留。固定源工具只读的实际Docker复现
`m144-ohpm-cache-real-before-after-01.json`严格记录before同样ENOENT/exit1、
after实际OHPM空依赖项目install exit0及未改链接/输入SHA；不是完整HAP通过。
当前R13使用最终统一配方
`3fedc12635bcee37654a01987b34c1b79303f1336540fa08fe77a36e7cac9891`
和全新冻结树`157ea23db20f270485a6fd0008dd0fdaea2873524da091edcb1ba4e30a3b972e`
重跑代表ABI的native→HAP→V8→SwiftShader→AVC。R13的native命令已以0退出，
五个实际ARM64 ELF和空failures已记录，实际总构建时间10分36秒。相同配方HAP
阶段实际OHPM install通过，但随后Hvigor包装器的npm install pnpm失败；
该轮package-build-evidence exit_code=1且未启动后续依赖阶段。当前异常只保留
stderr摘要而遮住具体stdout诊断，正在固定工具只读、独立复制项目的容器中
复现并保存两个输出流。完整HAP及新代表包运行结果仍待验证；
不得把旧配方 native 证据直接与新配方 HAP 拼接。后续HAP阶段使用其支持的
最多8个job，不沿用 native 的10-job参数。
实际独立复现进一步确认：固定Chromium GCS Node 24.11.1包没有npm，原HAP
包装器却调用该目录的npm。换用Release build项目所选完整Node 18.20.1后，
原最小环境丢失代理配置；保留环境后，普通镜像源又缺失`@ohos/hvigor`，
Docker对公共HarmonyOS源仍出现连接重置。第01至05轮失败分别保留，未把
下载或版本检查记作HAP通过。曾按package-lock下载Linux旧版工具
缓存，不执行依赖安装脚本；Docker只读挂载并验证缓存完整树SHA
`fe6bd6c57ab2ea3e0dc68c236e7fb1f9dcb39d7bb8c6b4754666d3f83b772aec`。
实际固定工具只读的第06、07轮启动原始Hvigor包装器，离线返回2.3.0/exit0；
第07轮同时验证Release build固定commit及Node/npm真实输入。工具缓存配方
为`e0e359ca6eae7e15a6e1a73e5ab5ed25d8580e1283818e96017a7cbbbf4a0ef9`。
HAP/HAR GN仅改用独立完整Node路径，不改Chromium Node；新增7项缓存/锁/
路径/环境边界通过`host-m144-offline-tools-02.log`，第01轮fixture缩进失败
保留。真实完整HAP和新包boot仍未通过；新构建必须使用新依赖配方。
R14已从仓库入口启动代表ARM64依赖链，统一配方为
`1f73a585812ad01e20f4f676be284651fdb867e6b4f1795700286aa7ec0d5abf`，
全新冻结输入树为`185fc6e903f65b9120c3fd561b0fc9cf65f0c26bf549935ddc017d1f4447ac71`。
正式容器中的`hap-host-tools-20261006T220226Z-19754.json`记录原始wrapper
离线preflight exit0及严格版本2.3.0，随后官方native构建exit0、failures为空，
五个实际ARM64 ELF均已记录，engine SHA仍为
`7d2b080dcf817c5984c5b1d5fd28f8cd94ad6761548e934c12dd42b8f97d9c9c`。
同一配方HAP阶段的主机冻结树也为上述185fc6e9值，但该轮仍失败：实际Hvigor
exit0后未生成要求的unsigned HAP，Build的缺包检查正确失败，package证据为1，
未进入V8等后续阶段。实际`.hvigor`报告记录moduleNum=0、metrics/workLog为空；
原命令在module模式下没有指定模块，导致空任务执行。正在独立副本验证明确
选择`module=entry@default`及`product=default`。第一轮独立测试实际触发任务，
但只读SDK被Hvigor拒绝；第二轮私有可写SDK测试确认旧版SDK manager 2.7.0
不支持原始SDK的metaVersion=3.0.2，不能靠wrapper启动成功判定HAP通过。
第03至06轮进一步暴露模型、SDK版本格式及previewer工具闭包问题，均保留。
第07、08轮的私有工具补丁方向虽能实际编译unsigned HAP，但已弃用，不进入
最终配方；只需要正确项目配置和SDK目录，不应修改SDK manager代码。

最终使用Release build固定commit配置选定的完整command-line-tools归档，
SHA-256为`83e45209c65662bbeab81d36d691807bf8db56d94d7d15c959600dcc348814c3`。
Hvigor/plugin为`6.0.0-release-patch-rc.2`、原配SDK manager为2.26.2，
所有工具代码和SDK原始元数据不改。项目modelVersion统一为6.0.0、
compileSdkVersion为`26.0.0`，对应私有SDK目录增加同名alias；compatibleSdkVersion
仍为12。该SDK的原始apiVersion=26、platformVersion=26.0.0由原版工具正确
解析。补齐第五个previewer工具组件，保留此前私有SDK证据后再更新，不覆盖
未知别名或元数据。旧版2.3 npm下载入口和实验性SDK-manager补丁已移除，
历史缓存及失败证据未删除。

原版工具缓存配方为
`8fa0429b67370b17f35349429fed0360a9b6cab2dfdf1110175cf71d259ca360`，
完整安装树SHA为
`317920a39c716c34f22f8b4d74637fa8bb5e856049aa3bede23d9497c7d535da`。
实际第11轮独立HAP测试使用仓库第0007/0008补丁、生产seed及原版固定缓存，
完成CompileArkTS与PackageHap，exit0且failures为空；unsigned HAP SHA为
`08f89b533826e05a7d29a27a52139ef540b5b94fa3af7ff18d30bbb678e57a2d`，
证据`m144-hvigor-entry-target-real-11/`。它仅确认工具/项目方向，不是官方
core provenance、签名core、新系统包或guest通过。
真实生产预检`m144-release-hap-tools-real-preflight-02.json`另确认原版工具版本
及11项合法/非法SDK版本边界；整数26作为项目版本仍被拒绝，点分26.0.0通过。
`m144-package-inputs-dot-api26-02/`完成真实源文件补丁及重复检查和Release
profile签名/验证，正常身份、权限和证书不变。第01轮仅因容器改变绝对alias
挂载路径导致签名工具缺失而失败，证据保留，第二轮按生产规范挂载后通过。
HAP组件改为从真实文件内容验证完整顺序补丁栈，支持已知连续prefix升级，
重叠补丁不再依赖逐条reverse或旧marker跳过；未知非连续状态在源码修改前
拒绝。native/HAP两阶段工具预检证据都纳入最终core的完整provenance校验。
其余五个系统包仍未启动，首包运行门槛仍未通过。

R15配方`75e03dfcfb387f7558e4467744f50aa03ccae12f5e36345974ccd8be633e156e`
使用全新冻结树`cf3415d791b5803d98959a402302da78f5d0ab6893aac1ac69d888a5d06d9f6c`，
正式原版工具预检和五个ARM64原生ELF构建通过，但正式HAP阶段仍失败。
官方`build.sh`在prepare前删除项目的派生`hvigor`目录，再复制
`dependencies/rk/*`；因此修改派生配置的旧0007/0008补丁被复制回2.3，
完整组件状态检查正确拒绝该非连续状态。没有签名core或新OS包通过。
修复改为`m144_core_build/0009`修改真正的
`dependencies/rk/hvigor/hvigor-config.json5`源模板，保留官方删除/复制/prepare
流程。HAP组件0007/0008不再修改派生配置；其wrapper、dot API26和根项目
模型修复仍保留。模板重复准备及组件回归27项通过
`host-m144-prepare-template-01.log`。第73轮完整回归发现新增通讯录测试中
过宽的断言（把仅改类名的行误判为改构造器）；改为逐行确认构造器不变，
失败证据保留，重新执行完整回归后才启动新配方。

第74轮完整725项回归通过。真实独立HAP第12轮使用已修复源模板及正常
复制流程、生产seed和原版固定工具，通过实际CompileArkTS/PackageHap及
unsigned HAP存在校验，证据`m144-hvigor-template-real-12/`，不是正式core签名
或guest验收。R16代表ARM64依赖链已从仓库入口启动，配方为
`1051f5c84fb10d0d6da72c1a2e0e69dbec510147ad6e6993ce834391ef244ff4`；
旧R15证据和缓存全部保留，未混接其他配方。新OS包仍待构建验证。
R16 native冻结树为
`b1b511865cac8c4ed98763a05ea4162183f64a64cd1c37344245bb54896ad95d`。
实际生产准备后，源模板与派生Hvigor配置均保持modelVersion=6.0.0，未出现
旧版本回退。R16正式HAP构建、完整ABI检查和真实SDK签名/验签均已通过，
HAP SHA-256为
`6ad8c67222f63830e7fbdf96735e96d97023cdee629223b6abaf30edfc746fd2`。
但core provenance记录失败：旧检查直接把native输出与HAP成员字节相比，
忽略原版Hvigor的NativeStrip步骤。该失败及R16全部证据保留，不补写成功
manifest，不将package-build-evidence中的exit0误当完整依赖链成功。

实际原版SDK LLVM15重放已确认五个HAP成员逐字节匹配，证据
`m144-native-transform-real-01/hap-native-transform.json`及同名log。引擎先从
本轮输出的自有副本移除kernelpermission，完整SHA确实回到原native证据的
`7d2b080dcf817c5984c5b1d5fd28f8cd94ad6761548e934c12dd42b8f97d9c9c`，
再用未修改的官方action/objcopy和encaps输入添加该section，最后由固定原版
API26 SDK NativeStrip转换。其余四库从原native完整字节直接重放。
没有改源码/out/SDK、跳过签名或放宽为只比较.text。这是独立诊断，不为R16
旧配方补发core manifest，也不是guest验证。
生产脚本现保存五个原native文件，并在打包后对全部五库执行相同完整转换
重放；工具、输入、原件、重放件与最终HAP完整SHA都绑定证据。unknown修改、
失败命令、缺文件和stale helper均失败。7项相关主机回归通过
`host-m144-native-transform-01.log`；正式统一依赖将使用新配方重建，首包门禁
及其余五个OS包仍未放行。

R17统一依赖由仓库入口重新构建，配方为
`e52486adb611d7b39c857e0c44b86ae818e0abb76bb46d099000f5e46cf2177e`，
native冻结树为
`d57644b6c0b0a35538d6fb42e4079c5a10d51c610ab99a6109395e4281a5030c`。
五个原生ELF、正式HAP、原版SDK签名/验签及五库完整转换重放均实际通过。
HAP SHA-256为
`b79e5e7afb5d88a5c2aa5bd8150d47a6c1510119bb5f22b64e880b4345c32152`，
完整core manifest SHA为
`294aa882575ef844231a69313893ddb1ddda5b961ff3ee5a57cdd1def83163e3`。
生产重放及独立主机core校验分别见本配方的`hap-native-transform.json`与
`m144-core-r17-host-validation-01.log`。但统一依赖链在随后V8阶段启动前失败：
macOS Bash3.2的`nounset`拒绝空`hap_tool_mounts`数组。保留原正式core及R17
失败，不误称V8/SwiftShader/AVC、完整依赖链或新系统包已通过。

仓库入口已对HAP mount及两处可选LFS参数改用原OS runner已有的安全数组
展开形式；空数组传零参数，非空数组保持原参数及路径空格，不更改构建命令、
权限或签名。实际执行原入口的六阶段×两种fetch选项mock外部工具回归通过，
macOS Bash3.2和Linux Bash均通过2项测试，证据
`host-m144-frontend-arrays-01.log`、`host-m144-frontend-arrays-linux-01.log`。
这些是入口参数边界测试，不是依赖构建或guest验收。修复改变依赖配方，下一轮
使用`3c0d5cd7d3302a0fad81b2056f947299c8258897e23a1c2e338a40baefd8b350`
的新冻结输入/缓存重建，不修改R17旧成功core或旧失败的来源证据。
第80轮完整741项回归通过后，R18代表ARM64统一依赖链已从原仓库入口启动，
日志`m144-dependency-arm64-r18-01.log`，native冻结树为
`6f54813cd2298b84b88fe6ccce3cb35829b4d6f3dcd1c597c78a4b8a54e365e7`。
新core及其余依赖尚待本轮完成；首包系统归档、启动和完整行为门槛仍未通过。

通讯录另外确认真实SDK26枚举`ContactSyncMode`未注册，未使用声明还存在
`ContactsSyncMode`及`DEFAULT_SELECT`两处错误名称。新增独立组件
`applications/standard/contacts_data/sync_mode`，固定项目commit
`c73bd27daa3fcd8ed6099b17cbffbd7021e3873e`，仅改名称并在Init注册原声明，
不添加占位DTO构造器，不改变同步实现和权限。修复后完整源文件SHA为
`1e695abbda171e24ba756d670f635ff5ee3cad748b5cdfe05a29f14002d85303`。
新鲜/重复/未知部分状态及实际声明的sanitizer主机测试通过
`host-contact-sync-mode-02.log`。只读实际源码的ARM64完整TU编译通过
`contact-sync-mode-arm64-03.json`；第01轮查询了整个依赖链而遇到非UTF8命令，
改用Ninja正式`commands -s`，第02轮ARM32缺少尚未生成的`ibundle_mgr_ext.h`，
失败记录均保留。不借用别的架构生成物宣称通过。另两ABI完整构建及真实
公开模块成员值、provider运行验证仍待新包完成，不能凭上述证据关闭缺口。

`contact-sync-mode`已接入默认普通应用验收：零额外权限、账号100真实normal
身份、每次新nonce，同时读取typed SDK两成员与真正`napi_load_module`的
own枚举成员。要求14项NAPI操作成功、真实类型正确、无异常，两路均为1/2，
拒绝仅有空对象/空函数、布尔伪数值、缺成员、旧运行和system身份。完整声明
由实际SDK TypeScript AST核对，绑定声明/解析器/生成页/native源文件SHA。
正常反射不再仅凭object类型关闭普通enum缺口，其他未验证枚举仍保留。
三个ABI的真实SDK unsigned HAP已构建，最终仅依赖acenapi、不携带另一个
C++运行时，目录`contact-sync-mode-unsigned-{arm64,armv7a,x86_64}-02/`。
这是验证程序构建，不是guest值、provider、cloud sync或六个OS包验收。
ARM64完整TU第04轮证据另外明确`all_three_products_checked=false`，不会把单
架构对象误写成三架构通过。第75轮729项回归只有Worker测试的旧字符串断言
失败；保留失败证据，更新新增persona断言并增加实际parser的互斥/无写入
测试后，第76轮730项全部通过。

音频另外确认`DeviceBlockStatus`有真实C++枚举值，但未在公开NAPI初始化中
注册。新增独立组件`foundation/multimedia/audio_framework/device_block_status`，
固定commit `6932fa64335b8272ca4a59de7808ab0d6c9eae7a`，仅增加原值
`UNBLOCKED=0`、`BLOCKED=1`的两成员map及既有注册调用，共五行。
完整最终源文件SHA为
`351b8bdb04cfe637c05643a050e8a964c3c4b09252461d3ded19b2d1504d51d0`。
三个源状态/sanitizer测试通过`host-audio-device-block-status-02.log`。
实际ARM64完整TU编译通过`audio-device-block-status-arm64-02.json`，明确
`all_three_products_checked=false`。三ABI编译第01轮因ARM32尚未生成
`ibundle_mgr_ext.h`失败，完整失败证据保留，不借用ARM64生成头文件。
补丁接入两个画像、三个ABI的统一源补丁计划，在正式编译遍历之前执行；
不更改硬件、音频路由、阻塞回调或权限，不凭枚举导出宣称这些后端已修复。

默认普通应用的`contact-sync-mode`验收现同时独立读取上述两个真实枚举，
typed SDK值和native own-member读取各自必须通过，零额外权限且normal
account-100身份不变。验证器对两个枚举分别检查14项操作、类型、成员值和
异常状态，SDK AST和当前编译输入共同绑定。6项结果回归通过
`host-contact-audio-enum-results-01.log`；三个ABI实际unsigned HAP通过，目录
`contact-audio-enums-unsigned-{arm64,armv7a,x86_64}-03/`。这些只证明验证程序
可构建，不是新guest的值观察，更不是通讯录同步或音频后端的闭环证据。

相册`FusionAssetType`同样已有真实C++定义及结果使用，却缺少公开NAPI导出。
独立组件`foundation/multimedia/media_library/fusion_asset_type`固定commit
`564ae888e7dcc7e0ec4c17ec9c77bf780e9cb380`，只注册现有`COMPATIBLE_ASSET=0`。
使用原有checked NAPI模式，不创建持续引用，不改相册存储、访问权限或同步。
完整最终CPP SHA为
`4be781efd4c1ab2be368facd0dce7eb66ce1243dcec2f1a5e43f7672fc4c312e`。
3项fresh/repeat/unknown状态及全部新增NAPI错误边界测试通过
`host-photo-fusion-asset-type-01.log`；真实ARM64完整TU通过
`photo-fusion-asset-type-arm64-01.json`，仍明确不是三ABI链接或guest验收。
首包03实际执行后确认还需002公共JS转发，已在本节开头记录实际崩溃、
修复及产品ABC编译证据；上述001的源注册/编译成功本身未关闭公共导入问题。
统一普通应用验收现要求通讯录、音频、相册三个枚举各自typed和native读值
成功；相册单成员必须是numeric 0，不接受false、缺成员或借用音频结果。
7项结果测试通过`host-contact-audio-photo-enum-results-01.log`，三个ABI实际
unsigned HAP通过`contact-audio-photo-enums-unsigned-{arm64,armv7a,x86_64}-04/`。
保留原通讯录02和通讯录/音频03目录作为历史构建证据，不用于当前输入的
首包验证。枚举观察不能关闭fusion/storage/provider或其他服务后端缺口。

其中显式 core artifact 路径也新增同一完整依赖配方校验，不只依赖默认目录
名称；构建器/共享helper发生变化时，旧冻结输入会被拒绝，相关72项主机
回归通过 `host-m144-package-closure-02.log`。下一轮代表依赖使用该最终配方
的默认缓存目录，方便随后从仓库矩阵入口复用；不混接R11旧配方证据。

固定 Git 工具源码、DEPS 的六个 GCS 对象、两个 Linux sysroot 已接入仓库构建
入口。全新独立工具目录中，实际从固定 ancestry/tag 构建 GN 的202个目标通过，
全部工具校验完成（`m144-clean-tool-bootstrap-01.json`）；没有借旧 GN 二进制。
这证明工具准备方向，不是六包或完整系统能力通过。其余五个系统包仍未启动。

仓库矩阵入口现默认调用 `scripts/validate_packaged_qemu.sh`，由私有全新 VM
执行系统 DSO 的24次退出回归、普通 Web/独立 Vulkan WSI与真正上屏测试及全部
32个当前 bindings 模块。`run_native_bindings_e2e.py` 复制实际未提交源码，
不改用户仓库，校验零漏测/零跳过/依赖锁不变，并用 OHOS 官方 signer 验证
实际 code-sign。当前独立源码副本的34个 Rust 示例、main/ohosTest unsigned HAP
已经重新构建，Cargo/pnpm 锁未变化；尚未在新包运行，不能称 E2E 通过。
验收证据升级为 schema2，要求实际内部结果、同 archive/boot UUID、完整审计
基线闭环；旧结构文本或单一绿色样例不能放行。完整 C++/ArkTS1.1 台账仍有
未注册真实闭环的项目，默认入口会明确失败而不会出具不真实的六包成功结论。
主机回归 `host-regression-capability-47.log` 为596项通过（105.333秒；该轮之后的新增修改仍需
重新完整回归），不是镜像验收。第46轮误用缺 Pillow 的系统 Python 的8项错误证据
保留，第47轮使用已有明确 test venv，未删测试或放宽断言。普通 HAP 验证新增完整 const-enum 真实 SDK 调用：
16项枚举、53个成员，API26 Release SDK 三 ABI 的 unsigned HAP 均实际编译通过，
输入保存在 `const-enum-sdk-three-abi-02/`。运行结果必须在新包、普通账号100应用、
新 nonce 下逐个与 SDK 编译器解析的声明值一致；不能由构建通过认定常量闭环，
更不代表其相关服务或硬件可用。bindings 的主/测试包设备声明仅在隔离副本中
补充 2in1，不改原仓库、权限或测试断言。

全新 Serial GN/output 暴露 JSONCPP generator 把 GN 提前创建的空输出目录当成坏树。
新增独立第二补丁，仅放行已知输出父目录且完全没有文件/链接的骨架；其他 partial
tree 不覆盖、失败仍非零。真实固定 archive 的只读生成、重复生成、失败保留和
上游121项测试通过；另一全新无 out seed 的 x86_64 GN→正常 Ninja action 通过，
无需人工隔离。Serial 授权完成修复的三 ABI 九个真实对象也全部编译通过，76项
host 回归通过，但授权 UI、真实 USB 字节及 detach/regrant 仍需新包验证。

默认 M144 依赖缓存现按固定源码锁、引擎补丁及 builder 配方 SHA 分目录；不会
删旧目录或让陈旧 manifest 放行。显式路径仍严格检查。冻结包输入现包含实际
capability/smoke 验证代码，测试变更不能复用旧包的通过记录。NAPI 导出审计改用
all-own-string-property 收集以包含 non-enumerable `napi_default`，三 ABI 真实 SDK
编译通过。第19轮旧诊断 guest 的普通账号100 HAP 已实际完成56个模块收集，54个
加载成功；phone 画像外的 Serial/NetFirewall 未加载，不能以此宣布2in1修复。
181项原始导出缺口中17项现在可直接读取，包括 matrix4 七函数、Ethernet 三函数和
System VPN 七项；其余164项仍待分别验证真实运行导出、factory/worker/DSL 契约。
不添加假的构造函数，不删除原始审计项。普通 const-enum 同一 guest 的16契约/53成员
也已实际通过。证据 `ordinary-exports-diagnostic-02/` 和 `ordinary-exports-diagnostic-03/`；
第01轮清理失败保留为失败，不用后续成功覆盖。均不是新包验收。

最终打包入口新增完整 Native ABI 检查：必须使用固定 SDK-C commit
`41b00f09528cf514b566553b2503c54e6347786b` 的真实头文件和 NDK manifest，按最终
system.img 的 SysCaps 检查所有接口，而非单一 symbol。声明或官方画像要求的库
缺少任何接口都会阻止打包。归档包含 `native-gap-abi-image.json`，独立包验证会重新
读取实际镜像库、ELF ABI、所有导出及校验和，不要求交付使用者另备源码树。
R9离线诊断03已通过 Location 12个、AudioSuite 65个完整符号；真实系统 loader
诊断01实际 dlopen/dlsym/dladdr 通过77个符号且来自对应DSO。四个画像外未声明的
可选库明确记录为未实现，不伪装成接口已提供。ABI 通过不是普通应用权限或后端数据证明。

同一第19轮 guest 的实际 root 诊断另通过 bitmap24项、user-ID20项、BPF23项、
Vibrator HDI14项及 AudioSuite 两轮3840样本 PCM。证据分别为
`bitmap-owned-boot-diagnostic-01/`、`userid-owned-boot-diagnostic-01/`、
`bpf-owned-boot-diagnostic-01/`、`vibrator-owned-boot-diagnostic-02/` 和
`audio-suite-owned-boot-diagnostic-01/`。runner 复核原始归档SHA、已完整验证的成员清单、
实际私有QEMU进程和内核UUID，不再每个小测试重复解压巨大userdata；没有替换系统库。
这些仍是旧诊断归档，不关闭新包门槛，也不证明NetManager策略、实时音频或HD振动。

普通账号100 AudioRenderer 的新 nonce 诊断实际通过71行完整结果：两轮非零 PCM
写入/回调、pause/flush/resume/stop/release/destroy/recreate，以及无效状态/声道和
null 边界。证据 `ordinary-audio-vulkan-diagnostic-01/audio-stream/evidence.json`；
同一父运行随后因 Vulkan 截图工具环境缺少 Pillow 失败，完整运行仍保留为失败。
注册的闭环只解决 Renderer 数据路径，不外推到 Capturer、主机扬声器、interrupt、
haptic 或分布式音频。应用测试只在实际默认休眠/唤醒验证后使用 PowerMgr 现有
有限 override；默认验证入口记录实际 before/setup/restored 三次查询，任何错误或
清理失败都不能放行。root 与普通应用 runner 均不使用定期输入保活。

独立 Vulkan 第02轮（正确 Pillow 环境）确实完成两代各五帧，但 compositor PNG
仍是启动窗口：预期 `(51,102,153,255)`，实际白色。真实 RS 和应用日志证明
COMMIT_TRANSACTION 的调用 PID=0、command PID=5330，严格身份校验拒绝全部
应用绘制事务；不是仅 SwiftShader 提交失败。现有异步 Binder 在内核中清零发送方
PID，GetCallingRealPid 也不能单独修复。用户已批准并实施两个最小独立组件：内核
仅为真实 one-way 发送任务持有私有 PID 引用，通过既有 sender-info ioctl 提供
真实 TGID；RS 仅对异步 COMMIT_TRANSACTION 的 wire PID=0 使用可信身份，身份
缺失/非正数仍拒绝。wire PID=0、async 协议、token/节点归属及全部权限保持不变，
不信任客户端自报 PID、不跳过校验。两组件均在统一补丁计划内、画像及遍历之前。
内核三 ABI 对象真实编译通过；新 ARM64 私有候选 Image 完成链接，SHA-256
`85d57c14da51e3d6b92c73f5bacf17168dee6ab12bcba458bf016f28b1e6d7be`。
RS 实际 fallback 代码的12800组 ASan/UBSan 身份边界通过；三个 ABI 的真实产品对象
编译均通过。缺失的生成头文件由实际固定 GN IDL action 在独立输出内生成，记录
原始命令、IDL/tool/generator 和生成文件 SHA，不写入主源码/out 或旧 GN seed。
证据 `rs-async-caller-three-abi-05.json`；此前失败尝试保留。这仍不是完整
RenderService 链接、普通应用上屏或安全 IPC 行为验证。
第20轮旧 R9 + 私有新内核的 root 真实 Binder 诊断35项通过：同步/异步真实 TGID、
one-way wire PID仍0、伪造输入PID/UID被忽略、发送方先退出仍正确、畸形异步拒绝、
有效后续事务和空 ioctl 边界。旧第19轮内核对照仅在两个异步真实PID检查失败，
完整失败证据保留。诊断使用无人占用的 vndbinder context，已有 manager 时硬拒绝，
关闭所有自有FD后撤销；不改系统 Binder manager。另两次休眠/已有 PowerMgr override
引起的诊断失败均保留；通过轮只在观察到睡眠后发送一次真实GPIO key、不改override。
这些不证明 RS token/foreign-node、普通应用画面或 Vulkan compositor 像素已经闭环。
证据 `binder-async-three-abi-01.json`、`power-binder-linked-arm64-06.json`、
`binder-sender-old-kernel-negative-01/`、`binder-sender-private-kernel-diagnostic-03/`，
以及 `ordinary-vulkan-diagnostic-02/`、
`vulkan-r9-owned-render-hilog-01.log` 和 `vulkan-r9-async-caller-source-01.log`。

AudioSuite 效果第01轮配置错误也完整保留：官方 SDK 仅允许输入/输出 builder
设置格式，效果节点继承管线格式。修正调用后第02轮仍失败，实际能力加载器
找不到 `iMedia_{Eq,Surround,Env}_GetSPECS`，不是已经证明的 namespace 问题。
现给真实 CPU DSP 补三个固定私有 ABI 能力入口，导出总数19；严格声明可实际处理
的 stereo/48kHz/S16LE/480帧，不声明 hard realtime、AI 或其他格式。10项主机
回归含149个实际 ASan/UBSan 信号/边界检查，三个 ABI 的实际产品参数对象编译
通过；ARM32/x64 旧图中的 AudioSuite stub 仅供取编译参数，不据此宣布新图启用。
ARM64 完整独立 GN和真实库链接已通过，新库SHA-256
`9bf04b365580be6ea8af0cccb8945eeeef1a1bde1bdad62892c6969e54f97430`。
真实 tiny ext2 的19符号、CFI入口、libc/math/ubsan依赖、三路 XML读回通过，移除
安全runtime的负例正确拒绝；此fixture不是系统包或声音行为。
36种普通应用效果管线尚未在新包通过。证据
`ordinary-audio-effects-avc-diagnostic-01/`、`ordinary-audio-effects-avc-diagnostic-02/`
以及 `audio-suite-dsp-specs-{arm64,armv7a,x86_64}-01.json`、
`audio-suite-dsp-specs-full-gn-arm64-01.json`、`audio-suite-dsp-specs-image-fixture-arm64-01.json`。

AVC 普通应用第01轮同时设置 bitrate 和 quality，实际 CodecParamChecker 正确
拒绝该冲突。修正为 CBR/VBR 仅 bitrate、CQ 仅 quality，并保留 CQ 动态 bitrate
真实拒绝边界后，第02轮全部12次编码配置、真实 SPS/帧/时间戳/IDR/EOS 执行通过。
但12轮解码均没有像素，完整437行严格验证失败；不能称 AVC 闭环。
实际 allocator_host 日志捕获 DRM dumb EINVAL，源码确认固定 QEMU gralloc 给 YUV
申请8-bit，而 Linux virtio GPU 仅接受32-bit。新独立
`device/qemu/virtio_yuv_buffer` 在画像/产品遍历之前应用：只对真实 virtio_gpu 的
CPU-accessible YUV 申请32-bit字节存储，保留逻辑YUV格式/尺寸和实际byte stride；
不声明YUV KMS scanout/protected，不改内核ABI或权限。8192组实际几何计算及
零尺寸/奇数chroma/溢出/不允许usage的 ASan/UBSan 边界通过，真实三个产品GN参数
对象编译均通过；未据此声称gralloc整库、真实DMA-buffer映射、像素、服务回归或
新包验收完成。证据 `qemu-virtio-yuv-{arm64,armv7a,x86_64}-03.json`，以及
`ordinary-avc-diagnostic-01/`、`ordinary-avc-diagnostic-02/`、
`avc-r9-owned-codec-hilog-01.log`、`avc-r9-owned-allocator-hilog-01.log`。
这些均不解除首包门槛，也不代替全新 M144、JSVM、SwiftShader 和六包验收。

Worker 的两个端口现增加真实线程上下文诊断，而不是伪造主线程导出。
固定 7.0 的 Worker version 在进程中不可混用；两种版本分别使用新的普通账号100
HAP 进程，无新增权限、native DSO 或 runtime 修改。每种版本创建/正常关闭/重建
两轮，四个256字节缓冲区真实转移并往返，验证全部256个变换后的 uint32、另一个
版本端口确实不存在，以及关闭后 legacy 的 silent no-op / ThreadWorker 的10200004
错误边界。7.0 的分离 ArrayBuffer 长度 getter 会真实抛出 `TypeError: IsDetachedBuffer`，
创建新 view 也必须被拒绝；记录这些实际结果，不把它伪造成 byteLength=0。
第01轮旧诊断的测试契约错误保留，第02轮普通应用两种版本均通过，电源原策略
完整恢复；证据 `ordinary-worker-context-diagnostic-02/`。实际 API26 Release SDK
ARM64 两种 HAP 和 `worker-{legacy,thread}-sdk-{armv7a,x86_64}-03/` 四个 unsigned
HAP 均编译通过。9项严格 host 回归检查全部256个字和挑战/身份/源码篡改负例。
默认新包套件已加入两个独立 persona，注册闭环仅针对 parentPort/workerPort 两项
上下文导出，不代表 TaskPool、sendable/shared-memory 或全部 Worker API；旧诊断
仍不能放行新包。第48轮完整605项回归发现一处仅匹配旧 builder 文本的断言；已
更新为继续要求 const-enum、反射和 Worker 都没有额外权限；随后第49轮完整回归
605项全部通过（103.652秒），证据 `host-regression-capability-49.log`。保留第48轮
失败证据；主机回归和旧镜像诊断均不解除新代表包启动/行为验收门槛。

身份修复的扩展稳定性检视另发现 frozen `TF_UPDATE_TXN` 替换旧事务时，需要
释放新增的内核 sender PID 引用。新增独立第二补丁覆盖该直接销毁路径，普通
销毁及错误路径仍各自只释放一次，不调用会重复扣减计数的完整事务析构。
修复后 Binder 源码 SHA-256 为
`e0d365c6c671b47f054f7d0af1162162a17e6b7d8b3a80a5d97eda8e5565a1cd`，
三个 ABI 的真实对象编译通过（`binder-async-three-abi-02.json`）。重新完整链接
ARM64 Image07，SHA-256
`f1109a98f7c27cf31db3c16026925c25e71a63850e20e2eb199c6e3df7d456c6`，
证据 `power-binder-linked-arm64-07.json`。第21轮私有启动、旧 R9 系统镜像的实际
Binder 第06轮诊断58项通过，包括64次冻结更新仅投递首末事务、冻结同步拒绝、
发送方退出后可信身份、伪造 PID/UID、畸形 offsets、空 ioctl 和恢复后续事务。
证据 `binder-sender-frozen-kernel-diagnostic-06/evidence.json`；真实运行覆盖该替换
路径，但没有直接测量内核 PID 引用计数，也未验证 RS 权限或普通应用像素。
PowerMgr 原有 timeout/override 全程不变，测试后复核相等；仅在实际观察到休眠
后发送有限实体 GPIO 按键。第04轮拒绝未知 override、第05轮 frozen info bitmask
契约错误均保留为失败：固定内核会同时置 rejected-sync 与 pending-work 位，
因此精确期望为3；修正探针后仍严格拒绝0/1/2，而不是放宽为任意非零。

RS 候选现在把已经验证的异步身份限制在私有 thread-local 请求作用域中，并
恢复嵌套调用的前值；统计归并只在该作用域内、wire PID=0 时使用可信身份。
不添加 Parcel 身份字段，不改公开 API、token、节点归属或权限。另修复
复制 Parcel 的 offsets 注入失败处理、ARM32 Binder64 数量乘法溢出、ashmem
整表偏移/重叠校验与4-byte协议对齐、失败路径所有权，以及 scene/followType
枚举与读取结果。实际 helper 的 ASan/UBSan 边界和跨两个翻译单元的线程/嵌套
身份回归通过；mock Parcel 测试不是实际客体 FD 清理证明。第09轮四个真实 RS
对象在三个 ABI 编译通过，`rs-async-caller-three-abi-09.json`。第06轮缺 libxml
生成头、第07轮缺 Rust/C++桥接生成头、第08轮 RO 源码 symlink 的路径归属检查
失败均保留。验证脚本调用固定 GN 的真实 IDL、libxml 与 bridge 生成步骤，
按词法路径核对 symlink 归属并再校验实际源码哈希；仅写入独立输出，不伪造
生成头、不修改主源码/out 或 completed seed。

第二轮57规则/9分类复核另发现5个缺口，已形成
`report/report_binder_rs_identity_revision_20261006_232308.md/.csv`。
新候选先复制共享 ashmem payload 到 receiver-private malloc，再验证和恢复表；
FD/FDR 的 sender 数值在发布 offsets 前清成 FD/-1，所有新 dup 均归接收端所有。
部分恢复或 token 拒绝由 Parcel 清理；成功异步路径 FlushBuffer 后才由 manual
worker 清理，不漏 FDR，也不重复关闭。合法4-byte offset 使用局部对齐结构和
字节复制，不收紧协议到8-byte；paired IPC 直接读取/清理路径同步修正。
FD 0 也纳入清理。SFC/DVSync/节点操作以 move-only 事务投递到主线程，不阻塞
Binder，并保留 calling-PID-valid 检查。三个 ABI 的5个真实 RS编译单元均通过
第11轮（15个对象），`rs-async-caller-three-abi-11.json`；IPC两单元通过第03轮
（6个对象），`binder-object-safety-three-abi-03.json`。补丁生成时丢失尾部 context
的第10轮/IPC第01轮与 IPC 错误 GN target 的第02轮失败保留，没有修改旧证据。
新主机回归使用实际 helper 和真实 OS FD，覆盖 FDR、合法4-byte偏移、FD 0
（仅在隔离子进程关闭 stdin）、部分恢复、任务取消、sender 后续改写映射、
主线程调度与 SFC invalid-PID 拒绝；并非真实客体 IPC/调度验收。第三轮稳定性
复核已完成，报告为修复前的冻结快照，见下文；完整共享库链接及新包普通应用
像素仍待验证。

IPC 新独立 `binder_connector_initialization` 部件消除 GetInstance 的无锁双检
读取，保持分配/OpenDriver 失败的既有重试。32线程共131072次实际新函数调用
及失败重试的主机 ASan/UBSan 回归通过；三个 ABI 的真实产品对象编译均通过，
证据 `binder-connector-three-abi-02.json`。第01轮因 completed seed 被另一个
活动验证使用而被保护拒绝，失败保留；第02轮直接读取只读产品图，没有绕开
保护。这不是 TSAN、目标 Binder 驱动或整库验证。组件均在统一补丁计划、
画像配置与遍历之前应用。完整主机回归第51轮615项、第52轮620项均通过；
最新第53轮629项通过（70.199秒），证据 `host-regression-capability-53.log`。
首包门槛仍为 false，其余五个系统包没有启动。

第三轮57规则/9分类审计形成
`report/report_binder_rs_identity_revision3_20261007_003744.md/.csv`，
确认10项（1 CRITICAL、6 HIGH、3 MEDIUM），不将四字节对齐、智能指针控制块
或已有独立锁误报。报告记录的是当时11文件冻结快照，不是后续修复验收。

IPC资源失败候选区分普通FD与内核处理的FDA、私有FDR，只释放真正由内核交付
的普通FD；覆盖allocator/reply拒绝、ReadAshmem分配失败和真实raw-data FD 0。
远端raw-data状态改为负哨兵，保留类布局。4项实际片段/OS FD主机ASan/UBSan
边界通过，三个ABI的6个真实对象通过
`binder-object-safety-three-abi-04.json`，不是客体驱动交付证明。
GetSelfTokenID改用当前调用线程的局部变量，保留原私有字段布局，标注
`[[maybe_unused]]`；256轮双线程成功/失败的确定性隔离及既有singleton回归通过。
三个ABI对象通过 `binder-connector-three-abi-05.json`，实际依赖表包含修改后的
自有头文件。第03轮部件路径、第04轮真实Clang unused-private-field失败均保留。

RS候选新增执行线程FD作用域及发布前无等待任务permit，嵌套/提前返回/取消时
恢复TLS并恰好清账；worker最终析构不再清另一线程TLS。委托命令不重设拒绝
标记，入队及执行均检查；注册PID核对内核caller，TID和16-bit ID前缀仅作
路由元数据，不授予权限，不把普通应用接口改为系统专用。FreezeScreen改用
现有类型检查cast。新 main-thread 队列按真实内核PID和实际接收Parcel字节数
限制每PID/全局待执行事务，保留异步调用；使用真实 EventHandler 投递返回值，
失败/取消/执行完成均恰好释放配额。原有 void PostTask 和类布局不变，不将
此队列预算误称全部RS堆内存上限。29项RS主机回归通过，证据
`host-rs-boundaries-01.log`。第16轮8个真实编译单元在三个ABI全部通过（24个对象），
`rs-async-caller-three-abi-16.json`；生成依赖使用真实固定Rust CXX、IDL和JsonCpp。
`rs-async-caller-three-abi-12.json`记录旧ARM32 GN绝对IDL路径失败，
第13轮记录completed seed头文件搜索未覆盖修改头的失败；第14轮缺JsonCpp
生成头、第15轮查询错生成target的失败均保留。三个完整部件现在采用全文件
exact-state补丁栈：首次应用先在私有副本预检全部补丁，重复应用只接受完整
最终哈希，过期单补丁marker不授权跳过。实际固定原始源码的三个部件首次/
重复应用均通过，`exact-component-stacks-01/evidence.json`；未修改只读原源码。
该轮完整主机第55轮655项通过（76.395秒），
`host-regression-capability-55.log`。当时内部sptr错误指针编码修复仍等待确认；
上述RS候选均尚无新包客体验收，不能声称RS完整修复。首包行为门槛仍为 false。

2026-10-07进一步只读复核固定IPC `b8d3e96cfcf382c8fae54502679ac8b3d827b428`：
`MessageParcel::Append`不能直接替代此修复。其实现逐offset将数据解释成flat对象，
AcquireObject只处理BINDER/HANDLE/FD，没有完整的长度/对齐预检、FDR/PTR支持，
FD dup失败也不返回给Append调用者；它不会将共享payload里的跨进程指针变成
可信Binder引用。`WriteRemoteObject`另维护holders并处理DBinder callback proxy，
`ReadRemoteObject`走标准对象/offset读取，不能用手填cookie/handle取代。
当时待批准方案必须让客户端/服务端统一对象编码，在Binder请求返回前保留标准解码的
强引用，覆盖普通异步私有副本和ashmem sidecar；DBinder可变元数据必须按真实
格式验证，不能因本地样例不使用它就拒绝合法数据或直接复制源进程指针。
null/截断/错offset/重复offset/元数据边界、IPC返回后的引用存活、任务取消及
跨节点权限拒绝均需独立验证。该段记录当时仅完成复核/方案；后续已授权候选
与验证状态见本文顶部，不是客体通过。

M144 R8 完整 native 构建在26321处发现另一个内部契约编译缺口：Release
`BufferRequestConfigAdapter` 不含 timestamp 虚函数，但 Chromium 具体 request
类仍声明 `GetTimestamp() override`。仅将具体 helper 改为 nonvirtual，保留
getter/setter 及 flush 的真实 PTS，不恢复错误 vtable 槽、不改公开 API。
真实失败浏览器 TU 使用原 GN/Clang22/SDK26 命令在私有输出编译通过，
`m144-buffer-request-01/evidence.json`；private-contract 7项主机回归通过。
R8失败证据保留。R9 native 在14184/22963处因多余的OHOS目标版
`generate_colors_info` 缺 `_start` 失败；实际 Linux 宿主生成器执行并与真实已有
生成头逐字节一致，`m144-colors-generator-01/evidence.json`，SHA-256
`8a6ca528d2b7943f1056820d2c035f8391fd47abe13a8e2fbe449f2f7c7d703a`。
新GN补丁在OHOS仅声明宿主工具，并将5处原始依赖均指向宿主工具链；保留
颜色/主题、原有生成动作及单测。R10的真实GN失败暴露第5处单测边，已由0006
单独修补，失败证据不覆盖。R11的冻结构建输入为
`54bcb8cb246c94d56b331d808dce9d6aeb4cf466bb097a8753fded9f3f7929b4`，输出
`/Volumes/PSSD/qemu/artifacts/arkweb-core-release-20261007-r11`。
该轮固定 dependency recipe 为
`e0d78a3c7a4944938207d6b75c48dc8168f86a655b7c59e759e0dd436d88c0f5`。
真实官方GN已生成29087个target；只读检查确认目标工具链不再声明多余的
colors executable，同时保留实际Linux宿主生成动作，
`m144-colors-generator-r11-01/evidence.json`。这只是GN方向及宿主工具执行证明。
签名 HAP、同 recipe V8/SwiftShader/AVC、新完整代表包及运行验证尚未完成。

Matrix4新增普通应用 typed SDK 行为探针，17条有序结果覆盖7个顶层helper、
矩阵乘法顺序、copy隔离、逆矩阵、平移/缩放/旋转/坐标实值、3类非法参数及
既有factory对象回归，另有64轮状态恢复。不请求权限，不用native shim补导出。
三个ABI的实际API26 SDK unsigned HAP均已构建，
`matrix4-sdk-three-abi-03/{arm64,armv7a,x86_64}/`；01/02编译失败因测试本身的
namespace-as-object和tuple断言不合法，修正测试写法后通过，未关闭编译器检查。
默认新包验收已加入该persona；闭环注册仅覆盖这7个helper，不能证明全部ArkUI。
尚未在新包运行。第56轮完整主机662项中1条旧脚本结构断言需更新；失败证据
保留。第57轮完整663项通过（125.823秒），`host-regression-capability-57.log`；
额外AST验证直接执行构建器的权限选择表达式，确保Matrix4/常量/导出/Worker
纯调用探针均不申请权限。主机测试不是新包验收。

## 历史 R6 首包运行结果（2026-10-06）

实际重新打包并全新解压启动的 ARM64 phone 为
`/Volumes/PSSD/qemu/packages/first-capability-repair-20261005-r6/openharmony-qemu-arm64-arm64_virt-phone.tar.gz`，
SHA-256 `502b08384576945bab9183281f8c4fe1475d836316354f3b15819962ece6a155`。
固定 7.0 manifest 不变。macOS ARM64 / QEMU 11.0.3 / HVF，4 vCPU、4 GiB、
800×500 virtio GPU，独立 HDC 18710 / 5682。诊断使用包外 QMP 每五秒输入保持唤醒；
不能由此声明默认无人值守启动通过。启动、包校验和命令见 `first-package-evidence.json`。

| R6 实际结果 | 精确范围 |
| --- | --- |
| ohos-native-bindings JSVM / QoS / vibrator | 新 main/test HAP 11 / 5 / 2 项通过，18 项零失败；六等级/worker 隔离、虚拟振动 start/cancel/custom 边界，不是调度时延或实体马达证明 |
| 普通应用 user-ID | 13 项通过，账号 100 与实际 UID 对应，不能自行 retag；不代表 renderer 分叉已正常 |
| I18n | 8 项通过，数据、numeric 202/401 和错误类型/缺参拒绝；没有放开系统权限 |
| root Vibrator HDI | R6 TCG 独立启动 14 项通过，真实 timer/preset/取消/错误参数无状态污染；该 VM 已关闭 |
| Vulkan 可见窗口 | generation 1/2 各五帧、销毁重建执行，但 QMP 与内部 compositor 都保留启动图；预期 `(51,102,153,255)`，实际白色，严格验证失败 |
| AudioRenderer | 新 normal HAP 两轮 Start=2，39/71 条，零 PCM 回调；AudioPolicy 报 route=1 没有 support pipe，ALSA 修复不是完整闭环 |
| ArkWeb | renderer 在页面执行前孵化失败：子进程 `SetUserId(100)` 返回 EPERM，StartRenderProcess=22；严格恢复流程未到达，不能继承旧首包 WebGL 通过 |

实际日志为 `r6-hvf-bindings-e2e-01.log`、`r6-hvf-userid-result-01.json`、
`r6-hvf-i18n-result-01.json`、`r6-hvf-vulkan-result-01.json`、
`r6-hvf-audio-stream-result-01.json` 和 `r6-hvf-arkweb-spawn-01.log`。
HVF 锁屏可见、boot completed=true，不等于普通应用首帧可见；TCG 的真实 freeze
栈另显示 UniRenderThread 正在 softpipe shader 执行，不能据此把 HVF 也归为同一根因。
当前修复方向仍需纠正 renderer 的身份初始化位置、7.0 音频 route 配置和应用渲染连接，
不得通过跳过错误、降低像素要求、取消官方能力或扩大权限来关闭问题。

本地回归最新 `host-regression-capability-25.log` 为 365 项通过（41.236 秒），
设备画像打包测试也通过；这些不是运行验收。Serial 的五个独立部件已接入 2in1
打包前准备，并加入真实 serial_manager/HDI 画像与固定 c05fbbf 缓存只读挂载；
服务/授权 UI/实际 enforcing guest 尚待验证。AVC/EOS、DSP、Calendar、Camera/Vivid、
严格 libjpeg、JSONcpp 等晚期候选均未进入 R6。剩余五包未启动，所有问题尚未修复。

新 `patches/common/vendor/ohemu/audio_policy_7` 候选已补五条现有 pipe 的 NORMAL flag、
八个设备的 reciprocal stream 映射、schema2.0 和正确 bufferSize；未添加设备/权限。
固定 pristine 源码双次补丁、reverse-check、真实 ext4 新配置回读、旧配置及未知编辑拒绝
通过；12 项主机边界通过。构建前强制打补丁，full-source 镜像强制校验 chip_prod 中
解析器实际优先读取的 XML。此候选尚未进入 R6，不能称 PCM callback 已通过。

早期图形源码诊断另确认 `CreateRenderConnection` 协议不一致：客户端要求成功 bool、remote object、
非零 token，服务端缺 bool 且成功返回 token0，与 guest hasRemoteObj 错误吻合。
记录 `render-process-ipc-source-01.log`。随后两个内部服务端点的最小回复修复
已获用户确认并落入 `render_connection_reply` 部件，保持客户端现有格式与
公开 API/backend/权限，真实三个 ABI 对象证据为
`render-connection-reply-three-abi-evidence-03.json`。nwebspawn UID3081 的最小
当前任务账号 setter 也已获确认并形成候选，不改 seccomp、不向最终 renderer
或普通应用开放 retag。两者仍需在统一依赖后的新代表包运行回归；后续发现的
sptr/大事务 ashmem 对象编码也已单独获用户批准，当前候选/测试状态见本文顶部。

## 历史首包运行结果（2026-10-05）

首个实际新包为
`/Volumes/PSSD/qemu/packages/first-capability-repair-20261005/openharmony-qemu-arm64-arm64_virt-phone.tar.gz`，
SHA-256 `c060979b682568ed747662b9cee7276befa6a06b9cf13b6b4905e8e7f5b2ef22`。
在 macOS ARM64/HVF、QEMU 11.0.3、独立 HDC 18710/目标 5681 启动，guest 为
OpenHarmony 7.0.0.39/API 26、phone/aarch64/Linux 6.6.101，账号 100 前台。
后面的原始审计数字保留历史含义，不据局部通过批量关闭全 API 台账。

| 实际新包测试 | 结果与严格范围 |
| --- | --- |
| kernel bitmap / root user-ID | 24 / 20 项通过；不代表普通应用已通过 |
| kernel BPF | 23 项通过，真实 map 回读/非法访问与 loopback UDP 过滤、替换放行、challenge 比对；root 内核链路，不代表 NetManager/NetFirewall/VPN 服务 |
| 普通应用 user-ID | 失败，AppSpawn 分配值不等于账号 100；强 common setter 待重包验收 |
| bindings JSVM / QoS | 普通 HAP 11 / 5 项通过；QoS 覆盖六等级、两个真实 worker 与主线程隔离、reset/重复 reset、非法等级和空输出拒绝；不是调度时延证明 |
| bindings ArkWeb | 两轮真实 custom 文档、JS/DOM/Canvas/WebGL1/2/Rust proxy 通过，另 5 项 Hypium 边界通过；不是 renderer 恢复 |
| ArkWeb renderer 恢复 | 失败，renderer 是 PID namespace init，默认 SIGTERM 被忽略；已补显式安全退出 handler，待新包验证 |
| Vulkan device / NativeWindow queue | device/queue/memory 回读与 10 帧/1500 consumer 像素通过；不等于上屏 |
| Vulkan XComponent 上屏 | 真实五帧与销毁重建回调完成，但两轮 compositor 截屏和 QMP 显示均黑；失败 |
| 权限定义 | 973 项与固定源码完全一致：825 启用、148 按 phone 限制缺省；4 项查询边界通过；不是应用授权流程 |
| AudioSuite PCM | 两轮 pipeline、3840 samples、回调与非法状态边界通过；算法插件/下载/真实音频设备不在此通过范围 |
| 实时 AudioRenderer | 普通非 system HAP 两次创建后 Start 均返回 2，未执行数据回调；与 AudioSuite 是不同链路，失败 |
| I18n | 五项数据调用通过；权限错误码字符串 `"202"`、缺参字符串 `"401"`、错误类型静默返回，违反 SDK 数字 BusinessError 契约 |
| Vibrator | HDI 可连接，但旧首包 time capacity=false / bindings customStart=801；有限计时 VDI 待重包验收 |

黑屏定位为 SceneBoard 已开启却缺统一渲染开关。phone/2in1 窄覆盖层都已设置
`graphic_2d_feature_rs_enable_uni_render=true`，保留 OpenGL/softpipe 并不启用 Rosen Vulkan；
当前真实 preloader 确认开关配套，新增编译前契约检查。开关正确仍不是可见呈现通过。
I18n 修复使用已有 numeric BusinessError helper，补四种 setter 类型校验，不放开权限。
两类 I18n 对象分别完成三个产品真实 clang 参数编译；未准备 PNG 的 ARM32/x86_64
只在 scratch 严格展开本产品固定依赖输入，没有借其他 ABI 输出或修改 live source/out。
实时音频的进一步定位：ES1370 设备和 PCM 节点存在，audio_host 也已注册，但
固定 ALSA 默认关闭 global config，`hw:0` 无定义；完整配置树未在其编译路径
`/vendor/etc/audio/alsa/share` 打包。新补丁开启两画像的已有开关，并将上游 79 个
配置文件安装到 chipset 镜像。三个产品的本地空 `alsa-lib` 条目会盖掉画像设置，
因此已独立迁移到共享 board inherit；没有放宽通用 local-shadow 检查。
实际重建此前被该检查拦截，修复后新的 ARM64 phone preloader 配对检查通过。
普通应用严格探针已在三 ABI 编译；两次 Renderer 创建/销毁、状态、非零 PCM 回调、
pause/flush/resume 和参数边界必须在新包实测，不能据配置正确判通过。
原始音频失败证据 `audio-stream-02-result.json`，normal 身份与 UID 20010036 同时保留；
输出仍使用 QEMU `none` 后端，不声称已验证宿主机扬声器或麦克风。
当前同一 ARM64 phone 首包继续重打（R6），首包门槛为 false，其余五包未启动。
证据目录 `/Volumes/PSSD/qemu/validation/first-20261005`，索引 `first-package-evidence.json`。
完整主机回归最新 302 项通过，包括 ALSA 本地条目迁移、配置树校验、Calendar 源码与
签名装配保护、BPF/AVC 严格结果校验、AVC EOS 与真实基础 DSP 修复、只读 NOTICE
输入、Fusion 服务账户保护、Camera 继承/生成配置/Vivid/照片验收边界、Serial 与 DSP 安全 runtime 校验；日志为
`host-regression-capability-20.log`。这些包含真实补丁 ASan/UBSan、fresh-run/严格结果
校验，但不是镜像 E2E，也不解除首包门槛。

官方范围内的 AudioSuite 算法、AVC/Vivid、Camera/Wi-Fi/BT/GNSS 虚拟后端、Serial、
CloudSync 与系统 Provider 等既有缺口仍未获得完整实现/运行证明，不能称“所有问题已修复”。

### 真实软件 AVC 候选（未进入当前 R6）

固定 `av_codec @ e5c525670d1f6622d441c9e5bf975ea0579ea177` 的软件 wrapper
实际依赖 `libavcenc_ohos.z.so`。原始首包 system.img 离线检查确认该库未打包，
结果 `avc-backend-original-01.json` 为失败；这不是原始普通 HAP 数据路径测试结果。
现用已有固定 M144 的 OpenH264 `652bdb7719f30b52b08e506645a7322ff1b2cc6f`
实现准确 wrapper ABI，不引入 master 或假成功实现。独立依赖构建不改 V8/SwiftShader
的 Ninja 图，也不修改正在编译的 R6 source/out。

宿主机真实编码/解码回读覆盖 Baseline/Main × CQP/CBR/VBR × 两次创建 × 八帧：
最新 `avc-backend-host-04.jsonl` 为 520 检查通过、96 帧全部回读，含动态码率上调、
请求 IDR、EOS、重建、输入/输出容量边界与 canary。Main decoder 有缓冲，按实际
输出时间戳核对并完整 drain，没有跳过首帧或降低像素阈值。初版动态码率上调及
旧解码测试的失败记录保留。ASan/UBSan 覆盖 adapter/probe，不能称底层静态 codec
全部经过 sanitizer，也不能据此宣称严格 CBR 性能达标。

实际 OHOS GN 编译三个 ABI 均通过，当前候选依赖目录为
`/Volumes/PSSD/qemu/artifacts/avc-m144-final-20261005`：

| ABI | `libavcenc_ohos.z.so` SHA-256 |
| --- | --- |
| arm | `0f086a17c7c9e2e4e8c6bef8b1698151a718b02cd672c8a945b3e20468d87c7c` |
| arm64 | `31bc322c9fc2bf1ecbd60198bfc01af9bdcf3aa3df314e42ec4827ee99eb721a` |
| x86_64 | `9916eab3e4220fda0d291bd1b4b5d204c4db3918c744478c3d5009b357061f26` |

构建前强制验证源码/ABI header/当前 adapter 哈希、实际 ELF class/machine、准确三个
导出、SONAME、仅 libc 运行依赖和四个固定许可证文件；过期产物拒绝复用。AVCodec
独立部件补丁把库、来源记录与 notices 纳入两个画像，并已在 pristine 固定 HEAD
重复应用两次通过。新 full-source 离线打包检查也强制读取 system.img 实际内容。
这些校验只证明依赖/装配，不将编译或归档变成运行通过。

进一步确认原固定 wrapper 的 EOS 分支只设置 flag，未更新复用 buffer 的 size/PTS，
并忽略后端错误。新增独立 `avc_eos` 部件：成功才按真实结果重置 size/PTS，失败
通过 OnError 保持 ERROR，不再覆盖成 EOS。准确源结构保护、旧/新 EOS branch 的
ASan/UBSan 模型边界、重复补丁与三个产品真实 clang 参数的 scratch 编译均通过。
补丁 SHA-256 `45ddd25e70795e75ae68bd910f1045a513f80d31c394ff263792b8c2e2608318`，
新 wrapper source SHA-256 `6e1b02a272ac78572d5a75edc96f5253366ea53bea716a1c3547f1d5b23fcdad`。
固定输出 buffer 数为四；普通 HAP 每轮 header+四帧再 EOS，必须覆盖真实复用，
不是只看标志。成功/失败语义还必须在新首包验证，EOS 候选同样不在 R6。

实际 debugfs 校验器另用三个 ABI 的真实候选库、来源记录和四个 notices 构建 tiny
ext2 fixture，正向回读/实际 ELF 核对及删除 runtime notice 后拒绝均通过，结果
`avc-ext2-readback-01.json`。这些不是 QEMU 系统产物或开机验收。

普通 normal/non-system HAP 的公开 AVCodec 测试已完成三个 ABI 的 SDK 26 编译，
ARM64 HAP 在实际 Linux source signer 签名及验签成功；macOS Java 17 的 ZIP64
签名失败原始日志保留，没有关闭 code-sign。测试要求 Baseline/Main × 三码率模式 ×
两次创建、48 帧全部实际 challenged Y-plane 像素/PTS 回读，实际 SPS profile、动态
码率/IDR、EOS、释放重建和边界，校验器独立核对 437 条完整记录及正常应用 UID。
本次旧诊断 VM 的 HDC/串口未返回应用结果，QMP running 不等于 guest 数据路径可用；
挂起的本次客户端已取消，不能记录 AVC 应用通过或把传输超时算作接口结果。

还必须将它纳入同一代表首包重建、启动后以新挑战完成真实普通应用测试。当前 R6
不含此候选，不启动其余五包，不关闭 AVC 整项，更不声称 HEVC/硬件编码、Vivid 或
AudioSuite 算法已补齐。

### AudioSuite 三种真实基础 DSP 候选（未进入当前 R6）

固定 `audio_framework @ 6932fa64335b8272ca4a59de7808ab0d6c9eae7a` 的三个基础节点
依赖未打包的 vendor `libimedia_sws.z.so`。新增独立 `audio_suite_dsp` 部件，从源码
构建 `libqemu_audio_suite_dsp.z.so`，只改 EQUALIZER/SOUND_FIELD/ENVIRONMENT_EFFECT
三项 XML 路由，不冒充原厂算法库，不把其他 AI/云算法改成成功或取消官方能力。
十段均衡器是真实 peaking biquad；四种声场为真实 mid/side 宽度；环境效果使用
radio/telephone/underwater/phonograph 滤波及受控 soft clipping。它们是 QEMU CPU
实现，不声称与厂商音效 bit-identical 或声学标定一致。

实际宿主机当前源代码 ASan/UBSan 信号回读 `audio-suite-dsp-host-01.jsonl` 的 146 项
全部通过：十个频段分别验证左右声道 +6/-6 dB（容差 0.08 dB）、动态归零、参数回读、
四种声场/环境、满幅双符号饱和、in-place、输出 canary 与无写入拒绝边界。
测试 binary SHA `680c28d5426be2ae40a14e94d6780c24bdafa77cf9073dc505dcd4ded569e578`，
log SHA `9bfe39af48e74ad2914a011372c6b27e1d398847342fd02c98322a180d115fcd`。
实际三个产品 clang 参数的 scratch 对象编译通过（`audio-suite-dsp-*-compile-*.json`）；
ARM32/x86_64 的既有图关闭了 AudioSuite，采用其实际 framework stub 的参数模板，
明确不把这次编译当作启用该旧图、完整 GN、库链接或 guest 运行通过。
GN 实际语法解析与固定 pristine HEAD 重复应用通过，九项主机回归通过；初版
安装器误检查 macOS `/tmp` 祖先 symlink 的失败保留，修复只检查源码根内路径并新增
子目录 symlink 无损拒绝测试。安装前后还精确核对 pinned HEAD 的整个 XML/BUILD
已知变换，不据旧 marker 猜测已应用；未知编辑、配置 symlink 或缺失路由均无损拒绝。

进一步执行隔离的真实 phone preload/load/GN，而非仅语法检查。完整 GN 暴露了
AudioSuite 对 CFI 的强制要求；新库已使用与该部件一致的 CFI/cross-DSO、UBSan、
integer overflow 和 boundary 配置，未关闭断言或豁免安全检查。ARM64 完整 GN 和
实际共享库链接均已通过，`/tmp/audio-dsp-full-gn-arm64-05` 库 SHA-256 为
`ddf1bb1e3a13f3f3f0c111ee7cd20bab357e05ffc087d2b678519f32d9bbaa0a`。
ARM32/x86_64 的启用图完整 GN 和实际链接也已通过，库 SHA-256 分别为
`9f7f5631a60e9585b33b331317f4062e637d962337c0b4fc6db3afe7fb667eb1` 与
`c24ead0fda47d0f54cf7a23944a7e88c88156b648cff11c5a3853e16bb42603f`。
ARM32 06 只含 Camera USB0001，x86_64 07 含 USB0001–3、未含后加 Vivid，
ARM64 05 早于 Camera 修复；均只证明 DSP 启用图/链接。x86_64 首次尝试的
Camera 未初始化 defines 失败保留，未关闭 Camera 或更换其他 ABI 绕过。早期 scratch 的缺 Python、GN format SIGILL、CFI 断言和
直接 Ninja 缺上游 `-w dupbuild=warn` 失败均保留，不覆盖成成功。

离线校验已要求真实 16 个算法导出、cross-DSO `__cfi_check`、准确 SONAME/架构专属
DT_NEEDED，以及镜像内同架构 libc 的 CFI/数学函数和 UBSan minimal 的实际导出。
真实 ARM32 还需要 libc++ 的两个 ARM EHABI personality 符号，严格检查该原生
依赖，没有为去掉依赖而关闭安全/展开配置。三个 ABI 的真实库与固定运行依赖 tiny
ext2 回读均通过，删除安全 runtime 后正确拒绝；日志为
`audio-suite-dsp-ext2-readback-01.json`、`audio-suite-dsp-arm32-ext2-readback-02.json`、
`audio-suite-dsp-x86_64-ext2-readback-01.json`。ARM32 初版固定 8MiB fixture 容量失败
保留，改按实际文件字节计算容量，未 strip 或替换验证输入。这是装配闭包验证，不是新 QEMU 包或 PCM
pipeline 行为通过。

该候选不在 R6 的冻结输入中，必须纳入下一轮同一首包，验证实际库/配置装配和公开
AudioSuite pipeline 的真实频响、状态/参数、destroy/recreate，不能只重复本地 adapter
测试。普通 HAP 已在三 ABI 实际 SDK 26 编译，ARM64 由 Linux source signer 完成
signCode=1 签名，并验证 actual code-sign/digest/permission 签名（`audio-suite-effects-hap-sign-verify-03.log`）。
测试只链接公开 OHAudioSuite，要求两轮各 18 个引擎/pipeline/三节点的创建释放、十个
EQ band 与四种声场/环境，完整 1359 条记录及 36 组 PCM 回读。独立校验器按 fresh nonce
重新计算输入 waveform energy，再核对双声道输出 energy/dB、边界和普通 UID；不是
仅核对测试自身的 passed。其五项 synthetic 回归不是 guest 数据路径结果。
signer runner 已强制实际验签与 `.cer`/`.p7b` 输出、四项成功标记；之前 `.pem` 输出
导致未执行验签的失败保留，AVC 当前 HAP 已用正确后缀重验（`avc-media-hap-verify-linux-04.log`）。
降噪、分离、变声、tempo/pitch、spatial/HOA 和云下载仍未修复。

### 只读构建与 Fusion 服务账户候选（未进入当前 R6）

固定 `build @ 5c0623072ed9c2ee93ab909a7a01f428fee95082` 的 NOTICE collector
读取源码许可证却使用 `O_RDWR | O_CREAT`，实际隔离编译因此在只读 musl COPYRIGHT
上失败。独立 `build/notice/readonly_input` 补丁仅把输入改为 `O_RDONLY`，保留输出、
去重和内容行为，不通过复制第三方源码掩盖错误，也不创建缺失许可证。固定源码
重复应用、四项边界测试和新 DSP 实际只读许可证动作通过；不是镜像运行验收。

固定 FusionConnectivity 的两个 init 配置使用 `fusion_ranging` 与
`partner_device_agent`，而 init 账户表未注册它们。新增独立 `init/fusion_accounts`
补丁，分别分配未占用的 6067/6068，保留原服务权限、capability 和 supplementary
groups，不复用 radio 的 `fusion_host`、不改 root、不开放登录。固定 passwd/group
与两个完整服务配置的保护、重复应用和真实 `passwd_appender.py` 的 0–6999 输出
检查通过，日志 `fusion-accounts-passwd-appender-01.log`。新镜像中的启动/SA 调用和
无线后端尚未验证，不能据账户生成称测距或蓝牙可用。

### Camera VDI/配置装配候选（未进入当前 R6）

固定 QEMU product-local Camera 条目会覆盖整个继承部件，只留下
`drivers_peripheral_camera_v4l2_emulator=false`；共享板默认 USB=false，匹配 USB
VDI 的 HCB 又默认关闭。phone 现明确选择真实 USB VDI/匹配 host config 开关，
不启用 express-camera 私有协议；独立 `vendor/ohemu/camera_profile` 迁移仅已知本地
条目到 board inherit，未知用户特性和 symlink 无损拒绝，不放宽通用 local-shadow
保护。2in1 原有官方画像之外的 Camera.Core 收紧保持不变。

独立 peripheral `camera/usb_backend` 补丁保留 USB 关闭时的 x86_64 原条件，只在
真实 USB 启用时纳入 HAL；完整 x86_64 phone GN 又发现 common adapter 的 defines
未定义，新增缺失时初始化而不清空已有 emulator list。上游生成 pipeline config
原本在 GN touch 源码并在 Ninja cp 回源码树，现改为当前产品 gen 的 C/header 和
显式 generator 依赖，避免不同产品互相覆盖，不再安装仅构建用途的源码 C 文件。
固定源码重复应用与七项主机测试通过。真实 ARM64 Camera 完整 GN 通过；独立
Ninja 在输入只读的 param_watcher IDL 被固定工具 W_OK 拒绝，失败保留。重试仅把
独占 scratch 原始 IDL 物化为同字节副本，保留完整组件目录骨架；不改生产输入，
不关闭工具检查，也不把完整 GN 当作 Camera 链接通过。

新加三个独立 `vivid_capture` 部件分别处理 Camera VDI opt-in、三内核 defconfig 与
固定 Linux 6.6 实际 Vivid producer 默认值。驱动和 vb2/TPG 帧生成保持不变，默认
只有一个 webcam Video Capture 节点，不创建 radio/SDR/VBI/output/meta/touch。
选择器仅接收真实 `driver/card=vivid`、`bus=platform:vivid-000`，使用每节点 device_caps，
拒绝非 streaming、output/meta 和仅 multiplanar 节点；保留真正 USB Camera 和原过滤逻辑。
没有冒充 USB、构造假 Camera ID/帧或放宽 `camera_host:camera_host 0660` 设备权限。
固定源重复应用两轮通过；实际三架构 Linux olddefconfig 全部 exit0、Vivid/依赖 builtin、
MAX_DEVS=1。真实 Linux V4L2 头文件下开关开启/关闭两组 ASan/UBSan 各 39 检查通过，
另七项主机保护测试通过。独立 `camera-vivid-kconfig-compile-07.json` 记录三架构
实际 targeted make exit0、各 20 个正确 ELF machine 对象及 built-in.a；不是整内核
链接或帧验收。早期 scratch 缺少固定板准备头文件/不完整上下文的失败保留，未借
旧 out 头文件。06 的三组实际 make 成功，但验收器误要求主 Makefile 不存在的
vivid-vb2.o；依据实际 20 个对象清单修正后，在新的 07 scratch 全部重编通过。

普通 Camera C++/ArkTS 1.1 HAP 使用真实 SDK26 编译三 ABI（ARM64/ARM32 02、
x86_64 修正 UDID 的 03），normal/非系统应用，只请求用户 Camera 权限。ARM64 02
实际 code-sign/digest/permission/verify-app 全部通过，签包 SHA-256
`744a58f7cb499c4c39c91a65bba67bd780be4890911f135209859d27e86d3918`。
首次 SDK 编译揭示的真实 EXCL/CameraInput.release/类型引用错误已修正并保留失败记录；
没有补造 SDK 声明。验收器另六项 fixture 通过：要求两轮 C++ 预览回调/生命周期、
两轮 ArkTS 拍照与重建、四张 JPEG 的独立解码像素、实际普通 UID 和新 challenge。
照片 fixture 不是真实 guest Camera 证据；HAP 尚未在新镜像执行。

以上候选均不在冻结 R6。新内核/VDI 链接、开机节点和 HDI metadata/格式协商，
普通应用 preview/photo/video 的帧/像素、权限及生命周期闭环仍须验证；不能据配置、
Kconfig、选择器 sanitizer 或完整 GN 关闭 Camera。

### CalendarData 候选源构建（未进入当前 R6）

进一步确认固定 `calendar_data @ f922427ca0dc20895a0e254ae41382e5b03299a4`
源码已有 `calendardata_whole` 与 `ReminderCallbackExtAbility`；旧 phone 预编译 HAP
却没有这些入口。现在按三个部件独立准备源 HAP、撤除旧预编译依赖和精确签名匹配补丁，
保留五个真实 HAR、lower/whole 权限、token/数据作用域检查和提醒服务授权。
API 26/model 6 由既有 6.x Hvigor/Node 18.20.1 构建；不需要引入 master 源码。
生产项目移除未使用的 Hypium dev registry 依赖，不跳过编译器或声明虚构的 SDK SysCap。
模块保留固定 SDK 的 default/tablet 声明，通过既有明确 BMS compatibility 画像适配
phone/2in1；强制改成 phone/2in1 在真实 Linux SDK 上失败，已经撤回。

实际固定源码 Linux `build/scripts/compile_app.py` 已完成 release 构建，SDK 为
26.0.0.39、目标 API 26、最低 API 23、VM ark13.0.1.0；标准 `app_sign.py` 签名成功。
固定源码 `hap-sign-tool.jar verify-app` 也实际通过 digest/权限签名校验，日志
`calendar-provider-production-verify-04.log`；这仍不是 BMS 或运行行为通过。
候选 HAP 不含 Native ELF，源 provider 与 Native calendar_manager 来自同一固定仓库。
signed HAP SHA-256 `c414d17fcd969b48d46da4be48b53e5bd30c64362ec15a9396a0d4f5f384eaea`，
路径 `/Volumes/PSSD/qemu/validation/first-20261005/calendar-provider-production-03-signed.hap`。
现有 system-core OS profile 的三个 ACL 没有扩大；只把该 bundle 的证书声明改成
与实际平台 leaf 匹配的 8E9386…F30024B5，不接受 wildcard 或无签名安装。
干净的固定 HEAD 重放又确认 pristine JSON 为 compact/CRLF，与 SceneBoard 的规范化
格式不同。现先精确校验原证书/两项 privilege/唯一 entry 和 JSON key，再按原值
规范化并打单个指纹补丁；原始和已整理两种格式、重复应用与未知策略无损拒绝均通过。

这些补丁晚于当前 R6 冻结，不修改正在编译的 source/out；候选 HAP也未手工替换到
测试 guest。还必须在下一次包含它的新首包中验证 BMS 注册、普通用户授权/拒绝、
两类 calendar CRUD、归属隔离和提醒/重启生命周期。
`EditorUIExtensionAbility` 依然缺失，Calendar UI 的关联流程也未验证，不能关闭整项缺口。

## 原始审计与候选实现记录

审计范围：ARM64 phone 与 ARM64 2in1 代表镜像。  
运行系统：`OpenHarmony-7.0.0.39` / API 26。  
固定 manifest：`f079c4ad9848f9cc4a9a4b3a3613ad8fbb142549`。  
本清单明确排除 ArkTS Static，只统计 Native C/C++ 公共 ABI、ArkTS 1.1 动态模块、
权限、System Ability、系统 HAP/Provider、运行时插件、内核和 QEMU 虚拟硬件后端。

完整逐项数据见 `docs/capability-audit/native-arkts11-gap-ledger.json`。它由
`ci/capability-audit/build_native_arkts11_gap_ledger.py` 从运行证据再生。
该台账来自先前 ARM64 代表镜像，不是六个架构/设备形态的新包验收结果。当前已准备的
Location API 26 符号、Ethernet API 与 firewall 开关解耦、matrix4 顶层导出补丁，
NetFirewall/System VPN feature、VPN/Settings bundle 名、DHardware UI 预装路径补丁，
以及 ArkWeb/Vulkan 图形补丁，只有在新首包启动并完成对应调用后才能从缺口中移除。

2026-09-25 首包构建记录（该轮已失败，后续状态见下文）：ARM64 phone、固定 7.0 manifest、仅这一个产物；
尚无新包运行结果，其他五个产物未启动。此次重启构建强制重编内核，避免复用旧
`Image` 后把源码中的 AccessToken ioctl 处理误判为已进入产物。
第一次启用 System VPN 的增量编译在 `sysvpn_config.cpp` 因未定义的
`MAX_LOCAL_ADDR_SIZE` 失败；已补地址向量的对称上限和负数/读取失败边界，正重试首包。
三个全量 QEMU 启动脚本此前均未创建设备，虽然对应内核配置启用了 ES1370；
现已给启动脚本加入 `es1370` 与确定性的 headless 音频后端。PCM 节点、
Renderer/Capturer frame 回调和录放数据仍须在新首包验证。
另外已按部件准备 Backup SA 非法 `CAP_CHMOD`、ModuleUpdate 初始化程序未纳入
部件产物（并修正 `execv` 参数）、UsageStatistics 陈旧无路径 init 配置，
及 HUKS init 会执行但未打包的兼容程序四处补丁。首包已在编译早期重启以纳入补丁；
它们仍须从新包验证启动日志和对应服务状态，不能据补丁存在就将台账项改为通过。
三架构 QEMU 内核 defconfig 均未启用 `BPF_SYSCALL`、`CGROUP_BPF` 和
`DMABUF_PROCESS_INFO`，ARM64 还未启用 FTrace；已加入共享内核配置补丁。
运行时仍要检查 BPF 程序实际加载、NetManager 统计/策略、DMA 进程信息和 tracing。
`userdata.img` 使用带 quota 特性的 F2FS，而三个内核 defconfig 缺少 VFS v2
quota 格式支持；内核补丁同时启用 `QFMT_V2`，新包必须使用新生成的 userdata 镜像，
并验证 F2FS quota 无损挂载、实际配额读写和空间统计。

2026-09-27：首包的下一处实际编译失败已定位到
`drivers/dma-buf/dma-buf-process-info.c`。固定 Linux 6.6 已有统计实现及
`get_dma_buf_from_file()` 定义，却缺少 `dma_buf.exp_pid`、`exp_task_comm` 字段和
对应函数声明。已按 `kernel/linux/linux_6_6/dmabuf_process_info` 部件补齐头文件，
保留统计功能，不通过关闭配置绕过失败。该修复已经完成内核编译，完整首包仍在重试；
尚无新包或启动结果，编译通过不等于运行通过。
I18n 六个 init 目录的属主已从不存在的 `i18n_service` 改为实际注册的 `i18n`；
三个 `hmos_cust_*_mount` 命令属于未提供的厂商定制覆盖层。2026-10-05 已准备移除
这三个调用而使用源码实际读取的 OpenHarmony 数据路径，保留 ICU 恢复程序；新增真实
数据/权限 HAP，必须在纳入新补丁的新包上运行才能将该装配问题移出缺口。

用户已允许收紧官方设备画像外的错误声明。本轮明确收紧 phone NetFirewall，
以及 phone/2in1 的 VideoProcessingEngine，并撤销 2in1 画像外的五项 CloudSync 声明
及 rich 继承的 Camera.Core 声明（保留 Camera 部件/库，不修改 phone）；
phone 文档内 CloudSync 仍需修复真实 Provider，2in1 NetFirewall 仍必须实现。
JSVM、QoS、Vibrator、ArkWeb、WebGL1/2、Vulkan 七项用户需求独立保护，不能因默认画像
未列入而撤销。收紧只纠正错误声明，不把真实实现需求转成声明检查。
AudioSuite 在官方 phone 文档中，不能仅因 SDK 默认列表未列出而删除其修复要求。
进一步检查发现固定源码已有 AudioSuite engine/pipeline/API 实现，但 QEMU 产品的
`audio_framework_feature_audiosuite_support=false` 让 Native target 生成占位库。
已准备 phone 的两个 feature 开关和真实 PCM 数据/状态边界探针；该开关已经进入
2026-10-05 的 phone-f02tvm 冻结输入，仍须编译、打包和启动验证。算法插件仍缺失，不把整项标为修复。
保护列表来自审计使用的 7.0 文档固定提交 `9585fb12fa8f977accfd9435d9f5537b14734473`，
与构建 manifest 独立记录；不要求构建源码包含已省略的 docs 仓库。

实际 load-only 检查暴露了第二个问题：hb 按整个部件覆盖继承项，后加载的
`virt_common.json` 清掉 NetManager 的产品级设置。现已增加位于最后的窄画像覆盖层，
保留最终 board 设置，只覆盖明确管理的 feature/SysCap；不移动整个 phone/2in1 画像。
在真实 phone preloader 的 `features.json`、`syscap.json` 和 `syscap.para` 中已确认
NetFirewall feature 为 false、两项错误 SysCap 均不再声明。它仍是配置证据，不是运行通过。
完整构建输入现为只读快照，补丁和脚本的文件哈希随包保留，避免长构建读到后续修改。
详见 `docs/OHOS_7_PROFILE_CONTRACT_REPAIR.md`。
正向复核曾发现 ARM64 phone 的九个声明名差异；六个是固定 registry 明确 abandoned、
SDK `.ts` 无引用的退休名称，对应部件保留且仍需行为审计。三个有效能力 AudioSuite、
AVInputCast、Window.SessionManager 已联合开启实现 feature 和声明；phone 也启用实际
SceneBoard（HandsetSmartWindow/non-PC），不只加 SysCap。新的打包/guest 契约检查包含
窄退休证据约束和七项用户需求，已经进入 phone-f02tvm；不代表调用通过。
此前完整构建在 sysvpn 两层开关不配套时链接失败；现在 phone/2in1 显式配套 base/ext
开关，并在当前 preload 后、编译前检查。新首包仍在编译，尚无包或 E2E 结果。
OHOS Vulkan CPU WSI 候选桥及 loader 的 surface/ICD 分发修复已完成 ARM64 实际编译，
并加入实际呈现/resize 探针；尚未在新 guest 运行，详见 ArkWeb/Vulkan 独立记录。
另新增真实 XComponent/截屏/销毁重建测试，已编译而未运行。

ARM32/x86_64 的 M144 SwiftShader ICD 也已实际编译，修复了 OHOS ARM32 Subzero 的
POSIX LLVM config header 装配问题，三个架构的依赖库均准备好；这不是六个 QEMU 包的
运行验收。bindings 新增真实同进程页面测试，并修复 custom response 缺 header/finish；
ARM64 主/测试 HAP 编译通过，18 项相关主机回归通过，但尚无新 guest 页面结果。
完整 QEMU 主机回归在增加 AccountMgr 最新快照保护后为 141 项通过。所有这些条目仍保持“候选实现、待新包验收”，
不据编译或测试驱动的 fixture 将原运行台账批量关闭。

2026-10-05 新确认但未完成的依赖闭环：AudioSuite 的 XML/loader 写死 lib64，已新增
按 ABI 选择 lib/lib64 的部件补丁，并支持 `/system` 指向 `/usr/system` 后的 canonical
只读路径，保留 realpath/目录白名单；多个算法 `.so` 仍缺失。
System VPN 的底层协议控制仍依赖未打包的 ipsec/协议工具，base/ext 配套仅修链接。
软件 AVC wrapper 动态加载 `libavcenc_ohos.z.so`，源码内尚无可用该库产物；
不能把开启 feature 或 RK 硬件 encoder 广告当作已完成编码适配。

ARM32 对应的 bindings 测试入口原先不接受该架构，现已在独立分支
`audit/ohos7-qemu-e2e-arm32` 补齐同步、HAP ABI、Hypium、XComponent/Accessibility 驱动，
安装前要求实际 ELF class/machine。JSVM/QoS/Vibrator ARM32 测试库已使用 API 26 SDK
交叉编译，九项驱动回归通过；尚无新的 ARM32 包启动及 E2E 结果。
Hypium 驱动还要求源文件中的所有用例逐项完成、summary 与逐用例记录一致、无忽略用例、
runner 成功退出；零用例、部分执行和陈旧日志不能算通过。旧 JSVM/QoS/Vibrator 日志
只用于验证解析兼容性，不计入新包运行验收。

Camera 更细的源码检查：QEMU HCS 引用 `libcamera_host_vdi_impl_1.0.z.so`，但没有相应
QEMU board VDI 构建；不能仅因 HDF host/interface 产物存在就认为 Camera Host 可用。
`drivers_peripheral_camera_v4l2_emulator` 分支会包含
`device/hmos_emulator/hardware/dcodec/include/ParamManager.h` 并使用专用 ioctl，
不是标准 QEMU/Linux V4L2 后端。因此不直接开启该 flag；修复仍需标准 V4L2 虚拟
数据源（如 kernel vivid）、对应 host/VDI/pipeline/HCS 与权限配置，以及实际预览/拍照验证。

2in1 Serial 的进一步源码复核：固定 manifest 仅包含 usb_manager，不含提供
`@ohos.busManager.serial` 的 serial_manager 服务仓库；不能把已编译的
`@ohos.usbManager.serial` 当成这个不同模块。官方 SIG 源码已只读锁定至
`c05fbbf156230982aa576373da6ee04378b09ca0`，当前真实服务使用 Serial HDI，缺失 HDI 时
枚举返回 service error，并非源码记忆文件声称的纯桩实现。QEMU 仍缺该 NAPI/client/SA
装配、HCS/板载 TTY 权限、授权 system dialog 及真实数据用例；尚未将额外源码纳入
固定 7.0 build 或声称串口已修复。上游 init 的厂商 `/dev/ttyHW8` 权限、授权缓存删除
及 dialog bundle 身份也需适配，不能直接照搬为 QEMU 生产配置。

## 判定原则

以下任一条件成立，都不能把 API 标为可用：

1. `canIUse()` 为 true，但模块、动态库、运行导出或权限定义缺失；
2. 模块或动态库能加载，但调用落入 unsupported、空实现或 false-success；
3. System Ability 已注册，但继续依赖的 HAP、Ability、UIExtension、DataShare authority
   或运行时插件缺失；
4. API 对象能创建，但真实数据路径依赖的内核功能或 QEMU 虚拟设备不存在；
5. 生命周期 smoke test 只验证 create/release，或把“成功或抛错”都视为通过。

设备官方画像内的能力必须完成真实调用闭环。镜像在官方画像外额外声明的能力，也必须在
“补齐实现”与“删除错误声明”之间二选一，不能继续保持虚假可用状态。

## 总览

| 层级 | phone | 2in1 |
| --- | ---: | ---: |
| Native 库或符号缺口 | 6 | 6 |
| 其中 SDK 设备画像内 Native 缺口（不含文档额外要求） | 1 | 1 |
| 官方 ArkTS 1.1 可调用模块整体加载失败 | 0 | 2 |
| 有官方运行导出缺失的动态模块 | 54 | 47（45 可加载、2 整体缺失） |
| 缺失 ArkTS 1.1 运行值/导出 | 181 | 152 |
| const enum 编译调用契约（待验证，非 NAPI 对象缺失） | 16 | 16 |
| 其中缺失 public/system 函数 | 13 / 35 | 15 / 23 |
| 官方接口使用、但系统未注册的权限 | 14 | 16 |
| 已有直接证据的行为/装配缺口 | 86 | 92 |
| 设备契约内不可用的 Provider 流程 | 44 / 71 | 39 / 71 |

行为缺口不是 API 数量：一个音频后端缺失会传递影响 Renderer、Capturer、录音、通话、
SoundPool、AVScreenCapture 等许多 API。

**ArkWeb 不能列为整体已通过。** 新的分段探针在旧 ARM64 phone 镜像上已证实页面 JavaScript、
DOM 和 Canvas 2D 可用，但 WebGL1/2 超时；ARM64 2in1 与另外两种架构仍待同样复验。
Vulkan 是独立的 Native 图形接口问题，不应把其 ICD 缺失当作 WebGL 的根因。

## Native C/C++ ABI 缺口

审计覆盖 130 个库契约、6,768 个有头文件依据的 C 函数。当前表面缺口如下：

| 能力 | 缺口 | phone 范围 | 2in1 范围 | 初步修复方向 |
| --- | --- | --- | --- | --- |
| Location.Core | `liblocation_ndk.so` 缺 `OH_LocationInfo_IsFromMock` | 官方契约 | 镜像额外声明 | 源码误导出为 `OH_Location_IsFromMock`，按 API 声明修正符号 |
| NetFirewall | 缺 `libnet_trafficfilter.so`，5 个函数 | 镜像额外声明 | 官方契约 | 打开 net firewall/traffic-filter feature，打包库、SA、权限与内核后端 |
| VideoProcessingEngine | 缺 `libimage_processing.so` 15 个函数和 `libvideo_processing.so` 19 个函数 | 镜像额外声明 | 镜像额外声明 | 构建并打包实际实现；否则删除错误 SysCap |
| Audio.SuiteEngine | `libohaudiosuite.so` 只是约 5 KiB 占位库，65 个 API 26 符号全缺 | 官方 phone 文档要求 | 未声明 | 开启已有 upstream engine/pipeline feature，实际编译验证所有导出及 PCM 闭环，再适配缺失算法插件；不能删除官方声明 |
| HUKS.CryptoExtension | 缺 `libhuks_external_crypto.z.so`，11 个函数 | 未声明 | 未声明 | 若纳入 QEMU 契约则构建插件并补行为测试，否则不声明 |

ABI 完整不等于行为完整。已有库仍存在这些关键 Native 行为失败：

- `OH_QoS_SetThreadQoS` 对普通应用 PID 因无授权数据被拒绝；现有 `ohos-native-bindings`
  用例只覆盖被允许的测试路径，不能代表通用接口闭环。

  此项仍需精确复核调用场景：旧镜像的 bindings 两个 QoS HAP 测试确实通过，
  其中包括 set/get 断言；不能把独立命令行进程没有 auth 记录简单等同于所有 HAP
  调用失败。新首包需分别覆盖正常应用、线程/等级切换与授权边界，不放开全局 ioctl。
- `OH_AudioRenderer_Start` 返回非法状态，0 frame、0 callback；依赖它的音频和媒体管线均不可用。
- Camera Manager 能创建，但相机枚举返回错误且数量为 0，因为没有 Camera Host。
- 旧镜像的 Vulkan `vkCreateInstance` 返回 `VK_ERROR_INCOMPATIBLE_DRIVER`；缺 ICD，而不是
  ArkWeb WebGL 的 EGL 错误。M144 SwiftShader 软件 ICD 在旧 ARM64 phone 镜像的暂存目录中
  已完成 instance、logical device、mapped buffer 和 headless swapchain 探测，但必须禁用
  不兼容的 OHOS implicit layers；新打包镜像尚待首包启动验收。
- 两个被广告的 Rockchip AVC/HEVC encoder 都无法创建实例。
- Audio Vivid builder 的公开入口存在，但缺 `libAudioVividMetaBuilder.z.so`，实际返回 unsupported。
- AccessToken API 26 的位图 ioctl 返回 `ENOTSUP`；eBPF、FTrace、DMABUF process info、F2FS quota
  也分别缺内核支持。2026-10-05 进一步确认旧 inline 补丁没有匹配 Linux 6.6 的 switch
  dispatcher，只改了头文件；此前“源码已经补齐，只需重编”的判断不成立。现在新增独立
  内核部件，真实复制锁内权限位图并修复单项查询在解锁后解引用节点的竞态。
  用户态仅在版本握手成功且协议为 v1 时选用 SPM，否则保留上游 legacy 路径；没有实现的
  SPM/refcount ioctl 不伪造成功。还实现真实 task user ID，并把 AppSpawn 设置顺序移到
  降权前、传播失败。进一步发现默认 sandbox 的 SetUserId 是返回 0 的弱符号空实现，
  现新增真实 common 实现、移除 custom 重复定义（尚未纳入在编首包）。8 项迁移/边界/ASan/UBSan 回归通过；原始位图及新增 user ID/fork/
  普通 HAP 探针已准备，尚未在新 guest 运行。parent-HAP-token 映射仍缺 kernel handler。
  已确认 GN 只依赖 kernel 顶层目录，嵌套补丁未必触发重编；现以补丁后输入指纹驱动
  action，打包核对实际 Image/模块证书。不能再据脚本的“强制重编”变量声称产物已更新。

## ArkTS 1.1 模块整体缺失

phone 官方画像内没有可调用模块整体加载失败。2in1 有两个：

| 模块 | SysCap | 表现 | 修复类型 |
| --- | --- | --- | --- |
| `@ohos.busManager.serial` | `SystemCapability.BusManager.Serial` | `canIUse=false`，NAPI status 10 | 部件/模块/画像打包 |
| `@ohos.net.netFirewall` | `SystemCapability.Communication.NetManager.NetFirewall` | NAPI status 10，Native traffic-filter 库也缺 | feature、模块、库、SA、权限和内核联合适配 |

## ArkTS 1.1 函数导出缺失

下面列出所有缺失函数。其余缺失运行值（enum/class/variable/namespace）完整保存在 JSON 台账中；
它们同样是 ABI 缺口，不能因为不是函数而忽略。

### 两种设备共同缺失

| 模块 | 缺失函数 | 根因方向 |
| --- | --- | --- |
| `@ohos.accessibility.config` | `startBlinking`, `stopBlinking` | 固定 BOM 实现落后于 API 26 声明，需要回移实现并验证服务调用 |
| `@ohos.arkui.intelligence.imageGeneration` | `closeGeneratorDialog`, `closeGeneratorNodeGraph`, `hideGeneratorDialog`, `hideGeneratorNodeGraph`, `openGeneratorNodeGraph`, `restoreGeneratorDialog`, `restoreGeneratorNodeGraph` | 导出与系统 Provider 同时核对，不能只补空函数 |
| `@ohos.bluetooth.connection` | `startPairOutOfBand` | 导出缺失；Bluetooth vendor/controller 后端也不可用 |
| `@ohos.matrix4` | `combine`, `copy`, `invert`, `rotate`, `scale`, `transformPoint`, `translate` | 底层矩阵实现已存在，缺 API 7 兼容顶层导出 |
| `@ohos.net.ethernet` | `disableEthernetInterface`, `enableEthernetInterface`, `isEthernetEnabled` | 完整实现已在源码，但错误地受 `netmanager_ext_feature_net_firewall` 控制 |
| `@ohos.net.vpn` | `addSysVpnConfig`, `deleteSysVpnConfig`, `getConnectedSysVpnConfig`, `getConnectedVpnAppInfo`, `getSysVpnConfig`, `getSysVpnConfigList` | QEMU 产品未打开 `netmanager_ext_feature_sysvpn` |
| `@ohos.net.vpnExtension` | `isAlwaysOnVpnEnabled`, `setAlwaysOnVpnEnabled` | 同上；还必须修复 VpnDialog 包名前缀 |

### phone 额外缺失

| 模块 | 缺失函数 | 根因方向 |
| --- | --- | --- |
| `@ohos.geoLocationManager` | public: `getCurrentDistrict`, `getPostProcessingTrack`, `startBluetoothSearch`, `stopBluetoothSearch`; system: `addFusionFence`, `getLocationIconStatus`, `isFusionFenceSupported`, `removeFusionFence` | 固定 BOM 导出落后；GNSS/network location 后端也缺 |
| `@ohos.telephony.call` | `offReceiveRttMessage`, `offRttErrCause`, `offRttModifyInd`, `onReceiveRttMessage`, `onRttErrCause`, `onRttModifyInd`, `sendRttMessage`, `setRttCapability`, `startRtt`, `stopRtt` | 导出落后；QEMU 无 modem/SIM/RIL 数据路径 |
| `@ohos.telephony.observer` | `offCommunicationStateChange`, `onCommunicationStateChange` | 导出落后；需虚拟 RIL 状态事件验证 |

### 2in1 额外缺失

| 模块 | 缺失函数 | 根因方向 |
| --- | --- | --- |
| `@ohos.busManager.serial` | `getSerialPortList`, `addPortAuthorization` | 整个模块未打包；QEMU serial 设备和授权状态需联合验证 |
| `@ohos.net.netFirewall` | public: `addNetFirewallRule`, `getNetFirewallPolicy`, `getNetFirewallRule`, `getNetFirewallRules`, `removeNetFirewallRule`, `setNetFirewallPolicy`, `updateNetFirewallRule`; system: `getInterceptedRecords` | 整个模块、Native 库、权限和 firewall 后端都缺 |

### 运行值缺口

除函数外，phone 还缺 51 个 class、62 个普通 enum、19 个 variable 和 1 个 namespace；2in1 缺
41 个 class、53 个普通 enum、19 个 variable 和 1 个 namespace。主要集中在 ArkUI 新组件、
PhotoAccessHelper、Accessibility、AbilityRuntime、Bluetooth、Audio、Camera/Image/WebView 等模块。
这些数量是模块对象与声明的表面不匹配，不等于同样数量的 API 都不可调用。函数需回移
真实实现；无公开 constructor 的数据类还需检查实际工厂返回对象及属性契约，不能仅凭
Object.keys() 断言其数据 API 无实现，也不能手写无行为的占位构造器。

2026-10-05 修正 `const enum` 分类：精确使用审计 SDK 提交
`411d28f767bd6cd2a6905e3c6b15f0992f55b81b` 再生，不改用更旧的构建 SDK。
每种设备原清单中的 14 个值是常量 enum，不是必须由 NAPI 提供的对象；从运行导出缺口
移到编译调用契约，真实函数缺口数量完全未变。总计 16 项常量契约单独保留为
`compiled_caller_not_verified`，仍待实际 ArkTS 1.1 编译调用验证，不能算已修复。

## ArkWeb 执行链：JavaScript 可用，WebGL 仍未验收

phone 和 2in1 的 WebView 探针均记录了 `web.page_begin=true`、`web.page_end=true`、
`web.title=Example Domain` 和 `web.url=https://example.com/`。这只能证明 Web 组件可启动、
HTTPS 页面可加载并能读取部分控制器状态，**不能证明页面脚本正常执行**。

原始复合探针在**同一段 JS** 中依次执行 Canvas、WebGL1 和 WebGL2，因此当时无法区分
V8/回调与图形上下文失败。新增分段探针在旧 ARM64 phone 镜像上取得明确结果：
`web.js.arithmetic.result=2`、`web.js.dom.result="Example Domain"`、
`web.canvas.2d.result=true`；WebGL1/2 分别超时。Native EGL 探针进一步证实公共 EGL wrapper
广告了 `EGL_EXT_create_context_robustness`，而 QEMU 的 Mesa backend 未提供该扩展；ArkWeb
据此请求 `EGL_CONTEXT_OPENGL_ROBUST_ACCESS_EXT`，Mesa 返回 `EGL_BAD_ATTRIBUTE`。当前新增
补丁只在 backend 真正支持时广告该扩展，效果还需首个新镜像的启动验证。原始复合证据见
`docs/capability-audit/runtime/arm64-phone/hap-probe-v9/results.log`、
`docs/capability-audit/runtime/arm64-2in1/hap-probe-v9/results.log` 与对应设备的
`hap-probe-v9/web-gpu-hilog.txt`。

| 路径 | 当前结论 | 不能推导出的结论 |
| --- | --- | --- |
| `@ohos.web.webview` 模块及页面加载 | 可加载；HTTPS 页面、标题和 URL 通过 | 全部 WebView API 可用 |
| 页面 JavaScript、DOM 与 `runJavaScript()` 返回值 | 旧 ARM64 phone 分段探针通过 | 其他架构和 2in1 全部通过 |
| Canvas 2D | 旧 ARM64 phone 分段探针通过 | WebGL/共享 GPU 上下文可用 |
| WebGL1 / WebGL2 | 旧 ARM64 phone 分段探针超时，EGL robust attribute 失败 | 将 native EGL pbuffer 成功等同于 ArkWeb GPU 成功 |
| `v8_shared` / Native JSVM | 现有 JSVM 用例通过其覆盖的子集 | JSVM 与 ArkWeb renderer 是同一执行链 |

`ohos-native-bindings` 的 `ark_web` 四个用例调用 `init`、`initAndKeep`、
`watchLifecycle`、`registerCustomProtocol`、`refreshPage`，旧版统一用 `ranOrThrew()`
断言；该 helper 忽略调用返回值，对成功或有文字的异常都返回 true，也未断言页面 JS 返回值、JS proxy
回调、`custom://` 响应或刷新后的实际行为。因此 4/4 pass **不构成 ArkWeb 执行通过**。
现已收紧为异常即失败、协议注册必须返回 true，并修正 WebviewController 的实际 webTag；
注册用例仍不构成页面执行证据，主进程 WebView 与独立 Hypium 进程也不能混为同一实例。

Vibrator 原用例同样会吞掉错误：现要求真实 start/customStart/cancel 成功。进一步发现
Custom JSON 被 VDI 的全部 false capacity 提前拒绝，上游时间序列 stop marker 也被拒绝。
已准备 time-delay-only 的真实时间轴修复及 4 项 ASan/UBSan 回归，尚未进入新 guest。
QoS smoke 也已改为精确检查六种 set/get 等级；旧的非空字符串结果不能代表这些切换通过。

下一步在新打包的 ARM64 phone 镜像上复验纯 JS、DOM、Canvas 2D、WebGL1/2，并补
JS proxy 双向回调、异常/renderer 退出边界；首包通过后再覆盖 2in1、armv7a、x86_64。
不能只检查 `libv8_shared.so` 或 ArkWebCore HAP 是否存在。

## 权限注册缺口

以下列表是旧镜像审计基线，不是当前设备契约下全部应开启的权限。
2026-10-05 复核固定 AccessToken 源码：phone 中 12 项缺失是明确限定 PC 的权限，
不能因 API 使用的广义 SysCap 同时覆盖 phone 就给手机放开它们（例如 diskSN 在非 PC
设备按 SDK 文档返回空值）。`HEALTH_DATA` / `HEART_RATE` 仅见于 since 8、deprecated
since 9 的 Sensor 重载注释，当前源码使用 `READ_HEALTH_DATA`；旧重载的权限兼容行为仍待验证，
不通过追加宽松权限定义伪装修复。

2in1 的 16 项旧缺失在固定源码中均明确支持 2in1。发现构建仍默认
`target_platform=phone`，AccessToken 按该变量而不是 `device_type` 生成表。
已准备构建显式传 `target_platform=pc`；表校验要求全部定义及原 APL/ACL/内核权限字段匹配，
没有修改权限等级。实际 source 的 phone 表 825 enabled/148 disabled 通过；隔离生成的
PC 表 887 enabled/86 disabled 通过，均包含 973 个源定义。PC 结果不是 2in1 编译、打包或运行证明。
这项构建修复晚于正在编译的 phone-8fBzhQ；首包 phone 已使用正确默认平台，后续 2in1
必须用包含新平台参数和表校验的冻结输入。其 16 项 API/权限流程仍需新包正常/系统应用验证。
权限扫描器现在保留 source 的设备限定证据，并将合法禁用项与真正缺失区分；不把它们标为 API 通过。

两种设备共同缺 11 个官方接口权限：

- `ohos.permission.ACCESS_DISK_PHY_INFO`
- `ohos.permission.ACQUIRE_LOCAL_ACCOUNT_AUTHORIZATION`
- `ohos.permission.CONTROL_DEVICE`
- `ohos.permission.CUSTOM_SCREEN_RECORDING`
- `ohos.permission.ENTERPRISE_GET_INSTALLED_BUNDLE_LIST`
- `ohos.permission.GET_ABILITY_INFO`
- `ohos.permission.MANAGE_APP_KEEP_ALIVE`
- `ohos.permission.MANAGE_SELF_SKILLS`
- `ohos.permission.MANAGE_SKILL`
- `ohos.permission.SET_NET_EXT_ATTRIBUTE`
- `ohos.permission.kernel.SUPPORT_LOCAL_PLUGIN`

phone 另外缺：

- `ohos.permission.BACKGROUND_MANAGER_POWER_SAVE_MODE`
- `ohos.permission.HEALTH_DATA`
- `ohos.permission.HEART_RATE`

2in1 另外缺：

- `ohos.permission.DLP_POLICY_MANAGER`
- `ohos.permission.ENTERPRISE_ACCESS_DLP_FILE`
- `ohos.permission.ENTERPRISE_DATA_IDENTIFY_FILE`
- `ohos.permission.ENTERPRISE_MANAGE_PRINT`
- `ohos.permission.kernel.TRAFFIC_FILTER`

这里只把权限写进 JSON 不够：还需同步权限定义、ACL、预授权、签名能力白名单和对应 HAP
签名，否则 API 仍会返回 201/202 或安装失败。

## SysCap / 产品画像缺口

旧 phone 镜像的官方文档/SDK 声明差异（不是九个已确认缺失实现）：

- DistributedFile、HiDumper、DataTransitManager、DeviceAuth、DeviceSecurityLevel、PinAuth：
  固定 registry 已 abandoned，当前 SDK 无 API 引用；按窄证据处理退休名称，服务保留，行为待审计；
- Window SessionManager：phone 已准备实际 SceneBoard 数据路径，不仅追加声明；
- SDK 默认画像中的 AVInputCast 与 phone 文档内 AudioSuite：联合开启实现，仍待真实闭环。

2in1 官方画像需要、镜像却未形成闭环：

- BusManager.Serial：SysCap、模块均缺；
- NetManager.Eap：模块可加载，但 SysCap 为 false；
- Audio.DeviceEnhance：manager 可创建，但 SysCap 为 false且路由 unsupported；
- Window SessionManager：相关窗口实现部分存在，但 SysCap 为 false，FloatingBall/FloatView disabled。

反向问题同样严重：phone 额外声明 61 个、2in1 额外声明 75 个超出官方 SDK 画像的能力。
其中多项没有后端。最终产物必须明确选择“实现”或“取消声明”。

## 系统 HAP、Provider 与插件缺口

这是 ArkTS 1.1 模块能加载、函数也存在，但调用仍失败的主要来源：

| 能力链路 | 当前缺口 | 适配方向 |
| --- | --- | --- |
| Share Picker | 配置引用 `com.ohos.sharepickerdialog`，payload 缺失 | 构建、签名、预装并验证回调，不接受 Promise 先成功后报错 |
| Distributed Hardware UI | HAP 实际目录与 `install_list.json` 路径不一致 | 修正预装路径 |
| AV Cast / Media Controller / Desktop Lyric | phone 无 provider；2in1 包名为 `com.hmos.*`，框架硬编码 `com.ohos.*`，入口也不全 | 统一 bundle/entrypoint，补预装和 UIExtension |
| Photos | 2in1 未注册且签名白名单不匹配；phone 缺三个 API 26 entrypoint | 重签/白名单/预装并补 Ability |
| Calendar | 2in1 HAP 未注册；两设备 whole authority、编辑和提醒入口不完整 | 修正签名与 DataShare/Ability 装配 |
| Print | 2in1 PrintSpooler 未注册、无 PrintExtension/远端 provider | 构建 QEMU virtual printer provider 或明确取消能力 |
| DLP | 2in1 payload 未注册、签名能力不匹配且缺凭据 provider | 修正签名/白名单并提供 QEMU provider |
| Settings/navigation | `com.ohos.settings` 与源码硬编码 `com.huawei.hmos.settings` 不一致，多个 UIExtension 缺失 | 参数化/改包名并补入口 |
| PermissionManager | 2in1 缺 `OpenSettingAbility`；phone 无 manual_settings 权限，不应追加 PC 权限 | 已准备独立单项协议入口、真实授权/状态确认及身份/session 边界；8 项主机回归、隔离系统 API ArkTS 编译通过，新包/2in1 UI 仍待验收；不以旧数组授权弹窗代替 |
| Accessibility | core E2E 可用，但 ScreenReader、Caption、Settings entrypoint 缺失 | 打包最小 QEMU provider 并验证 enable/disable 行为 |
| VPN authorization | 框架找 `com.huawei.hmos.vpndialog`，镜像是 `com.ohos.vpndialog` | 修正 bundle target，并与 sysvpn 导出一起验证 |
| Camera/Contacts picker | phone HAP 缺框架硬编码的 picker Ability | 补 Ability 或修正目标 |
| AppDomainVerify | 可选 extension 缺失，但上游已有 HTTP 验证 fallback；Want conversion fallback 返回空目标 | 测试真实验证/刷新及 HTTP/HTTPS 路由；不能仅凭缺可选库判定验证失败 |
| ArkUI 文本菜单 | expanded-menu、share、translate、text-analyzer 插件及目标应用缺失 | 打包插件与最小 QEMU handler |

## QEMU 后端缺口

这些问题不能仅靠复制库或增加 SysCap 解决：

| 后端 | 当前状态 | QEMU 可用化要求 |
| --- | --- | --- |
| Audio | 无 PCM，`/dev/snd` 只有 timer，未启用 virtio-snd | QEMU audio device + guest kernel/ALSA/HDF + renderer/capturer 数据回环 |
| Camera | 无 `/dev/video*` 与 Camera Host | virtio/v4l2 或确定性虚拟 Camera HDI，能枚举、预览、拍照 |
| Wi-Fi | 只有 virtio `eth0`，HDF 寻找 AP6275S | 虚拟 WLAN/受控 mock HDI，状态转换、扫描、连接/AP/P2P 不能 false-success |
| Bluetooth | 无 controller/vendor library | 虚拟 HCI/vendor backend，至少完成 enable、发现、配对、GATT 基础闭环 |
| Location | 无 GNSS/network provider | 可注入坐标的 QEMU location provider，支持回调、mock 标记与 geofence |
| Telephony | 无 modem/SIM/RIL | 虚拟 RIL/SIM 状态机；否则 phone 不得宣告通话/短信/蜂窝数据可用 |
| Vulkan | 无可用 ICD | 打包 Mesa lavapipe/virtio Vulkan ICD，并验证 instance/device/queue |
| ArkWeb 图形/执行链 | 页面加载通过；复合 `runJavaScript()` 探针未返回；EGL shared context/SharedImage 失败 | 先隔离纯 JS、DOM、proxy 与 WebGL，再按故障层适配 ArkWeb renderer/V8 或 EGL/虚拟 GPU |
| Video encoder | 广告 RK encoder，但实例创建失败 | 软件编码器或可用 virtio codec，且能力枚举必须与实例创建一致 |
| USB gadget | `/sys/class/udc` 为空 | QEMU UDC 后端或取消 gadget/device-mode 声明 |
| Distributed/SoftBus | user-mode NAT 隔离 guest | 提供 bridge 启动模式和双机 E2E |

内核还需单独补齐并验证 eBPF、ARM64 FTrace、DMABUF process info、F2FS quota、AccessToken ioctl
和资源调度 cgroup。配置项存在不等于 syscall/文件系统行为通过。

## 现有 `ohos-native-bindings` E2E 的覆盖边界

当前 ARM64 记录为 33 个模块、96 pass。它对 JSVM、vibrator、基础 ArkUI/Input、HUKS、文件、
图像、网络查询等已覆盖路径很有价值，但不能作为“全部接口可用”的结论：

- Camera 用例验证的是未运行时稳定拒绝，没有枚举/预览/拍照；
- ArkWeb、NetStack、NetConnection 等多处 `ranOrThrew()` 允许异常也算通过；
- 多数模块只覆盖 create/release 或一两个 happy path；
- 没有覆盖上述 48/38 个缺失函数、权限拒绝分支、Provider 入口和大部分虚拟硬件数据路径；
- WindowManager 的 phone 失败是设备边界，2in1 剩余 visible-layout 数量是 fixture 假设，二者不应
  与真正 API 缺失混为一谈。

后续验收需要新增一个 Native/ArkTS 1.1 capability gate：表面完整性、权限、真实调用结果和
后端可观察状态分别断言，禁止用 `ranOrThrew()` 覆盖失败。

## 建议修复顺序

1. **P0 表面与契约**：Native 符号、两个 2in1 模块、48/38 个函数及运行值、权限注册、SysCap
   画像；先消除固定 BOM 与 OHOS 7 API 26 契约错配。
2. **P0 可直接装配**：Ethernet/VPN feature、DHardware 路径、HAP 预装/签名、明确的 bundle 与
   entrypoint 错配、运行时插件。
3. **P1 执行与通用 QEMU 后端**：先隔离并修复 ArkWeb 页面 JS/proxy 与 WebGL 图形链，随后是
   Audio、Vulkan、软件视频编码、eBPF/FTrace/quota/DMABUF、QoS 与 AccessToken。这些会同时
   解锁大量 Native 与 ArkTS API。
4. **P1 系统 Provider**：Share、Settings、Permission、MediaController、Photos、Calendar、
   Accessibility、Print、DLP。
5. **P2 设备模拟**：Camera、Location、Wi-Fi、Bluetooth、Telephony、USB gadget、双机 SoftBus。

完成每一批共同修复后，先构建一个 ARM64 代表包，启动新镜像执行严格行为验证；首包通过后才
构建其余五个产物。
