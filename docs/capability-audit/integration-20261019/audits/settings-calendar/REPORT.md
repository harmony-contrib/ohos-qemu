# 应用候选整合审计 374

**结论：b8a4c1b 的28个新增路径确实未在a0d中；应保留到单一开发分支。Calendar 0b725ce 的两处修复已完整保留并由更新版本承接，应保留a0d文件。** 此次只读Git对象，不实施合并、删分支/工作区、运行测试或资源。

审计基准 `a0d62155747253f203952878594e21976c12a92c`。Settings候选 `b8a4c1b992c79acd5fcbfa42c579f3f96820a63f`；Calendar历史修复 `0b725cea695eafb56e0be47ea33cf30666130fbd`。逐文件29行及双方blob SHA见 `FILE_RECONCILIATION.json`，全部实际git show/diff argv/输出SHA及对象SHA见 `SOURCE_PINS.json`。

## Settings原功能确实遗漏

b8新增独立私有标准UIAbility `com.ohos.settings/PickerDialog`，三份ChoosePicker ETS、完整两项目9目标manifest/安装器/guard及host测试。native AMS/ DialogSessionManager桥保存原Want/caller token/requestCode，绑定实际provider UID/token/PID/UIAbility，重新查询真实handler，保留原结果/取消/死亡/十分钟deadline与URI授权链。它处理固定源码实际`ACTION_CHOOSE = ohos.want.action.select`；deprecated SDK `ohos.want.action.choose` 是另一路字面量。现有modal `startAbilityByType(share)`不是等价替代。

28个路径对`a0d:path`逐一git show均不存在。13个组件文件+1个host test属于待纳入候选，14个交接/原始host记录属于应保留的历史材料；将其纳入开发分支不等于候选已经接入实际产品。完整原字节diff在 `b8-unique-from-a0d.patch`。

### 整合后仍需明确处理的真实接线边界

1. b8的安装器锁定旧modal依赖：SharePickerController要求`656e4cdb...`而a0d guard最终是`7cbf03a9...`；SharePickerExtension要求`bc80e70c...`而当前是`2b7dc87f...`。`apply.py:125–128`会在写前拒绝。要新增准确完整组合状态，不得为通过旧安装器回滚当前生命周期修复。完整SHA在JSON。
2. 当前Share/WP guard只认识既有完整module/pages状态，不认识b8的`8bb80334...` module和`99ce1938...` pages后像。需要原guard验证完整9目标及精确依赖的后继组合；不能以一个新module哈希授权跳过全部旧组件。四个native真实前像尚需root完整vector核对，本审查未访问source/out。
3. b8没有修改shared build或system params；a0d build脚本也没有`share_picker_choose`调用。原交接要求后续设`const.system.sharePicker.bundleName=com.ohos.settings`与`abilityName=PickerDialog`并准确排顺序。保留候选后不要标已安装/已执行。
4. b8自己明确保留private-start源证明缺口：实际`SupportSystemAbilityPermission::IsSupportSaCallPermission`实现/header未取得，不能用native token/静态权限或shell显式启动代替普通caller真实正例。旧18方法host证据也不证明SDK/native CFI/完整TU/guest身份和URI边界。合并范围审计不为它补造通过。

## Calendar应保留更新版

`ci/capability-audit/batch_system_calendar_runtime_capture.py`：

- DSO label白名单表达式`re.sub([^A-Za-z0-9_-], -, name)`从0b保留至a0d第222行；同时完整DSO验证已升级为installed_runtime_profile、全部DT_NEEDED、runtime_guest_script与archive绑定的verify_guest_runtime_raw（第211–224行），不再接受plan指定旧guest_dsos。旧文件覆盖会丢失这些后续强化。
- `Collector.notification_click`整体AST在0b与a0d完全相同（只行号变化：377–417→451–491）；真实通知shade仅对LayoutNotReady/NodeNotReady重试，期限min(timeout,30)s，实际bundle/node/PNG/点击保持。没有遗漏此功能。

原0b diff与其到当前的差异分别保存为`calendar-original0b.diff`、`calendar-current-vs0b.diff`。对这个文件不需要再cherry-pick旧修改，也不能恢复旧整blob。

## 全路径归类

|路径|结论|
|---|---|
|`ci/capability-audit/test_batch_apps_share_picker_choose.py`|确实遗漏，纳入候选/历史；角色：host_regression|
|`docs/capability-audit/parallel/apps/round17-share-picker-choose/HANDOFF.md`|确实遗漏，纳入候选/历史；角色：historical_source_review_or_test_receipt|
|`docs/capability-audit/parallel/apps/round17-share-picker-choose/host-final-01.json`|确实遗漏，纳入候选/历史；角色：historical_source_review_or_test_receipt|
|`docs/capability-audit/parallel/apps/round17-share-picker-choose/host-final-01.stderr.log`|确实遗漏，纳入候选/历史；角色：historical_source_review_or_test_receipt|
|`docs/capability-audit/parallel/apps/round17-share-picker-choose/host-final-01.stdout.log`|确实遗漏，纳入候选/历史；角色：historical_source_review_or_test_receipt|
|`docs/capability-audit/parallel/apps/round17-share-picker-choose/host-final-02.json`|确实遗漏，纳入候选/历史；角色：historical_source_review_or_test_receipt|
|`docs/capability-audit/parallel/apps/round17-share-picker-choose/host-final-02.stderr.log`|确实遗漏，纳入候选/历史；角色：historical_source_review_or_test_receipt|
|`docs/capability-audit/parallel/apps/round17-share-picker-choose/host-final-02.stdout.log`|确实遗漏，纳入候选/历史；角色：historical_source_review_or_test_receipt|
|`docs/capability-audit/parallel/apps/round17-share-picker-choose/host-final-03.json`|确实遗漏，纳入候选/历史；角色：historical_source_review_or_test_receipt|
|`docs/capability-audit/parallel/apps/round17-share-picker-choose/host-final-03.stderr.log`|确实遗漏，纳入候选/历史；角色：historical_source_review_or_test_receipt|
|`docs/capability-audit/parallel/apps/round17-share-picker-choose/host-final-03.stdout.log`|确实遗漏，纳入候选/历史；角色：historical_source_review_or_test_receipt|
|`docs/capability-audit/parallel/apps/round17-share-picker-choose/private-start-chain.json`|确实遗漏，纳入候选/历史；角色：historical_source_review_or_test_receipt|
|`docs/capability-audit/parallel/apps/round17-share-picker-choose/result.json`|确实遗漏，纳入候选/历史；角色：historical_source_review_or_test_receipt|
|`docs/capability-audit/parallel/apps/round17-share-picker-choose/source-contract.json`|确实遗漏，纳入候选/历史；角色：historical_source_review_or_test_receipt|
|`docs/capability-audit/parallel/apps/round17-share-picker-choose/validation-history.json`|确实遗漏，纳入候选/历史；角色：historical_source_review_or_test_receipt|
|`patches/common/applications/standard/settings/share_picker_choose/0001-register-private-settings-picker.patch`|确实遗漏，纳入候选/历史；角色：component_source_or_support|
|`patches/common/applications/standard/settings/share_picker_choose/0002-authenticate-native-select-dialog-session.patch`|确实遗漏，纳入候选/历史；角色：component_source_or_support|
|`patches/common/applications/standard/settings/share_picker_choose/README.md`|确实遗漏，纳入候选/历史；角色：component_source_or_support|
|`patches/common/applications/standard/settings/share_picker_choose/apply.py`|确实遗漏，纳入候选/历史；角色：component_source_or_support|
|`patches/common/applications/standard/settings/share_picker_choose/apply.sh`|确实遗漏，纳入候选/历史；角色：component_source_or_support|
|`patches/common/applications/standard/settings/share_picker_choose/files/ChoosePicker.ets`|确实遗漏，纳入候选/历史；角色：component_source_or_support|
|`patches/common/applications/standard/settings/share_picker_choose/files/ChoosePickerAbility.ets`|确实遗漏，纳入候选/历史；角色：component_source_or_support|
|`patches/common/applications/standard/settings/share_picker_choose/files/ChoosePickerController.ets`|确实遗漏，纳入候选/历史；角色：component_source_or_support|
|`patches/common/applications/standard/settings/share_picker_choose/manifest.json`|确实遗漏，纳入候选/历史；角色：component_source_or_support|
|`patches/common/applications/standard/settings/share_picker_choose/tests/ability.cjs`|确实遗漏，纳入候选/历史；角色：component_source_or_support|
|`patches/common/applications/standard/settings/share_picker_choose/tests/controller.cjs`|确实遗漏，纳入候选/历史；角色：component_source_or_support|
|`patches/common/applications/standard/settings/share_picker_choose/tests/predecessor.json`|确实遗漏，纳入候选/历史；角色：component_source_or_support|
|`patches/common/applications/standard/settings/share_picker_choose/verify_source.py`|确实遗漏，纳入候选/历史；角色：component_source_or_support|
|`ci/capability-audit/batch_system_calendar_runtime_capture.py`|当前更新版本完整保留原两点，保留a0d|

此次所有写入仅本全新目录。没有修改MAIN/F/旧worktree或既有373/369/372目录，没有Git stage/commit/reset/checkout/cherry-pick/清理，也没有import候选、测试、SDK、crypto、编译、容器、VM/HDC或actual source/out操作。root可据此先集中整合候选与历史，再按独占流程补准确接线/验收；不以旧82销项数替代用户要求的补丁整合。
