# 普通 Contacts 调用方交接

本批只新增两脚本和六个 fixture。没有新增上游产品目标，没有改前批五文件
ContactsData 协议补丁或已冻结的 Contacts/Theme 业务、metadata、共享 suite。
真实 SDK39、签名、安装、种子、QEMU、UI 输入和总门禁由 root 统一执行。
本批未编译 HAP，不能把本工具的源代码或 host 合成正例作为运行证明。

## 准备和调用

运行：

```sh
python3 ci/capability-audit/batch_apps_contact_picker_runtime.py prepare \
  --output-dir <尚不存在的私有绝对目录>
```

输出普通 Stage 模型 HAP 项目、确定性的 metadata 和
`caller-source-manifest.json`。使用现有完整 Linux API26 SDK39 runner 构建；
fixture 没有第三方依赖，不需要 OHPM 网络下载。生成器不运行构建，不填签名。
root 必须给 `com.ohos.qemu.contactpickercaller` 使用 APL normal、非
`hos_system_app`、零 ACL/受限权限的真实有效 profile；实际 BMS/token 校验仍必需。

通过普通 `EntryAbility` Want 传入以下参数，显示界面后点击
`contact_case_start`。`onNewWant` 只加载新配置，不自动调用 API。

| 参数 | 类型和含义 |
| --- | --- |
| `runId` | `[A-Za-z0-9_-]{1,64}`，本次新包运行的唯一 nonce；也写入实际种子姓名。 |
| `launchId` | 同样的字符限制；跨重启也不能重复。 |
| `caseId` | 六文件中的 `case-matrix.json` 的 ID。 |
| `seedIds` | JSON 字符串，真实独立读回的联系人数字 ID 数组；完整矩阵至少 205 个。 |
| `queryKey` | `query-no-read` 使用的真实种子 lookup key；其他用例可空。 |

HAP 在自己的 `filesDir/contact-picker-{runId}.jsonl` 逐行同步追加原始
Observation。公开返回值直接 JSON 序列化，不按种子补齐，不转换 bare-number
错误，不自行判断 PASS。回调重复、旧请求在新配置之后返回、page dispose 后返回
均保留原 invocation ID；UI 只更新当前 launch。180 秒 observer 只写观察到的
超时事件，不伪造 API 失败或成功。长 deadline 用例观察期限 660 秒。
dispose 会清理自己的 observer timers；公开 API 没有取消方法，不冒充取消完成。

## 用例操作

必需 15 用例、16 个 invocation，覆盖四种 `selectContacts` 与两种旧
`selectContact` 重载、两个 205 条完整往返、无默认取消、有默认且修改后取消、
同步参数错误、真正 provider 的异步错误、无读权限查询、重叠 session、退出重启。
六个单选用例通过 UI 选中的具体种子偏移在 matrix 中列明。

`options-*-205` 仅把真实 205 个 ID 构造成公开过滤/默认选中选项，必须看到实际
`selectedText` 为 205 并点击真 `doneButton`。独立 verifier 比较所有真实
ID/key/name/phoneNumbers，100 条部分结果、重复 ID 和跨 session 结果均失败。
没有向 HAP 传任何预期 Contact 记录。

`cancel-default` 默认前三个种子，真实 UI 先取消第 0 个、选择第 3 个，再通过
真取消按钮退出；结果仍应是原始三个默认联系人。`cancel-empty` 应返回空数组。
`invalid-limit-*` 期待同步 BusinessError 401，不启动 provider；
`invalid-filter-callback` 以类型化但非法枚举 999 进入真实 provider，必须返回
BusinessError 401 callback；不能只用 JS 参数错误替代 native/provider 错误。
`query-no-read` 必须得到 201，任何成功读取均失败。

`dual-session` 在同一 JS turn 发起 A Promise 和 B callback，两项 begin 都必须
先于任何结果；真实 UI 分别完成两个 modal，返回不同的实际种子集合。
`exit-pending` 在 picker 可见后由 root force-stop 普通 caller；可无终态或只返回
退出引起的真实 BusinessError。记录 AppMgr 中旧 PID、退出后无进程、重启后新 PID。
`reopen` 使用新 launch，返回其自己的种子。不能把 caller 内部 UI 状态或根本未
真正停止的进程当作重启证明。

`deadline` 和 `navigation-dismiss` 是明确列出的可选诊断，不默认为已过。
若确实运行，它们的失败也会由默认 verifier 报出。deadline 必须实际等待 native
600–660 秒内终态；不允许立即模拟 timeout。navigation 的源码配置仅已接线，
真实路由/后台效果仍需 root 验证。所有用例均不核销能力账本。

## 输入证据 JSON 合同

所有 artifact descriptor 为 `{"path":"实际绝对文件路径","sha256":"64位小写十六进制"}`。
脚本读取文件并重算 SHA，不接受只有路径或只有 PASS 标志。下面字段必须来自
root 的独立采集；示例字段说明不是可复制为通过的结果。

`build.json`：

- `run_id`、`architecture: "arm64"`、`device_profile: "phone"`。
- `representative_package`、`caller_hap`、`provider_hap` 三个 artifact。
- `booted_package_sha256` 必须等于该实际新代表包 SHA，`boot_session_id` 非空。
- `caller_fixture_hashes` 为六个 fixture 的文件名→SHA 字典，必须与本批实际文件一致。
- `caller_source_manifest` 是 prepare 产出的实际 source manifest artifact。

`identity.json`：

- `run_id`、`hap_sha256` 与实际构建 caller HAP 匹配；
  `installed_caller_hap` 必须是设备安装目录取回的 HAP artifact，SHA 相同。
- `bms_dump` 为实际 `bm dump` JSON（可有文字前缀）artifact。其 applicationInfo
  必须实际包含匹配的 `bundleName`、`isSystemApp:false`、`appPrivilegeLevel:"normal"`
  （或 `apl`）、数字 `uid`、`accessTokenId`。单独的 source 声明不算证明。
- `permission_probe` 为实际独立 root AccessToken API 原始结果 artifact：
  `api` 为 `abilityAccessCtrl.verifyAccessToken`/`verifyAccessTokenSync` 或
  `AccessTokenKit::VerifyAccessToken`；`token_id` 匹配 BMS，`READ_CONTACTS` 和
  `WRITE_CONTACTS` 都是实际 -1。不能以 profile 不声明权限替代 token 检查。
- `decoded_profile` 为实际已签 HAP 的 profile 导出 JSON artifact；`bundle-info`
  要匹配 bundle/APL normal/非 hos_system_app，不能含 allowed-acls 或 restricted-permissions。
- `signature_verification` 为 root 实际 signer `verify-app` 命令的结果 artifact，含
  `command` argv、`exit_code:0`、`hap_sha256`、`decoded_profile_sha256`。
  本脚本核对关联和原始文件；密码学验签由 root 专用签名工具完成，不能伪写该报告。

`seed.json`：

- `run_id`、`create_api` (`contact.addContact` 或 `contact.addContacts`)、
  `read_api` (`contact.queryContact` 或 `contact.queryContacts`)。
- `contacts` 是公开 API 独立读回的至少 205 个真实完整 Contact，ID/key 唯一，
  `name.fullName` 含 runId nonce，电话号码非空。该顺序也用于传给 HAP 的 seedIds。
- `raw_create` artifact JSON 含 `run_id`、`api`、真实返回的 `ids`，没有 error。
- `raw_readback` artifact JSON 含 `run_id`、`api`、实际 `contacts`，与 ledger 完全一致，
  没有 error。不能直接写 DB、用预期输入替代读回或把失败转换成空结果。

`cleanup.json`：

- 同 run_id，`delete_api:"contact.deleteContact"`，`read_api` 为上述查询之一。
- `deleted_keys` 恰好等于种子 key 集，`remaining_contacts:[]`。
- `raw_delete` artifact JSON 含 run_id/api/真实删除调用的 keys，无 error。
- `raw_readback` artifact JSON 含 run_id/api/实际 contacts:[]，无 error。
  这是确认清理后的真实公共读取，不能用删除调用成功日志代替。

`ui.json`：

- 同 `run_id` 和 build 中的 `boot_session_id`，`events` 每项带准确 `invocation_id`
  (`launchId/a` 或 `launchId/b`)。
- 每 invocation 恰好一个 `caller_start`：实际普通 caller 界面的 `layout`、
  `screenshot` artifact；layout 含 bundleName 和 `contact_case_start`。
- 有 UI 的用例要记录真实 `picker_visible`、终结输入 `done`/`cancel`/`force_stop`
  （可选诊断为 `home`/`deadline_wait`）。终结输入项包含实际 provider 的 `layout`、
  `screenshot`、真实被点击的 `node_id`。Done 必须 doneButton，Cancel 可为固定
  源码对应的 close_click_btn/Settings_close_btn/contactList_contacts_back_arrowBack。
- 终结输入前通过 HDC 取回当时原始 `journal_before` artifact；它必须是最终原始
  journal 的字节前缀，包含本 invocation 的 begin，尚无其任何终态。
  因而“API 先返回固定成功，之后再点界面”的做法会失败。
- `picker_absent` 包含退出后的真实 `layout`、`screenshot` artifact，layout 不能仍
  可见 provider。该可见性证明不等于隐藏 native 资源全面无泄漏，root 继续做自己的
  WMS/ability/session 边界检查。
- 205 用例终结 layout 的 `selectedText` 节点必须显示 205。
- cancel-default 还要记录 `unselect` 第 0 个种子和 `select` 第 3 个种子的真实输入，
  每项含 contact_id 及当时实际 layout（可见对应种子全名）。
- invalid-filter-callback 需要 `provider_launch`，其中 `raw_log` artifact 含实际
  com.ohos.contacts 和 ContactUiExtentionAbility 启动证据。
- `caller_processes` 为 before_exit/after_exit/after_reopen 三个 artifact；每个原始
  JSON 含 `api:"appManager.getRunningProcessInformation"`、真实 `processes` 数组，
  数组元素含 pid/bundleNames。退出后该 bundle 无进程，重启 PID 必须不同。

layout 接受实际 UITest JSON 的嵌套 attributes/children（递归读取 id/text/bundleName）；
截图支持 PNG 或 QEMU PPM。若真实工具输出不同字段，应先保留实际输出并做窄格式
适配，不能生成含预期节点的替代布局来通过。

## 独立核验和交付边界

```sh
python3 ci/capability-audit/batch_apps_contact_picker_runtime.py verify \
  --journal <设备取回的原始jsonl> --seed <seed.json> --cleanup <cleanup.json> \
  --ui <ui.json> --identity <identity.json> --build <build.json> --output <report.json>
```

可以用 `--case <id>` 做单项诊断；输出明确标记 one_case_only。默认核验所有必需
用例以及已经运行的可选用例。缺证据、重复重跑混在同一 run、未知 invocation、
observer 超时、错误数据/回调/权限/包身份均失败。旧失败证据不能被追加一次新成功
覆盖，重跑需新 runId 并保留旧证据。

即使原始结果全部匹配，输出也始终 `ledger_closed:false` 和
`first_artifact_behavior_gate_passed:false`。root 负责密码学验签、实际安装来源、
资源/服务重启、整套能力行为、代表包第一次完整验收门；本脚本不替代共享 suite。
本次 8 项主机检查包含真实提取 recorder 类的适配测试和明确合成的 verifier
正反例。它们不是 HAP 编译或运行证明。
