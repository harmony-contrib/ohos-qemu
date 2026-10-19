# 单一开发分支整合（2026-10-19）

当前开发分支为 `codex/ohos7-integrated-development`，主目录为
`/Volumes/PSSD/code/ohos-rs/ohos-qemu`。以 `a0d6215` 的较新完整修复为基底，
逐项审查其他 29 个本地分支的独有提交，按内容整合，避免旧文件覆盖新修复。

## 补回的独有内容

| 候选 | 来源提交 | 整合后状态 |
| --- | --- | --- |
| Settings 原生 select PickerDialog | b8a4c1b | 28 路径已纳入；待当前 Share 依赖/完整 guard、构建参数和真实 private-start 接线 |
| Calendar GetEvents/异步队列生命周期 | ba14ab5（与 a8d5d2b 相同） | 完整候选已纳入；旧分支也未接 build；仍待原生验证与构建接线 |
| Calendar 浏览/增删改页面 | 098bafe（与 331b5fd 相同） | 独立 calendar_main 候选保留；现行 main_ui 提醒页面继续启用；旧测试改名为 test_batch_system_calendar_crud_candidate.py |
| AudioHaptic 公共 API/只读 TIME 观测 | 436c2cf（与 6c3dd81 相同） | 原候选和历史保留；当前较新的 PCM/VDI 主方案继续使用 |
| AudioHaptic 三 UID renderer focus | 93b0307（与 a6ce594 相同） | 独有候选保留；旧 token/资源接口需迁移，缺真实 onset anchor，不能登记为通过 |
| 双虚机共享 Ethernet peer | 1b57a04 | 10 文件及 packager 四个增量已纳入；保留当前 UTC、完整校验和、PrivacyCenter 校验 |

当前 Calendar notification/DSO 修复、reminder owner、Mesa 755 修复已覆盖旧候选。
设备类型、无障碍、窗口和 GPU 分支通过相同整树的历史 squash 已进入主线；
QoS/JSVM/vibrator/ABI 旧提交的现行组件及接线也已核对。详见 audits。

整合不是恢复旧分支的整份脚本。内容处理完成后，使用 reconciliation merge
记录旧分支历史归属，保留当前经过审查的文件树。各原始分支 tip 见
branch-reconciliation.json。受保护旧工作区保留历史目录，不用于后续开发。

## 验证和当前限制

整合回归 155 项通过。首次回归保留在外部证据目录；其中选择器只读
`git apply --numstat` 从仓库子目录执行时误过滤路径，已固定中立工作目录，
新增回归后完整重验通过。未运行新包构建或虚机，未把主机通过计为能力闭合。
具体命令、日志 SHA 和结果见 host-validation.json。

剩余实现、接线和新包验收工作见 remaining-gaps.md。历史 82 项是未销项需求集合，
不能称为 82 项当前缺失实现，也不能因补回候选就扣减正式账本。

## 保全和后续协作

原分支 Git bundle 和 14 份完整工作区归档已校验；路径及 SHA 见 preservation.json
和 worktree-backups.json。归档包含 ignored/untracked 草稿（约 49.69 MiB），
其中 network scratch 和 8 份未完成的 native mock header 作为历史草稿保留。
它们未被混作已完成的生产修复。

后续五个能力方向共用本分支。父 agent 分配互不重叠的具体文件，独占共享脚本、
Git index/提交及 source/out、SDK/签名、Docker、QEMU/HDC/QMP。旧工作区和旧
冻结配置中的路径仅代表历史证据；新运行必须绑定当前主目录及当前提交。
只有新代表包完整运行验收通过后，才启动其余五包。
