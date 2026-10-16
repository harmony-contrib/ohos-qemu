# 音频双 UID HAP：通知授权与后台任务只读观测合同

这是一份固定源码合同，未执行 guest 命令、通知发布、授权点击或重任务。真源是只读 inspector `ohos-qemu-parallel-source-20261016-02:/ohos`。后台任务项目提交为 `ada26aa972cc85b94949a3abf2b1fc7053b19bb8`，通知项目提交为 `08a878a934511503bca88d3d69c686cc283c198c`。同名 JSON 保存 25 份文件的完整 SHA256、带行号边界的精确源码片段及可供 runner 使用的参数和字段合同。

## 服务命令与字段

以下是供父级执行的只读命令；本任务没有执行它们。把 `<实际HAP UID>` 换成通过真实运行身份取得的非负十进制 UID。

```text
hidumper -s 1903 -a "-C --get <实际HAP UID>"
hidumper -s 1903 -a "-C --all"
hidumper -s 3203 -a "--active"
```

后台任务 SA 为 `1903`，进程 `resource_schedule_service`，通知 SA 为 `3203`，进程 `foundation`。依据分别是 `sa_profile/1903.json` 与 `sa_profile/3203.json`，JSON 的 `bg_sa` / `ans_sa` 包含原文和哈希。

后台任务的真实分派在 `background_task_mgr/services/core/src/background_task_mgr_service.cpp:876–879`。连续任务的 `--get` 在 `bg_continuous_task_mgr.cpp:148,2576–2577`，未出现在该版本帮助文本里，但确由实现处理。`bg_continuous_task_dumper.cpp:73–116` 要求参数恰好为 `-C --get UID` 三项，输出：

- 每条由 `No.N` 开头，首行紧接两个 tab 和 `abilityName:`，随后为 `uid:`、`pid:`、`notificationId:`、`continuousTaskId:`、`abilityId:`、`backgroundModes:` 等字段。
- 空列表为 `No running continuous task\n`；参数错误原文为 `param invaild\n`。
- `--all` 额外包含 `bundleName:`、`suspendState:`、`backgroundMode:`、`notificationLabel:`、`userId:` 及组合通知字段，见 `bg_continuous_task_mgr.cpp:2586–2635`。
- `audioRecording` 的数值为 `3`，见 `interfaces/innerkits/include/background_mode.h:29`。模式向量打印带尾逗号；按整数解析，不能用字符串包含 `3`，否则会误匹配模式 `13`。批量 API 应检查 `backgroundModes` 中的 `3`，主字段 `backgroundMode` 只表示其中一个模式。

`GetAllContinuousTasksInner` 的默认参数是 `includeSuspended=true, exemptUid=false`，见 `bg_continuous_task_mgr.h:183–184`。因此 UID 查询存在记录不能证明任务未挂起。用 `(uid,pid,continuousTaskId)` 对齐 `--all`，核对 `suspendState: false`。双 UID 应分别取得快照，保留原始 stdout/stderr，不把另一个 UID 的记录算作本应用。

后台 Dump 还要求启动时读取的 `const.debuggable != 0` 和第一 token 的 `ohos.permission.DUMP`；manager 必须 ready。通知 Dump 由 `services/ans/BUILD.gn:308–310` 的 `build_variant == "root"` 决定是否编入，并在 `ShellDump` 限定 shell/native token。不能把未编入、权限失败或空错误输出当作真实无记录。

通知 hidumper 接口只接受一个参数 `--active`（别名 `-a`），不能追加 `--uid`。实现见 `advanced_notification_utils.cpp:1490–1529`。输出为：

```text
notification list:
No.N
    UserId: ...
    CreatePid: ...
    OwnerBundleName: ...
    OwnerUid: ...
    ReceiverUserId: ...
    DeliveryTime = ...
    Notification:
        Id: ...
        Label: ...
        SlotType = ...
```

精确 tab 和字段拼写见 JSON 的 `ans_dump`，这里只示结构。空列表原文为 `no notification\n`。这是专用 active 输出，不是 `NotificationRequest::Dump()` 的小写字段格式。`GetDumpInfo` 未检查 `ShellDump` 返回值，所以单独出现 `no notification` 仍需确认编译、token 与服务调用成功。

## UID 与通知关联

后台任务通知的 creator 是后台服务，owner 才是 HAP。`notification_tools.cpp:102,113` 明确执行 `SetCreatorUid(serviceUid)` 和 `SetOwnerUid(continuousTaskRecord->GetUid())`。成功发布后，任务记录保留实际 `notificationId` 与 `notificationLabel`，见同文件 `157–169`。

| 后台任务字段 | ANS active 字段 |
| --- | --- |
| `uid` | `OwnerUid` |
| `notificationId` | `Id` |
| `notificationLabel` | `Label` |

使用 `(OwnerUid,Id,Label)` 联合关联，不能只按 Id、数组序号、label 或通知 `CreatePid`。HAP 的实际 PID 取后台任务字段；服务代发通知的 CreatePid 可以是服务 PID。普通非 agent HAP 发布时，真实通知服务把 creator UID/PID 设为 IPC caller，默认 owner 设为 caller UID，见 `advanced_notification_service.cpp:242–255`；其普通通知还应对齐实际 OwnerBundleName 和已知 request Id。组合通知、subNotificationId 必须依 `--all` 的实际字段处理，不能预设一任务一通知。

## 授权弹窗与 selector

实际 bundle 为 `com.ohos.notificationdialog`，extension ability 为 `EnableNotificationDialog`，由 AppScope/app.json 与 entry/src/main/module.json 确认。phone 页面是 `pages/notificationDialog`，PC 页面是 `pages/pcNotificationDialog`。默认选 phone；`etc/notification/notification_config.json` 的实际配置可切换页面。源码检查 `deviceInfo.isPc !== undefined`，并非检查其值为 true，后续 isTv/isCar 定义还可能覆盖；应以客体实际配置及可见页面确认，不能仅按产品名称推断。

两页面标题都使用 `app.string.group_label_notification`，参数来自被请求应用的真实 bundle resource `label`，不是 bundleName 字符串。两页面按钮使用同一 `ALLOW` / `BAN` 资源：

| 资源 locale | 标题模板 | 允许 | 拒绝 |
| --- | --- | --- | --- |
| base / en_GB | Allow %s to send you notifications? | Allow | Deny |
| zh_CN | 允许“%s”向你发送通知？ | 允许 | 不允许 |
| zh_HK | 允許「%s」向你發送通知？ | 允許 | 不允許 |
| zh_TW | 允許「%s」傳送通知給您？ | 允許 | 不允許 |

英文实际是 `Deny`，不是 `Don't allow`。每个翻译文件的原始资源行与 SHA256 均在 JSON。phone 有横排及单行两组按钮，按可见性切换；没有单独稳定的按钮 id，phone 的容器源码 id 为 `mainWindow`。selector 应限制在本次应用标题对应的通知 dialog bundle 内，匹配可见且 enabled 的 Button 及当前 locale 的精确文本，要求唯一可见匹配，不按按钮序号选择。实际 UI hierarchy 本任务未观测，JSON 中 selector 是源合同，不是假装已验证的树节点。

phone `notificationDialog.ets:206–220` 与 PC `pcNotificationDialog.ets:209–223` 分别把拒绝/允许传为 `enableNotification(false/true)`。随后调用 `publishButtonClickedEvent`，发送 `OnNotificationServiceDialogClicked`，携带 `bundleName,bundleUid`；代码 0/1 分别表示 ALLOW_CLICKED / DENY_CLICKED。普通 HAP 的 bundle/UID 由 `onSessionCreate` 从系统 caller 参数复制，而服务订阅端限定发布方为上述 dialog bundle。

真实服务回调链为 `OnReceiveEvent -> OnBundleEnabledStatusChanged -> OnDialogButtonClicked -> SetNotificationsEnabledForSpecialBundle -> HandleOneDialogClosed`，精确片段在 JSON 的 `ui_entry` / `ui_callback`。其中设置授权失败只记日志，仍继续关闭回调，因此不能只凭弹窗消失或 callback 宣告授权成功。父级应随后用 HAP 自身的通知 enabled 只读查询、实际普通通知 active 记录，以及后台任务/ANS 联合记录验收。

本支援未更改源码、runner、策略、现有结果报告或账本；未核销音频、网络或新包运行门槛。
