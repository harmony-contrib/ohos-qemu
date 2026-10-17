# Apps / Accessibility 本批交接

完成一组可独立审查的 Settings 生命周期源码修复，未核销能力账本。按原 apps 34 条逐项核对后，分类保持：

| 分类 | 条数 |
| --- | ---: |
| 已有修复待新包验收 | 11 |
| 仓库实现仍缺 | 18 |
| 真实外部后端/对端/数据待齐 | 2 |
| 待新运行结果定位 | 3 |

完整 34 条 ID、原分类、真实下一步和本批状态见 `result.json`。本批只改两个 Settings component、其 Apps fixtures/tests 与此目录；未改 Wallpaper、Calendar/calendardata、共享计划/runner/ledger、产品 BUILD/init/SELinux，也未接触 Docker/source/out、SDK 或 VM。

## 可审查源码批次

- `accessibility_service_completion/0002-*`：每个已排队通知 action 绑定 service 世代；销毁后未开始的 config/preference 操作不再执行，旧异步完成不续写本地 cache/event。重建不复用旧世代。保留真实四个 action、实际配置写、错误处理和原 framework service 生命周期。
- `share_picker/0002-*`：每次 session 创建有独立世代；旧 `loadContent` 延迟失败不能删掉、dispose 或 terminate 同对象重建后的新 controller。取消/销毁的列表查询在 await 返回后不再启动后续 label 查询。实际 caller 委托、BMS 再查、URI READ 和取消/重试结果契约保留。

先用新反例跑旧已提交候选，得到 9 个预期失败（`baseline-regression.log`）；修后 17 项 targeted host tests 通过，包含 service 14 场景、Share controller 22 场景、session 5 场景、MMS 5 回归场景和 8 项迁移/生成器测试。`host-tests.json` 记录完整命令与范围，`host-tests.log` 记录结果。测试使用 fixture 上实际应用后的源码，平台调用仍为 host doubles，未运行 SDK/HAP 编译或新包验收。

## Root 接线

对当前完整旧候选 source 快照，先独占 source lease 运行一次：

```sh
python3 ci/capability-audit/batch_apps_upgrade_settings_lifetimes.py --source-root /path/to/current/source
```

工具用原组件锁，先校验两个完整组件并在 scratch 验证 delta/new SHA，再只替换三个精确旧文件；未知/部分状态或 symlink 在源码写入前拒绝。精确旧 preimage 保留在 `fixtures/batch_apps/settings_lifetime_previous/`，三组旧/新 SHA 在 result 中。完整 Wallpaper 后继可迁移且保持原字节，缺 companion 拒绝。重复执行为 no-op。

这是现有已应用快照的一次性迁移工具。真正 fresh checkout 不需要它：按照既有 Settings prerequisite 顺序应用原 component 的两段 patch；Share 的 original 状态必须已完成 external_input 等原前置，不能把迁移工具无条件放在真正 pristine 源码之前。原 `0001` 保持原字节；原 manifest/module/Wallpaper SHA 均未改。现有 generator 也能精确再生成两段 Share patch 和保留后继 guard。

Root 再执行既有 prepare/最终源码验证、官方 SDK Settings 编译/签名、单个 ARM64 phone 新归档与完整运行验收。重点是真实四种无障碍通知 action、销毁/重建/在途成功和拒绝、真实 config-cache 同步；Share 普通 caller、文件授权正反例、旧/禁用目标、取消/退出、多 session、延迟页面错误和结果失败重试。首包 gate 仍未通过；不要由这些 host tests 启动剩余矩阵。

## 真实剩余

本批 service guard 不取消或回滚已发出的 native config 操作；该操作仍可实际完成。真实 cache/listener 重同步和安全 idle-stop 仍需实现方向与新包证明。不能以本批宣称整个无障碍 provider 完成。

Legacy `ACTION_CHOOSE` 仍经独立 `ShowPickerDialog` UIAbility 配置到缺失 provider；此次没有用 UIExtension 名称别名冒充实现。Share phone modal 的实际 BMS/普通 caller/URI 委托和其他画像验收仍缺。MMS UTD/附件与 Bluetooth HMS 协议也未实现。本批未减少请求能力或把空结果当成功。

其余仓库实现项、11 条已有修复待新包项和 3 条待定位项保留逐条后续任务。明确外部项仍为实际 cast peer 和合法电话归属/标记/骚扰/反诈数据服务；ASR/翻译/识别引擎与模型、HMS 分享后端来源也不能用空壳补齐。没有新增关闭项，也没有更改任何共享账本。
