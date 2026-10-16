本批提供可执行普通调用方驱动与独立种子 HAP 源项目，尚未进行 SDK、native 编译或 QEMU 验收。普通 caller 的四份 ETS 与六份 fixture 保持冻结。现有 verifier 只增加准确的 native AppMgr API 名及错误码检查。

根可用以下命令生成私有种子项目，再用既有 SDK39 runner 编译、normal 非 system 签名、安装。它只声明 READ_CONTACTS/WRITE_CONTACTS，权限由实际用户对话框授予；observer 是单独 root 测试程序，不能放入种子 HAP、不能给 HAP 添加任何 system ACL。

```sh
python3 ci/capability-audit/batch_apps_run_contact_picker_runtime.py prepare-seed --output-dir /ABS/private/contact-seed-project
```

种子应用 `SeedStore.ets` 逐条调用真实 `contact.addContact(context, Contact)`，创建 205 条 `QCP_{runId}_NNN` 联系人，保留每次真实 ID，再调用 `queryContacts(context)` 读回完整 Contact。清理重新公开查询该 nonce，逐个用真实 key 调用 `deleteContact(context,key)`，再公开查询。部分创建可恢复；错误记录保留并阻止形成成功 receipt；不会直接访问数据库。没有 `expected` 或 PASS 字段。完整 journal 在 app filesDir 中同步追加，driver 的 ledger 由真实记录生成并引用原始 journal hash。

根需要独立提供构建/签名来源 JSON，driver 从当前 guest 获取安装包、BMS UID/token、真实权限 API，并校验签名证据，不能用 JSON 自述代替实际安装：

- `--build` 沿用冻结 verifier 的 build schema，另增加 `seed_hap:{path,sha256}`、`seed_source_manifest:{path,sha256}`。后者是 prepare 生成的 `seed-source-manifest.json`。caller 的 fixture/source manifest 仍使用已冻结的原六份 fixture；provider_hap 是真实 Contacts 源 HAP。representative_package 必须与当前 enclosing boot archive 一致。
- `--identity` 与 `--seed-identity` 各含真实 `decoded_profile:{path,sha256}`、`signature_verification:{path,sha256}`，后者保留真实 verify-app command/exit/两项哈希；另含 `installed_remote_hap`，必须是 `/data/app/el1/bundle/public/{bundle}/...hap` 的实际安装路径。driver 实际 recv 该文件并比较 signed HAP hash，实际运行 bm dump 与 observer，不接受调用者提供的 BMS/token 结论。
- `--observer-local` 是根真实产品头、库、CFI 编译出的 ARM64 ELF；`--observer` 是根已 push 的 guest 绝对路径。driver 校验 ELF 架构与 guest sha256sum，之后才调用。根负责 build/push，driver 不提供编译、签名、安装入口。

```sh
python3 ci/capability-audit/batch_apps_run_contact_picker_runtime.py run \
  --boot /ABS/suite/boot/boot.json --archive /ABS/new-arm64-phone-package.tar.gz \
  --hdc /ABS/hdc --build /ABS/root-build.json \
  --identity /ABS/caller-signing-input.json --seed-identity /ABS/seed-signing-input.json \
  --observer-local /ABS/product-built-contact-observer \
  --observer /data/local/tmp/contact-picker-observer \
  --output /ABS/new-runtime-output
```

可用 `--permission-bundle` 与重复的 `--allow-text` 指定当前实际系统权限对话框的精确 bundle/文本（默认 com.ohos.permissionmanager，允许/Allow）；driver 只从该 bundle 的真实可见、enabled、clickable 节点取中心点击，不猜坐标。不支持的 UI/无法唯一匹配会有界失败，不能借 shell 授权。首次种子 token 两项权限必须均 denied，再记录真实用户 Allow、公开权限请求返回和实际 token 两项 granted；重复使用已授权安装会失败，根应使用新安装。

驱动借用 `EnclosingAcceptanceGuest`，要求新包 ARM64 phone、原 archive hash/boot_id/QEMU PID/命令保持一致，不启动或销毁 suite VM。它按真实 `GuestUi` 执行 15 个 required case/16 个 invocation：6 overload、205 默认与实际清空再全选、空取消、改变选择后取消、参数错误/无读权限、双 session、pending force-stop、退出后新进程 reopen。双 session 根据真实 selectedText 的 count/limit 唯一识别当前 session；两者完成后同一真实 provider-absent 快照绑定两次关闭，不在另一窗口仍存在时伪造“provider消失”。错误 filter 必须提供 caller Start 之后新增的真实 hilog 目标，不能复用旧日志。可另外显式选择 deadline/navigation-dismiss 诊断。

每次完成输入前重新读 journal，要求自身 begin 已有、终态尚无；保存原始 prefix、layout、截图与真实 node。退出前、退出后、reopen 的原始 AppMgr 输出独立绑定 invocation。所有原始 HDC/guest 命令、BMS、token、AMS、hilog、currentboot、截图、UI tree 与 caller journal 留存。每个 case 失败后收集错误，继续本批其他 case；finally 通过独立 seed HAP 的真实公开 CRUD 清理，清理失败独立记录，不能掩盖前面的 picker 失败。最后调用既有独立 verifier，保存成功/失败结果。主机模拟不能作为 runtime proof；driver/report/verifier 均不核销账本，也不放行剩余五包。

observer 精确产品依赖（只读核对固定容器 `ohos-qemu-parallel-source-20261016-02:/ohos`）：

- source: `ci/capability-audit/fixtures/batch_apps/contact_picker_seed/observer.cpp`（测试源，不是新 upstream patch）。
- GN deps: `//foundation/ability/ability_runtime/interfaces/inner_api/app_manager:app_manager`、`//base/security/access_token/interfaces/innerkits/accesstoken:libaccesstoken_sdk`；`external_deps = [ "json:nlohmann_json_static" ]`。根可按现有 product probe 组再添加真实 transitive deps，保持产品 CFI 选项。
- headers: `app_mgr_client.h`、`running_process_info.h` 位于 `foundation/ability/ability_runtime/interfaces/inner_api/app_manager/include/appmgr`（app_manager 的 public appmgr_sdk_config 导出）；`accesstoken_kit.h`、`hap_token_info.h` 位于 `base/security/access_token/interfaces/innerkits/accesstoken/include`（libaccesstoken_sdk public config 导出）；`json.hpp` 由真实 nlohmann target 导出。
- 真实方法 `AppMgrClient::GetAllRunningProcesses(std::vector<RunningProcessInfo>&)`，不声明不存在的 GetRunningProcessInformation，也不将 native 输出伪称 JS；实际实现 app_mgr_client.cpp:508 经真实 AppMgr proxy 获取记录。保留 client 错误码，非零 exit；其 RunningProcessInfo DTO 只读取 `pid_` 与 `bundleNames`。
- permissions 先严格 parse uint32 positive token（不接受符号/前导零/溢出/尾随），bundle 只能是 caller/seed 两个固定值，真实 `GetHapTokenInfo` 必须成功且 bundle 匹配，再分别真实 `VerifyAccessToken`。仅查询，无 grant/revoke/set-token/DB/系统状态修改。

主机检查覆盖实际提取的 SeedStore.ets CRUD/拒绝/部分失败/删除失败/读失败、真实 Driver 代码在明确 transport model 下的 205/6overload/default取消/双 session/force-stop重开/清理失败保留、native API verifier 反例与项目元数据。SDK39、新 observer 的实际产品编译、normal 签名/BMS、用户授权和新包 UI/CRUD/回调仍全部留给根串行验收。
