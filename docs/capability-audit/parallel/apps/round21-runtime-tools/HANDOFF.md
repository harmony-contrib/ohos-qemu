# Apps 生命周期运行验收工具复核

冻结审查版本：`f40b63e5ee69f9e84021ad02be66d73bc1dbc0b9`。Root 已报告 Settings 完整实际 SDK HAP 编译成功，代表 03 正在 source prepare；本轮没有重新读取 SDK、source/out、HAP 或包，也未启动任何测试、Docker、VM 或重任务。只新增此目录的报告。

**现有工具没有这三个 race 的专用 guest runner。** 三个精确时序都已有 host 源码逻辑测试，但新包实际运行证明仍缺。Settings 导航、普通 ScreenBlink 成功、HAP 编译和 BMS 注册都不能代替它们。逐项来源、SHA、预置条件和命令见 `result.json`。

| 要验收的行为 | 已有精确覆盖 | 新包目前能直接覆盖什么 | 仍缺什么 |
| --- | --- | --- | --- |
| Settings service epoch：销毁后不启动旧排队动作、不续写旧完成 | `test_batch_apps_accessibility_service.py` 的 `destroy_before_dispatch`、`destroy_queued_success/rejection`、`recreate_epoch`；真实 patched class，config/preference/model/event 为 host doubles | 现有导航 runner 只调用十二种导航 API。真实通知 action、服务停止/重启可以手工验 smoke，但还没有该 driver | 真实授权/普通拒绝 caller 或通知 UI 编排、native config Promise 屏障、`onDestroy` 与 operation/世代观测、真实 config/preference/cache/event 读取 |
| Share 旧 `loadContent` reject 不得 dispose/delete/terminate 新 session | `extension.cjs:20` 的 `recreate_while_loading`：同一个模拟 JS session 对象先销毁再重建，最后 reject 旧 Promise | 有真实 Share UI 源码和稳定 UI ID；现有 generic builder 只请求空 payload。没有独立普通 Share caller/runner | loadContent pending/error 屏障、session wrapper/世代/controller ID、dispose/terminate 观测、native 是否复用同一 JS wrapper 的可达性证明 |
| Share 取消/销毁后不再继续旧 label 查询 | `controller.cjs:31` 开始的 `cancel_label`、`destroy_label`、`cancel_query_no_label`、`destroy_query_no_label`；双目标、Promise 屏障和调用计数均为 host doubles | 可实际点击 Cancel、观察取消结果/页面退出；当前工具不能把原生 query/label 停在指定点或计数后续 RPC | 至少两个真实匹配 receiver、原生 query/首 label 屏障、每个 controller 的调用计数与迟到 continuation 观测、独立同包证据 verifier |

## 现有 runner 的真实边界

- `run_settings_all_navigation_probe.py:122` 起，依次跑 `input/detail/network/display/mobile/refresh/sound/biometrics/about/nfc/app-detail/double-click` 两轮，采实际 provider、UID/PID、标题/像素、返回和普通 caller 清理。`build_settings_all_navigation_probe.py` 的 `CONTRACTS` 只有 `behavior:settings-navigation-provider-mismatch`；没有启动 `IgnoreRepeatClickExtService`，也没有 Share。
- `build_hap_probe.py:1216` 起，在 3 秒定时器中调用 `startAbilityByType('share', {}, callback)`，记录 invoked/start/error/callback。它没有非空 payload、独立 session nonce、取消 UI 控制、目标 receiver journal 或任何延迟/失败屏障；这段 generic 模板也不能自动当成普通 caller 证明。该 Promise resolve 只表示调用返回，不等于 page 成功、用户选择或正确结果。
- `parallel_runtime_suite.py:14` 的四个 family 是 `contacts-picker`、`wallpaper`、`external-inputs`、`knowledge-holiday`；没有这三个 Apps race。
- `verify_screen_blink_evidence.py:17` 只返回 `startBlinking/stopBlinking` 两个 export contract，scope 明写 `NOT_complete_lifecycle`；其像素、stop、caller exit/restart 实验不执行 Settings 服务队列或 Share 会话。`verify_gap_closure.py:1089` 起也按这些窄 contract 接收。
- `verify_settings_provider_image.py` 验实际 HAP/ABC、ABI、签名、预装、扩展类型及权限；服务保留 `ACCESS_SYSTEM_SETTINGS`，Share 保留 `sysPicker/share`/instance/export。报告明确 `provider_runtime_validated=False`。这属于运行前提。
- `guest_ui.py` 可复用真实 UITest hierarchy、按节点点击和 compositor 截图；它本身没有以上 fault injection 或 race verifier。Contacts 的 host native lifecycle/协议测试也只覆盖 Contacts，不能冒充 Settings/Share 原生测试。

## Root 现在可执行的命令

以下仅列命令，**本轮没有执行**。Host 命令可独立运行；任何 SDK/VM 命令须由 root 在代表 03 新归档完成后取得独占资源执行。

仓库根目录执行精确 host 时序测试，不访问 SDK/Docker：

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest \
  ci.capability-audit.test_batch_apps_accessibility_service.AccessibilityServiceCompletionTests.test_real_service_body_success_failures_queue_reentry_and_lifetime \
  ci.capability-audit.test_batch_apps_share_provider.ShareProviderTests.test_actual_picker_controller \
  ci.capability-audit.test_batch_apps_share_provider.ShareProviderTests.test_actual_extension_session_isolation_destroy_and_error_codes -v
```

前提是 Python 3 和提供 `node:module.stripTypeScriptTypes` 的 Node。三个方法合计 service 14、controller 22、extension 5 个场景，全部仍是 host 平台 doubles。单独复现旧加载失败的所有权断言：

```sh
node --unhandled-rejections=strict \
  ci/capability-audit/fixtures/batch_apps/share_provider/extension.cjs \
  ci/capability-audit/fixtures/batch_apps/share_provider/candidate/SharePickerExtension.ets \
  recreate_while_loading
```

现有完整新包 suite 的入口：

```sh
python3 ci/capability-audit/run_with_owned_hdc.py \
  --package-archive "$TASK_ARCHIVE" \
  --evidence-output "$TASK_OUT/full-suite.json"
```

前提：root 独占 VM/重资源；新归档完成，输出路径全新；设置真实 `HDC`、API 26 Release `QEMU_TEST_SDK_HOME`、`QEMU_TEST_HVIGOR_HOME`、`QEMU_TEST_NODE_HOME`、`DOCKER_SOURCE_VOLUME`、`QEMU_TEST_DOCKER_IMAGE`，以及 `QEMU_TEST_CLOCK_PROBE`、`QEMU_TEST_CLOCK_PROBE_BUILD`、完整 `QEMU_TEST_CAPABILITY_INPUTS`。wrapper 负责私有 HDC port/TMPDIR；不要另起 runner 竞争同一个 caller/VM。该 suite 的现有 pass 仍不能新增这三个 race 的结论。

若 root 已在自己持有的同一个新 ARM64 phone acceptance guest 中，仅重跑现有导航子项，可用：

```sh
python3 ci/capability-audit/run_settings_all_navigation_probe.py \
  --archive "$TASK_ARCHIVE" --sdk "$QEMU_TEST_SDK_HOME" \
  --arch arm64 --device phone --target "$TASK_TARGET" \
  --udid "$TASK_UDID" --boot-id "$TASK_BOOT_ID" --hdc "$HDC" \
  --output "$TASK_OUT/settings-navigation" \
  --hvigor-home "$QEMU_TEST_HVIGOR_HOME" --node-home "$QEMU_TEST_NODE_HOME" \
  --source-volume "$DOCKER_SOURCE_VOLUME" --docker-image "$QEMU_TEST_DOCKER_IMAGE"
```

`TASK_TARGET/UDID/BOOT_ID` 必须来自当前 root 所有的新包 boot 记录，并继承同一私有 HDC transport。该 runner 会替换/停止共享 audit caller，不能与其他普通 caller 任务并行。它验证导航基础和资源清理，不验证上述服务/Share race。

同一 guest 的注册/AMS 只读辅助快照可用下列现有命令；另存 archive SHA、boot ID、命令与退出码：

```sh
"$HDC" -t "$TASK_TARGET" shell "bm dump -n com.ohos.settings" > "$TASK_OUT/settings-bms.txt"
"$HDC" -t "$TASK_TARGET" shell "aa dump -a -u 100" > "$TASK_OUT/settings-ams.txt"
```

当前没有“再加几个现成 CLI 参数即可验证三个 race”的命令。不能把 shell 提权直接启动服务当成普通 caller 权限正例，也不应猜 `aa` 的 action/stop 参数后把未触发的分支算通过。

## 补齐实际验收所需的最小可观测性

**Settings 服务：** 用真实 AAMS 通知 action，或另行提供受控、实际签名且权限精确的 caller，分别验证 `disableIgnoreRepeatClick`、`disableNotificaiton`（保留上游拼写）、`reOpenTransitionAnimations`、`disableTransitionAnimationsNotification`。同时用普通无权限 caller 验拒绝。先保存真实配置/两个 secure preference，再选可区分的初态；所有 setter 都写 false/0，初态已经 false/0 会让旧代码的错误写入不可见。

精确 race 必须先观察第一个实际 config 调用已进入 pending；后两条 action 只排队；再观察同一 service 的真实 `onDestroy`；最后释放第一个 native completion，核对后两条 backend dispatch 为零、旧世代无 cache/event 续写，并验证新 lifetime 自己的请求和真实状态同步。允许销毁前已接受的 native config 操作实际完成，不能把它当成 patch 承诺取消/回滚的事务。

`onDisconnect` 没有使 epoch 失效；退出 Settings 页面也不证明服务被销毁。`aa force-stop com.ohos.settings` 会杀掉待验证的 JS continuation，不能证明同进程迟到回调安全。现有 LogUtil 只有 create/request/action/destroy，没有私有 generation、请求序号、enqueue/dispatch/backend operation ID；需要受控 native/framework 屏障和独立计数/真实状态、cache/event 观测。Host 的同对象 `onCreate` 重用还需单独确认 native 可达性。

**Share 旧 load reject：** 需要记录第一轮真实 session/controller/load operation pending，接着 destroy(old)、create(new)、旧 reject 的顺序，证明新 controller 没有 dispose、delete、terminate，且新 page/结果可继续使用。现有 Share 代码没有这些 operation/session/generation/counter 日志。Host 故意复用了**同一个 JS session 对象**；真实 native 是否这样复用尚无证据。只测两个不同 wrapper 的正常会话可以作为隔离回归，但不能声称命中了相同 Map key 的世代分支。

**Share 旧 label：** 至少两个实际 enabled/exported 且匹配 sendData MIME/URI 的唯一 UIAbility receiver。把 query 或第一个实际 getAbilityLabel 停在 pending；从真实 UI 按 `system-share-cancel` 或观察真实 session destroy/dispose；然后释放 pending，让 continuation 可观测地执行。label pending 变体后续调用总数应为 1，query pending 变体应为 0；receiver launch 必须为 0，仍存活 caller 的取消结果应为 `1/cancelled`。原生请求已经发出后无需被撤回。

只看页面退出、最终 targets 为空或没有新报错不够：旧代码原先已经保护最终列表发布，仍可能悄悄做额外 label RPC。只有一个 receiver 也不能区分“没有下一项”与“正确停止”。`SharePicker.aboutToDisappear` 只改变 view 的 active，不能代替 controller.dispose 的生命周期证据。

三个协议都需要 archive/HAP/source binding、boot、caller UID/token/PID、session/controller/lifetime/operation ID、单调序列、屏障进入与释放、backend dispatch/complete、结果和清理。可考虑经过验证的 native/framework 异步屏障或 debugger 机制，但本轮没有实现或授权接线。直接在 caller JS 构造 fake session 仍是 host/协议测试；改包内页面/DSO 或用另一份诊断 image 不得无声替换最终归档的验收对象。若 native 保证 context 销毁就不再执行 Promise continuation，应保留该可达性事实，按真实 native 语义与 host 对抗时序分别报告。

本轮结论为**覆盖缺口清单**：未新增 runner、未修生产代码、未运行测试、未关闭任何能力项。Root 可以继续当前完整构建；上述精确 race 的运行验收仍须保留未完成状态。
