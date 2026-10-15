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
