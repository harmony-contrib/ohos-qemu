# 整合前只读内容审计：媒体、Calendar、Mesa

基底 `a0d62155747253f203952878594e21976c12a92c`；审阅 core-next `93b030742823dd864b97781299a349955485eab9` 的 8 项，以及旧 system/media 两支各 2 项。只读 Git 对象，不读取旧工作区，不运行候选或测试。

## 结论及合并决定

不能仅按路径不存在就认定实现遗漏：97 个触及路径中，91 个在基底无同名文件、6 个不同，包含大量历史文档和已由不同路径实现的功能。逐文件 blob/SHA/建议在 FILE_AUDIT.json；原 8 个提交完整二进制 diff 在 commit-diffs/，均未应用。

| core 提交 | 当前 a0d 状态 | 建议保留内容和整合限制 |
| --- | --- | --- |
| 098bafe Calendar Main | 旧 calendar_main 文件族没有；当前 main_ui 已实现另一套提醒 viewer | 保留旧源和历史。提醒的实际已安装 bundle、持久化内容读取、URI 校验、Ability storage/lifecycle 已有当前实现。旧日浏览、calendar 选择、normal 非递归事件 CRUD、queryEventInstances 精确实例路由是独有候选，不能称完全等价合入。不要把旧安装器接在当前 main_ui 之后，两者改写相同 MainAbility/index/module/reminder 文件且 postimage 不同。 |
| 436c2cf round21 AudioHaptic/TIME | 同名旧 4 个代码/测试文件均不存在；新 project/runtime/verifier/sampler 已替代大部分功能 | 保留候选/测试来源，当前生命周期、坏资源、权限、PCM/VDI、EOS/loop/stop/release/recreate 走当前实现。旧 ACTIVE journal 协议与当前 Date.now v1 不兼容，不能把其字段/解析器局部替换到旧证据。 |
| 49c20a Calendar Main 接线 | 当前已换成 main_ui + require-reminder-ui 和完整 source guards | 活跃 build/guard 保持 a0d。旧 require-main 对 READ/WRITE 两个 scene 均加 MainAbility；当前 viewer 只加 READ，主动请求用户读权限。旧集成测试调用已不存在的 validate_main_source/require_main，不能未经改造加入当前统一 test discovery。 |
| 4d4934 reminder native owner | 当前 calendar_owner 已有相同 NAME 修正，以及更完整 metadata 兼容 | 活跃实现保留当前组件。旧 calendar_provider_owner 要求旧 calendar_main 存在且 exact postimage，无法直接替代当前 guard。 |
| c4b660 whitespace context | 当前独立 NAME hunk 已保留，不含旧冗余空白上下文 | 无产品逻辑遗漏。历史 diff 保留即可；不能用旧只接受 ohos 的 consumer 覆盖当前兼容 ohos+hmos 的判断。 |
| 0021da Mesa action mode | 755 新安装/重放修复已存在 | 保持 a0d atomic_write keyword-only mode 和当前 installer 级测试；不回退实现/测试。 |
| ba14ab GetEvents/async queue | 当前所有 patches/ci grep 无该组件/等价 native snapshot/AsyncEnvironment 修复 | 真正遗漏的独有 native 修复候选。保留完整 component、两份 exact payload、manifest、fixture、model/test；需 root 另外接入实际 build 并验 native/ABI/环境销毁。core93 原本也没有 filter_async_lifetime 的 build 调用。 |
| 93b030 AudioHaptic focus coordinator | 旧同名 coordinator/test 不在当前；当前 MIC/VOIP focus 是另一项 | 保留三 UID renderer focus/background-task 候选及完整限定。原 run/verify 即使有限观测无误也永远 exit1、accepted=false，缺独立首呈现帧 onset anchor；不得接成绿色总门。 |

旧 system 的 `331b5fd` 与 core `098bafe`、`a8d5d2b` 与 `ba14ab`，旧 media 的 `6c3dd81` 与 `436c2cf`、`a6ce594` 与 `93b0307`，各自 `git show --format= --binary` 逐字节完全相同。因此这 4 项相对 core 的 8 项不再增独有内容；保留一次实现和共同历史即可。精确 diff SHA 在 FILE_AUDIT.json。

## Calendar Main：哪些已替代，哪些仍独有

当前 `main_ui/0001` 把普通/important reminder Want 的目标改成真实 `com.ohos.calendardata/MainAbility`，保留旧持久化 URI，通过公开 CalendarManager getAllCalendars/getEvents 查询真实 DB 内容；额外 start/end 不提供可信数据。请求 READ_WHOLE_CALENDAR 用户授权，空链接只显示提醒入口说明，reader dispose/generation 拒绝旧读回填；`0002` 用 `@Entry({ useSharedStorage: true })` 绑定 Ability-local storage。当前 `calendar_provider.py --require-reminder-ui` 再验证 main_ui+calendar_owner 整套，当前 event_editor guard 接受 final/prefix1 精确状态。

旧 `calendar_main` 也使用 Ability-local LocalStorage 和显式 useSharedStorage，并非没有共享 storage。差异是 controller/view storage 协议和完整页面被另一个 current reminder viewer 替代。旧 Controller 另有选择日历、前/后一天、日列表、用户 save/delete、重读并保留 untouched public fields、readonly 丰富 event 类型、background/dispose invalidation、mutations settle 后重读。它同时接受 calendardata 和 legacy calendar URI，并要求 queryEventInstances 返回的 ID/实例时间完全匹配。当前 read-only viewer 明确不含这些通用 UI 功能。它们应保留为候选或后续能力，不能在“已整合全部内容”时静默丢弃，也不能因保留文件就说已在产品启用。

同名 `ci/capability-audit/test_batch_system_calendar_main.py` 是真实冲突：旧套件针对旧 controller/install，当前套件针对 viewer/native consumer。保留当前同名测试；如需在单分支上保留旧套件，需 root 显式命名/限定对应候选，或仅保留整合历史，不能用旧测试覆盖当前测试。`test_calendar_main_integration.py` 更直接依赖旧 provider.validate_main_source 与 require_main，目前不存在，未经适配会失败。

## GetEvents：最小必须保留的独有修复

`filter_async_lifetime` 修改两个上游文件：

- `calendarmanager/napi/src/calendar_napi.cpp`：JS 线程 unwrap Calendar/EventFilter 并复制 native shared_ptr；worker 只使用 native snapshot；移除 async 排队后立即 delete filter ref 的旧生命周期；保留真实无 filter overload，并拒绝坏 wrapper/native。
- `calendarmanager/napi/src/napi_queue.cpp`：处理 promise/callback/self ref/resource/work/hook/queue 失败；保留原 promise 并 reject/回调一次；独立 environment hook token+弱 ContextBase，环境销毁后不访问 NAPI；numeric BusinessError code 放 property；真实 undefined receiver。

基底当前 viewer 用 `calendar.getEvents(calendarManager.EventFilter.filterById([id]))` 临时 filter，故这项并不因改成 viewer 就失去意义。旧候选固定上游 revision 与 8 个不变 native 依赖，其中 editor_callback_dispatch 的两份后像 SHA 与当前 a0d verifier 一致。它不修改当前 main_ui 的 UI 文件或 editor manager pair，源路径上可以独立组合，但“可以组合”尚未被实际执行证明。

core93 构建脚本没有调用该组件，旧候选日志也明确未 native 编译。因此 root 若启用，需要在 source_provider/event_editor/editor_callback_dispatch 之后、Calendar HAP build 之前加入实际 apply/require-patched；完成与当前全部 strict source guards 的原态/重放/混合态/回滚验证。必须再完成真实 OHOS NAPI header 编译、实际 engine env teardown/worker ordering/native sanitizer 与产品 CFI/link/新包 API 生命周期。不能因模型测试或旧作者报告就声称 runtime 修好。原 13 个 queue caller 共享改动，失败处理是更宽 native 范围；需关注一次交付、cancel、callback reentry、null completion env、cleanup-hook 删除失败与原有引用析构顺序。

## AudioHaptic/TIME/coordinator：保留而不冒充可直接运行

当前 `fixtures/batch_media/audio_haptic_runtime/sampler.cpp` 已使用实际 product IVibratorInterface，提供 read-only clock/token/sample，逐次 IsVibratorRunning 真实 RPC，MONOTONIC/REALTIME brackets，owned stop file，未调用 Start/Stop。旧 round21 getter 的基础功能已覆盖；当前 74 阶段主方案还有真实新 challenge PCM、VDI 安静/活跃边界及原签名/BMS/token/raw transport checks。

旧 coordinator 的独有重点是三个普通 UID：MEDIA owner（VIBRATE+KEEP_BACKGROUND_RUNNING）、VOICE_COMMUNICATION contender（mute haptics）、denied。它做真实 notification 授权/background task/source-bound callback、双 PCM 的 renderer forced BEGIN PAUSE/STOP 观测。当前 `audio_focus_runtime.py` 的 SCOPE 是 ordinary dual UID MIC/VOIP focus，不是该 AudioHaptic renderer 试验；当前 AudioHaptic phases 也无 contender。因此该候选不能作为“已经完全被 MIC focus 替代”丢弃。

但有至少三个不可直接接入的界面风险：

1. 旧 TOKEN_SOURCE 把 `HapTokenInfo.uid == actual uid` 当必要条件。当前 `hap_identity_binding.py` 明确该版本 HapTokenInfoParcel 不传 UID，UID 必须由原 BMS application/user account tuple 绑定，at_reported_uid 仅诊断。旧 helper/parser 如激活需整套迁移到当前真实 BMS/AT/进程身份证明，不能放宽任意返回或只用 argument echo。
2. 旧 coordinator 单独创建 EnclosingAcceptanceGuest，SDK/signature/helper 编译收据/QMP 调用仍是旧构造接口；它没有继承 root 当前 332/287 resource owner。保留文件不是资源准入。root 需审查 exact constructor/argv/log/Counter 与当前 source/image/helper 依赖，不能由 agent 启动或绕过 owner。
3. 原 no_onset_anchor 主动拒绝 supplied anchor，verify_observations 的 accepted/ledger/full gate 均 false，CLI run/verify 固定 return1。它仍缺流绑定的首次实际呈现帧到 MONOTONIC 映射；latency、Promise、文件增长和主机动作时间不能变成 onset。保留此限定，不把它串进全套“全 return0”的门槛，不修改为 pass。

旧 probe 使用 ACTIVE 纳秒安全整数协议；当前 probe 为 Date.now 毫秒 schema1，另外以 native sample brackets 校准。二者不是逐字段替换。当前 a0d RTC UTC/hilog 修复与严格新签名/typed proof 均保留。未来采用单调 caller 时间仍需版本化完整 producer/consumer/边界算术/SDK pins，不能重释旧222证据。

## Mesa：修复已经存在

core0021 的 atomic_write optional mode 与 SOURCE_SCRIPT mode=0755，当前 a0d 均保留；差别只有 mode 改为 keyword-only 及注释。当前测试从安装器 apply 端实际执行 action、重放修复被改回0644的已知文件，并拒绝 unknown bytes/保留0640；旧测试只是单独 atomic_write synthetic script。当前实现覆盖所需行为，无需再应用旧补丁或用旧测试替换当前更强测试。

## 父 agent 的具体操作边界

建议整合历史及独有候选后保留一个开发分支，活跃路径使用 a0d 当前更严格实现。保留旧候选来源不等于启用；若最终保留多个互斥安装器，需要在整合记录清晰标明只有 main_ui/calendar_owner 为 active，并把旧泛日历功能/AudioHaptic renderer focus/真正缺失的 GetEvents native 接线列入后续评估。若目标要求这些独有功能也必须立即启用，则必须逐项做正式 successor，不能直接覆写新版代码。

本审计没有做 Git merge/cherry-pick/commit/branch/worktree 修改，没有写 R/F/其他工作树，没有运行测试、候选、SDK/编译、crypto、Docker、VM、HDC 或 QMP。所有新增输出都只在本审计目录。原构建与行为失败继续是原事实；本包不计任何能力闭合。
