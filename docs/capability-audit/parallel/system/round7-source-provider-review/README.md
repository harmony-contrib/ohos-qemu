# MMS source provider 与 Settings 叠加栈只读审查

审查基点：主树 `e51e3fed3cabcaf605db46f46eb31962fa4a1150`。
本批只增加此目录中的报告、固定源码证据和最小 host 复现；不改 root/vendor/apps
代码，不编译、签名或创建镜像，不占用重型租约，不启动新容器。

确认并立即上报主 agent 的两个验收问题：

1. **实际镜像的 MMS 预装选择没有检查。**
   `verify_mms_provider_image.py` 的 image 分支只提取 HAP、capability、permissions；
   `mms_provider.verify` 检查的 `install_list.json` 却来自 source root。
   保留 HAP 与授权文件、删掉镜像中的 MMS 预装条目不会被该分支检测。
   固定 BMS 在 `ParsePreBundleProFile` 中读取实际配置，在
   `GetPreInstallDirFromLoadProFile` / `OnBundleBootStart` 中按该列表选择应用。
   当前 ARM64 `libbms.ninja` 确实启用 `USE_PRE_BUNDLE_PROFILE`。
   这项判断来自真实控制流和固定源码，没有用替代签名或假镜像制造 PASS。

2. **字典相等不是严格 JSON 类型比较。**
   实际 e51 `policy` 接受 `singleton:1`、`keepAlive:0` 和
   `permissions[].userCancellable:0/1`；预装选择比较也接受 `removable:0`。
   本地直接调用真实函数及执行其原始预装判断表达式均复现了该问题。
   固定 BMS `BMSJsonUtil::GetBoolValueIfFindKey` 明确检查 `is_boolean()`，
   类型错误会使 `PreBundleProfile` 的预装解析跳过该条目，不能按 Python
   `0 == False` 的结果放行。

主 agent 已接手两项：镜像分支提取唯一实际 `install_list.json` 并检查原 MMS 行；
用递归 `same_json` 检查类型及值，并增加数字代替布尔值的负向用例。
`root-followup-observation.json` 记录只读观察到的修复文件哈希和相关代码行。
实际签名、真实 ext4 正负用例及其通过结论由主 agent 运行与归档；本报告不代判通过。

e51 还有主 agent 自查并修复的 `certificates` 局部 lambda 作用域问题：
`prepare.verify` 从模块层查找该名称会产生 `NameError`。
主 agent 已将其提升为模块函数。本批按已知修复记录，没有重复修改或归为新发现。

本批通过的有界 host 检查：

- 从只读固定源码 Git 对象提取18个原始文件，记录项目 revision、原始字节与SHA256。
- Settings `source_provider → accessibility_service_completion → external_input →
  input_2in1_navigation → refresh_rate_page → share_picker` 连续三轮应用通过。
  MMS source/send_data_text 以及 HAP calendar/photos/settings/admin/mms 选择栈
  在同三轮中通过。最终文件哈希完整保存。
- 缺失或未知 `SharePicker.ets` 后重放 external_input 被拒绝，所有输入文件保持原样。
- 真实原 MMS CMS 由 OpenSSL 验签，确认原 normal/hos_system_app/os_integration
  身份和 profile SHA。`desired_profile` 仅替换现有 OS application leaf 与有限 expiry；
  其余原 profile/ACL/permissions 字段保留，既有两份授权行重绑定可幂等重放。
- 固定 GN `app.gni` 确实将 `certificate_profile` 传入签名 action，
  `app_internal.gni` 和 `app_sign.py` 使用真实 `-profileFile/-appCertFile/-keyAlias`
  等 CLI 输入；真实 SignProfileParameters/Options 接受所用 profile 签名参数。
  四个签名输入哈希与 MMS pin 一致。这里只读核对规则，没有执行 signer。
- full source phone/2in1 打包分支已接入一次实际 MMS 镜像检查，未发现另外的已复现接线阻断。

重放命令：

```sh
LC_ALL=C LC_CTYPE=C LANG=C PYTHONDONTWRITEBYTECODE=1 python3 \
  docs/capability-audit/parallel/system/round7-source-provider-review/review_replay.py \
  --repository /path/to/ohos-qemu
LC_ALL=C LC_CTYPE=C LANG=C PYTHONDONTWRITEBYTECODE=1 python3 \
  docs/capability-audit/parallel/system/round7-source-provider-review/boolean_boundary.py \
  --repository /path/to/ohos-qemu
```

第一次审查重放因报告 scratch 位于 Git worktree 内，Git 向上发现父仓库并跳过
源目录之外的 diff，出现缺少 BUILD.gn 的测试环境错误。只给复现子进程设置
`GIT_CEILING_DIRECTORIES` 后恢复产品临时目录通常具有的无父仓库行为，整栈通过；
该环境记录在 `replay-setup-note.json`，未改产品 applicator。

本批不证明完整 GN 编译、真实 HAP/profile 签名或 BMS/分享/输入法 UI 运行通过。
原10项 system 需求及新代表包运行门禁均保持未核销。
