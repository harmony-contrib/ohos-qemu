# API26 前台定位授权：固定文本与运行时合同

本批仅文档，只读固定PermissionManager/locale源码和当时的混合staged参数。没有操作guest、HDC、编译、签名、权限或wrapper。**全部 `/ohos` 和活动out读取已结束，读租约已向root释放；后续不再访问这些路径。** root决定首包data-only配置使用下值，不新增auto机制：

```json
{"permission_allow_text": "仅使用期间允许"}
```

这有固定源码依据，不是已经在首个新guest观测的标签。实际GuestUi exact/unique/visible/enabled/clickable检查及普通权限回调仍须通过。

## 真正的按钮合同

`applications/standard/permission_manager/permissionmanager/src/main/ets/common/permissionGroupManager/LocationStrategy.ets:47–48` 返回：

```text
ALLOW_ONLY_DURING_USE, ALLOW_THIS_TIME, CANCEL
```

`common/model/permissionGroup.ets:117–123` 映射首项到 **app.string.allowed_only_during_use**。`ButtonStatus.ALLOW_ONLY_DURING_USE`是业务内部enum；资源名是编译资源标识，**两者均不是UITest node id**。

| 资源目录 | foreground允许 | 一次性允许 | 取消 |
| --- | --- | --- | --- |
| base / en_GB | Allow while using the app | Allow this time only | Cancel |
| zh_CN | 仅使用期间允许 | 允许本次使用 | 取消 |
| zh_HK / zh_TW | 僅使用期間允許 | 允許本次使用 | 取消 |

普通`Allow`/`允许`虽存在于app.string.allow，但LocationStrategy这个buttonList没有ALLOW项，因此不能填这个泛化文本。

`ServiceExtAbility/GrantDialogModel.ets:225–247` 创建TYPE_DIALOG，载入`pages/dialogPlus`；ServiceExtAbility:55的窗口名`permissionDialog<startId>`包含动态编号。`pages/dialogPlus.ets:155–203` 从buttonList动态生成Button；location的3按钮走vertical ForEach。Button没有显式`.id(...)`、`.key(...)`或专用稳定语义identifier。全ETS扫描结果和数量见`fixed-source.json`：仅另外的OpenSettingDialog有`qemu_manual_permission_allow/deny`，其文本为Allow/Cancel，属于手动权限设置能力，不能用于此次普通requestPermissionsFromUser前台定位授权。

当前capture报告中`identifier='real-location-consent'`也是orchestrator写的逻辑标签，不是PermissionManager源里的UI组件id。实际UI身份应看保存的`selected_node.attributes`与layout。

## 默认locale来源与限制

固定 `base/global/i18n/frameworks/intl/etc/i18n.para:13–20`：persist.global.language/locale为空，const.global.language=zh-Hans、const.global.locale=zh-Hans-CN。当时只读 `out/arm64_virt/packages/phone/system/etc/param/i18n.para` 对应值相同；混合staging不能当成新system.img或新guest的证明。

`locale_config.cpp:64–70,465–490`的真实优先级是：

1. `GetEffectiveLocale`先读`persist.global.locale`，非空即返回。
2. 再读`const.global.locale`；仍为空则回退`zh-Hans-CN`。
3. language相应优先persist.global.language、再const.global.language、再zh-Hans。
4. `GetSystemLocale:522–529`会去掉扩展参数；不是固定英文。

因此一个没有持久化语言覆盖的干净默认中文包使用zh_CN资源有依据。持久化用户/资源配置或实际打包内容可能不同，首新guest尚未观测；若实际树不含这个精确标签，必须失败或保留诊断，不能自动改语言、乱点索引或放宽成Allow。

## 现有wrapper已足够处理显式文本

root当前`batch_system_live_inputs_suite.py`将artifacts.permission_allow_text传给capture；`batch_system_run_live_inputs.py:220–233`先点自有`live-permissions`，随后调用：

```text
GuestUi.click('com.ohos.permissionmanager', text=permission_allow_text,
              label='actual-location-consent')
```

`guest_ui.py`实读UITest layout并保存，`select_node`要求指定bundle、精确text、唯一可见节点，且enabled/clickable为true、bounds有效；点击用这个实际节点的中心，不是猜测坐标。UI树/label未出现不会被当成已授权。

普通caller真实调用 `requestPermissionsFromUser`，只请求APPROXIMATELY_LOCATION与LOCATION；`batch_system_verify_live_inputs.py:214–216`仍严格要求这两项且authResults=[0,0]。签名、normal APL、空ACL、UID和输入协议边界未变。`GrantDialogModel:382–405`将ALLOW_THIS_TIME列为临时flag，而foreground允许走普通PERMISSION_FLAG；LocationStrategy:85–92仅当实际precise状态启用才授LOCATION，不能以一次模糊授权冒充两项成功。

当前runner的ui_actions保留layout，但严格验收器没有独立重算这次consent节点。它通过实际API返回和normal身份验证权限结果；若root将来需要把“点中了哪一个foreground按钮”也提升为独立离线门禁，应重新核layout SHA、可信bundle、实际text与visible/enabled/clickable唯一性，并绑定当前caller标题。当前自有HAP生成的AppScope label为`Live input audit`；permission标题源为`group_label_location`（或实际fuzzy/upgrade分支），不能伪造固定新id。本批没有扩大或修改此验收范围。

root已经选择**不新增auto**。如果将来重提auto，固定源没有可直接使用的稳定id；只能先证明实际树及资源语义，或另行授权真正产品dialog id改动并重新构建。不能把内部enum、资源key或逻辑报告identifier冒充实际UI id。

## 保存证据与未完成项

- `fixed-source.json`：11份实际源码/当时staging文件SHA、原始行号片段；5套语言资源SHA和实际条目；全ETS显式id/key扫描结果。
- `source-query.py.txt`：本次有界只读查询原文；没有GN/Ninja/guest操作。
- `repository-inputs.json`：当时读取的6份现有工具/fixture SHA和读取时间。
- `result.json`：明确数据配置、读租约释放、未观察的新guest边界和轻量一致性检查。

没有新guest实际UI标签、没有新permission callback结果；first_artifact_behavior_gate_passed仍false，0核销。后续真实树和签名/normal权限结果必须留在同一新包/boot证据中。
