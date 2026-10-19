# Round 375 核心集成记录

所有修复进入 `codex/ohos7-integrated-development`。root 独占 Git、共享构建/打包/验证入口及 SDK、source/out、QEMU/HDC、Docker；五个能力任务采用互斥文件授权与三子任务并发上限。

Calendar 原生 filter/queue 生命周期批次已由 root 接线并提交 `a714da4`。Settings 私有 select 组件采用原始请求、线程局部 RAII、原始 userId 和完整会话/调用者验证；root 增补真实 CLI 接线，完整 chooser/Share/Wallpaper/ExternalInput 组合 guard，以及依赖完整组件的成对产品参数写入。HAP 检查校验实际编译私有 ability 的入口、启动模式、不导出、不增加 skills/权限和实际页面资源；原签名、ACL、权限及三 ABI 检查保留。

ArkUI CFI 组件只修改已封存真实 GN 的 UIExtension source-set 和最终 libace_compatible sanitizer 块，已接入相邻原生 identity 组件的产品入口。必须重新 GN、whole-TU 编译、链接并检查最终 DSO，源码及 host 结果不能代替这些证明。

网络首批提供 RootExecutor、原 OpenVPN ledger producer 及双 QEMU LAN 业务窗口与回收。root 仍需连接实际 guardian/bootstrap、跨 actor durable reservation/registry、双 VM 与新包业务；84 项 host 检查不关闭九个正式 ID。

root 只读采集实际源卷的三个 GN 向量、Settings/AMS/Calendar 向量和 Vivid sink/依赖向量，输出位于统一 validation BASE 的 `r60-*-375-01`。每次严格关闭自己持有的容器与 CLI，source/out 未写入。host 镜像与真实 prepared 项目 HEAD 不同的，以实际源卷及原始 SHA 为准。

首个新包必须是 ARM64 phone，记录路径/SHA/环境/命令/原始结果。完整同 boot 验收后才放行其余 ARM64/ARMv7/x86_64 × phone/2in1 五份产物。旧 17-06 包以及旧 detached F 工作区的结果仅作历史证据。

用户在 2026-10-19 明确要求：检查 OpenHarmony 及相关 SIG，公开可交付实现则接入；缺完整实现的能力记为不支持。官方实现、模型/数据、产品凭据分别记录；不支持不是修复或 runtime pass。官方来源调查在 `../parallel/network/round375-provider-research/`。

当前修复/验收正在进行：尚未宣称新代表包通过或启动其他五包。

核心增量复核：160 项 host 回归、Settings 旧 chooser 19 项、用户范围/原始账本/源码快照 23 项通过（不同批次有重叠，不合计为唯一测试数）。真实 Vivid 原函数的受控 native harness 首次编译暴露夹具 uint64_t/size_t 同声明推导错误；拆开声明后 ASan/UBSan 的 30 场景及 4 项源/安装/native方法通过，失败日志保留。它仍不是完整 native TU、codec/plugin 或新 guest 验收。原样保留 patch context 与 upstream fixture 的已有空白，不修改其 SHA 来迎合 whitespace lint。

九个精确完整 provider 的公开交付边界由 unsupported-public-providers.json 及其源证据固定。full audit 原始 ledger 不改；root gate 仍重新核对相同新包/boot 的每一个保留需求及 raw child proof，用户确认的不支持另列且不算关闭。号码公开本地用户标记/有限号段不是完整反诈、HSDR 或数据产品；此子能力另列待接入。

6f5372d 全量预检已真实执行：host 1031 方法（1029通过、2条件跳过），Linux 9组全部通过，原14调用者SDK五阶段全部通过。额外三角色的caller成功、target_a角色字面量比较编译失败，target_b尚未执行；失败与小修细节见sdk-preflight-repair.json。只改两文件，root的13项回归通过，待新commit真实SDK复验。

普通框架时间含估算，音频/振动同步仍需独立真实呈现锚；ALSA只读内核帧观测候选尚未达到产品接线条件。按本轮构建规则先完成已收齐修复的代表包及整个runtime尝试，保存所有失败，再把观测候选与该轮失败统一修复；不因此放行其余五包。

后续 403 代表尝试已完整收尾：ARM64 phone 原生构建、镜像及包检查通过，产生 935483946 字节新归档，SHA256 为 `24f521aa3d8642ba10a12a678346020b40bab2b365037a2ca6cb77df81b9da79`。首次实际 VM 尝试在 HDC 连接重试前被验收器的 CRLF 文本转换错误阻断，尚未进入业务验收；Owner、子进程、容器和共享锁均已关闭。包路径、环境、命令和失败原始证据保存在 `batch454-evidence.json` 所列记录中。

本次批量修复保留原 HDC 原始输出字节，修正 Docker 完整 provider 校验中的镜像环境与 created/exited 字段区别，并接入经过两轮 fork 问题修复和独立复核的 ALSA PCM 观测组件。GN 开关只作用于 libasound；源码状态必须完整匹配 before/after，禁用时显式清除已打补丁树的旧 true 参数。443 三种 whole-TU 模式均真实编译通过，完整 DSO 重链、新镜像和真实 onset 仍待新一轮验收。

403 包的后续诊断还完成了两个 provider 的实际镜像 HAP/签名及完整候选 API 校验、PrivacyCenter 新路径输入的真实签名验证、GNSS 两个 whole-TU 和镜像角色检查、完整 GNSS 原82/435文件前置，以及两份新网络 caller HAP 和 Linux VPN 对端编译。这些均有独立结果文件；不作为 guest callback、权限切换、网络联机或正式能力销项。历史 82 个未闭项中，9 个精确公开 provider 依用户规则记不支持，其余73项仍需新包运行证据，并非73个已确认代码缺陷。后续继续先完成一个新代表包全量运行验收，才启动其余五包。
