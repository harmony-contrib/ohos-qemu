# Round375 — Settings select 后继源码与 host 交接

本批完成可审查的 private `PickerDialog` 后继组件，使用当前 Share 生命周期/WP 完整源码组合。**37 个 host 方法通过；没有执行 native 编译、SDK、签名、包或 guest，不能称 private-start/URI/行为验收通过。34 项没有新增正式销项。** 组件与下列 host 源码现冻结，root 可接共享 build/native 审查。

## 实际来源与实现

根的 `r60-source-vector-375-01` sealed source 与本组件 **全部 6 个已有目标前像、18 个不可变依赖，共 24 文件**逐字节 SHA 相等；另 3 个新 ETS 目标按 manifest 应不存在。host mirror 的不同内容没有用来替代实际前像。两 project 固定 HEAD、文件路径/前后 SHA、实际导出 receipt 与每文件 pin 见 `source-pins.json`。该证据仍仅 RO 源码观测。

原 `0001` / `0002` 和三个 ETS payload 保持原字节；旧 manifest/fixture 分别保存在 `historical-v1.json`、`tests/predecessor-v1.json`，没有改写历史。新 `0003` 是精确完整原二 patch native 后像的后继，涉及 AMS/DSM 两个 cpp/header。最终组件 manifest SHA：

`4fc97612896fca6de7cd014ce5ea1707055a071af542660176b77e9b43f13bde`

新 0003 SHA：`8010353f8b2b123a945388519e3e68ec4f517e6b915df41c96417997f047524b`。

真实 `SupportSystemAbilityPermission` 不含 foundation UID 5523，原 `IN_PROCESS_CALL` 不能单独证明 private PAGE start 获准。新路径只在同步 native 栈作用域内持有真实原始 `AbilityRequest` 与 SID；TLS RAII 退出复位，禁止复用/重入，要求 self PID/UID/token 和 native foundation token。DSM 再核对已存 caller token/requestCode/accessToken/user、实时 caller record、完整 BMS provider bundle/module/ability/UID/token、PAGE/private/system/enabled 及未绑定/未提交/未超时/非 busy 状态；一次 admission 后才能绑定真实 UI token/PID。没有修改通用 SA 白名单或加入外部 Want 放行字段。

最终复核发现：真实普通 `StartAbilityInner` 在 PAGE 权限调用**之后**才赋 `AbilityRequest.userId`，而 `GenerateAbilityRequest` 不填它。新 0003 将实际 wrapper 的 `oriValidUserId` 显式透传三层 PAGE helper；其他入口默认 -1，拒绝 admission。host 正例刻意保留 target.userId=-1，分别拒绝缺失/错 requested user，防止 host fixture 先填 100 掩盖真实正常路径失败。仍须 root 实际 native/SDK/新包确认此调用链。

保留普通 caller/目标权限、原 URI/flags、真实结果 requestCode、取消/死亡/十分钟 timeout 和 UI 实例隔离；host 检查不能证明真实 IPC/锁/CFI/调度行为。

## Installer 与组合拒绝

只接受完整 CURRENT before 或 CURRENT after；所有当前 Share/WP 文件精确不可变。source symlink/hardlink、非 canonical 根、混合/部分/未知修改与旧 modal 向量均拒绝。

事务保留所有 target/dependency 的 bytes、mode、inode/link/parent identity，在 prepare 后及每次写前完整复检。`atomic_write` 返回真实 publication identity；只有实际发布且仍属本事务的文件才能回滚。未写文件的外部编辑、已写文件的外部新值均保留；后者留下 recovery originals/manifest 并明确失败。只对自建 scratch 使用 Git discovery ceiling，避免 TMPDIR 落在仓库内导致 patch 被静默过滤。

root 已修改 Share/WP 两 guard；最终 host06 实际读取它们，正常完整 after 通过，逐个破坏 9 targets + 18 dependencies 均拒绝。外部输入 guard 的**一文件增量**待 root 应用：

`.tmp/parallel-capability-20261016/round375-apps/external-input-guard-integration.patch`

必须先验证完整 chooser，再继续验证 external_input 自己两份独有 ETS；不能凭 module SHA 提前成功。旧 `superseded-three-guard-proposal.patch` 仅为此前提案，**不要应用**。

## Host 结果与复跑

最终 `host-06`：20 methods / 9.068s / OK；最终 `legacy-host-02`：17 methods / 7.333s / OK。原回归包含 22 controller 与 5 ability 子场景；旧测试仅两处 fault wrapper 增加 `return original_write(*args)`，保留故障与事务断言。新检查含正常/双重重放、所有混合/未知依赖、same-bytes inode/link/symlink/chmod 变化、发布后外部编辑保护、精确 publication identity，以及提取真实 C++ 布尔谓词的 host 反例和调用顺序静态检查。提取谓词使用显式 Node 平台值 double，**没有运行 C++ 或真实 native IPC**。

在 `ci/capability-audit` 目录执行：

```sh
python3 -B -m unittest -v test_batch_apps_select375_composition test_batch_apps_select375_native_scope
```

原 17 项纯 host 回归：

```sh
python3 -B -c 'import unittest, test_batch_apps_share_picker_choose as m; excluded={"test_official_sdk_imports_and_source_uses_no_fake_result_or_settings_grant", "test_private_standard_ability_preserves_entire_existing_module_and_pages"}; tests=unittest.defaultTestLoader.loadTestsFromTestCase(m.ChooseSourceTests); selected=unittest.TestSuite(t for t in tests if t._testMethodName not in excluded); result=unittest.TextTestRunner(verbosity=2).run(selected); raise SystemExit(not result.wasSuccessful())'
```

上述排除的两项分别会读取 SDK declarations、SDK 工具内 JSON5；本 agent 无 SDK 执行权，root 后续实际 SDK 验收时应完整运行。中途 host02 的一个 C++ string host adapter 错误、host04 的 git HEAD host double 漏项已修正；失败原日志保留，未改写为 PASS。全部日志路径/哈希见 `host-results.json`。

## Root 接入与历史状态

精确请求见 `root-integration-requests.json`。建议顺序：原 Settings providers/external_input → **CURRENT Share lifetime → WP → chooser**；再用完整 chooser after guard 接 root 的原子 `settings_select` 参数 pair。root 报告该参数组件与 6 host tests 已完成；此处没有代跑。参数必须为 `com.ohos.settings / PickerDialog`。

当前实际 r60 卷是 chooser 完整 before，**不需要旧 v1 upgrade**。当前 installer 不接受真正的旧 v1 after，也没有提供自动历史 restore。若未来遇到这种卷，必须先停 prepare，验证历史全部 9 目标和旧完整依赖后独立事务恢复历史精确前像；随后升级 Share/WP，再 current chooser。禁止把旧状态直接标记新版本、重放 0001/0002、无条件 git checkout 或覆盖未知修改。

root 仍需接 compiled private ability/page/source/HAP/image guard，真实 AMS/DSM TU/CFI、SDK105 Settings HAP/系统签名，再对第一个新包执行普通 caller 真实 select/目标消费 URI/结果/取消/直接 private start 拒绝、伪 SID/caller/token/UID/user/provider、已绑定/提交 SID、回调重入、并发/死亡/超时及旧 Share/WP 回归。固定 native action 是 `ohos.want.action.select`；deprecated `ohos.want.action.choose` 不会被本实现静默改写。

## 六个完整 provider 缺项与下一批

`provider-dependencies.json` 按 6 个精确 ID 列出实际产品名/authority/plugin 路径、协议/模型/合法数据缺口。ScreenReader、Caption、DesktopLyric、number identity、expanded menu、三类 text-service plugin 的完整实现均未由本 chooser 交付或关闭。不能用空 ability/空库/固定内容代替真实行为。34 项计数只引用373历史分类，本批没有重新宣称全部34实现完整。

root 已授权后继独立 caller preparation lease：`fixtures/batch_apps/select375/**` + 新 `batch_apps_select375_*`。该批将在本批冻结后另行恢复，提供真正普通 caller + 两 target 的 SDK105 project/challenge/source manifests：真实 file URI 所有者读写、选择后的被授予/外来读取拒绝、结果/取消、直接 private start 拒绝。**当前交接不包含已完成的专用 SDK producer/guest runner，也没有其编译/运行成功证据。** 不复用旧 HAP 重新 hash 冒充新 fixture。

完整源码增量含 pre/post SHA 见 `source-changes.json`；可审查统一 diff 为 H/round375-apps/review-component-and-host.patch（只包含本 agent 12 个变更文件，root shared edits 排除）。不需要 root 应用该 diff 到 MAIN；获准源码已在 MAIN，由 root 统一提交。未 stage/commit，未创建 branch/worktree，未接触 source/out 或任何重资源。交接后本批写租约释放。
