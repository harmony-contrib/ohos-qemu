# 当前历史需求与运行验收缺口（577）

本次逐一核对原 82 个历史未销项 ID，源基线为统一开发分支的 `75da6c3`。
9 个精确原 ID 仍按已核官方来源范围记 unsupported；其余 73 项尚未由本轮新包完整运行证明。
73 不是缺实现数量，也不是新确认故障数量。

|当前计划范围|原 ID 数|
|---|---:|
|精确 unsupported（不是修复或 runtime pass）|9|
|未找到完整原 ID 运行计划/收口|51|
|只有有限范围运行计划|20|
|广义视频缺 AVScreenCapture/AVTranscoder 实际输出用例|1|
|AudioHaptic onset anchor 仍未知|1|

[逐 ID 映射、原入口和输入缺口](coverage577-current.json)保留三组只读审计的全部具体结论。
原 47 项套件和 Audio/Calendar/Number/GNSS/Network 五个窄链即使将来通过，也不足以自动关闭
全部适用历史项。电话 RTT/通信状态、八个 Location 新 API、多项应用服务协议以及系统广义
聚合能力仍需真实 caller、输入、输出、权限、取消/死亡/重启和清理证据。缺少计划不等于
源码不存在；SDK/host/static 成功也不关闭原 ID。正式总账尚未按新包重算。

本轮代表构建实际采用 OrbStack 24 GiB，容器 RAM 14 GiB、swap 24 GiB、CPU4；
7 项前置检查闭合成功。GN 在多 worker 生成阶段停止推进，父子线程持续 futex 等待，
当时约 2.08 GiB 内存、swap0、OOM0。root 对确认身份与出生时间的原 Owner 发 TERM，
由原 Owner 完成容器、launcher 和 lease 清理，结果 exit1、无产包。这是受控中断的
挂起尝试，不应记录成自然编译结束或 OOM。详见[原始证据与清理结果](representative577-host-stall.json)。

下一批对宿主翻译执行的 GN 使用原 HB `--gn-flags=--threads=1`，并清除持久化 `gn_flags`，
避免 worker 限制跨宿主模式/构建继承。原 GN 二进制、编译/LTO/CFI 选项保持。
8 项针对性 host 检查和脚本语法检查通过；这只是待新代表构建验证的缓解，未证明具体
模拟器锁问题已修复。应用、Location、广义视频的实际 caller/oracle 补齐已分配独占候选
目录；root 负责共享接线、Git、SDK、构建、签名和 VM 资源。

所有已知修复合批后，仍先构建并完整运行验收一份新代表产物，记录路径、校验和、环境、
命令、边界/回归/cleanup。收集该轮实际失败后统一修复；完整首件行为门通过前不启动
其余五份产物。所有原断言和已有证据保留，未把旧包或窄链结果当全范围通过。
