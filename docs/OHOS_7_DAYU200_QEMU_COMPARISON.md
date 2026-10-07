# OpenHarmony 7.0 dayu200 与 QEMU 能力差异和补丁原因

本报告同时回答两个问题：dayu200 开发产品与当前 QEMU 适配有哪些能力差异，以及为什么选择同名部件后，QEMU 仍需要额外补丁。结论是：**部件数量接近，实际功能由 feature、板级实现、内核构建、预装资产和运行环境共同决定；现有补丁中还包含共享上游缺陷和构建环境修复，不能全部归因于模拟器。**

日期：2026-10-07（配置对比来自10月6日，图形运行证据补充至10月7日）。这里的“完整”指固定版本中选定产品的全部显式配置差异、四组装配目录的全部文件差异、当前补丁树的全部叶部件，以及对应的能力适配清单。**没有指定或取得带校验和的 dayu200 开发镜像，也没有实板运行记录，因此本报告不宣称 dayu200 的全部 API 已通过，不提供臆测的二进制镜像差异。**

## 对比版本与证据边界

采用 QEMU 当前固定的 `OpenHarmony-7.0-Release` manifest `f079c4ad9848f9cc4a9a4b3a3613ad8fbb142549`，对比同一源码树中的 dayu200 `vendor/hihope/rk3568/config.json`。没有用 master 的配置替代固定发布版本，也没有把商业 HarmonyOS 的系统应用当成 OpenHarmony 已交付能力。

| 输入 | 固定版本或实测来源 |
| --- | --- |
| dayu200 vendor | `vendor_hihope @ c168631ffe39d4c556361841d7ffe30d1f5ef207` |
| dayu200 board | `device_board_hihope @ b3ff979de8e36a9a3b4e8e4fd20bd45c78cf6df8` |
| Rockchip SoC | `device_soc_rockchip @ 0aa6ba16f89844023137fb84ac03189b30c8780b` |
| QEMU vendor 基础 | `vendor_ohemu @ b56c5a95ec590543691278b85afe9fe228744163` 加当前本地补丁 |
| QEMU device 基础 | `device_qemu @ b017aee8e2dfc97e45aeb508facc1527c3d06f4b` 加当前本地补丁 |
| 画像生成 | 当前仓库 phone 与 2in1 的 `make_effective_profile()`，只读内存生成六种选择 |
| 当前预加载校验 | ARM64 phone：97 项显式 feature 与真实 preloader 一致，0 项差异；实际源产品与内存生成选择也无差异 |
| 已有运行审计 | 2026-09 的 ARM64 phone/2in1 包，以及 2026-10-05 首个新 ARM64 phone 包；不等于六包验收 |

dayu200 的三个板级仓库相关目录在检查时没有本地修改。QEMU 部分已经打补丁，因此同时保留了共享仓库的原始 `git show HEAD:文件` 证据，防止用修复后的文件反推 dayu200 原始实现。

完整数据在 [source-comparison.json](capability-audit/dayu200/source-comparison.json)，原始共享实现见 [shared-head-evidence.json](capability-audit/dayu200/shared-head-evidence.json)，预装策略语义差异见 [preinstall-semantic-diff.json](capability-audit/dayu200/preinstall-semantic-diff.json)。官方固定版本的 [rk3568 产品配置](https://github.com/openharmony/vendor_hihope/blob/c168631ffe39d4c556361841d7ffe30d1f5ef207/rk3568/config.json) 和 [内核构建脚本](https://github.com/openharmony/device_board_hihope/blob/b3ff979de8e36a9a3b4e8e4fd20bd45c78cf6df8/rk3568/kernel/build_kernel.sh) 可以直接复核。

## 产品与打包的基础差异

| 项目 | dayu200 开发产品 | QEMU 当前选择 | 含义 |
| --- | --- | --- | --- |
| 芯片与用户态 | Cortex-A55；产品 `target_cpu=arm`，内核按 ARM64 构建 | ARMv7a、ARM64、x86_64，各自的用户态和内核 | 64 位芯片不代表 dayu 默认是 ARM64 用户态；不能直接复用其 ELF、指针宽度和 ioctl 假设 |
| 产品继承 | `rich.json + chipset_common.json` | rich + 兼容 phone/2in1 + board + 后置契约覆盖 | 三者是不同设备契约；dayu rich 不能作为完整 phone/2in1 的合格证明 |
| 产品 API 字段 | JSON 中仍有历史 `api_version=8` | 同样保留历史字段；实测系统 API 26 | 这个字段不能用来判断最终系统/SDK API 版本 |
| 直接配置部件 | 385 | phone 385；2in1 382 | 这里统计继承后的产品选择，未计 GN 传递依赖；不是全部最终二进制数量 |
| dayu 独有选择 | SmartPerf host、LPPlayer interface、VPE、Rockchip board、Noto CJK、NotoFonts、tex-hyphen | 都未在 QEMU 产品选择中出现 | 字体和 LPPlayer 等还需查传递依赖和镜像；“未直接选择”不等于全部文件缺失 |
| QEMU 额外选择 | dayu 没有显式 JSVM | JSVM、QEMU board、alsa-utils，以及重复命名空间的 wpa_supplicant；phone 另有 Camera/Photos/Notes | 需要区分新增需求、命名空间重复和实际运行依赖 |
| 内核构建 | HDF/RK 板级 patch 加 common_modules；合并 standard、board arch、base fragment | QEMU defconfig 加 qos fragment 和自己的 kernel patch | `kernel` 部件同名，生成的内核及设备树完全不同 |
| 启动和分区 | Rockchip loader/U-Boot、`boot_linux`、GPT by-name、misc/bootctrl、实体 eMMC | 直接 `-kernel/-initrd`；virtio 分盘镜像；userdata 为 F2FS | updater、恢复出厂、A/B、块设备名字与用户数据不能照搬 |
| A/B | 产品 `enable_absystem=false`，但显式 `init_feature_ab_partition=true`，另有 A/B loader 配置 | 产品同为 false，init 未显式选择该 feature | dayu 配置自身也需要区分“提供 A/B 方案”和“当前产品实际启用 A/B” |
| 调试连接 | 板上 USB/实体接口路径 | TCP HDC、QEMU 用户网络、主机端口转发 | HDC、USB gadget、设备发现和主机控制具有不同传输路径 |
| 图形与媒体 | board group 默认图形、硬件 codec、boot animation 为 true；装配 Mali/MPP/ISP | QEMU graph 默认硬件 codec 和 boot animation 为 false；Mesa/软件 ICD/软件 AVC 适配 | generic HDI/服务存在不代表 board OEM 实现已提供 |
| 系统预装目录策略 | 54 条 | 当前 phone 源树也是 54 条 | 两边数量相等，但目录、签名、特权和生命周期属性不相同 |

按 ARM64、ARMv7a、x86_64 的顺序，QEMU phone 相对 dayu 有 47、47、48 项显式赋值差异，2in1 有 50、50、51 项；x86_64 多出的赋值差异是 `runtime_core_enable_codegen=false`。产品顶层还另有 x86_64 `build_seccomp=false`，未包含在这些部件赋值计数中。没有赋值的项目必须继续解析 GN 默认值。本轮已确认 Skia、ArkUI 升级 Skia、Graphic2D 升级 Skia、ImageFramework 升级 Skia 的当前 GN 默认值都是 true，**不能把它们在 QEMU JSON 中省略解读为图形能力退化**。相反，SELinux enforce 和 ETS static backtrace 的默认值为 true，而 QEMU 显式 false，是真实的构建选择差异。

## 对现有清单的新增与细化

下面列出原 API 审计之外新增的配置检查点，或原有大类中本次才能具体定位的子链路。状态“配置差异”不自动等于行为失败；“待验证”必须保留。P0 表示影响现有首包正确性，P1 表示可优先补齐的系统功能，P2 表示需要虚拟后端，P3 表示硬件性能或扩展范围。

| 编号 | 能力差异与直接证据 | QEMU 影响和适配方案 | 验收要求 |
| --- | --- | --- | --- |
| N01 | SELinux：两边 build_selinux=true，QEMU 显式 `selinux_adapter_enforce=false`，dayu 使用 true 默认 | P1。增加独立 enforcing 验证画像，完善 virtio/HDI/AppSpawn/设备节点策略；保留开发模式的明确选择 | guest `getenforce`、实际拒绝案例、HAP/图形/音频正常路径；不能只比较是否生成 policy |
| N02 | ETS runtime：QEMU 显式关闭 static backtrace；dayu 默认 true | P1。逐 ABI 复核关闭原因和 unwinder/符号产物；能支持的架构恢复开关，失败架构准确标注 | Native/Ark 栈、真实异常和崩溃回溯；不将它混同为 ArkTS 静态语言支持 |
| N03 | dayu 选择 `smartperf_host_device=true`；QEMU 未直接选择 SmartPerf host | P1。补设备侧采集工具/服务与依赖；采集虚拟 CPU/GPU 指标时注明含义 | 包含工具、启动、权限和非空有效 trace/采集文件；perf 不因工具存在自动可用 |
| N04 | dayu 选择 Noto CJK、NotoFonts、tex-hyphen；QEMU 只有其他基础字体的旧镜像证据 | P1。先查最终依赖和文件，不以部件差异判“没有中文字体”；补语言 fallback、断词资源和字体配置 | 中日韩、阿拉伯、印地、emoji、混排、连字和自动断词截图；字体授权及资源清单一致 |
| N05 | dayu resource plugin 列表启用 `libcgroup_sched.z.so`；QEMU 列表没有该项，而旧镜像已有库 | P1。补插件开关和实际 cgroup action/mount/controller 路径；不要重复打包已有库 | HAP 前后台/worker 变化时 PID/TID 实际迁组、非法路径失败、退出清理；QoS set/get 通过不能代替此项 |
| N06 | 合并内核输入中 dayu PSI/freezer=y；QEMU ARM64/x64=n，ARMv7a=y | P1。为 ARM64/x64补对应内核能力并配套系统配置 | `/proc/pressure`、真实资源压力、冻结/解冻和生命周期；验证 cgroup v1/v2 使用路径 |
| N07 | dayu memmgr 显式 hyperhold=true、内核 HYPERHOLD=y；QEMU feature 默认 false，三架构内核 n | P2。先维持可工作的 zram/内存回收；如需 Hyperhold，补完整 kernel/userspace/backing-store，不只写 true | 内存压力、回收/写回/恢复、OOM与数据完整性；与物理板性能结果分开 |
| N08 | dayu `hiview_feature_bbox_userspace=true`；QEMU 未显式选择；ARM64 PSTORE_RAM=n，其他架构虽 y仍无持久区证明 | P1。接入 userspace BlackBox 与虚拟 ramoops/持久日志存储，补 reserved memory 或等价后端 | 服务/内核故障后日志保留和下次启动读取；编译 pstore=y不足以证明持久化 |
| N09 | dayu 脚本合入 tzdriver/XPM/CED/hideaddr/ucollection/code-sign 等 common module；QEMU 集成序列不同 | P1。逐模块审查补丁、Kconfig、实际产物和对应服务。当前 QEMU ARM64/x64 XPM=y，不能泛称缺 XPM | 真实 hook/ioctl/trace/错误边界；CFI、内存初始化等按工具链与架构可行性单独验证 |
| N10 | dayu 的 RTG/WALT 调度输入与 QEMU 不同；QEMU 残留对 `/dev/sched_rtg_ctrl` 的 init 操作 | P2。为资源调度选择已支持的虚拟实现，或补 RTG/common modules 的实际控制路径 | 线程分组和调度状态变化；接口成功不代表获得物理芯片的时延/功耗 |
| N11 | dayu 网络 fragment 有 xt BPF/quota2 等；QEMU 与之不同，root BPF 回归仅证明 map/socket-filter | P1。依据 NetManager/NetFirewall/统计实际代码选 BPF/netfilter hook 与权限；避免全量复制板内核 | 普通 HAP →服务→真实流量计数、限额/拒绝/恢复/IPv4/IPv6；root syscall不能替代 |
| N12 | ARM64 QEMU `DMABUF_SYSFS_STATS=n`，dayu=y；已补的是另一项 DMABUF process info | P1。按内存统计服务实际需求补 sysfs统计，区分两种功能 | 实际 buffer 导出/释放前后统计、权限和无悬挂记录；不能用头文件修复当作所有统计通过 |
| N13 | dayu UHDF 注册 `usb_device_interface_service` 和 `usb_port_interface_service`；QEMU 删除这两项 | P2。USB device/port 需 HDI与UDC/端口后端同时适配；host 枚举是独立链路 | device配置、role/插拔回调、授权拒绝与恢复；只有 root hub不算 host外设可用 |
| N14 | dayu 注册 `usb_serial_ddk_service`；QEMU 未注册，旧镜像却已包含该 driver/proxy库 | P1。补 HCS service，并提供虚拟 USB CDC ACM/实际 passthrough 或受控适配器 | DDK授权、发现/open、双向真实字节、断连和重连；不同于 `@ohos.busManager.serial` |
| N15 | dayu 注册 `scsi_peripheral_ddk_service`；QEMU 未注册，旧镜像已有 SCSI DDK 库 | P1。补服务与虚拟 USB mass-storage/SCSI设备、授权及存储发现 | Inquiry/read/write/容量/非法命令/拔出；使用可丢弃测试盘 |
| N16 | dayu 注册 Wi-Fi `chip_interface_service`；QEMU 删除且 `wifi_feature_with_hdi_chip_supported=false` | P2。在 WLAN 总体适配中补芯片级 HDI接口和能力协商，或明确选择无需该接口的受支持路径 | service发现、STA/AP/P2P组合限制、MAC/接口生命周期和失败回滚 |
| N17 | dayu P2P random MAC=true、接口名 `p2p-dev-wlan0`；QEMU random MAC=false、没有显式对应名 | P2。完成虚拟 WLAN后对齐接口命名/随机MAC策略；不要把 eth0重命名当WLAN | 连续建组/移除、MAC不泄露与正确变化、接口路由清理 |
| N18 | dayu 音频配置有 primary RK809 + HDMI；QEMU ALSA card为AudioPCI，旧/新policy的route、format、buffer、并发字段也不同 | P0/P2。先修ES1370实时播放/采集，再按虚拟设备重新生成policy；HDMI/USB/BT路由要对应实际后端 | 非零播放/录音数据，格式/采样率、focus、多流、设备切换/断连、进程重启；none后端不证明宿主扬声器/麦克风 |
| N19 | dayu HDMI检测feature=true；QEMU省略；两边部分HDI版本/DMABuffer选择不同 | P2。补确有设备的 route/detection；没有 HDMI时准确报告设备清单，不广告物理功能 | route callback与真实PCM；跨window/media buffer路径验证stride/像素/生命周期 |
| N20 | dayu 独有 `drivers_interface_lpplayer`，Rockchip codec/OMX/MPP与RGA/JPEG源目标；QEMU board硬件codec=false | P2/P3。LPPlayer、硬件JPEG/RGA、低功耗媒体分别查最终目标；公共API可选择真实软件实现 | 编码/解码/图像转换的真实输出；低功耗性能不能从软件功能等价推断 |
| N21 | dayu battery_manager显式charger=true，QEMU phone省略；实体PMIC和虚拟power patch不同 | P2。实现可注入电量/充电/温度/电源事件的虚拟HDI，区分查询和charger/UI行为 | 多次状态转换、事件顺序、边界值、持久性；不制造真实宿主电池或充电能力 |
| N22 | DPI dayu240/QEMU150；QEMU配置 waterfall和横屏压缩=true、decor=true，dayu对应false | P1。按phone/2in1分别生成矩形屏/窗口配置，核对legacy XML是否仍被SceneBoard消费 | 旋转/安全区/密度/尺寸/浮窗装饰、鼠标命中与截图；是语义差异，不自动判退化 |
| N23 | dayu硬件有多显示接口；QEMU默认单virtio-gpu，bootstrap_hotplug是其特有设置 | P2。提供明确的多显示器启动模式与display HDI，不仅增加QEMU heads | 外接/移除、不同DPI和方向、跨屏窗口、截图及全屏恢复；实板显示带宽不作等效承诺 |
| N24 | dayu板级UART/SPI/watchdog地址；QEMU保留多份板配置，ADC include被注释，实体传感/光/相机KHDF条目减少 | P2/P3。GPIO、I2C、SPI、UART、ADC、PWM、RTC、watchdog、SDIO/eMMC、MIPI逐类采用虚拟HDI、QEMU设备或可选passthrough | 逐接口真实数据/中断/超时/权限；不能因HCS文件存在声称实体寄存器可访问 |
| N25 | dayu有实体SD/SATA/PCIe，QEMU固定virtio系统盘不覆盖可移除存储 | P2。增加可丢弃热插拔测试盘及StorageManager/udev权限、分区文件系统配置 | 插拔→枚举→授权→挂载→读写→卸载，忙盘/坏盘/配额/格式失败；不对真实宿主盘进行验收 |
| N26 | QEMU updater fstab仍写Rockchip `fe310000.sdhci/mmcblk`，runtime init也残留多个物理节点和ispserver | P1。生成独立virtio by-name/fstab/misc协议和recovery启动方式；清理无后端init任务 | recovery实际启动、签名升级、失败恢复、恢复出厂、userdata保留/清除；再单独决定A/B方案 |
| N27 | dayu预装SecurityPrivacyCenter目录；QEMU清单无此目录，旧QEMU镜像却有该HAP文件 | P1。先查当前包BMS激活/入口和签名，补需要的隐私中心UI；不由payload推定可用 | 系统跳转/权限/界面与普通用户隔离；这是一条新增装配风险，尚非新包运行失败结论 |
| N28 | dayu能力白名单42项、QEMU39项，缺ArkWebCore/FilePicker/LocationDialog/TelephonyResources条目并新增SceneBoard | P1。逐HAP依当前真实签名和privilege需求精确补规则；不能盲拷签名指纹 | 验签→首装→BMS注册→UI/Extension启动，拒绝伪证书和非特权调用 |
| N29 | FormRender singleton false→true；SettingsData增加keepAlive；Launcher移除first-locked运行特权；若干hide属性不同 | P1。确认phone/2in1所需首锁屏与多用户策略，补确有需求的属性 | 双用户DataShare、form渲染隔离、首锁屏启动、杀进程恢复；不同策略不等于bug |
| N30 | MediaLibrary在dayu有READ_IMAGEVIDEO预授权、QEMU没有；BackgroundTask/Spooler/DLP签名规则也不同 | P1。核对实际签名和服务角色，最小化补授权；保留普通HAP用户授权流程 | 读图像/视频授权与拒绝、后台资源申请、打印/DLP生命周期；不通过扩大所有应用权限解决 |
| N31 | dayu芯片包含GPU/NPU，QEMU无RockchipNPU设备；选择MindSpore等公共部件不能等同硬件backend | P3。优先CPU推理或真实受支持软件NNRT driver；如需NPU契约再单独接入代理/虚拟后端 | 设备枚举与实际模型输入输出、算子/精度/拒绝边界；硬件规格并不证明dayu该开发镜像已有NPU HDI |
| N32 | dayu默认boot animation，QEMU默认关闭；QEMU还新增TCP开发模式、测试CLI和自动解锁等策略 | 产品选择。按需求维护可选启动动画及交互/自动化模式；不把明确的测试扩展算缺陷 | 启动完成、前台账号、显示、解锁事件身份和交互模式；自动化策略需要明确记录 |
| N33 | x86_64 QEMU显式 `runtime_core_enable_codegen=false`；dayu未赋值，static_core GN默认true | P1。该开关关闭static_core的irtoc/codegen；追踪x86目标和最终产物，按需要恢复受支持backend或明确执行限制。不能据此推断动态ArkTS/JSVM全部不可用 | 实际静态核心compiler/runtime产物与对应语言程序，编译、解释/JIT/AOT适用路径及异常；分别验证动态ETS/V8链 |
| N34 | dayu和QEMU两种ARM产品 `build_seccomp=true`，QEMU x86_64=false | P1。补x86_64 syscall号和生成policy、AppSpawn/服务沙箱集成；先解决正常调用被误拦，再恢复产品开关 | 普通HAP及相关服务的 `/proc/PID/status` Seccomp状态、允许/拒绝syscall案例、跨进程与fork/exec；不能把生成policy当沙箱已启用 |

N06、N08、N09、N11、N12 的内核数据是脚本实际选取并按顺序合并的显式输入，尚未在dayu执行Kconfig。QEMU ARM64 phone的既有新包root BPF通过只覆盖已有探针；这些补充项未做新运行验收。

板级物理接口范围参考官方 [dayu200/RK3568说明](https://github.com/openharmony/device_board_hihope/blob/OpenHarmony-7.0-Release/rk3568/README_zh.md)。硬件规格用于确定后端差异，不代表每个接口都已在所选开发产品中交付。

## 既有问题仍需保留的完整能力范围

以下按根因归并原有清单；每一项的细分API、permission、SysCap和原始状态由已有逐项台账保持，不将历史失败数字直接作为当前新包结果。完整325个SysCap分类见 [capability-coverage-ledger.json](capability-audit/capability-coverage-ledger.json)，178条原审计finding见 [known-findings.json](../ci/capability-audit/known-findings.json)，Native/ArkTS 1.1逐导出缺口见 [native-arkts11-gap-ledger.json](capability-audit/native-arkts11-gap-ledger.json)。

| 能力范围 | 当前问题或证据边界 | 适配方案与闭环验收 |
| --- | --- | --- |
| Native ABI与ArkTS动态导出 | Location错误符号、matrix4顶层导出；函数/运行值/API26契约不齐 | 从固定SDK生成逐导出校验，补实际实现和同接口行为；不能用stub补齐数量 |
| 设备SysCap/权限定义 | rich继承超出画像，官方需求/feature/registry不一致 | 精确设备契约+后置覆盖+guest双向检查；普通HAP grant/deny/revoke/重启重新核对 |
| JSVM | 是QEMU新增M144 V8组合；ARM64新包11项普通HAP测试已通过 | 三ABI引擎、C++符号/ABI、真实JS/GC/异常/异步/Native函数；不能以dayu未选择该部件推断无需兼容 |
| QoS与后台任务/进程 | 新包普通HAP六等级/线程隔离/reset子集已通过；调度时延、cgroup和后台进程契约未整体覆盖 | 保留authority；实际worker及生命周期、前后台策略和权限，另测调度状态 |
| Native Child Process | 两DSO singleton、150KiB参数Parcel边界、设备资格和ARM32清理 | 已有C API回归继续按新包/设备/ABI执行；Unicode、FD、边界、重复创建与退出 |
| AccessToken与账号身份 | 新包root bitmap/user-ID通过，普通HAP user-ID失败；SPM/parent-token不是全实现 | 内核真实协议+版本协商+AppSpawn降权前设置；HAP身份、授权/隔离/fork/拒绝 |
| ArkWeb/WebGL | 旧首包renderer恢复失败；10月7日02归档独立复验JS/DOM/Canvas/WebGL1/2/proxy/reload和renderer终止恢复通过，尚非03完整套件或浏览器可见上屏验收 | 正确EGL扩展、PID namespace退出及RS对象/身份协议；绘制像素、刷新、异常、销毁重建、renderer恢复，按每个新包重测 |
| Vulkan与可见显示 | 旧首包XComponent黑；02归档独立native队列/OHOS WSI/resize通过，可见窗口首次捕获仍是启动图而失败，之后真实系统截图/QMP及完整窗口复跑通过 | 配套SceneBoard统一渲染、CPU WSI/loader分发、RS对象/身份协议；有界等待真实compositor全像素，保留失败，03新包重测；首轮精确延迟原因未证实 |
| 普通实时音频、录音及依赖管线 | 新首包AudioRenderer Start=2，无callback；AudioSuite PCM已通过但不是设备音频 | ES1370/ALSA config/HDF/policy闭环，renderer/capturer输出、回环、焦点、录音/SoundPool/AVScreenCapture |
| AudioSuite、增强算法、Audio Vivid | 多种算法插件与Vivid builder缺失；新增CPU EQ/SoundField/EnvironmentEffect backend候选尚未新包验收，2in1 DeviceEnhance未闭环 | 逐插件真实PCM处理/合法路径/ABI；Vivid metadata构建；未提供算法不得广告全功能 |
| 视频编码、转码、录屏 | RK AVC/HEVC广告无法实例化；软件AVC候选，EOS等边界需验收 | 真实编码→解码→像素/PTS，IDR/码率/EOS/重建；HEVC单列，不借AVC成功关闭整项 |
| Camera和Camera Picker | 无可用QEMU Camera board VDI/数据源；Picker入口缺 | 标准V4L2虚拟源（如vivid）+board VDI/pipeline/HCS与权限；预览/拍照/录像及Picker回调 |
| Wi-Fi与EAP/热点/P2P | 只有eth0；WLAN硬件/UI链缺；2in1 EAP声明不齐 | mac80211_hwsim等受控后端+HDI/服务/UI；扫描、连接/AP/P2P、EAP、错误/断连恢复；不能做false-success |
| Bluetooth | enable假成功、无controller/vendor | 可控HCI/vendor后端；发现、配对、GATT、断连重连，A2DP另需音频链 |
| 定位/围栏/隐私UI | GNSS/network provider无有效数据，dialog/详情目标不齐 | 注入坐标provider、mock标记、频率/撤销/围栏；隐私dialog和设置按实际目标验证 |
| 通信/SIM/RIL/短信/蜂窝数据 | QEMU无modem/SIM；号码识别/SpamShield/HSDR/APN Provider缺 | 虚拟RIL/SIM状态机和可控数据；电话UI/短信/蜂窝路由单列；dayu原板也不因有RIL部件证明有modem |
| Sensor、Vibrator、Light/IR | Sensor旧镜像是随机模拟加速度计；Vibrator计时能力旧首包失败；IR可正确报告无emitter | 可重复注入sensor事件；time VDI严格报告可用子集；Light/IR真实虚拟backend或准确unsupported，不用固定成功值 |
| Power/Battery/Thermal | 查询子集能返回，thermal zone读失败/零数据 | 虚拟power/thermal事件；睡眠/唤醒/电池变化、温度升降和policy触发；实体DVFS/功耗独立 |
| USB host/gadget/MTP与Serial | 缺UDC与真实host外设；MediaLibrary MtpService缺；Bus Serial不同于USB Serial，新增固定SIG源导入及授权dialog候选未新包验收 | host passthrough/虚拟设备、UDC或明确无device mode；MTP provider；BusManager NAPI/SA/HDI/tty和dialog，授权/跨用户/超时/撤销及真实字节 |
| SoftBus、分布式文件/数据与硬件 | user NAT影响LAN发现，源sink版本/系统UI也有问题 | 显式bridge/socket网络模式、双guest+同版本或兼容对端；发现/认证/数据/迁移/故障恢复 |
| 系统分享、隐式Want与文本菜单 | Share Picker/sendData/search/appdetail handler缺；expanded-menu/share/translate/analyzer插件缺 | 源Provider/插件+精确skill/action/entity/URI/UTD；真正完成UI选择和回调，不以Promise先成功判通过 |
| Photos/Contacts/Calendar | Picker等API26入口缺；2in1签名/预装；Calendar whole/editor/reminder链 | 同固定源码构建HAP、精确签名白名单；普通用户CRUD/选取、whole/lower隔离和提醒/重启 |
| Media Controller/AVSession/投屏 | `com.hmos`与`com.ohos`、CastPicker/歌词/输入Cast入口不齐 | 统一bundle/入口与签名装配；投屏设备、歌词UI、privacy和输入分发实际运行 |
| Settings/Permission/通知/录屏授权 | Huawei hardcoded bundle不匹配；OpenSetting、NotificationAccess、SceneBoard/SystemUI精确目标缺 | 配置实际bundle/Ability/Extension；独立单项权限手动设置和真实用户决定；不增加phone画像外PC权限 |
| Accessibility与字幕 | core输入E2E可用，ScreenReader/Caption/Settings Provider缺 | 最小系统Provider、事件/手势/朗读/字幕开关；通用CLI只是测试辅助 |
| Print/DLP/Selection | HAP未激活、证书不符、额外provider/ANI extension缺 | 源HAP和精确签名；虚拟打印job/PDF、DLP凭据/文件隔离、Selection panel真实入口 |
| CloudSync | phone源码硬连缺失示例provider；2in1画像外收紧 | phone接真实受控Cloud provider和账号/同步/冲突/离线/恢复；2in1保持准确契约 |
| AppDomainVerify | 缺可选extension但已有HTTP验证fallback；Want转换返回空 | 本地HTTP/HTTPS验签/刷新/路由E2E；不能用可选库缺失直接判全部失败 |
| 企业provisioning/Wallpaper/安全服务 | EDM/wallpaper provider缺；SecurityGuard模型/证书流程部分问题；TEE/biometric无完整后端 | 最小provider与可控policy/model；软件HUKS可用子集与硬件安全级别分开，真正enrollment/认证另测 |
| Storage/Backup/ModuleUpdate/UsageStatistics/HUKS/I18n | init/program/用户/能力名/数据路径不一致；I18n新包错误码是字符串 | 正确target、init、权限和数据资源；quota/备份还原/更新/升级兼容与I18n数值BusinessError边界 |
| ArkUI/Graphic3D/MSDP/Fusion/短键 | 各自还有provider、模型、client/账号、空启动目标与运行链问题 | 分别补实际数据/模型/目标应用和生命周期；不能从基础ArkUI页面成功推导全部子系统 |

上述清单包含关联传递失败：例如AudioRenderer失败会影响录音/媒体录制，VideoEncoder失败会影响转码/录屏，系统HAP入口缺失会影响对应公开API。它们应按根因修复、按每条公开能力链验收，避免重复累计为互不相关的故障。

## 为什么同名部件在 QEMU 上仍需要补丁

“同名部件”只表示顶层选中同一个 source component。实际调用链如下：

```text
SDK声明与设备契约
  → 产品feature/SysCap + GN默认值 + 继承覆盖
  → 编译目标/传递依赖/ABI/软件或硬件分支
  → 镜像安装路径/资产/证书/权限/预装注册
  → init/SA/HDF service/VDI与配置
  → 内核patch/Kconfig/ioctl/挂载/设备树
  → 虚拟或物理设备 + 网络/显示/账号运行状态
  → API的真实数据、UI与生命周期
```

链上任何一层不同，就可能需要不同适配。当前可以归为八种原因。

| 原因 | dayu 路径与 QEMU 路径 | 补丁的正确归属 |
| --- | --- | --- |
| 板级后端不同 | dayu有自己的Mali、MPP、ISP、RK809、蓝牙firmware/实体设备；QEMU是virtio、Mesa、ES1370及软件codec | QEMU device/vendor/HDI/VDI适配；公共框架只修真正通用接口问题 |
| 内核构建集成不同 | dayu构建已应用RK/HDF patch与多种common module；QEMU原构建没有相同覆盖 | 独立QEMU kernel integration与真实最终产物检查，不能仅复制feature列表 |
| feature与产品目标不同 | dayu rich关闭sysvpn/firewall；QEMU补phone/2in1、JSVM、SceneBoard、AudioSuite等契约 | 画像/feature、运行资产和后置覆盖；新增需求不等于dayu回归 |
| 目标架构不同 | dayu默认ARM32用户态/ARM64内核；QEMU需三种ABI以及x86平台 | portable UAPI/syscall、compat ioctl、指针与32位生成目标修复 |
| 运行资产不同 | HAP已存在仍可能旧版本、错误Ability、证书或install-list不符；M144 V8也有独立ABI | 固定资产provenance、源HAP构建、签名和provider契约 |
| 分支维护滞后 | pinned QEMU ALSA vendor路径未被新版drivers消费、callback ABI仍旧 | 修QEMU未维护分支；实体dayu没走它，不会触发同一错误 |
| 共享上游缺陷或SDK/BOM不齐 | Location符号、matrix4导出、I18n错误码等在固定原始HEAD就有缺陷 | upstream修复/回移；同源码同调用dayu也受影响或仍需同探针复核 |
| 构建宿主与验证范围不同 | 官方Linux获取完整资产；我们还有GitHub替代LFS、macOS大小写/VirtioFS、完整SDK/跨ABI构建 | 构建工具或条件兼容；不要修改运行语义来解决宿主问题 |

### dayu200 本身并不是无补丁构建

固定板级脚本显式调用 `patch_hdf.sh`、`patch -p1 < rk3568_patch/kernel.patch`，并在对应脚本存在时调用 newip、tzdriver、XPM、container escape detection、qos_auth、hideaddr、ucollection、code_sign、DEC。它还合并自己的Kconfig fragment并选择Mali GPU构建环境。**“没有应用本仓库的patches目录”与“最终运行系统未经过patch”是两件事。** [固定板级内核构建脚本](https://github.com/openharmony/device_board_hihope/blob/b3ff979de8e36a9a3b4e8e4fd20bd45c78cf6df8/rk3568/kernel/build_kernel.sh) 明确提供这些步骤；条件调用仍需最终内核确认。

QEMU当前脚本具有另一套 hdf/virt/qos/virtio_gpu/es1370/power 等patch序列，因而两个产品的“kernel组件”不能当成相同二进制。

### 已确认的具体因果链

| 同名部件或需求 | 原始实现和dayu情况 | QEMU为何需要补丁 | 结论 |
| --- | --- | --- | --- |
| Audio drivers | dayu `drivers_peripheral_audio_feature_alsa_lib=false`，走RK板音频；QEMU=true且指定vendor路径 | pinned drivers没有消费该路径；QEMU vendor仍用旧7.0 callback参数、缺scene hooks；x64内置ALSA分支另有缺陷 | 同一部件编译不同分支，属于QEMU分支接口维护问题 |
| ALSA全局配置 | dayu已经打开config feature；原始ALSA conf GN未写chipset install_images | QEMU命名 `hw:0` 需要完整79个配置文件且实际读vendor路径；仅config=true不闭环 | 位置装配问题是共享风险；dayu走RK主音频并不能证明同ALSA分支可用 |
| Graphic2D/EGL | dayu通常走Mali；QEMU走Mesa kms_swrast/softpipe | EGL wrapper曾宣告backend不支持的robustness扩展，ArkWeb按广告创建context后失败 | 修通用扩展契约；Mali若支持该扩展可不触发，不能直接把Mali库搬到QEMU |
| AVCodec | dayuboard graph接Rockchip OMX/MPP；QEMU硬件codec group为空、仍可能带RK能力广告 | 缺硬件设备/OEM实现；软件AVC wrapper还需要真正动态backend | 实例枚举和能力广告需一致；QEMU补软件backend，不表示dayu公共软件分支自动完整 |
| QoS | dayu构建已经调用qos_auth common module | QEMU未完整接模块/fragment/authority，并有arm32/x86 ioctl宽度问题 | 补QEMU构建与compat；新包普通HAP测试已支持有限结论 |
| Vibrator | dayu有HDF物理vibrator/DRV2605L等配置；QEMU无该I2C外设 | HDI service优先加载product VDI；需要可观察时间状态和正确VDI导出 | QEMU虚拟硬件适配；frequency/intensity/HD haptics仍明确unsupported |
| Camera | dayuboard module_list明确包含camera_board_vdi_impl，并装配ISP | QEMU保留generic Camera Host/HCS，但board group没有等价可工作设备链 | 不是补camera SysCap能解决；需数据源+VDI/pipeline，专用hmos-emulator ioctl不能直接当标准V4L2 |
| Wi-Fi/BT | dayuboard部署AP6xxx firmware、BT vendor/BCM firmware和实体接口 | QEMU只挂virtio网络，没有对应SDIO/UART无线controller | 需要虚拟协议/HDI/backend或受控passthrough，不是复制firmware |
| SceneBoard | dayu rich与QEMU full phone/2in1的窗口产品、HAP和模式不同 | QEMU新增SceneBoard并依赖账号/解锁事件、BMS whitelist、统一渲染；旧首包黑屏。02新归档的实际桌面解锁和Vulkan完整窗口复跑通过，另修复RS服务回复、可信异步身份和对象编码；完整03门槛仍待验收 | 产品迁移需要完整装配与真实新包验证；不把uni-render参数或独立子集通过当作六包能力完整通过 |
| JSVM | dayu配置未显式选择JSVM，也未定义我们要求的M144 V8组合 | QEMU新增JSVM，需V8 API、std::__h ABI/version、pointer compression与32位JIT适配 | 比较新增需求的同一引擎版本，不能用dayu别的JS引擎运行成功替代 |
| Location Native | 原始固定HEAD导出 `OH_Location_IsFromMock`，SDK要求 `OH_LocationInfo_IsFromMock` | 必须修正确符号才能满足API26 C ABI | 同固定源码的公共缺陷，与模拟器无关；dayu同符号调用也不匹配 |
| matrix4 | 原始HEAD对Matrix对象加公共方法，却没加到顶层InitMatrix4Module | QEMU逐导出审计发现SDK保留的顶层函数缺失 | 公共导出缺陷；dayu只调用对象方法不会暴露问题 |
| I18n错误码 | 原始公共NAPI用string构造errCode；没有QEMU条件 | 新包普通HAP检测到字符串202/401和错误类型静默返回 | 与板无关的API契约问题；正常查询成功不能覆盖异常分支 |
| Ethernet enable/disable | 原始公共GN错误绑到firewall，dayu该feature默认false | QEMU补与实际ethernet feature关联 | 固定dayu同组合也缺这三个入口；不能将dayu能联网当这些API通过 |
| System VPN | dayu默认sysvpn=false；QEMU新要求开启base/ext | 一端开关导致链接/IPC不配套，地址parcel边界缺陷会在新分支暴露 | 默认关闭绕过路径不等于同能力在dayu可用；协议工具与授权UI仍需另补 |
| Native child args | 原始header singleton可能跨DSO分裂，UTF16使150KiB ASCII超过200KiB Parcel | QEMU直接C API运行边界发现；共享实现需要共同重编 | 不属于virtio硬件问题；dayu同功能/链接布局需同回归，设备资格也要一致 |
| Permission/VPN/Settings Provider | 公共源码找的bundle/Ability与OpenHarmony HAP不匹配 | QEMU普通HAP/手动设置/UIExtension实测覆盖到错误目标 | 同资产组合dayu也有风险；桌面手工打开Settings不能替代公开跳转API |
| CalendarData | fixed源码已有whole/reminder，旧预编译HAP没有；当前源构建候选不在实测首包 | QEMU通过源码构建替换陈旧payload并配套精确签名 | 是资产版本/装配问题；同旧HAP的dayu也要检查，Editor仍未实现 |
| AudioSuite plugin loader | dayu默认ARM32产品且Suite feature=true；原实现曾写死lib64 | QEMU增加按ABI选目录与canonical只读路径校验 | 同ARM32库布局的dayu也需要核查；CPU PCM通过不能证明算法插件齐全 |
| Renderer终止 | 原始nwebspawn renderer成为PID namespace init，默认SIGTERM会被特殊处理 | QEMU新增恢复测试发现默认终止无效，补显式退出handler | 是相同Linux进程语义路径的共享问题，不能归因QEMU信号实现；规则见 [pid_namespaces(7)](https://man7.org/linux/man-pages/man7/pid_namespaces.7.html) |
| AccessToken内核协议 | dayu生成内核受到板patch/common modules影响；普通HEAD不是最终内核证明 | QEMU曾仅改头文件而没实现switch handler，SPM失败仍走错误路径；普通HAP setter又是弱符号空实现 | 内核/用户态/身份必须共同验证；不知道dayu最终ioctl时保留待测，不能称dayu必然完整 |
| 内核重编证据 | dayu与QEMU都可能只把目录列作action输入 | QEMU长构建复用旧Image暴露nested patch不触发问题 | 构建依赖缺陷；需内容指纹和真实Image证明，不是API修复本身 |
| updater分区配置 | 两边 `config/fstab.updater` 完全相同，指向Rockchip SDHCI/mmcblk/by-name路径 | QEMU实际使用virtio盘；相同文件在这里指向不存在的设备，编译成功不能使升级可用 | 同配置依赖不同环境；需要QEMU分区和recovery协议适配，不是公共updater算法缺陷 |
| Bus Serial | 实板UART驱动不等于SDK的BusManager Serial服务链；新增2in1候选从固定SIG提交 `c05fbbf156230982aa576373da6ee04378b09ca0` 导入源码 | 补动态NAPI/SA/HDI及授权流程；公共dialog还存在先关闭再异步授权的竞态，服务需要token、账号、请求及超时边界 | 部分属于新增软件BOM和集成，部分属于共享生命周期；候选未进入新包验收，不能称dayu对应公开API已经完整 |

### 构建宿主与打包脚本也属于差异来源

除了编号patch，`build_standard_qemu_in_docker.sh` 还有条件修复：大小写不敏感目录上的libselinux `VERSION`/C++ `<version>`、XMP `Endian.h`/系统`endian.h`、iptables及kernel netfilter大小写文件；VirtioFS的symlink/metadata复制；共享Arkoala生成器竞争；x86 MindSpore错误包含ARM `asm/hwcap.h`；ETS/Hvigor/SDK依赖与registry恢复。这些问题在原生Linux完整资产环境下可能不触发，与运行guest是不是dayu无关。

`package_standard_qemu.sh` 还会生成或规范化启动器、HDC/RD参数、developer policy、system根符号链接、TUN兼容节点、F2FS镜像校验及跨主机启动方式。最终镜像行为不能仅通过`patches/`编号文件推导。因此本次在 [patch-cause-inventory.json](capability-audit/dayu200/patch-cause-inventory.json) 记录了**74个叶部件、126个编号patch、3个payload/migration patch**，并单列这些脚本转换。它是当前工作树库存，不表示每一项已经进入首包。

原先 `patches/phone/apply.sh` 和 `patches/2in1/apply.sh` 的聚合入口漏掉了完整Docker runner中的Location/Ethernet/Matrix4/Provider/内核/音频等修复。现已移除该部分组件列表，两入口调用构建器唯一的 `apply_qemu_capability_patch_plan`，在已准备的Ubuntu 22.04 Docker内执行且要求源码ArkWeb HAP、V8、SwiftShader和AVC四类依赖。补丁执行不包含源码同步、hb/GN、打包或运行验收；入口一致性回归也不是完整系统能力通过。

## 适配顺序与实施边界

先把现有首包真实失败清零，再扩大接口覆盖。P0首包范围包含普通HAP user-ID、实时音频数据、Vibrator time能力、I18n numeric BusinessError及参数边界、renderer退出恢复、Vulkan实际compositor上屏。配置差异N18/N22及相关SceneBoard、ALSA依赖应在这一阶段验证。JSVM、QoS、WebGL和AudioSuite PCM已通过的子集保留，但必须在重包后回归。

P1优先修纯软件与装配问题：后置画像和入口一致性、Provider签名/预装/目标、Calendar/Share/Settings/通知入口，SmartPerf、字体、cgroup插件、PSI/freezer、BlackBox/pstore、USB serial/SCSI DDK注册、updater块设备配置。每个改动必须对应实际消费配置的服务与运行用例，不能只追求与dayu JSON相同。

P2逐个建设虚拟硬件与双机环境：Camera、WLAN/BT、Location/RIL、音频多route、Sensor/Power/Thermal、USB host/device、Bus Serial、多显示器、外部存储、SoftBus。优先采用既有Linux/QEMU标准设备和可控数据源，再补HDI/VDI；随机模拟或固定success需要改成可重复、有明确能力边界和失败语义的实现。

P3单独处理物理性能与扩展：Mali/RGA/MPP/ISP/NPU、低功耗播放、实体DVFS/PMIC、板级总线。QEMU软件实现可满足功能接口，但不能承诺物理硬件的吞吐、功耗、传感精度或安全等级。硬件规格只用于确定差异范围；相关源码部件或最终镜像是否真正支持仍需证据。

补丁整理应按因果归属推进：QEMU专属内容放device/vendor；公共错误导出、BusinessError、ABI和权限协议推动上游或维护精确回移；资产与签名由构建/打包契约管理；宿主兼容按条件应用；纯验证步骤保留在CI。不要为减少patch数而关闭官方契约内能力，也不要为对齐dayu把ARM二进制或实体寄存器配置拷到QEMU。

## 运行验证与待补证据

2026-10-06 续修：最新已启动的代表产物是 R6 ARM64 phone，归档路径
`/Volumes/PSSD/qemu/packages/first-capability-repair-20261005-r6/openharmony-qemu-arm64-arm64_virt-phone.tar.gz`，
SHA-256 `502b08384576945bab9183281f8c4fe1475d836316354f3b15819962ece6a155`。
**首包门槛仍为 false，其余五包未启动。** 下方最早首包记录保留为历史证据。

Issue [#19](https://github.com/harmony-contrib/ohos-qemu/issues/19) 与
[#20](https://github.com/harmony-contrib/ohos-qemu/issues/20) 是两条独立链路。
x64 的完整 ArkWebCore 不能用 ARM64 HAP 或 JSVM 的 V8 DSO 替代；新打包检查
验证所有核心 ELF 的真实架构、资源与 bundle 元数据。完整 M144 的 GN 生成通过，
但源码内核/HAP/页面运行验收仍未完成。

UDMF 关联退出崩溃已在 R6 ARM64 的空 main + AVPlayer/UDMF 链接顺序实际复现
3/3。Native debugger 确认 libsurface 与 shared fence 两个退出回调释放同一个
INVALID_FENCE global；真实 GN link inputs 证明 FrameReport 的 static fence
传递依赖将第二份实现嵌入 libsurface。候选只将这个依赖改为既有 shared provider，
并强制打包 ELF 单一 owner/依赖检查；不修改 UDMF/Pasteboard API 或丢弃退出清理。
这不是“缺少 UDMF 部件”，也不能将 ARM64 的诊断推广为三个架构已修复。

两处获批准的最小修复保持现有客户端 IPC/权限边界：RenderService 回写成功 bool
和实际注册 token，nwebspawn UID 3081 只可设置当前任务账号 ID。新 kernel driver
三 ABI 真实对象编译通过；RenderService ARM64 两对象及 Surface/fence 的正常
ARM64 Ninja link/重复 link 通过。隔离候选库在旧 Pixelmap 的加载阶段失败，说明
不能只替换两个 DSO：完整重链接必须让 Pixelmap 保留直接 shared fence 依赖，
新镜像检查已覆盖该导入闭环。该诊断不是新包通过记录。
**上述编译/静态检查不解除新归档启动验证门槛。** 命令、输入、实际失败
和候选证据在 `/Volumes/PSSD/qemu/validation/first-20261005/issue-20-20261006/`。

早期代表产物系统 R8 在本地 Docker 构建时发现 CalendarData 旧式资源链拒绝
Stage `distro`。原部件 BUILD 已修正为由 Hvigor 统一编译 Stage/HAR/资源，后续
系统 R9 已实际完成编译打包，但仍是旧 ArkWeb/JSVM/SwiftShader/AVC 依赖的诊断包。
默认空闲后的实际 s2idle 暴露缺少 wakelocks/电源键唤醒及 virtio GPU resume
重置队列问题。三个独立候选部件的实际三 ABI 配置/对象验证和完整 ARM64
候选内核链接通过；旧 R9 私有候选内核第19轮的 sysfs 边界、两次默认休眠唤醒及
真实 compositor 恢复均通过。它们不能替代统一依赖的新归档启动验收。
Camera 三 ABI 真实 CPP 编译和真实
libjpeg sanitizer 回归通过，不替代 guest 拍照验收。完整 M144 native 构建已通过
两个先前失败对象（既有 WindowAdapter 方法、Blankless 生成头依赖），仍未完成
完整内核/HAP/页面闭环。WebRTC 新独立部件三个 ABI 编译通过，真实源码 host 和
ARM64 root 各 2176 项线程身份检查通过，不代表 WebRTC session 可用。私有图形
及 HiTrace 接口的公共契约/虚函数布局差异已获用户允许并修复：三 ABI 九个真实
CPP 对象和真实源码/SDK 声明的 ASAN/UBSAN 主机边界测试通过，覆盖 100 次销毁、
失败回退和 in-flight callback 保活；不是完整内核/实际页面验证。
完整 M144 native 的工具源码、LFS、GCS/sysroots 和配套 release 源码已固定。
后续 R7 实际链接又发现 SDK15 ARM64 静态 runtime 缺少 BTI；从同一固定 LLVM
commit 重建全部原有对象并保持 ABI，真实严格 BTI libffmpeg 链接通过。当前
M144 native R8 编译仍在运行，未产出统一依赖的新包/HAP，不关闭任何页面能力缺口。
只读 include 扫描单独解析真实生成头，并区分未启用 nweb_ex 与公开核心引用。
最近一轮完整主机回归 537 项通过（该轮之后的新增修改另需回归），
不代表全部 API 可用，不启动其余五包。
冻结输入和下一验收边界见 [首包修复记录](OHOS_7_PROFILE_CONTRACT_REPAIR.md)。

已有首个新包：`/Volumes/PSSD/qemu/packages/first-capability-repair-20261005/openharmony-qemu-arm64-arm64_virt-phone.tar.gz`，SHA-256 `c060979b682568ed747662b9cee7276befa6a06b9cf13b6b4905e8e7f5b2ef22`。环境为macOS ARM64/HVF、QEMU11.0.3、独立HDC18710/目标5681，guest OpenHarmony7.0.0.39/API26/phone/aarch64/Linux6.6.101、前台账号100。

该包首包门槛为false；最新记录是同一ARM64 phone继续重打。本文只做只读审计和文档，不启动或改变现有构建/guest，不启动其余五包。实际包、命令、环境和结果保留在 `/Volumes/PSSD/qemu/validation/first-20261005/first-package-evidence.json` 及 [既有首包记录](OHOS_7_PROFILE_CONTRACT_REPAIR.md)。若构建记录后来变化，应以相应新包SHA和新运行证据重新判定。

按 [AGENTS.md](../AGENTS.md) 执行多包改动时，先构建并打包一个代表产物，启动这个新包完成目标行为、边界和回归；失败就继续修复并重打同一包。记录package path/SHA、source/patch输入、host/guest、完整命令、普通HAP身份和结果后，才可扩到其余五包；其余架构与设备形态分别完成适用的运行验证。静态对比、编译或旧包运行都不解除此门槛。

要把“dayu相同API确实无需额外修复”作为运行结论，还缺一份精确dayu开发镜像的path/SHA、manifest/版本/ABI/build variant/SDK信息，以及**同签名、同权限、同账号、同数据和边界的探针**。应取出最终syscap、permission、SA、HAP manifest/证书/install-list、HCS、ELF符号、kernel.config、init/mount及运行日志，再对照本报告逐项测试。没有这些证据，目前可完整解释配置和代码上的原因，但不能科学地确认所有dayu运行优势。

本轮只读复算命令如下，检查容器的OHOS source/out都是只读挂载：

```sh
docker exec -e PYTHONDONTWRITEBYTECODE=1 ohos-qemu-capability-inspect \
  python3 /work/ci/capability-audit/compare_dayu200_config.py \
  --source-root /Volumes/PSSD/qemu/openharmony --qemu-repo /work \
  > docs/capability-audit/dayu200/source-comparison.json
```

脚本只在内存生成六个画像，不调用apply main、hb、GN、编译、打包或guest命令。输出的null表示未显式赋值；内核比较记录按构建脚本合并的input，未执行dayu Kconfig。源目录和文件SHA、生成脚本SHA均写入JSON。

补丁库存由 [inventory_dayu200_patches.py](../ci/capability-audit/inventory_dayu200_patches.py) 结合台账中已审阅的原因注释生成；新出现或删除的叶部件会使复算失败，必须先补充归因。台账同时记录patch以外的脚本/资产SHA及采集时间。执行时将stdout写到**其他文件**，避免截断作为输入的注释台账：

```sh
python3 ci/capability-audit/inventory_dayu200_patches.py \
  --annotations docs/capability-audit/dayu200/patch-cause-inventory.json \
  > /tmp/dayu200-patch-inventory-review.json
```

本轮的源配置复算、完整库存核对和审计文件SHA汇总见 [audit-evidence.json](capability-audit/dayu200/audit-evidence.json)。它只证明静态审计的范围和一致性，不解除首包运行验证门槛。

## 完整显式赋值差异

以下列出ARM64 phone全部47项、2in1的全部附加/替代项，以及x86_64独有项。ARMv7a与ARM64的部件赋值差异列表相同。`未赋值`表示本次产品继承后没有显式赋值，必须解析GN默认值；既不等于false，也不等于能力缺失。逐项来源路径见机器台账。

### 产品顶层字段

| 字段 | dayu200 | QEMU ARM64 | QEMU ARMv7a | QEMU x86_64 |
| --- | --- | --- | --- | --- |
| `api_version` | `8` | `8` | `8` | `8` |
| `board` | `rk3568` | `arm64_virt` | `armv7a_virt` | `x86_64_virt` |
| `build_seccomp` | `true` | `true` | `true` | `false` |
| `build_selinux` | `true` | `true` | `true` | `true` |
| `device_build_path` | `device/board/hihope/rk3568` | `device/qemu/arm_virt/linux_full` | `device/qemu/arm_virt/linux_full_armv7a` | `device/qemu/x86_64_virt/linux_full` |
| `device_company` | `rockchip` | `qemu` | `qemu` | `qemu` |
| `enable_absystem` | `false` | `false` | `false` | `false` |
| `enable_ramdisk` | `true` | `true` | `true` | `true` |
| `ext_sanitizer_check_list_path` | 未赋值 | `vendor/ohemu/virt/security_config/sanitizer_check_list.gni` | `vendor/ohemu/virt/security_config/sanitizer_check_list.gni` | `vendor/ohemu/virt/security_config/sanitizer_check_list.gni` |
| `product_name` | `rk3568` | `arm64_virt` | `armv7a_virt` | `x86_64_virt` |
| `target_cpu` | `arm` | `arm64` | `arm` | `x86_64` |
| `target_os` | 未赋值 | 未赋值 | `ohos` | 未赋值 |
| `type` | `standard` | `standard` | `standard` | `standard` |
| `version` | `3.0` | `3.0` | `3.0` | `3.0` |

这里phone与2in1的顶层字段相同。`ext_sanitizer_check_list_path` 是QEMU另外选用的检查清单路径，其内容和编译模式仍需配套判断，不能仅由该字段判定sanitizer已启用。

### 直接选择部件的完整增减

| 方向 | 部件 | phone | 2in1 |
| --- | --- | --- | --- |
| 仅dayu选择 | `developtools:smartperf_host` | 有 | 有 |
| 仅dayu选择 | `hdf:drivers_interface_lpplayer` | 有 | 有 |
| 仅dayu选择 | `multimedia:video_processing_engine` | 有 | 有 |
| 仅dayu选择 | `rockchip_products:rockchip_products` | 有 | 有 |
| 仅dayu选择 | `thirdparty:noto-cjk` | 有 | 有 |
| 仅dayu选择 | `thirdparty:notofonts` | 有 | 有 |
| 仅dayu选择 | `thirdparty:tex-hyphen` | 有 | 有 |
| 仅QEMU选择 | `applications:camera` | 有 | 无 |
| 仅QEMU选择 | `applications:notes` | 有 | 无 |
| 仅QEMU选择 | `applications:photos` | 有 | 无 |
| 仅QEMU选择 | `arkcompiler:jsvm` | 有 | 有 |
| 仅QEMU选择 | `device_arm64_virt:qemu_virt_full` | 有 | 有 |
| 仅QEMU选择 | `thirdparty:alsa-utils` | 有 | 有 |
| 仅QEMU选择 | `wpa_supplicant:wpa_supplicant` | 有 | 有 |

### ARM64 phone的47项部件赋值差异

| 部件 | 类型与键 | dayu200 | QEMU phone |
| --- | --- | --- | --- |
| `arkcompiler:ets_runtime` | features / `ets_runtime_feature_enable_static_backtrace` | 未赋值 | `false` |
| `arkui:ace_engine` | features / `ace_engine_feature_enable_upgrade_skia` | `true` | 未赋值 |
| `communication:netmanager_base` | features / `netmanager_base_enable_feature_net_firewall` | 未赋值 | `false` |
| `communication:netmanager_base` | features / `netmanager_base_enable_feature_sysvpn` | 未赋值 | `true` |
| `communication:netmanager_ext` | features / `netmanager_ext_feature_net_firewall` | 未赋值 | `false` |
| `communication:netmanager_ext` | features / `netmanager_ext_feature_sysvpn` | 未赋值 | `true` |
| `communication:wifi` | features / `wifi_feature_p2p_random_mac_addr` | `true` | `false` |
| `communication:wifi` | features / `wifi_feature_with_hdi_chip_supported` | 未赋值 | `false` |
| `graphic:graphic_2d` | features / `graphic_2d_feature_ace_enable_gpu` | 未赋值 | `true` |
| `graphic:graphic_2d` | features / `graphic_2d_feature_enable_opengl` | 未赋值 | `true` |
| `graphic:graphic_2d` | features / `graphic_2d_feature_enable_vulkan` | 未赋值 | `false` |
| `graphic:graphic_2d` | features / `graphic_2d_feature_parallel_render_enable` | 未赋值 | `true` |
| `graphic:graphic_2d` | features / `graphic_2d_feature_rs_enable_uni_render` | 未赋值 | `true` |
| `graphic:graphic_2d` | features / `graphic_2d_feature_upgrade_skia` | `true` | 未赋值 |
| `hdf:drivers_interface_audio` | features / `drivers_interface_audio_community` | `true` | 未赋值 |
| `hdf:drivers_peripheral_audio` | features / `drivers_peripheral_audio_feature_alsa_lib` | `false` | `true` |
| `hdf:drivers_peripheral_audio` | features / `drivers_peripheral_audio_vendor_alsa_path` | 未赋值 | `"//device/qemu/common/virt_full/audio_alsa"` |
| `hdf:drivers_peripheral_camera` | features / `drivers_peripheral_camera_v4l2_emulator` | 未赋值 | `false` |
| `hdf:drivers_peripheral_codec` | features / `drivers_peripheral_codec_feature_support_hdi_v1` | `true` | `false` |
| `hdf:drivers_peripheral_codec` | features / `drivers_peripheral_codec_feature_support_omx_extend_test` | `true` | `false` |
| `hdf:drivers_peripheral_display` | features / `drivers_peripheral_display_bootstrap_hotplug` | 未赋值 | `true` |
| `hdf:drivers_peripheral_display` | features / `drivers_peripheral_display_community` | `true` | 未赋值 |
| `hdf:drivers_peripheral_display` | features / `drivers_peripheral_display_vdi_default` | `true` | 未赋值 |
| `hdf:drivers_peripheral_wlan` | features / `drivers_peripheral_wlan_feature_vendor` | `default` | 未赋值 |
| `hdf:drivers_peripheral_wlan` | features / `drivers_peripheral_wlan_p2p_name` | `p2p-dev-wlan0` | 未赋值 |
| `hdf:hdf_core` | features / `hdf_core_default_peripheral_config` | `false` | 未赋值 |
| `hdf:hdf_core` | features / `hdf_core_platform_test_support` | `false` | `true` |
| `hiviewdfx:hiview` | features / `hiview_feature_bbox_userspace` | `true` | 未赋值 |
| `multimedia:audio_framework` | features / `audio_framework_feature_audiosuite_format_convert_support` | 未赋值 | `true` |
| `multimedia:audio_framework` | features / `audio_framework_feature_hdmi_detect_audio` | `true` | 未赋值 |
| `multimedia:audio_framework` | syscap / `SystemCapability.Multimedia.Audio.SuiteEngine` | 未赋值 | `true` |
| `multimedia:av_codec` | features / `av_codec_fcodec_enable_dmabuffer_at_buffermode` | `false` | 未赋值 |
| `multimedia:av_session` | features / `av_session_enable_input_redistribute` | 未赋值 | `true` |
| `multimedia:image_framework` | features / `image_framework_feature_upgrade_skia` | `true` | 未赋值 |
| `multimedia:media_foundation` | syscap / `SystemCapability.Multimedia.VideoProcessingEngine` | 未赋值 | `false` |
| `powermgr:battery_manager` | features / `battery_manager_feature_enable_charger` | `true` | 未赋值 |
| `resourceschedule:memmgr` | features / `memmgr_hyperhold_memory` | `true` | 未赋值 |
| `security:selinux_adapter` | features / `selinux_adapter_enforce` | 未赋值 | `false` |
| `startup:init` | features / `init_feature_ab_partition` | `true` | 未赋值 |
| `telephony:core_service` | syscap / `SystemCapability.Telephony.CoreService.Esim` | `false` | 未赋值 |
| `thirdparty:skia` | features / `skia_feature_upgrade` | `true` | 未赋值 |
| `usb:usb_manager` | features / `usb_manager_feature_device` | `true` | 未赋值 |
| `usb:usb_manager` | features / `usb_manager_feature_host` | `true` | 未赋值 |
| `usb:usb_manager` | features / `usb_manager_feature_pop_up_func_switch_model` | `false` | 未赋值 |
| `usb:usb_manager` | features / `usb_manager_feature_port` | `true` | 未赋值 |
| `window:window_manager` | features / `window_manager_use_sceneboard` | 未赋值 | `true` |
| `window:window_manager` | syscap / `SystemCapability.Window.SessionManager` | 未赋值 | `true` |

### 2in1相对phone的全部附加或替代

| 部件 | 类型与键 | dayu200 | QEMU phone | QEMU 2in1 |
| --- | --- | --- | --- | --- |
| `communication:netmanager_base` | features / `netmanager_base_enable_feature_net_firewall` | 未赋值 | `false` | `true` |
| `communication:netmanager_ext` | features / `netmanager_ext_feature_net_firewall` | 未赋值 | `false` | `true` |
| `communication:netmanager_ext` | syscap / `SystemCapability.Communication.NetManager.NetFirewall` | `false` | `false` | 未赋值 |
| `distributeddatamgr:relational_store` | syscap / `SystemCapability.DistributedDataManager.CloudSync.Client` | 未赋值 | 未赋值 | `false` |
| `distributeddatamgr:relational_store` | syscap / `SystemCapability.DistributedDataManager.CloudSync.Config` | 未赋值 | 未赋值 | `false` |
| `distributeddatamgr:relational_store` | syscap / `SystemCapability.DistributedDataManager.CloudSync.Server` | 未赋值 | 未赋值 | `false` |
| `filemanagement:dfs_service` | syscap / `SystemCapability.FileManagement.DistributedFileService.CloudSync.Core` | 未赋值 | 未赋值 | `false` |
| `filemanagement:dfs_service` | syscap / `SystemCapability.FileManagement.DistributedFileService.CloudSyncManager` | 未赋值 | 未赋值 | `false` |
| `multimedia:audio_framework` | features / `audio_framework_feature_audiosuite_format_convert_support` | 未赋值 | `true` | 未赋值 |
| `multimedia:audio_framework` | features / `audio_framework_feature_audiosuite_support` | `true` | `true` | 未赋值 |
| `multimedia:audio_framework` | syscap / `SystemCapability.Multimedia.Audio.SuiteEngine` | 未赋值 | `true` | 未赋值 |
| `multimedia:av_session` | features / `av_session_enable_input_redistribute` | 未赋值 | `true` | 未赋值 |
| `multimedia:camera_framework` | syscap / `SystemCapability.Multimedia.Camera.Core` | 未赋值 | 未赋值 | `false` |
| `powermgr:battery_manager` | features / `battery_manager_feature_enable_charger` | `true` | 未赋值 | `true` |
| `window:window_manager` | syscap / `SystemCapability.Window.SessionManager` | 未赋值 | `true` | 未赋值 |

### x86_64独有的额外部件赋值

| 部件 | 类型与键 | dayu200 | QEMU x86_64 phone/2in1 |
| --- | --- | --- | --- |
| `arkcompiler:runtime_core` | features / `runtime_core_enable_codegen` | 未赋值 | `false` |

## 配置及资产的完整扫描库存

扫描vendor产品目录及board的cfg、distributedhardware、updater四组目录：40个同名文件内容不同、31个仅dayu存在、32个仅QEMU存在、69个相同。这里覆盖所有普通文件，包含fstab、Makefile、firmware、源代码、生成画像和构建残留；不是只扫描JSON。按目录相对路径配对，路径改名不能直接判文件或功能缺失。JSON保留文字文件diff、二进制差异标记和每个文件SHA。

生成画像和 `.d` 等构建残留属于采集时源码树状态，不能作为另一种设备画像已经构建/交付的证据。两边updater fstab内容相同，却仍写实体SDHCI路径，是相同配置必须做QEMU适配的直接例子。

### vendor/hihope/rk3568 ↔ vendor/ohemu/virt

| 类型 | 完整相对路径列表 |
| --- | --- |
| 内容不同 | `default_app_config/BUILD.gn`、`etc/BUILD.gn`、`hals/audio/BUILD.gn`、`hals/audio/alsa_adapter.json`、`hals/audio/audio_adapter.json`、`hals/audio/audio_paths.json`、`hals/audio/config/arm/audio_policy_config.xml`、`hals/audio/config/arm64/audio_policy_config.xml`、`hals/audio/config/audio_policy_config_new.xml`、`hals/audio/product.gni`、`hals/codec/BUILD.gn`、`hdf_config/khdf/camera/camera_config.hcs`、`hdf_config/khdf/device_info/device_info.hcs`、`hdf_config/khdf/hdf.hcs`、`hdf_config/khdf/vibrator/vibrator_config.hcs`、`hdf_config/khdf/wifi/wlan_platform.hcs`、`hdf_config/uhdf/BUILD.gn`、`hdf_config/uhdf/camera/hdi_impl/camera_host_config.hcs`、`hdf_config/uhdf/camera/pipeline_core/config.hcs`、`hdf_config/uhdf/device_info.hcs`、`hdf_config/uhdf/usb_ecm_acm.hcs`、`image_conf/BUILD.gn`、`image_conf/system_image_conf.txt`、`image_conf/updater_ramdisk_image_conf.txt`、`preinstall-config/BUILD.gn`、`preinstall-config/install_list.json`、`preinstall-config/install_list_capability.json`、`preinstall-config/install_list_permissions.json`、`resourceschedule/BUILD.gn`、`resourceschedule/ressched/res_sched_plugin_switch.xml`、`security_config/critical_reboot_process_list.json`、`security_config/sanitizer_check_list.gni`、`window_config/BUILD.gn`、`window_config/display_manager_config.xml`、`window_config/window_manager_config.xml` |
| 仅dayu存在 | `bluetooth/BCM4362A2.hcd`、`bluetooth/BUILD.gn`、`bluetooth/include/bt_hci_bdroid.h`、`bluetooth/include/bt_vendor_brcm.h`、`bluetooth/include/bt_vendor_lib.h`、`bluetooth/include/esco_parameters.h`、`bluetooth/include/uipc_msg.h`、`bluetooth/include/upio.h`、`bluetooth/include/userial.h`、`bluetooth/include/userial_vendor.h`、`bluetooth/include/utils/Log.h`、`bluetooth/src/bt_vendor_brcm.c`、`bluetooth/src/conf.c`、`bluetooth/src/hardware.c`、`bluetooth/src/upio.c`、`bluetooth/src/userial_vendor.c`、`config.json`、`etc/param/hardware_rk3568.para`、`etc/param/product_rk3568.para`、`hdf_config/khdf/hdf_test/hdf_hcs.hcb`、`hdf_config/khdf/platform/rk3568_spi_config.hcs`、`hdf_config/khdf/platform/rk3568_uart_config.hcs`、`hdf_config/khdf/platform/rk3568_watchdog_config.hcs`、`hdf_config/khdf/sensor/gas/bme688_config.hcs`、`hdf_config/uhdf/hdf_peripheral.cfg`、`ohos.build`、`product.gni` |
| 仅QEMU存在 | `BUILD.gn`、`etc/param/hardware_virt.para`、`etc/param/product_virt.para`、`etc/qemu_sceneboard_unlock.cfg`、`hals/audio/config/riscv64/audio_policy_config.xml`、`hals/audio/config/x86_64/audio_policy_config.xml`、`hals/vibrator/BUILD.gn`、`hals/vibrator/qemu_virtual_vibrator.cpp`、`hdf_config/khdf/.hdf_hcs_hex.o.d`、`hdf_config/khdf/platform/virt_spi_config.hcs`、`hdf_config/khdf/platform/virt_uart_config.hcs`、`hdf_config/khdf/platform/virt_watchdog_config.hcs`、`image_conf/chip_prod_image_conf.txt`、`image_conf/sys_prod_image_conf.txt`、`image_conf/updater_image_conf.txt`、`image_conf/userdata_image_conf.txt`、`image_conf/vendor_image_conf.txt`、`power_config/power_mode_config.xml`、`virt_2in1_full.json`、`virt_2in1_full.meta.json`、`virt_common.json`、`virt_common_armv7a.json`、`virt_common_x86_64.json`、`virt_phone_contract_arm64_virt.json`、`virt_phone_full.json`、`virt_phone_full.meta.json` |
| 内容相同 | `default_app_config/default_app.json`、`hals/audio/alsa_paths.json`、`hals/audio/audio_effect.json`、`hdf_config/khdf/Makefile`、`hdf_config/khdf/audio/analog_headset_config.hcs`、`hdf_config/khdf/audio/audio_config.hcs`、`hdf_config/khdf/audio/codec_config.hcs`、`hdf_config/khdf/audio/dai_config.hcs`、`hdf_config/khdf/audio/dma_config.hcs`、`hdf_config/khdf/audio/dsp_config.hcs`、`hdf_config/khdf/hdf_test/Makefile`、`hdf_config/khdf/hdf_test/adc_test_config.hcs`、`hdf_config/khdf/hdf_test/emmc_test_config.hcs`、`hdf_config/khdf/hdf_test/gpio_test_config.hcs`、`hdf_config/khdf/hdf_test/hdf.hcs`、`hdf_config/khdf/hdf_test/hdf_config_test.hcs`、`hdf_config/khdf/hdf_test/hdf_test_manager/device_info.hcs`、`hdf_config/khdf/hdf_test/i2c_test_config.hcs`、`hdf_config/khdf/hdf_test/pwm_test_config.hcs`、`hdf_config/khdf/hdf_test/rtc_test_config.hcs`、`hdf_config/khdf/hdf_test/sdio_test_config.hcs`、`hdf_config/khdf/hdf_test/spi_test_config.hcs`、`hdf_config/khdf/hdf_test/uart_test_config.hcs`、`hdf_config/khdf/hdf_test/watchdog_test_config.hcs`、`hdf_config/khdf/input/input_config.hcs`、`hdf_config/khdf/lcd/lcd_config.hcs`、`hdf_config/khdf/light/light_config.hcs`、`hdf_config/khdf/platform/adc_config_linux.hcs`、`hdf_config/khdf/platform/emmc_config.hcs`、`hdf_config/khdf/platform/i2c_config.hcs`、`hdf_config/khdf/platform/pwm_config.hcs`、`hdf_config/khdf/platform/sdio_config.hcs`、`hdf_config/khdf/sensor/accel/bmi160_config.hcs`、`hdf_config/khdf/sensor/accel/mxc6655xa_config.hcs`、`hdf_config/khdf/sensor/als/bh1745_config.hcs`、`hdf_config/khdf/sensor/humidity/humidity_aht20_config.hcs`、`hdf_config/khdf/sensor/humidity/humidity_sht30_config.hcs`、`hdf_config/khdf/sensor/magnetic/magnetic_lsm303_config.hcs`、`hdf_config/khdf/sensor/proximity/proximity_apds9960_config.hcs`、`hdf_config/khdf/sensor/sensor_common.hcs`、`hdf_config/khdf/sensor/sensor_config.hcs`、`hdf_config/khdf/sensor/temperature/temperature_aht20_config.hcs`、`hdf_config/khdf/sensor/temperature/temperature_sht30_config.hcs`、`hdf_config/khdf/vibrator/drv2605l_linear_vibrator_config.hcs`、`hdf_config/khdf/vibrator/linear_vibrator_config.hcs`、`hdf_config/khdf/wifi/wlan_chip_ap6275s.hcs`、`hdf_config/khdf/wifi/wlan_chip_hi3881.hcs`、`hdf_config/uhdf/camera/pipeline_core/ipp_algo_config.hcs`、`hdf_config/uhdf/camera/pipeline_core/params.hcs`、`hdf_config/uhdf/hdf.hcs`、`hdf_config/uhdf/media_codec/codec_adapter_capabilities.hcs`、`hdf_config/uhdf/media_codec/codec_component_capabilities.hcs`、`hdf_config/uhdf/media_codec/codec_hdi1.0_capabilities.hcs`、`hdf_config/uhdf/media_codec/image_codec_capabilities.hcs`、`hdf_config/uhdf/media_codec/media_codec_capabilities.hcs`、`hdf_config/uhdf/usb_pnp_device.hcs`、`image_conf/ramdisk_image_conf.txt`、`preinstall-config/uninstall_list.json`、`resourceschedule/cgroup_sched/cgroup_action_config.json`、`resourceschedule/ressched/res_sched_config.xml`、`resourceschedule/soc_perf/socperf_boost_config.xml`、`resourceschedule/soc_perf/socperf_resource_config.xml`、`security_config/high_privilege_process_list.json`、`updater_config/build_cfg.gni` |

### device/board/hihope/rk3568/cfg ↔ device/qemu/common/virt_full/cfg

| 类型 | 完整相对路径列表 |
| --- | --- |
| 内容不同 | `BUILD.gn` |
| 仅dayu存在 | `fstab.rk3568`、`init.rk3568.cfg`、`init.rk3568.usb.cfg` |
| 仅QEMU存在 | `default.para`、`fstab.virt`、`init.virt.cfg`、`init.virt.usb.cfg`、`reverted/fstab.virt` |
| 内容相同 | 无 |

### device/board/hihope/rk3568/distributedhardware ↔ device/qemu/common/virt_full/distributedhardware

| 类型 | 完整相对路径列表 |
| --- | --- |
| 内容不同 | `BUILD.gn`、`distributed_hardware_components_cfg.json` |
| 仅dayu存在 | 无 |
| 仅QEMU存在 | 无 |
| 内容相同 | `dinput_business_event_whitelist.cfg` |

### device/board/hihope/rk3568/updater ↔ device/qemu/common/virt_full/updater

| 类型 | 完整相对路径列表 |
| --- | --- |
| 内容不同 | `BUILD.gn`、`config/init.cfg` |
| 仅dayu存在 | `config/init.rk3568.usb.cfg` |
| 仅QEMU存在 | `config/init.virt.usb.cfg` |
| 内容相同 | `config/fstab.updater`、`config/lastword.sh`、`config/signing_cert.crt`、`updater_ramdisk_resource_config.ini` |

## 当前补丁部件的完整归因库存

下面覆盖全部74个叶部件。编号patch合计126个，另有qos_auth payload及2个迁移patch；0表示该部件通过脚本或资产转换工作。每个patch的完整路径、目标源码和SHA见 [patch-cause-inventory.json](capability-audit/dayu200/patch-cause-inventory.json)。主要原因分类允许一个部件包含多种问题，不能用分类推断其每个patch都只对QEMU生效；对dayu的适用条件见台账和前面的具体因果链。

| 部件入口 | 编号patch | 主要归因 | 实际修复或装配内容 |
| --- | --- | --- | --- |
| [2in1/base/busmanager/serial_manager](../patches/2in1/base/busmanager/serial_manager/apply.sh) | 1 | 缺失源码装配与共享授权边界 | 新增Serial源码装配及动态NAPI/SA/HDI链，修dialog超时、uint32 token和请求内跨用户授权边界；候选未新包验收。 |
| [2in1/base/startup/init/serial_devices](../patches/2in1/base/startup/init/serial_devices/apply.sh) | 1 | 设备节点权限装配 | USB serial节点按真实服务用户和授权链收紧访问权限；不能用world-writable节点替代普通HAP授权。 |
| [2in1/base/usb/usb_manager/serial_dialog](../patches/2in1/base/usb/usb_manager/serial_dialog/apply.sh) | 1 | 共享Provider异步生命周期 | SerialDialog等待addPortAuthorization完成再关闭，并阻止重复授权提交；候选未新包验收。 |
| [2in1/device/qemu/serial_usb_endpoint](../patches/2in1/device/qemu/serial_usb_endpoint/apply.sh) | 1 | QEMU虚拟外设与内核装配 | 在QEMU内核接入FTDI USB serial endpoint驱动；配套QEMU设备、HDI和普通用户授权仍需新包运行验收。 |
| [2in1/product_profile](../patches/2in1/product_profile/apply.sh) | 0 | 产品配置与运行装配 | 生成2in1设备契约、官方SysCap与后置feature覆盖。 |
| [2in1/sceneboard_runtime](../patches/2in1/sceneboard_runtime/apply.sh) | 2 | 产品配置与运行装配 | 装配2in1 SceneBoard资产；修解锁事件及用户身份参数。 |
| [common/applications/standard/calendardata/source_provider](../patches/common/applications/standard/calendardata/source_provider/apply.sh) | 3 | 共享源码与资产版本 | 源Calendar已有whole/reminder入口，旧预编译HAP缺失；改为真实源构建并匹配生产构建模型。 |
| [common/applications/standard/hap/calendar_provider](../patches/common/applications/standard/hap/calendar_provider/apply.sh) | 1 | 共享源码与资产版本 | 停止打包缺少新入口的旧CalendarData预编译HAP。 |
| [common/applications/standard/permission_manager/open_setting](../patches/common/applications/standard/permission_manager/open_setting/apply.sh) | 0 | 共享Provider契约与产品身份 | 补实际PermissionManager单权限设置入口及目标装配。 |
| [common/applications/standard/settings/network_navigation](../patches/common/applications/standard/settings/network_navigation/apply.sh) | 1 | 共享Provider契约与产品身份 | 把网络设置跳转目标改为已安装的OpenHarmony Settings bundle。 |
| [common/arkcompiler/jsvm](../patches/common/arkcompiler/jsvm/apply.sh) | 11 | 引擎版本与二进制ABI | 新增JSVM并连接固定M144 V8；修复新旧V8 API、libc++命名空间、指针压缩、32位JIT和DFX链接。 |
| [common/base/global/i18n/builtin_data](../patches/common/base/global/i18n/builtin_data/apply.sh) | 1 | 共享源码与厂商定制路径 | 改用已打包OHOS数据，删除不存在的厂商mount命令。 |
| [common/base/global/i18n/business_error](../patches/common/base/global/i18n/business_error/apply.sh) | 2 | 共享上游实现缺陷 | 保持numeric BusinessError code，并拒绝系统setter错误参数类型。 |
| [common/base/global/i18n/init_ownership](../patches/common/base/global/i18n/init_ownership/apply.sh) | 1 | 共享源码与厂商定制路径 | 使I18n目录归属使用系统已注册用户。 |
| [common/base/location/location_ndk](../patches/common/base/location/location_ndk/apply.sh) | 1 | 共享上游实现缺陷 | 修API26声明与真实导出不一致的LocationInfo符号。 |
| [common/base/notification/common_event_service/cem_unlock](../patches/common/base/notification/common_event_service/cem_unlock/apply.sh) | 1 | 产品配置与运行装配 | 让测试CLI发布的解锁Want带上实际user-ID，避免账号语义丢失。 |
| [common/base/security/access_token/kernel_spm_handshake](../patches/common/base/security/access_token/kernel_spm_handshake/apply.sh) | 1 | 共享内核和用户态协议 | 只在成功读取受支持SPM版本时进入新协议，保留legacy回退。 |
| [common/base/security/huks/compatibility_bin](../patches/common/base/security/huks/compatibility_bin/apply.sh) | 1 | 共享上游实现缺陷 | 打包init配置引用但未安装的HUKS compatibility helper。 |
| [common/base/startup/appspawn/kernel_user_id](../patches/common/base/startup/appspawn/kernel_user_id/apply.sh) | 2 | 共享内核和用户态协议 | 在降权前且不依赖custom sandbox路径写入真实task user-ID。 |
| [common/base/startup/appspawn/render_pid_namespace](../patches/common/base/startup/appspawn/render_pid_namespace/apply.sh) | 1 | 共享上游实现缺陷 | 显式处理namespace init renderer的终止信号以支持恢复测试。 |
| [common/base/update/sys_installer/module_update_init](../patches/common/base/update/sys_installer/module_update_init/apply.sh) | 1 | 共享上游实现缺陷 | 打包init调用但未安装的module-update initializer。 |
| [common/build/compile_app/release_dependencies](../patches/common/build/compile_app/release_dependencies/apply.sh) | 1 | 构建宿主与依赖获取 | 生产HAP安装跳过仅开发需要的依赖，匹配release构建模型。 |
| [common/build/github_lfs_assets](../patches/common/build/github_lfs_assets/apply.sh) | 0 | 构建宿主与依赖获取 | 恢复GitHub镜像缺失的真实LFS对象，避免把pointer当资产。 |
| [common/device/qemu/armv7a_product/components/appspawn_cleanup](../patches/common/device/qemu/armv7a_product/components/appspawn_cleanup/apply.sh) | 2 | ARM32产品与ABI | 规避ARMv7 native-spawn cleanup的日志/锁引用崩溃路径。 |
| [common/device/qemu/armv7a_product/components/build_whitelist](../patches/common/device/qemu/armv7a_product/components/build_whitelist/apply.sh) | 1 | ARM32产品与ABI | 注册新增QEMU ARMv7产品的子系统选择。 |
| [common/device/qemu/armv7a_product/components/compact_child_args](../patches/common/device/qemu/armv7a_product/components/compact_child_args/apply.sh) | 1 | ARM32产品与ABI | ARMv7子进程参数使用UTF8以满足Parcel大小约束。 |
| [common/device/qemu/armv7a_product/components/device_qemu](../patches/common/device/qemu/armv7a_product/components/device_qemu/apply.sh) | 1 | ARM32产品与ABI | 新增ARMv7 QEMU device和构建入口。 |
| [common/device/qemu/armv7a_product/components/kernel](../patches/common/device/qemu/armv7a_product/components/kernel/apply.sh) | 1 | ARM32产品与ABI | 接入ARMv7 QEMU内核构建。 |
| [common/device/qemu/armv7a_product/components/libvpx](../patches/common/device/qemu/armv7a_product/components/libvpx/apply.sh) | 1 | ARM32产品与ABI | 补ARM目标RTCD生成头文件。 |
| [common/device/qemu/armv7a_product/components/mesa3d](../patches/common/device/qemu/armv7a_product/components/mesa3d/apply.sh) | 1 | ARM32产品与ABI | 接入ARMv7 Mesa源构建。 |
| [common/device/qemu/armv7a_product/components/vendor_ohemu](../patches/common/device/qemu/armv7a_product/components/vendor_ohemu/apply.sh) | 1 | ARM32产品与ABI | 新增ARMv7 QEMU vendor产品配置。 |
| [common/device/qemu/kernel_build_dependencies](../patches/common/device/qemu/kernel_build_dependencies/apply.sh) | 1 | QEMU内核构建与输入证据 | 用实际准备输入和内容证据驱动内核重编，防止嵌套patch漏触发。 |
| [common/device/qemu/kernel_capability](../patches/common/device/qemu/kernel_capability/apply.sh) | 2 | QEMU内核构建与输入证据 | 补BPF/FTrace/DMABUF和F2FS quota内核输入。 |
| [common/drivers/peripheral/audio](../patches/common/drivers/peripheral/audio/apply.sh) | 7 | QEMU音频分支与接口版本 | 补7.0未消费的vendor ALSA路径、变更的callback ABI和scene hooks；x64内置ALSA分支也有缺陷。 |
| [common/drivers/peripheral/vibrator](../patches/common/drivers/peripheral/vibrator/apply.sh) | 3 | QEMU虚拟外设 | 装配time-only虚拟振动VDI及各ABI目标依赖；不实现频率/强度。 |
| [common/foundation/ability/ability_runtime/native_child_process](../patches/common/foundation/ability/ability_runtime/native_child_process/apply.sh) | 2 | 共享上游实现缺陷 | 共享跨DSO子进程参数，并约束Parcel编码后的真实大小。 |
| [common/foundation/arkui/ace_engine/matrix4_exports](../patches/common/foundation/arkui/ace_engine/matrix4_exports/apply.sh) | 1 | 共享上游实现缺陷 | 恢复SDK声明但顶层module Init缺少的matrix4函数导出。 |
| [common/foundation/barrierfree/accessibility](../patches/common/foundation/barrierfree/accessibility/apply.sh) | 1 | QEMU测试工具扩展 | 提供通用无障碍测试CLI，按实际extension metadata检验capability mask。 |
| [common/foundation/communication/netmanager_ext/api26_features](../patches/common/foundation/communication/netmanager_ext/api26_features/apply.sh) | 2 | 功能选择与共享边界 | 配套base/ext feature并修system VPN地址parcel边界；不能只声明SysCap。 |
| [common/foundation/communication/netmanager_ext/ethernet_api26](../patches/common/foundation/communication/netmanager_ext/ethernet_api26/apply.sh) | 1 | 共享上游实现缺陷 | Ethernet enable/disable开关按ethernet feature构建，不绑定firewall。 |
| [common/foundation/communication/netmanager_ext/vpn_dialog_bundle](../patches/common/foundation/communication/netmanager_ext/vpn_dialog_bundle/apply.sh) | 1 | 共享Provider契约与产品身份 | VPN授权对话框使用实际装配的bundle。 |
| [common/foundation/filemanagement/app_file_service/backup_init](../patches/common/foundation/filemanagement/app_file_service/backup_init/apply.sh) | 1 | 共享上游实现缺陷 | 删除init配置中系统不存在的chmod capability。 |
| [common/foundation/multimedia/audio_framework/audio_suite_dsp](../patches/common/foundation/multimedia/audio_framework/audio_suite_dsp/apply.sh) | 1 | 音频算法依赖与软件后端 | 新增真实CPU EQ/SoundField/EnvironmentEffect替代backend候选；其余AI/变速等插件仍独立缺失，尚未新包运行验收。 |
| [common/foundation/multimedia/audio_framework/audio_suite_library_path](../patches/common/foundation/multimedia/audio_framework/audio_suite_library_path/apply.sh) | 2 | 音频ABI与文件布局 | 按真实ABI选lib/lib64并允许受控canonical只读目录；不提供缺失算法。 |
| [common/foundation/multimedia/av_codec/avc_eos](../patches/common/foundation/multimedia/av_codec/avc_eos/apply.sh) | 1 | 共享上游实现缺陷 | 重置EOS输出buffer状态并传递真实backend失败。 |
| [common/foundation/multimedia/av_codec/software_avc](../patches/common/foundation/multimedia/av_codec/software_avc/apply.sh) | 1 | QEMU软件媒体后端 | 补真正OpenH264 AVC运行依赖及构建目标；不冒充HEVC或硬件能力。 |
| [common/foundation/multimodalinput/input/absolute_pointer](../patches/common/foundation/multimodalinput/input/absolute_pointer/apply.sh) | 1 | QEMU虚拟外设 | 映射QEMU绝对指针坐标到实际显示尺寸。 |
| [common/foundation/resourceschedule/device_usage_statistics/init_profile](../patches/common/foundation/resourceschedule/device_usage_statistics/init_profile/apply.sh) | 1 | 共享上游实现缺陷 | 删除无效且未被使用的init service配置。 |
| [common/foundation/resourceschedule/qos_manager](../patches/common/foundation/resourceschedule/qos_manager/apply.sh) | 7 | QEMU内核集成与架构ABI | 把既有QoS模块接入QEMU内核，保留authority并修arm32/x86 compat指针。 |
| [common/kernel/linux/linux_6_6/access_token_abi](../patches/common/kernel/linux/linux_6_6/access_token_abi/apply.sh) | 1 | 共享内核和用户态协议 | 实现受锁保护的真实权限bitmap查询及真实task身份ABI；另含旧状态迁移。 |
| [common/kernel/linux/linux_6_6/dmabuf_process_info](../patches/common/kernel/linux/linux_6_6/dmabuf_process_info/apply.sh) | 1 | 共享内核源码完整性 | 补Linux6.6 DMABUF统计实现缺少的头文件字段和函数声明。 |
| [common/standard_vpn/components/code_sign](../patches/common/standard_vpn/components/code_sign/apply.sh) | 1 | 架构和系统调用ABI | 使code-sign适配QEMU目标架构和系统调用ABI。 |
| [common/standard_vpn/components/device_qemu_kernel](../patches/common/standard_vpn/components/device_qemu_kernel/apply.sh) | 2 | QEMU内核与镜像装配 | 接入VPN/verity配置，并在QoS之后装配安全模块。 |
| [common/standard_vpn/components/graphic_2d_egl](../patches/common/standard_vpn/components/graphic_2d_egl/apply.sh) | 1 | QEMU软件GPU及EGL契约 | 只有实际EGL backend支持时才宣告robust context扩展。 |
| [common/standard_vpn/components/linux_security](../patches/common/standard_vpn/components/linux_security/apply.sh) | 2 | 架构和系统调用ABI | 修32位安全模块编译及open code-sign descriptor边界。 |
| [common/standard_vpn/components/musl_uapi](../patches/common/standard_vpn/components/musl_uapi/apply.sh) | 1 | 架构和系统调用ABI | 选择真实x86 UAPI头文件，避免ARM syscall布局。 |
| [common/standard_vpn/components/qemu_mesa](../patches/common/standard_vpn/components/qemu_mesa/apply.sh) | 1 | QEMU软件GPU及EGL契约 | 替换不匹配的预编译Mesa为当前源构建。 |
| [common/standard_vpn/components/qemu_vulkan](../patches/common/standard_vpn/components/qemu_vulkan/apply.sh) | 2 | QEMU Vulkan软件后端与WSI | 装配SwiftShader ICD并关闭不兼容的OHOS Vulkan layer。 |
| [common/standard_vpn/components/validate](../patches/common/standard_vpn/components/validate/apply.sh) | 0 | 静态校验与签名装配 | 静态校验配置与构建依赖；该步骤本身不修运行能力。 |
| [common/standard_vpn/components/vendor_product](../patches/common/standard_vpn/components/vendor_product/apply.sh) | 1 | QEMU内核与镜像装配 | 配置QEMU VPN、F2FS镜像、网络与图形选择。 |
| [common/standard_vpn/components/vpn_dialog](../patches/common/standard_vpn/components/vpn_dialog/apply.sh) | 0 | 静态校验与签名装配 | 装配精确签名/ACL的VPN系统dialog资产。 |
| [common/standard_vpn/components/xpm](../patches/common/standard_vpn/components/xpm/apply.sh) | 1 | 架构和系统调用ABI | 接入portable XPM调用及目标构建边界。 |
| [common/third_party/alsa-lib/config_install](../patches/common/third_party/alsa-lib/config_install/apply.sh) | 1 | 共享打包位置缺陷 | ALSA named hw配置要装到chipset；仅开feature不能证明最终路径存在。 |
| [common/third_party/musl/cortex_m_sdk](../patches/common/third_party/musl/cortex_m_sdk/apply.sh) | 1 | 构建宿主与依赖获取 | Cortex-M SDK脚本用POSIX语法；属于完整SDK构建兼容。 |
| [common/third_party/vulkan-loader/ohos_surface_dispatch](../patches/common/third_party/vulkan-loader/ohos_surface_dispatch/apply.sh) | 1 | QEMU Vulkan软件后端与WSI | 补软件ICD、禁用不兼容layer、OHOS surface分发与NativeWindow呈现；不得仅凭离屏成功宣告上屏。 |
| [common/vendor/ohemu/audio_profile](../patches/common/vendor/ohemu/audio_profile/apply.sh) | 2 | QEMU部件继承覆盖 | 迁移空ALSA条目以让已有窄覆盖层生效，不放宽local-shadow拒绝检查。 |
| [common/vendor/ohemu/qemu_audio_device](../patches/common/vendor/ohemu/qemu_audio_device/apply.sh) | 1 | QEMU虚拟外设 | 在full QEMU启动器挂载ES1370音频设备。 |
| [common/vendor/ohemu/virt/calendar_provider](../patches/common/vendor/ohemu/virt/calendar_provider/apply.sh) | 1 | QEMU预装身份与路径 | 匹配源构建CalendarData的实际平台leaf证书。 |
| [common/vendor/ohemu/virt/dhardware_preinstall](../patches/common/vendor/ohemu/virt/dhardware_preinstall/apply.sh) | 1 | QEMU预装身份与路径 | 预装清单匹配DHardware UI实际安装目录。 |
| [common/web/arkweb/m144_avc_encoder](../patches/common/web/arkweb/m144_avc_encoder/apply.sh) | 1 | QEMU软件媒体后端 | 生成真实软件AVC adapter的GN运行目标。 |
| [common/web/arkweb/m144_swiftshader](../patches/common/web/arkweb/m144_swiftshader/apply.sh) | 5 | QEMU Vulkan软件后端与WSI | 补软件ICD、禁用不兼容layer、OHOS surface分发与NativeWindow呈现；不得仅凭离屏成功宣告上屏。 |
| [common/web/arkweb/m144_v8_shared](../patches/common/web/arkweb/m144_v8_shared/apply.sh) | 18 | M144依赖构建与运行ABI | 从M144源重建ArkWeb依赖；修GN边界、LLVM配置、编译器/runtime和OHOS libc++ ABI。 |
| [phone/product_profile](../patches/phone/product_profile/apply.sh) | 0 | 产品配置与运行装配 | 生成phone设备契约、官方SysCap与后置feature覆盖。 |
| [phone/sceneboard_runtime](../patches/phone/sceneboard_runtime/apply.sh) | 0 | 产品配置与运行装配 | 装配phone SceneBoard签名资产、BMS规则与运行配置。 |
