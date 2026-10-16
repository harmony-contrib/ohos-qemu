# OHOS 7 能力并行修复与集中验收

2026-10-15：先整理提交已有适配，再从同一个提交创建五份独立 worktree。
本轮基线是 R49 的 281/199/82，另有 R50 HiTrace 超时与 R51
RenderService 重启两项整体验收故障。提交源码、主机回归或独立诊断不核销缺口。
CloudSync、imageGeneration、ArkTS Static 三项既有排除保持不变。

| 子 agent | 能力 | 要求数 |
| --- | --- | ---: |
| apps | 系统应用/入口、无障碍、能力声明/运行时插件 | 34 |
| network | VPN、网络与外设 | 9 |
| location | 定位、电话与通信 | 22 |
| media | 音视频输入/处理、媒体知识数据 | 7 |
| system | 其他系统服务、子进程与内核身份 | 10 |
| 合计 | 互斥且完整覆盖现有未闭合要求 | 82 |

逐项分配、允许修改的路径与基线来源保存在
`capability-audit/parallel-work-plan.json`。每组先逐项复核固定源码和已有证明，
选择可实施的真实修复，补齐有针对性的检查，再提交该组分支。不能以空实现、
虚假成功、扩大排除或删除需求替代适配。无法完成的项目须写明具体缺失环节。
当前工具同时容纳主 agent 与三个子 agent；五组分批运行，完成一组再启动下一组。

每组使用自己的 worktree、临时目录、输出目录和分支。禁止修改主工作树、
其他组目录、共享 OpenHarmony 源码/out 卷或原始证据。除 Git worktree 隔离外，
每组必须申报补丁实际修改的上游源码相对路径；主 agent 在集成前同时检查
仓库文件与上游目标是否重叠。跨组目标由主 agent 指定唯一所有者后处理。

主 agent 独占公共构建脚本、正式测试入口、完整账本和交付状态。各组新增探针
使用自己的 `batch_<组>_` / `test_batch_<组>_` 前缀；公共入口接线通过该组
报告中的 `integration_requests` 提交，由主 agent 统一实现。

集成检查器为 `scripts/verify_capability_agent_scope.py`。各组的
`result.json` 必须包含全部分配 ID 的 `requirements_review`（按 ID 建表，
或带 `id` 的列表）、完整 `upstream_targets` 列表、`tests`、
`integration_requests` 和 `remaining_gaps`。检查器读取待合入的 Git 提交，
核对允许路径与编号补丁的实际上游路径，并与已接受组的报告比较目标重叠；
这项检查通过只代表分工正确，不代表能力验收通过。

资源规则：各组可运行有界的本地主机检查；Docker、官方 SDK 编译、QEMU、HDC、
制品构建和清理都先向主 agent 申请资源。默认最多一个重任务，编译 jobs=2；
以实际内存和磁盘余量决定是否调整。容器、卷、端口、客体和输出目录必须唯一。
不得重启 Docker、停止其他任务、复用他人的 HDC guest 或清理他人的卷。
共享源码及 out 只读挂载，各组写入私有 scratch；正式构建由主 agent 执行。
宿主检查使用 `LC_ALL=C LC_CTYPE=C LANG=C`，避免 macOS Perl/shasum
继承 Linux 的 `C.UTF-8` 后崩溃；不得以此修改产品代码或放宽测试断言。

集成时先验证各组提交的修改范围、上游目标、测试记录和未闭合清单，再按顺序
合入并运行完整主机回归。全部已知修复集中准备后才冻结 ARM64 phone 代表包；
记录归档路径、SHA256、环境、命令及完整运行结果。失败集中收集后统一修复，
首包完整门槛通过后才构建和验证其他五包。已有失败及证据保持原样。

## 2026-10-16 首轮集成结果

现有适配已先提交为 `2aa40c0cdaa9710c9d330814211f10c686ddd431`。
五组均从该基线使用独立工作树，受工具并发上限约束分批执行；各组修改已顺序合入。
本轮产品代码冻结提交为 `3748d4c4d3d2835e61dd7419a339575ec7c6ce5e`。

| 组 | 复核要求数 | 已合入的源码修复 |
| --- | ---: | --- |
| apps | 34 | 无障碍设置等待实际完成后再更新缓存/发成功通知，串行处理请求 |
| network | 9 | VPN 控制错误传播、断开信息清理、父进程被杀后的子进程清理 |
| location | 22 | RTT 多订阅/去重/可选 off、排队取消、环境清理及注册对象生命周期 |
| media | 7 | AVC 输入 offset、RGBA 字节 stride、YUV 平面和容量边界、拒绝后的 Surface 归还 |
| system | 10 | 子进程启动前保存回调引用、失败清理、并发/重入通知只回调一次 |

五组申报的 17 个上游目标均无重叠，范围检查也核对补丁的实际目标，避免两个不同
仓库补丁目录修改同一个上游文件。公共脚本仅由主 agent 接线。
Settings、RTT、AVC 新组件已接入公共构建流程；子进程由已有组件应用新增补丁。
VPN 两个控制组件及后端仍保留为待整体接入：GN、二进制、init、许可证、DAC、
SELinux 与真实协商/路由/DNS/IPv6 验收尚未齐备，不能只接控制入口就算交付。

集中检查结果与完整证据索引见 `capability-audit/parallel/integration-result.json`。
Linux 下 5 项网络生命周期测试全部通过，包含实际 fork/exec 与父进程 SIGKILL。
网络两个完整 ARM64 产品编译单元通过；netsys 的候选宏为显式诊断参数，尚未证明
GN 选择。RTT 两个完整 ARM64 产品编译单元通过，真实命令已含 SUPPORT_RTT_CALL，
并核对 ThinLTO 的目标三元组及补丁头文件依赖。上述结果均未证明产品链接或新包行为。

完整主机回归收集 1,891 项：1,888 项通过、3 项平台条件跳过，零失败、零错误，耗时 513.814 秒。
冻结前后 2,527 个受版本管理文件的 SHA256 一致。基线中两个 macOS Perl/shasum locale 错误已用
可移植 C locale 重放 8 项全部通过；原始失败记录保留。
旧 Mesa consumer05 证据的构建器哈希与当前输入不同，已实测被当前校验器拒绝，
没有把它用于核销 RenderService 故障或满足代表包门槛。

本轮新增核销为 **0**：仍为 281 项要求中 199 项已闭合、82 项未闭合
（26 项导出、56 项行为），另有 HiTrace 超时与 RenderService 重启两条验收故障记录。
这些是重叠的审计记录，不能直接解释为 84 个独立代码缺陷。
五组结果文件逐项列出剩余实现和证据缺口；系统组特别指出 StartMode 是 SDK const enum，
缺反射对象本身不足以证明运行时错误，仍须按真实生命周期契约验收。

尚未新建制品；完整交付验收保持 0/6，代表包门槛未通过，也未启动其余五包矩阵。
下一阶段先集中补齐产品编译/链接、Settings HAP 和正式调用方边界用例，以及两个
核心整体验收故障，再冻结单个 ARM64 phone 新包，按 AGENTS.md 记录归档路径、
校验和、环境、命令和完整结果。首包通过后才构建其余五包。

## 2026-10-16 持续修复与产品编译进展

任务仍在执行，当前状态与证据索引见
`capability-audit/parallel/core/round2/progress.json`。首轮报告保留为历史记录。
截至本次检查点，新增核销仍为 0，交付运行验收仍为 0/6。

本轮已合入定位图标的真实权限使用状态、BLE 实际服务过滤与回调生命周期，
3D 引擎完整初始化/失败重试，媒体知识内容的真实数据库查询候选，音频完整读取、
Stop/Resume 代次和退出处理，以及 VPN 原子会话/协商网络状态和 API26 OOB 入口候选。
知识内容的部分语义、OOB 服务/GAP 实现和其余提供方仍在补齐，不能以入口存在核销。

| 实际执行的产品检查 | 结果与限制 |
| --- | --- |
| 当前 Mesa 消费端 | 1,078 个构建步骤完成；尚无新包 GL/RenderService 运行通过证明 |
| AVC、子进程、3D、音频采集 | 各 2 个完整 ARM64 产品编译单元通过，共 8 个；不代表链接或运行 |
| 定位 | 产品 IDL 重新生成全部接口/代理/桩，8 个业务编译单元与新代理/桩共 10 个完整单元通过 |
| 正式 AVC 调用方 | API26 Release SDK 的 ARM64、ARMv7、x86_64 三个共享库编译/链接通过；尚无签名 HAP/运行证明 |
| ALSA 内核/设备选择 | 三份固定源码配置与 vendor JSON 的实际安装、重放通过；尚无新内核 PCM 验证 |
| 集成防护与音频主机回归 | 22 项完整源码状态/所有权检查及 9 项音频检查通过；受控依赖不是产品运行证据 |

3D 首次验证误将 split-LTO 对象视为单个文本模块，两个实际编译命令均返回 0。
修正验证器后，在新目录复验原始对象及其全部 4 个真实 LLVM 模块通过；原始失败和
对象哈希保持不变，没有关闭 LTO/CFI 或删除编译选项。

公共构建流程已统一接入定位、知识内容、音频完整读取及完整 VPN 源码输入。
ALSA 输入保留 card0 ES1370 播放，新增 card1 QemuCapture/device0 采集；真实
producer 写入内核 loopback 对端 device1，公开 Capturer 必须经 AudioService/HDI
采集并由独立检查器核对挑战内容。三个内核配置、vendor JSON 和启动参数由主 agent
独占修改；仅 `device/qemu/common/virt_full/audio_alsa/vendor_capture.c` 精确授权媒体组。
网络组的 Bluetooth 服务/GAP 文件也按精确名单登记，不与其他组重叠。

应用组当前独占 CalendarData 官方 SDK 构建租约，网络组继续 OOB 服务/GAP，
系统组接替媒体组的并发槽位继续 MSDP 等系统提供方。定位业务与虚拟 GNSS/HCI/
RIL/IMS、媒体剩余语义和完整链接/新包运行仍在队列中；重任务保持一次一个。
设备证明的合法 OEM 身份、密钥和服务配置尚未提供，AudioVivid 真实构建器依赖
尚未找到，均保留未通过。不得伪造凭据或用固定结果填补能力。

本次尚未启动新的完整制品构建，也未启动其余五包。下一轮代表包仍须集中当前已知
修复后冻结输入，保留归档路径/SHA256、环境、命令及全部边界/回归运行证据；
首包完整行为门禁未通过之前，其余五包不得开始。

后续本轮检查：ALSA 播放共享代码/采集驱动的 4 个完整产品 C 单元均通过，累计
22 个完整 ARM64 产品编译单元通过（不含另行记录的 SDK 调用方）。锁定 OpenVPN
2.7.8 更新后的完整源码已交叉编译并链接通过，二进制 SHA256 为
`782038937c8bfdf0363fcb3e56b4650cbd13d95e1d8b0c2cfe33da9aae2d201b`。
第一次尝试被诊断容器 `/tmp` 的 noexec 挂载阻止，实测确认后修正容器挂载并重跑；
原始失败保留，没有据此修改产品实现。

本轮当前 Mesa 的真实 EGL/GLES QEMU 用户态检查完成 6 次上下文生命周期与
19,507,428 个着色器像素检查，FDE 警告为零。六个新库的真实 ext4 写入、当前配方
来源校验、离线往返和篡改拒绝均通过。EGL 检查使用明确记录的 surfaceless 与库别名，
ext4 是仅含依赖的诊断图像；两者均不证明默认 OHOS 显示、新包 RenderService 或休眠。

CalendarData 新表单和 UIExtension 已完成实际官方 API26 Release HAP 编译，全部
五个本地 HAR 参与，unsigned HAP 及输入/SDK/工具/失败记录均绑定哈希。主 agent
已接入精确 Editor 字典与原有权限/签名防护，并以 require-editor 拒绝缺少界面的
最终源状态，14 项相关主机回归通过。后续源码复核发现 UI 回调没有保证 NAPI 环境
线程和生命周期，应用组正在补齐真实调度/清理后再统一编译该原生单元。
蓝牙 OOB 的真实服务/GAP/HCI 候选已合入，完整平台编译进行中；尚无实际控制器
及 peer 配对验收。以上均不核销原有 82 项，也不解除其余五包的门禁。

继续集成后，Calendar 回调调度/环境清理已合入，其完整平台单元通过；蓝牙六个服务
单元及一个 NAPI 单元也全部通过。此前 22 个既有产品单元加这 8 个，共 30 个完整
既有平台目标单元通过。新传感器的两个完整源使用实际 HDI 目标选项编译通过，并用
该目标的 LTO/CFI 链接选项生成真实 `libhdi_sensor_impl.z.so`；只调整并发数/私有缓存、
替换新对象并移除新 GN 分支不再依赖的旧 HAL。该诊断尚不证明正式 GN 选中和 HDF 加载。

AdminProvisioning 已合入真实 Stage/Hvigor 构建和激活/取消/重试/新 Want 生命周期修复，
官方 API26 Release unsigned HAP 编译通过。主集成保持原 normal APL、系统应用身份、
三项原 ACL 和五项请求权限，以准确平台叶证书绑定预装授权；实际固定源码的安装、
签名策略和传感器 init/GN 配置组合检查通过。新包仍须完成签名校验、BMS 和真实 UI 行为。

VPN 回调已绑定实际控制器/owner/account/UID/PID/vpnId，采用可撤销 listener epoch 和
真实 FFRT 串行队列。实际抽取函数用官方 Linux API26 编译，并链接输出中的真实
`libffrt.so` 在 QEMU 用户态通过全部断言；账户、IPC 和 VPN 后端在此探针中仍为明确
double。当前两个完整辅助程序已用真实产品客户端编译选项及严格警告编译、原生链接。
首轮发现上游空回调的命名参数警告，已精确去掉五个未使用参数名；未关闭 Werror。
次轮保留两个成功对象，修正证据脚本变量遮蔽后复验同一对象并补齐桥接程序链接。
原始失败和输入/对象哈希均保留。后续多 owner broker 还在开发，会另行集中验证新批次。

传感器 socket 固定为 `/dev/unix/socket/qemu_sensor/input`，init 先创建 sensor_host
所有的 0700 专属目录，socket 为 0600；外部输入另受 UID、随机 nonce 和序列检查。
完整普通/开发 SELinux 策略编译均通过。第一轮发现非开发策略没有 `su` 类型，已将
HDC root 客户端规则限定在开发策略内，保留原始失败，未给普通应用开放写入路径。
HDI 加载优先级及真实运行时 DAC/SELinux 拒绝仍由新包验收确认。

公开 AudioCapturer 调用方的 ARM64、ARMv7、x86_64 API26 共享库编译/链接均通过，
ARM64 实际 ALSA PCM producer 也已编译链接。其余两种 producer 缺少当前输出中的
libasound，记录为未完成；未为此提前构建其余五包。普通 HAP 只经公开 Capturer 采样，
随机双声道挑战仅交 root producer，独立相关性、时间戳、生命周期和令牌边界仍待实际
新包执行。新增包检查器拒绝旧/混合 OpenVPN 构建、错误程序或签名/授权不符的提供方。

当前并发为网络 multiowner/TUN 归属、定位 district/轨迹/围栏/5A、媒体真实采集与
KnowledgeContent 日历索引；所有目标按独占路径登记。重型工作仍一次一个，正式构建
限制同一时间一个产品链接任务。详细路径/SHA256 与各诊断的适用范围见 core/round2
进度索引。代表包完整行为门禁仍为 false，六包完整验收仍为 0/6；尚未启动其他五包。

本轮继续收齐定位 district/滑雪业务链与 Holiday 索引。定位实际新 IDL 和 13 个完整
平台单元全部执行，12 个通过，NAPI 的 MAX_BUF_LEN 未声明错误交回定位组，在
当前融合围栏/5A 批统一修复。KnowledgeContent 六个完整单元全部执行，四个通过，
新 producer 的错误日志头名和 NAPI 直接 GN 依赖缺失交回媒体组统一修复；旧成功对象
和全部失败日志保留。首个 Knowledge 诊断缺少历史完整照片前置栈，属于编译组织
错误，第二次按正式构建相同的完整顺序应用，没有放松 source guard 或手工 -I。

普通 MIC HAP 第二次官方 API26 构建通过，SHA256 为
`8770670d422a22bad0e3756cc5474c63e3c29a192be63302dccfb02c3aefcd94`，
实际包内 MIC 声明和 native PT_LOAD 代码绑定验证通过；第一次真实 SDK 的 WRITE_ONLY
枚举错误已修复并保留日志。独立 root PCM 注入与 actual AccessTokenKit 查询/受控撤权
工具完整 ARM64 编译链接通过，加入单调时钟范围和实际系统库绑定。正式普通应用
runner 现要求真实可信授权界面、初始拒绝/用户决策/采样后令牌观察，私有 PCM 提取、
独立双声道随机相关性与时钟/生命周期验证；完整新包门禁要求同镜像 grant/deny/grant
三组对照。尚未执行新包，不能用这些构建或主机 fixture 核销录音能力。

固定可信 ICS 目录/资源合同已接产品 GN，默认没有任何虚构日期。只有明确的真实
外部 ICS 输入才进入包，原始字节及来源/SHA256 留档；缺省时只安装资源描述文件。
与 Sensor 的 GN 同文件声明采用可组合的完整状态检查，两者重复应用、来源哈希、
未知/部分/符号链接拒绝和写入回滚主机检查均通过。

RIL 固定 CRLF IDL 已追加真实 modem 通信态回调。实际重新生成完整继承接口前后
全部旧命令映射一致，新号为 162，真实签名使用 V1_1 RilRadioResponseInfo 与 bool，
oneway 的 TF_ASYNC/WriteBool/SendRequest 已核对，两个完整生成 proxy/stub 平台
单元均通过。三次先前诊断分别暴露输出范围、CRLF 处理和验证器 namespace 正则
问题，均保留；不把 HDI 通过当成真正 AT/HRil/registry/应用回调的运行验收。

总账仍是 281 项、已关 199、未关 82；本轮新增核销 0，六包完整验收 0/6，代表包
完整运行门禁未通过，其余五包尚未开始。


2026-10-16 当前集成追加：定位 round5（worker 94d765b，集成 264c020）通过与其他四组互斥的 upstream scope 检查，移除补造卫星，修复 GNSS 配置初始化和失败传播，27 项 host 回归通过。VPN broker Linux 第三次完整回归固定 e72fbea、GCC/G++、保留 Werror/ASan/UBSan，41 项全部通过、0 跳过；前两次环境与 fixture 失败日志原样保留。证据：`/Volumes/PSSD/qemu/validation/first-20261005/issue-20-20261006/r52-VPN-broker-complete-Linux-host-03/artifacts/evidence.json`。

主构建已接入 base/ext broker、完整 5A 通信状态组件及 Recorder 配置修复。VPN 两个私有监听 socket 由 init 创建并传递，netsysnative 原有配置逐字段保留；源安装 7 项事务/未知修改测试通过。诊断编译器新增真实 GN public config 字面 include 导出来源记录，保留原产品所有编译保护，并明确该补充不证明新 GN 的真实依赖选择。新增完整 GNSS/Recorder/VPN TU 编译检查，等待集中结果。以上仍为源码和诊断阶段，82 项仍待关闭、代表包运行门禁 false、验收交付 0/6，其余五包未启动。


2026-10-16 GNSS系统批 e16465a+a9b7697 通过25个累计upstream所有权检查后集成160f785+09ab0d3；根已为真实1022 location_host接入专属0700目录、input0600策略、GN目标、const.location.supl_mode=1实际standalone配置。根联合Sensor+GNSS+VPN完整普通/开发者SELinux编译PASS（r52-combined-Sensor-GNSS-VPN-SELinux-policy-01，19.585s）。GNSS四个完整真实平台TU保留CFI/LTO/栈保护全部PASS（r52-GNSS-bridge-provider-full-TUs-01，56.676s），实际新bridge和vendorGnssAdapter.so两个共享库按HDI完整CFI/LTO链接及符号/SONAME检查PASS（r52-GNSS-bridge-provider-actual-CFI-links-01，9.812s）。以上均未声称新GN目标已经在产品选择或新guest实际加载。

根也完成实际Sensor DSO的依赖专用ext4读回与四项拒绝测试（r52-real-Sensor-DSO-runtime-assets-ext4-01）：配置改字节、额外未绑定ICS、优先级更高的product VDI、两个不同真实inode歧义均拒绝。不是产品镜像，不核销运行能力。新增GNSS源码/构建图/三层真实库/启动和参数的镜像绑定检查，包装及离线检查均必须执行。

完整能力TU第一批416.977s：location 14/15PASS，真实const AppIdentity&缺口由round6修复并集成b934096；Knowledge 4/6PASS，缺RDB/OpenSSL declared exports；Recorder标准CLI与私有stage清单问题、VPN遗漏前驱问题全部收齐。媒体round5 63395d3已通过scope集成aaecdc8，补真实普通后台录音与RDB direct dep/Recorder标准CLI；47 host tests及Recorder/audio_event最终三ABI链接PASS，真正HAP/权限/运行仍待验。VPN当前helpers两个完整TU和实际executable links PASS。真实FFRT第一批health PASS、callback fail；已实证为探针遗留单应用VPN触发正确互斥过滤，network修探针e262999集成8667c52，保留原断言并补抑制分支，待真实libffrt复验。所有失败证据原样保留；其余五包未开始、门禁false、0/6、82项仍待闭环。

2026-10-16 后续集中复验：location 15 个完整平台 TU、Recorder 完整 TU 及真实 libffrt callback 回归通过（r52-current-capability-full-TUs-and-FFRT-02）。六类普通 HAP 第一轮中 Capturer/Recorder/拒绝 Recorder 的真实 API26 unsigned HAP 和 native/权限合同通过；三个 event HAP 发现同一 ArkTS throw 类型问题，67ea121 修复后仅重建这三个角色，r52-three-audio-event-ordinary-HAP-roles-02 三项均通过。仍未证明签名安装、真实权限 UI、后台任务或录音事件。

真实通信 17 个完整 TU 首轮完整统计为 11 PASS/6 FAIL（此前只摘录部分错误日志误写14/3，已按objects全表纠正）（r52-communication-complete-platform-04）：其中3个新增权限检查的 NAPI/ANI consumer 缺真实 access_token direct GN dependency；另外两份proxy缺完整override声明、registry service缺ipc_skeleton.h。所有失败交原所有者集中修复；Rust完整链接尚未通过。VPN 完整 TU 首轮 7 PASS/1 FAIL，真实基接口非虚析构暴露 fixture 错误；network 修复 a942364 已经 scope 检查集成 d9ac091，保留共享接口和 Werror，等待受影响平台 TU 复编。Holiday 在真实产品 -fno-exceptions 下的 try/catch 编译错误已交 media 集中修复，未修改编译保护。

根完成 Recorder 普通应用权限 UI/token、私有输入/输出、两个录制生命周期与独立 ffmpeg/ffprobe 实际 AAC/AVC 解码验收接线，首包门禁要求同一新归档、同一 boot、三个新 nonce 的 grant/deny/grant；离线门禁重新运行解码而不接受旧 pass 字段。36 项相关权限边界/证据/调度回归通过（recorder-acceptance-host-01.log），不是 guest 或包验收。真实 ffmpeg/ffprobe 9.0.1 工具及 SHA 另存 r52-independent-media-decoder-tools/evidence.json。

截至此处仍为 281/199/82，新核销 0、交付验收 0/6、首包完整运行门禁 false，其余五包未启动。

根追加前台 active MIC revoke 实际运行与严格重放：真实 UI 启动普通 public Capturer，经原系统 MIC 允许对话框、真实 RUNNING/PCM checkpoint 后，仅对自有实际 token 调用 RevokePermission（不杀进程），验证前后同 PID/starttime/UID，再回传新 nonce ACK。验收要求撤权发生在该新 handshake 区间内、后续真实 PCM 静默、Start 被拒绝、同一源的 producer 成功完成以及实际 native Release/Destroy/UIAbility completion。首包正式 suite/离线门禁已纳入 audio-revoke；37 项相关 mutation/既有证据调度回归 PASS，实际 guest 尚未执行，不核销82项中的任何记录。

2026-10-16 集中源修复复编 r52-batched-platform-fixes-05（冻结bdc156a，113.211s）全部通过：Holiday 1完整TU保留-fno-exceptions；VPN networkvpn_service 1完整TU保留Werror；通信3个权限consumer及当前生成wrapper 4完整TU。各证据明确selected_only，不能把这6项误写为重新编完所有能力单元。原先通过的未改源单元证据单独保留；新增GN真实选择仍待产品构建。

GNSS系统Linux测试4288e492已scope检查合入30774b8：GNU11.4/Werror/ASan/UBSan/LSan，provider35场景和bridge24对照完成通过。两次真实unload marker、同进程reload、新nonce拒旧帧/新代回调均实测；仅修host harness可移植性，0产品target变化。证据在 parallel/system/round5-linux-gnss/，容器已删除。真实OHOS客体CFI加载、公开API以及首包行为仍待验。

完整Rust ANI首轮进入实际ld.lld，但旧产品 libtel_state_registry_api.z.so 缺新增虚方法/调整thunk而失败；r52-communication-full-Rust-01 原日志保留，正用真实新对象与原solink recipe闭合私有依赖，禁止用stub/放宽no-undefined替代。根已核对后台服务1903/ANS3203实际源码并增加严格task UID/pid/未挂起状态与notification OwnerUid/Id/Label联合观测；双UID焦点运行编排与独立验收继续进行。82未关、新核销0、首包完整门禁false、六包0/6、其余五包未启动。

通信完整结果二次核对：04真实objects为11 PASS/6 FAIL，05仅复验并通过其中3个权限consumer加wrapper；另2个proxy与registry service仍待集中修复/复验。此前14/3为根统计错误，已纠正正文与progress，不使用任何失败对象进行API/Rust链接。

根已接入实际双UID焦点运行入口和独立核心重放：两个正常APL/空ACL的签名HAP，各自真实MIC/通知授权与normal KEEP_BACKGROUND_RUNNING token，联合1903/3203服务和两次请求后的新0.5s PCM，随后VOIP真实Start才允许归因owner forced STOP；contender真实Stop/Release和后台任务清理后才允许owner重新Start。核心重放逐字节关联snapshot与最终callback PCM，重新做独立挑战相关，严格检查token/进程/时钟/ACK/事件归因/通知与任务退出，不接受计数或先前checkpoint。已纳入正式suite/首包离线门禁，42项相关核心host检查PASS（不是guest验收）。根另修前台revoke的ready完成标记与ACK原子发布竞争；网络独占runner正在同批修相同ready/journal读取完成竞争。

真实当前子进程libchild_process.so及3D的lib3dWidgetAdapter.z.so、libKitHelper.z.so完整链接通过（r52-child-Graphics3D-actual-CFI-links-02，18.356s）；KitHelper链接本批新adapter库。原flags/全部输入SHA保留，child的CFI符号核对通过；两个3D原目标仅选LTO，不伪称它们选择CFI。01原先对3D误加CFI符号断言的失败证据保留，未修改产品保护选项。新fresh-PCM/last_callback媒体caller的三个实际API26 unsigned event HAP再次全部通过（r52-three-audio-event-fresh-PCM-HAP-roles-03）。本轮仍无新guest运行通过、0/6/82未闭合。

根集成 network 47f535f→8a712b9，五组路径互斥scope通过；18项host回归通过。ready等待真实event_ready完成，journal只允许当前尾项2s短写重试并保留原始字节，最终collect严格复核。根另发现fresh PCM回复仍有CREATE/短写竞争，调整为先等唯一实际event_fresh_reply再收JSON/PCM；独立重放绑定当时完成日志、最终native日志、私有文件和时钟，27项相关核心检查通过。此处均非guest验收，82未关、0/6、首包门禁false。

本批apps独占Settings share picker5文件与MMS text sendData3文件（详见parallel-work-plan.json）；ACTION_CHOOSE/HMS/Bluetooth及未实现附件链仍明确缺失。system获唯一CPU2/mem5g租约，仅做真实OHOS GNSS DSO ABI/CFI消费端；Settings/MMS官方SDK编译排队，不并发重型任务。

apps324d17f经五组upstream互斥scope通过后合入38c630e：真实Settings sysPicker/share与MMS text/plain草稿路由。根新增MMS固定26df98e源码ohos_app、QEMU原mms_hap选择接到源码目标，保留非QEMU预编译分支；仅将原MMS normal/system-app profile的分发证书和到期时间接到现有公共OS签名者，原ACL/受限项、两份原预装能力/四项授权的字段全部精确保留。未知签名/额外权限/重复条目拒绝；Admin完整已知MMS后继哈希允许整栈重放。33项相关source/策略/Share/Settings包检查PASS；01最初mac /var符号路径fixture失败保留，修正fixture.resolve后02/03通过。Settings/MMS官方SDK及实际签名/BMS/界面仍待验，分享不宣称消息发送成功，旧ACTION_CHOOSE/HMS/file-attachment缺口保留。

system实际OHOS ABI/CFI消费端 b80c6b1合入8484f87：QEMU-user02 exit0，13真实DSO、两次callback/unmap、reload和旧nonce拒绝，源码与真实loader证据保留；非guest/Binder路径。scope首查漏登记已授权tests目录而失败，明确补录该前缀后再查PASS，01失败保留，未发现五组产品文件重叠。

media只读round9 a9f988f合入a945ca9，发现ETS ready短写、主流error_callback漏判、event时间戳仅增量三个缺口；根已集中修，11项对应host检查PASS，包括实际ETS helper11场景和mode0/1/2 error/超前一小时负向对照。新ETS尚须三HAP真实编译和guest执行。

Settings/MMS当前官方SDK01完整尝试失败：host公共26.0.0.105缺系统组件声明（419 compiler errors，418条带文件坐标），MMS官方OHPM TLS重置。未将公共SDK缺system声明误认为419个独立产品缺陷。Settings转实际产品Linux26.0.0.39 SDK；02的CLI fetch_timeout太小、03的image原有/root/.ohpm断链、04缺私有pnpm缓存依次保留，均未进入ArkTS；05用私有root tmpfs和已有真实pnpm10.27缓存正在完整编译。根另固定真实NPM class-transformer0.5.1 tar SHA256=49efad879d3cc811a46e6baf72b0454a4f271c0da6b7899d024bdfcf94961f7e（已与官方metadata sha512核对），改本地固定依赖并去掉生产HAP未用的hypium devDependency；不改运行权限/ACL。

Contacts/Theme八个构建元数据d3823b8经scope通过合入f7a6ff5；真实业务仍有picker会话/计时器和renderer窗口清理待apps本批修复。Theme仅渲染扩展，未称壁纸设置UI已提供。82项未关闭、交付0/6、代表包完整运行门禁false，其余五包未启动。

Settings05实际完整产品Linux26.0.0.39 SDK编译PASS（256.309s），真实57,479,660B unsigned HAP SHA7487d5e02e9683e4fd506c589438d63d57b5e37a738e1deb1d194a342144a705，实际44扩展含sysPicker/share和3ABI共6原生库检查PASS。MMS02同真实SDK完整编译PASS（140.831s），真实8,091,208B unsigned HAP SHAa6a5847b9a5fde069fbe9f9571b3dae173bc2b2040ef9b00973d96abd0241951；原37权限、完整入口/skills及text/plain草稿接收合同PASS。MMS初版检查器误将旧visible字段当成未exported，失败另存；修为逐字段保留visible/exported的真实源/编译manifest后通过，未修改权限或BMS边界。

根修复external_input在share_picker后继全五文件已完整时的整栈重放，拒绝缺文件/未知共享后继；Settings镜像检查同时要求所有当前候选组件完整。MMS新增只读源/原profile/OS signer/原两份授权校验及强制镜像HAP检查；26项相关package/source mutation检查PASS。实际签名/镜像检查尚待执行，不把上述unsigned HAP当交付或运行验收。

最新ETS ready短写修复后，3个普通音频event HAP在真实API26 unsigned构建和native/权限/后台合同中全部PASS（r52-three-audio-event-ready-completion-HAP-roles-04）；仍待guest。根自查MMS签名helper提取公共输入函数后 certificates lambda 作用域错误，提升为模块函数并补外部签名/Git/CMS超时；将用真实公共OS key/profile/HAP和独立ext4反例完成签名与镜像检查，未提前称通过。
# Actual preinstall selection and MMS signing follow-up (2026-10-16)

The real source MMS unsigned HAP was signed with the existing public OS key,
verified with the pinned signer tool and checked against the original unchanged
ACL/grant policy. Private ext4 validation passed one positive and eight negative
cases (missing/duplicate/removable/numeric install row, wildcard grant, numeric
capability, duplicate HAP inode and altered ABC). Signed HAP SHA256 is
06f55bc9315ed6c0b436200132c46697cdd61d11426c68df27c84e9e806cca47.
Evidence is preserved under core/round2/MMS-real-OS-signing-and-policy-01.

Cross-review confirmed the same image install selection omission for Settings,
Photos and AdminProvisioning, plus BMS uninstall-list vetoes. Four package guards
now use a common source/image selection check with strict JSON types and the
actual uninstall/recover policy. Admin policy booleans also retain their types.
Thirty-nine focused tests passed, including actual ext4 positive and negative
selection cases for all four apps. A follow-up actual signed MMS image batch
will verify this combined check. No product image, BMS launch or first-package
runtime gate is claimed; packages accepted remain 0/6 and audit entries open 82.

# MMS actual preinstall selection follow-up (2026-10-16)

The image verifier now extracts the actual install_list.json and requires the
unique original /system/app/com.ohos.mms entry with removable=false. Source-only
checks did not cover BMS image selection. The policy matcher also checks JSON
types recursively; numeric 0/1 cannot replace BMS boolean fields. Six focused
host tests pass, including missing, duplicated, changed-path, removable and
numeric-boolean counterexamples. Real OS signing and ext4 counterexamples are
the next batch. No new guest acceptance or audit closure is claimed.
