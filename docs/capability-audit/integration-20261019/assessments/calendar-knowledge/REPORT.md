# 373系统方向：未闭环能力ID统计

本方向（日历与Knowledge）还有 **2个唯一能力ID未闭环**，不是2个测试或2个producer。两项均有关键源码修复已提交，但都还缺a0d新代表包的实际运行验收。未确认新的专属producer实现缺陷；这不等于已证明完整广义能力实现齐全。

| 精确ID | 归属 / 媒体重叠 | 当前状态与仍缺内容 |
| --- | --- | --- |
| `behavior:calendar-lifecycle-device-difference` | 系统/日历；不与媒体重复 | MainAbility共享LocalStorage和305 locale分隔符比较已修；待新包实际权限、公开创建/独立读、通知点击到UI、URI更新/删除/清理。完整cold/warm实例、rapid OnNewWant、独立实例、viewer退出重启及guest重启连续性仍缺充分证明。当前verifier明确保留remaining_required_gaps、full_calendar_lifecycle_verified=false、ledger_closed=false。 |
| `arkts_export:@ohos.file.photoAccessHelper:KnowledgeContent` | 本轮系统/Knowledge；**与媒体方向重叠1个ID，汇总只计一次** | 真实有权限media-owner查询路径和350 capture阻断已修；待新包同run/boot22阶段与完整独立verifier。HOLIDAY/account100有限链即使通过，也不自动证明非空analysis producer、账号隔离或完整KnowledgeContent class语义；原verified_closures(knowledge-holiday)返回空ID集合。 |

精确分类：确认仍缺实现的ID **0个（本审计未确认，不能理解为广义能力都已实现）**；源码修复后待新包验收 **2个**；当前a0d已有完整scoped case实际通过但未全门闭环 **0个**。这些类别不能把子断言、旧包观察或交叉归属重复相加。两个ID的更广范围证据义务均仍存在，不能在有限case通过后直接减账。

计数来源是255 FACTS.historical_open_82.requirements的原始两个ID及其原group/next_required，并与当前F能力目录、82/17 case输入和原verifier的闭合范围核对。255保存的是历史82项工作清单，不是本轮新a0d全量open采集。这里不据此宣称当前全项目仍恰好82项，不把历史199或旧E通过移植到本F，也不根据producer、host/SDK测试或stage数量推导能力数。COUNTS.json保留精确集合和原目录两行。

实际旧296不能算本方向case通过：Calendar只完成public locale子操作，两个API真实返回zh-Hans-CN和zh_Hans_CN；旧比较器在prepare阶段拒绝，phases为空，完整生命周期未进入。Knowledge整轮因真实screenCap guest1失败；后续emergency cleanup与原22操作局部journal不修复该失败，正常最终token/raw oracle和独立verifier未到达。两份失败证据保留。它们提供了修复依据及局部观察，不是a0d的新包scoped pass。

当前源码的直接依据：Calendar batch_system_calendar_runtime_verify.py:431–440保留完整生命周期/ledger false；contract.json列出20项coverage，其中cold/warm、rapid OnNewWant、独立实例及reboot不能从stage名称推断。Knowledge batch_media_knowledge_suite.py:1428–1429即使有限验收成功仍返回account_isolation_verified=false、nonempty_analysis_producer_verified=false、closed_requirement_ids=[]；parallel_runtime_suite.py:117–127明确不注册Knowledge ID。305/350通过源回归与独立源码review说明修复可进入下一轮，并不改变这些实际运行/全范围门槛。

Root报告a0d62155747253f203952878594e21976c12a92c已提交且813 host（812pass/1skip）、9 Linux组和14 SDK角色通过，新a0d代表包尚未构建。这些是父任务状态，本统计未重跑或将其计为guest能力闭合。下一实际前置是root合批完成后的新包及对应installed profile/helpers/source/SDK绑定，再分别在独占新VM执行Calendar和Knowledge原case及严格独立验收；失败收齐后统一修复。Calendar的完整生命周期和Knowledge广义语义仍需各自原充分证据，不能只等待一个狭义“pass”就自动登记原ID。

按父任务最新要求，本轮候选扩展已暂停。本目录只有统计、来源pins和空候选修改清单；没有写F/MAIN/旧源码或旧证据，没有新增patch，也未触及verify_evidence、guest_ui、owner/SDK/签名或audio。未import/执行候选、tests、Git、SDK、编译、crypto、容器、VM/HDC/QMP或大镜像操作。所有读取单文件均≤6MiB；不读包或镜像。SOURCE_PINS.json、PREIMAGE-POSTIMAGE.json可核对边界。后续源码任务需root另行安排。
