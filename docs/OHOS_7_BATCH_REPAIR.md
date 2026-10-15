# OpenHarmony 7.0 全量修复批次

执行方式：集中修复全部已知缺口并完成对应编译/主机检查，再冻结、打包一次 ARM64 phone 代表产物并启动完整验收。汇总这一轮全部错误后再批量修复、统一打包。首包完整门槛通过后才构建其余五包。

当前权威完整账本为 R49：281 项、199 项闭合、82 项未闭合（26 项 ArkTS 接口、56 项行为）。本表不关闭任何条目；R50 单项通过和候选编译不能直接扣减。R51 保留原冻结输入完成了一次验收尝试，结果如下。

R51 已生成新归档，但启动稳定性门槛失败：同一内核在真实休眠/一次电源键唤醒后，RenderService 从 PID 665 变为 2574，init 记录原进程退出码 0。根因尚未确定；本轮未执行启动后的接口、ArkWeb、退出、Vulkan 与完整账本验证，不能减少上述 82 项。该启动回归与 R50 的 HiTrace 全量流程失败另行纳入本批次。

从保留的失败数据盘只读提取了 PID 665 的 SERVICE_BLOCK/SERVICE_WARNING。与新包实际库的 Build ID 匹配后，主线程栈为 RSDrawFrame::PostAndWait，渲染线程位于 Mesa softpipe 的 TGSI 片元解释执行；阻塞在休眠前已经出现。实际 Mesa 已以 -O2 构建，不能把重复开启优化当作修复。正在验证固定 M144 SwiftShader 提供的 LLVM 10 源码能否为 OHOS llvmpipe 提供 JIT 后端；ARM64 候选已完成 Mesa 链接和独立 GL 执行诊断，尚未装包或验证实际 RenderService，不关闭任何缺口，也未改动看门狗策略。

LLVM 候选 05 在保留候选 04 的实际 JIT 证明后，依据 Mesa 完整链接的 43 个未解析符号，集中补齐反汇编和优化 pass 所属组件，复用原对象新增编译 56 个源文件，再次通过 3 次 JIT 生命周期、384 个向量结果、48 次外部数学调用。Mesa 已实际链接安装；新驱动 SHA256 为 dbfc3a77b1c2cee3a3d2816a72d609b89520cef3b4312a74adc9f1bbc37aa360。默认选择 llvmpipe；与同一驱动显式选择的 softpipe 各完成 3 次上下文生命周期、36 帧、9753714 个像素参考值检查，覆盖 1×1、65×33、320×180、1280×800、着色器、混合、裁剪、步幅填充和销毁。严格字节校验和比较失败的原始记录保留；随后独立比较两边全部原始像素，最大差异为 RGBA8 的 1 个量化单位。证据目录为 /Volumes/PSSD/qemu/validation/first-20261005/issue-20-20261006/r51-mesa-actual-dri-render-06。

GL 诊断发现的 libunwind FDE 注册问题已完成依赖级修复：固定 OHOS ARM64/x86_64 运行库导出逐 FDE 的 __unw_add_dynamic_fde 接口，而 LLVM 10 原非 Apple 路径把整个 EH frame 段交给 __register_frame。回移上游按 unwinder 区分注册方式的条件，并确保编译宏实际进入 llvm 子目录目标。真实 OHOS ARM64 JIT 对照中，原库报 CIE/FDE 错误且退出码为 13；修复库连续 3 次穿过 JIT 展开至原生调用者，每次 6 帧，错误警告为零，向量和外部数学调用回归仍通过。证据目录为 /Volumes/PSSD/qemu/validation/first-20261005/issue-20-20261006/r51-llvm10-real-unwind-backport-03。

Mesa 使用修复后的 LLVM 重新链接安装，当前候选驱动 SHA256 为 3d59d9251ff589bc15b9f3b09f703f764f424cea28668ffc0c977b041b902722。两个后端再次各完成 3 次生命周期、36 帧、9753714 个像素参考值检查及全部原始像素独立比较，最大差异仍为 RGBA8 的 1 个量化单位，FDE 错误警告均为零。原始驱动与失败记录保留。新证据目录为 /Volumes/PSSD/qemu/validation/first-20261005/issue-20-20261006/r51-mesa-actual-dri-render-07。仓库构建脚本已包含此私有源文件回移，并校验实际运行库符号和编译命令；ARM 使用原有 EHABI 路径，尚需其实际 JIT ABI 验证。以上仍未证明修复 R51 的真实启动故障，也不替代新包的 ArkWeb、退出、Vulkan 或完整能力账本。

新增 scripts/build_qemu_mesa_llvm.py 及配套 Docker 入口，从现有 M144 锁校验 SwiftShader 提交、LLVM Git tree 和源码清洁状态，生成单架构私有 LLVM。ARMv7a 实际构建暴露了第二份 config.h 写回 hard-float triple、以及软浮点调用约定的 musl 未定义 FE_INEXACT 两项问题。现已同时修正两份私有头，按实际声明设置 HAVE_DECL_FE_INEXACT；四种目标的预处理检查证明仅 OHOS ARMv7a 的三项宏改变。修正后的 ARMv7a 完整依赖编译仍在运行，尚无 ARMv7a JIT/GL 执行证明。以上均是依赖准备，未解决首包运行门槛，也未启动其余五包。

VPN 管理协议候选也已依据固定 OpenVPN 源码修正：纯 IPv4 状态为 8 个字段，带隧道 IPv6 时才增加第 9 个字段；旧候选错误地要求始终为 9 个字段。新候选使用原 log_entry_print 函数体通过了 30 项 ASan/UBSan 主机边界检查。该解析器尚未接入完整系统 VPN 后端，不能据此关闭 VPN 条目。

| 分组 | 未闭合数 |
| --- | ---: |
| 系统应用与入口 | 27 |
| 电话与通信 | 13 |
| 定位 | 9 |
| 其他系统服务 | 8 |
| 网络与外设 | 6 |
| 音视频输入与处理 | 6 |
| 能力声明与运行时插件 | 4 |
| VPN | 3 |
| 无障碍 | 3 |
| 子进程与内核身份 | 2 |
| 媒体知识数据 | 1 |
| 合计 | 82 |

仅保留用户批准的 CloudSync、imageGeneration、ArkTS Static 三项排除，不新增排除。

| 分组 | 未闭合条目 | 当前准备状态 |
| --- | --- | --- |
| 无障碍 | `arkts_export:@ohos.accessibility.config:startBlinking` | R50 新包 ScreenBlink 单项通过，待后续全量账本确认 |
| 无障碍 | `arkts_export:@ohos.accessibility.config:stopBlinking` | R50 新包 ScreenBlink 单项通过，待后续全量账本确认 |
| 网络与外设 | `arkts_export:@ohos.bluetooth.connection:startPairOutOfBand` | 实现与完整验证尚未齐备 |
| 媒体知识数据 | `arkts_export:@ohos.file.photoAccessHelper:KnowledgeContent` | 实现与完整验证尚未齐备 |
| 定位 | `arkts_export:@ohos.geoLocationManager:addFusionFence` | 实现与完整验证尚未齐备 |
| 定位 | `arkts_export:@ohos.geoLocationManager:getCurrentDistrict` | 实现与完整验证尚未齐备 |
| 定位 | `arkts_export:@ohos.geoLocationManager:getLocationIconStatus` | 实现与完整验证尚未齐备 |
| 定位 | `arkts_export:@ohos.geoLocationManager:getPostProcessingTrack` | 实现与完整验证尚未齐备 |
| 定位 | `arkts_export:@ohos.geoLocationManager:isFusionFenceSupported` | 实现与完整验证尚未齐备 |
| 定位 | `arkts_export:@ohos.geoLocationManager:removeFusionFence` | 实现与完整验证尚未齐备 |
| 定位 | `arkts_export:@ohos.geoLocationManager:startBluetoothSearch` | 实现与完整验证尚未齐备 |
| 定位 | `arkts_export:@ohos.geoLocationManager:stopBluetoothSearch` | 实现与完整验证尚未齐备 |
| VPN | `arkts_export:@ohos.net.vpn:getConnectedSysVpnConfig` | 四补丁及三架构 TU 已验证；后端/完整运行未完成 |
| VPN | `arkts_export:@ohos.net.vpn:getConnectedVpnAppInfo` | 四补丁及三架构 TU 已验证；后端/完整运行未完成 |
| 电话与通信 | `arkts_export:@ohos.telephony.call:offReceiveRttMessage` | 实现与完整验证尚未齐备 |
| 电话与通信 | `arkts_export:@ohos.telephony.call:offRttErrCause` | 实现与完整验证尚未齐备 |
| 电话与通信 | `arkts_export:@ohos.telephony.call:offRttModifyInd` | 实现与完整验证尚未齐备 |
| 电话与通信 | `arkts_export:@ohos.telephony.call:onReceiveRttMessage` | 实现与完整验证尚未齐备 |
| 电话与通信 | `arkts_export:@ohos.telephony.call:onRttErrCause` | 实现与完整验证尚未齐备 |
| 电话与通信 | `arkts_export:@ohos.telephony.call:onRttModifyInd` | 实现与完整验证尚未齐备 |
| 电话与通信 | `arkts_export:@ohos.telephony.call:sendRttMessage` | 实现与完整验证尚未齐备 |
| 电话与通信 | `arkts_export:@ohos.telephony.call:setRttCapability` | 实现与完整验证尚未齐备 |
| 电话与通信 | `arkts_export:@ohos.telephony.call:startRtt` | 实现与完整验证尚未齐备 |
| 电话与通信 | `arkts_export:@ohos.telephony.call:stopRtt` | 实现与完整验证尚未齐备 |
| 电话与通信 | `arkts_export:@ohos.telephony.observer:offCommunicationStateChange` | 实现与完整验证尚未齐备 |
| 电话与通信 | `arkts_export:@ohos.telephony.observer:onCommunicationStateChange` | 实现与完整验证尚未齐备 |
| 子进程与内核身份 | `behavior:access-token-api26-kernel-abi` | 实现与完整验证尚未齐备 |
| 其他系统服务 | `behavior:msdp-device-status-mock-or-missing-clients` | 实现与完整验证尚未齐备 |
| 网络与外设 | `behavior:netmanager-ebpf-backend` | 实现与完整验证尚未齐备 |
| 子进程与内核身份 | `behavior:native-child-process-phone-boundary` | 禁用画像参数/载荷修复待 R51；启用画像完整生命周期尚未完成 |
| 网络与外设 | `behavior:bluetooth-state-transition-false-success` | 实现与完整验证尚未齐备 |
| 网络与外设 | `behavior:wifi-sta-backend-unavailable` | 实现与完整验证尚未齐备 |
| 网络与外设 | `behavior:usb-manager-device-query` | 实现与完整验证尚未齐备 |
| 其他系统服务 | `behavior:session-manager-profile-gap` | 实现与完整验证尚未齐备 |
| 能力声明与运行时插件 | `behavior:phone-published-capabilities-not-declared` | 实现与完整验证尚未齐备 |
| 能力声明与运行时插件 | `behavior:phone-avinputcast-not-declared` | 实现与完整验证尚未齐备 |
| 定位 | `behavior:location-provider-backends-missing` | 实现与完整验证尚未齐备 |
| 电话与通信 | `behavior:telephony-no-modem-or-sim` | 实现与完整验证尚未齐备 |
| 音视频输入与处理 | `behavior:audio-capture-and-dependent-pipelines` | 实现与完整验证尚未齐备 |
| 音视频输入与处理 | `behavior:media-recording-input-backends-missing` | 实现与完整验证尚未齐备 |
| 无障碍 | `behavior:accessibility-qemu-input-e2e` | 实现与完整验证尚未齐备 |
| 网络与外设 | `behavior:peer-device-user-nat-isolation` | 实现与完整验证尚未齐备 |
| 其他系统服务 | `behavior:calendar-lifecycle-device-difference` | 实现与完整验证尚未齐备 |
| VPN | `behavior:vpn-runtime-export-gaps` | 四补丁及三架构 TU 已验证；后端/完整运行未完成 |
| 其他系统服务 | `behavior:device-attest-uninitialized` | 实现与完整验证尚未齐备 |
| 能力声明与运行时插件 | `behavior:api26-runtime-export-mismatches-phone` | 实现与完整验证尚未齐备 |
| 其他系统服务 | `behavior:advertising-service-provider-missing` | 实现与完整验证尚未齐备 |
| 系统应用与入口 | `behavior:intelligent-scene-notification-query-fails` | 实现与完整验证尚未齐备 |
| 其他系统服务 | `behavior:graphics3d-scene-manager-unavailable` | 实现与完整验证尚未齐备 |
| 音视频输入与处理 | `behavior:audio-interrupt-haptic-renderer-dependency` | 实现与完整验证尚未齐备 |
| 音视频输入与处理 | `behavior:media-codec-base-partial` | 实现与完整验证尚未齐备 |
| 系统应用与入口 | `behavior:shortkey-empty-launch-config` | 实现与完整验证尚未齐备 |
| 系统应用与入口 | `behavior:certificate-dialog-device-result` | 实现与完整验证尚未齐备 |
| 其他系统服务 | `behavior:security-guard-empty-model-config` | 实现与完整验证尚未齐备 |
| 系统应用与入口 | `behavior:ability-share-picker-system-provider-missing` | 实现与完整验证尚未齐备 |
| 系统应用与入口 | `behavior:ability-send-data-action-has-no-enabled-handler` | 实现与完整验证尚未齐备 |
| 系统应用与入口 | `behavior:avcast-media-controller-provider-mismatch` | 实现与完整验证尚未齐备 |
| 系统应用与入口 | `behavior:media-control-volume-provider-activation` | 实现与完整验证尚未齐备 |
| 系统应用与入口 | `behavior:distributed-hardware-ui-preinstall-path-mismatch` | 实现与完整验证尚未齐备 |
| 系统应用与入口 | `behavior:photo-provider-not-activated-2in1` | 实现与完整验证尚未齐备 |
| 系统应用与入口 | `behavior:enterprise-provisioning-provider-missing` | 实现与完整验证尚未齐备 |
| 系统应用与入口 | `behavior:wallpaper-ui-provider-missing` | 实现与完整验证尚未齐备 |
| 系统应用与入口 | `behavior:accessibility-screen-reader-provider-missing` | 实现与完整验证尚未齐备 |
| 系统应用与入口 | `behavior:accessibility-caption-provider-missing` | 实现与完整验证尚未齐备 |
| 系统应用与入口 | `behavior:vpn-dialog-provider-prefix-mismatch` | 实现与完整验证尚未齐备 |
| 系统应用与入口 | `behavior:network-policy-settings-providers-missing` | 实现与完整验证尚未齐备 |
| 系统应用与入口 | `behavior:telephony-apn-settings-provider-missing` | 实现与完整验证尚未齐备 |
| 系统应用与入口 | `behavior:wifi-system-ui-providers-not-activated` | 实现与完整验证尚未齐备 |
| 系统应用与入口 | `behavior:camera-picker-entrypoint-missing-phone` | 实现与完整验证尚未齐备 |
| 系统应用与入口 | `behavior:notification-extension-settings-entrypoint-missing` | 实现与完整验证尚未齐备 |
| 系统应用与入口 | `behavior:accessibility-settings-entrypoints-unavailable` | 实现与完整验证尚未齐备 |
| 系统应用与入口 | `behavior:notification-manager-settings-provider-missing-phone` | 实现与完整验证尚未齐备 |
| 系统应用与入口 | `behavior:avsession-desktop-lyrics-provider-missing` | 实现与完整验证尚未齐备 |
| 系统应用与入口 | `behavior:location-privacy-ui-providers-unavailable` | 实现与完整验证尚未齐备 |
| 系统应用与入口 | `behavior:telephony-number-identity-provider-missing` | 实现与完整验证尚未齐备 |
| 系统应用与入口 | `behavior:settings-navigation-provider-mismatch` | R50 新包完整 Settings 单项通过，待后续全量账本确认 |
| 系统应用与入口 | `behavior:contacts-picker-entrypoint-missing-phone` | 实现与完整验证尚未齐备 |
| 系统应用与入口 | `behavior:arkui-expanded-text-menu-providers-missing` | 实现与完整验证尚未齐备 |
| 能力声明与运行时插件 | `behavior:arkui-text-service-runtime-plugins-missing` | 实现与完整验证尚未齐备 |
| 其他系统服务 | `behavior:app-domain-verification-extension-missing` | 实现与完整验证尚未齐备 |
| 音视频输入与处理 | `behavior:audio-vivid-metadata-runtime-plugin-missing` | 实现与完整验证尚未齐备 |
| 音视频输入与处理 | `behavior:video-encoder-dependent-media-pipelines` | 实现与完整验证尚未齐备 |

每项闭合必须绑定新归档 SHA256、冻结输入、实际 boot、调用者身份、全部对应行为及边界结果。完整账本、ArkWeb、UDMF/Pasteboard/AVPlayer 实际退出和完整 Vulkan 均须通过。

批次准备及额外验收故障证据：`/Volumes/PSSD/qemu/validation/first-20261005/issue-20-20261006/r51-full-unresolved-batch-worklist-04.json`。

2026-10-15 依赖与后端批次新增进展（不核销上述 82 项）：

- 当前 LLVM 配方 `634e042f…` 的 ARM64 完整源码构建已成功；全量头文件、归档对象架构和双源码锁均记录在实际产物 manifest 中。真实产物经过旧配方、错产品、头文件篡改、混合架构对象和虚假 runtime 标记的拒绝验证，以及实际 staging/restore/reapply 验证。
- ARMv7a 的实际 OHOS QEMU 用户态 JIT 已完成三次生命周期、384 个向量结果及 48 个外部数学调用检查。它仍使用此前冻结的诊断依赖，不是 ARMv7a 完整镜像验收。
- 新 Mesa 消费端使用显式旧冻结依赖的接口诊断已完整编译；直接 EGL/GLES 2/3 用户态诊断实际完成 6 次上下文和 19,507,428 个着色器像素检查，退出码 0、FDE 警告 0。它使用 surfaceless 和显式库别名，不证明默认 OHOS 显示、RenderService 稳定性或 Vulkan。
- 当前 LLVM 配方的 Mesa 消费端重建至 677/1078 时，宿主磁盘写满触发 OrbStack I/O 停机，Docker 返回 125/EOF。保留原始失败，不能将它登记为 Mesa 编译完成。
- 正常打包新增六个实际 Mesa 库与构建来源的字节绑定，完整归档包含 LLVM manifest、消费端构建证明与库清单；离线检查会再次核对图像。新检查的四组负例通过；真实当前消费端图像绑定仍待构建完成验证。
- 新 OpenVPN 原生监督程序及 TUN 桥已实际 ARM64 编译、链接。进程所有权、真实 management/TUN 双条件连接发布已进入源码；GN/init/netsys 接线、完整配置与网络行为及新包真实对端验证尚未完成。

本批未开始新 QEMU 打包，也未开始其余五包。R50 HiTrace 和 R51 RenderService 两个整体验收故障仍待新包证明修复。

宿主恢复历史：正常启动 OrbStack 后，两份已结束且无容器引用的 LLVM 工作卷在完整产物/日志 SHA 校验后回收，构建盘恢复约 14 GiB 可用。Mesa03 的续编请求及当时真实进度保留在 `r49-current-work-state-86.json` 和 `r51-ended-LLVM-build-volume-recovery-23.json`，不能解释为当前仍在运行。

2026-10-15 整理提交时复核：当前配方的 Mesa 消费端 05 已完成，`r51-mesa-integrated-consumer-05/host-evidence.json` 与 `evidence.json` 均记录构建退出码 0。当前没有运行中的 QEMU 构建容器；该依赖结果仍不证明新包、默认显示链路或 RenderService 稳定性。历史 Mesa ELF note 的边界修复及针对性回归已加入源码，后续仍需同批次新包验收。

全部 82 项要求已按能力互斥分配给五组，公共构建、账本和正式验收由主 agent 统一管理。隔离与资源规则见 `OHOS_7_PARALLEL_REPAIR.md`，逐项清单见 `capability-audit/parallel-work-plan.json`。
