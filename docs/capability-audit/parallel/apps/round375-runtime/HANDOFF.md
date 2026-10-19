# Select375 ordinary three-role preparation — SOURCE/HOST ONLY

三独立 role 的真实 SDK105 源码和只读 raw 核验器已交付。**13 项新 host 方法通过；只读核对官方 SDK105 metadata/declarations 13 文件。未编译、签名、安装或运行 guest，没有 private-start、URI 或能力销项通过声明。** 已冻结 chooser/共享 guards/旧 host37 未改、未重跑。本批源码交接后停止修改；后续官方 provider 研究文件另列，不改变 producer freeze。

## 九个新增源码文件

- `fixtures/batch_apps/select375/{contract.json,EntryAbility.ets,Index.ets,SelectAudit.ets,cpu-cap.cjs}`
- `batch_apps_select375_project.py`：challenge/project/request CLI、精确 source recipe 与完整 inputs/SDK binding。
- `batch_apps_select375_project_build.py`：root 注入 runner 的 serial SDK builder，**CLI 一律拒绝直接 SDK 执行**，无 Popen/SDK subprocess fallback、无 nested lease、无 JSON `root_owned` 放行。
- `batch_apps_select375_project_verify.py`：实际 SDK/HAP/BMS/boot/原始 JSONL 独立 join。
- `test_batch_apps_select375_project.py`：13 methods，内存 synthetic raw 反例，绝不生成 runtime 成功 receipt。

源码均在已分配 MAIN 路径，无 Git mutation。完整 SHA、AST/JSON 及日志 pins 在 producer manifest。旧 frozen375 组件未改。

## 三普通 role 与实际调用

所有 profile 必须 `apl=normal / hos_normal_app / empty ACL / empty restricted permissions`；模块 `requestPermissions=[]`，BMS 必须 `isSystemApp=false`，account100、三个不同 UID/token。不得用系统 APL/权限化解失败。

| role | bundle | launchType |
|---|---|---|
|caller|org.harmonycontrib.select375caller|singleton|
|target_a|org.harmonycontrib.select375targeta|standard|
|target_b|org.harmonycontrib.select375targetb|standard|

两个 target skills 均绑定唯一自有 MIME `application/vnd.harmonycontrib.select375` 与 entity `org.harmonycontrib.select375`；原生实际 matching 会清空外层 select action。root 应先观察新安装两 target 真实 BMS/chooser 枚举，不能靠源码猜已枚举成功。匹配错误必须保留失败。

Caller 从 app-root `getApplicationContext().filesDir` 创建不可复用 run/op nonce 文本，自己真实回读；通过原始 `ohos.want.action.select`、URI/flags/自有 MIME/entity 启动 `startAbilityForResult`。被选 target 真实读取 URI，并尝试写入。Read-only 与无 grant 的写尝试**只 open/close，不修改数据**；write-a 真写入同长度独特内容，caller 真回读 modified bytes。

每个非 cancel select 的前、后，caller 显式启动未选 target，仅在 `parameters.probe_uri` 传 URI 文本，Want 没有 uri、flags=0。该 target 两次真实 read/open-write 必须获得 `13900012 Permission denied`，不能用 ENOENT、解析错误或 transport 失败冒充权限拒绝。每个 target 返回自己 `terminateSelfWithResult` 的 run/op/case/role/phase receipt；caller 收到实际 result 后独立 join。不是 picker launch 成功代替目标结果。

FileIO SDK105 没有 EXCL，本实现先拒绝既有 nonce 文件，使用 NOFOLLOW、唯一随机 operation 名和单 instance busy guard；没有声称 O_EXCL。删除前严格比较实际 inode、regular file 与预期内容；调用 unlink 后记录实际 accessSync=false。异常留文件供 root 收集，不把 VM disposal 当 public cleanup。

EntryAbility 的实例 LocalStorage + `@Entry({ useSharedStorage:true })`、onCreate/onNewWant 与 Watch 使冷/热启动发布当前 request；busy 时不会替换正在执行的 audit，结束后才展示新的待执行 request。重复 operation/phase 在 API 调用前拒绝。root 须实际覆盖 cold、新 Want、重复点击和两个 role 隔离，host 静态检查不是 UI race 通过。

## root 准备 / 构建接口

先统一提交/冻结本九文件及本轮其他已知修复，再设置 `COMMIT=<真实最终commit>`。工具核对 HEAD、tracked clean、每个 producer input 在该 commit 中逐字相等；不能借未提交文件冒充 source commit。

以下仅 CLI 计划，使用 root 的实际 SDK/私有新目录，不自动执行：

```sh
python3 -B ci/capability-audit/batch_apps_select375_project.py challenge --commit "$COMMIT" --output "$PRIVATE/challenge"
python3 -B ci/capability-audit/batch_apps_select375_project.py project --role caller --challenge "$PRIVATE/challenge/challenge.json" --sdk "$SDK105" --output "$PRIVATE/caller"
python3 -B ci/capability-audit/batch_apps_select375_project.py project --role target_a --challenge "$PRIVATE/challenge/challenge.json" --sdk "$SDK105" --output "$PRIVATE/target_a"
python3 -B ci/capability-audit/batch_apps_select375_project.py project --role target_b --challenge "$PRIVATE/challenge/challenge.json" --sdk "$SDK105" --output "$PRIVATE/target_b"
```

官方 RO 声明来源：`/Volumes/PSSD/qemu/validation/first-20261005/provider-sdk-26-full/26.0.0`，metadata 实为 `26.0.0.105 / api26`；不是 native SDK39，也未跑 compiler。`common.AbilityResult`、UIAbilityContext Promise results、FileURI/FileIO、UID/PID、bundle self、TextEncoder/Decoder 实际声明均已核对，pin 见私有 `sdk105-declarations-readonly.json`。

Root 持有 H/SDK-batch375 的**同一真实 sdk26_common lease**，调用：

```python
report = batch_apps_select375_project_build.build(args, runner=actual_owned_callback)
```

args：`execute_sdk_build=True, commit, challenge:Path, sdk:Path, output:Path, node:Path, ohpm:Path, hvigor:Path, hvigor_cache:Path, ohpm_cache:Path|None, project=['caller=/ABS/caller','target_a=/ABS/target_a','target_b=/ABS/target_b']`。hvigor_cache 只复制 wrapper，所有生成输出私有。root 应传实际 canonical tool paths。

callback 签名：`runner(argv, *, cwd:Path, env:dict, log:Path, timeout:int, role:str, label:str) -> dict`。由 root 的既有 owner 实际执行，返回 `{argv:list[str], cwd:str, exit_code:int, log:{path,sha256}, started_ns:int, finished_ns:int, ...}`；nonzero 也返回原始记录，builder 据此 fail。builder 不开进程、不自行取 lease，不接受 `--execute` 代替 callback。Node --version 同样走该 callback；两条 official ohpm/hvigor argv 由 `sdk_commands(tools)` 固定，三 role 串行 6 commands，完整日志/源码/HAP inventories 保存 evidence.json。独立 verifier 强制实际成功日志、源码 recipe、所有角色 inventory 与对应 HAP bytes；没有任意 SDK report fallback。

root 再用既有 `batch_apps_contact_picker_coordinator.sign_normal_hap(...,permissions=[])` / `verify_signed_hap_artifacts(...,apl='normal',system_app=False)` 做真实 Java/CMS/profile 验证及安装，保留原始 command/log/chain/profile。该操作未由本 agent 执行。

## 实际 runtime 输入与收集

新包 boot 后逐 case 生成真实 request，不能重用 operation nonce：

```sh
python3 -B ci/capability-audit/batch_apps_select375_project.py request --challenge "$PRIVATE/challenge/challenge.json" --boot "$BOOT" --archive-sha "$ARCHIVE_SHA" --case read-a
```

cases：read-a / read-b / write-a / no-grant-a / cancel / private-start / forged-sid。输出 JSON 作为 caller Want 的 string parameter `request`。root 用实际普通 `aa start`/既有 UI collector 发送，不能用 root直接启动 target 代替选择。caller 界面必须实际显示 `select375-ready` 的 `RUN/OP/CASE/run`，fresh tree/PNG 同 boot 核对后才点 `select375-run`；真 chooser namespace com.ohos.settings，目标 ID 为 `system-choose-target-BUNDLE/entry/EntryAbility`、cancel ID `system-choose-cancel`。读 fresh DOM 选择实际唯一 enabled node，不能猜坐标。真实 target 自动消费并返回；不需要给它 grant 或点击伪确认。全局 bounded wait/异常 UI capture 由 root 已有 collector 驱动，本批没有新 HDC/VM driver。

`forged-sid` 是普通 caller 向 private explicit start 注入伪造 SID 的负例，**不声称等价于已活跃 session 的已知 SID/错误 caller native owner 全部反例**。那些仍在 native/host 层候选及 root 待验范围。

每个 case 保存 trusted request artifact，以及操作前、后各 10 条只读实际命令：boot；按 caller/A/B 次序各 BMS、完整 journal、已安装 HAP sha256sum。`journal_script(req,role)` 与 `wrapped(script,op)` 给出精确命令/terminal footer；fresh 未产生 journal 用独特 absence 输出，禁止吞一般 rc1。records 必须有真实 host exit、原始 raw descriptor、开始结束 monotonic ns。

`verify_runtime` evidence：

```text
{schema_version:1, request:{path,sha256},
 applications:{caller:APP,target_a:APP,target_b:APP}, commands:[20 exact before/after records]}
APP={source_project:ABS, sdk_evidence:{path,sha256}, unsigned_hap:{path,sha256},
 signed_hap:{path,sha256}, installed_hap:{path,sha256}, decoded_profile:{path,sha256}, actual_guest_udid:HEX64}
COMMAND={argv:[actual_hdc,'-t',endpoint,'shell',wrapped],host_exit_code:0,
 raw:{path,sha256},started_ns:INT,finished_ns:INT}
```

`installed_hap` 是真实 guest 原路径回收的文件，独立 guest sha256sum、BMS 唯一 hapPath、signed HAP 同 SHA；root 还应保留 file recv 原 command/log。argv[0]/endpoint/实际 archive SHA/request 由 root 显式传入，不能从 evidence 自己反推预期。

```sh
python3 -B ci/capability-audit/batch_apps_select375_project_verify.py --evidence /ABS/evidence.json --challenge /ABS/challenge.json --request /ABS/request.json --hdc /ABS/actual/hdc --endpoint ACTUAL --archive-sha ACTUAL_SHA
```

核验器逐行重放三 role 完整 JSONL，拒绝截断/重复 JSON key、额外字段、错序/额外操作、nonce/UID/token/boot/包错配，join caller 的原始 Want/URI/grant、target 实际读取/拒绝/写入与目标真实结果，再看 owner readback 与删除/不存在观测。N-API 允许的已知空 Want 字段只按准确空值接受；未知/非空 metadata 不剥离。BMS before/after 必须完全相同，所有实际 HAP hashes、SDK inventories 及 code payload 相等。

结果仅为 **raw API join**。真实 cryptographic signature、fresh UI点击、private Settings/native SA 身份、owner/session timeout/death/reentry/concurrency/退出后无状态遗留仍由 root 独立验收。返回字段明确 `signature_cryptography_verified_here=false / UI_choice_verified_here=false / native_owner_release_verified_here=false / gate=false / ledger_closed=false`。cancel 没有 target journal 增量本身不是完整 native owner 销毁证明。

## 本批验证与未执行范围

13 host methods 通过（host-05），全部是隔离 synthetic raw/source 检查，包含 7 正常形状、nonce/身份/boot/payload/URI grant/缺数据拒绝、result/cancel/保留metadata、重放/额外/错序、transport/footer、cold/onNewWant storage源码、callback无owner拒绝、未提交input不能借commit。首个 host-01 是写测试文件时 cwd 路径错误导致的 import failure，原日志保留，之后未改成 PASS。host02..05 为递进源码版本；最终以 host05 与 manifest pins 为准。

```sh
cd ci/capability-audit
python3 -B -m unittest -v test_batch_apps_select375_project
```

没有 rerun 旧37/实际SDK/native/crypto/container/VM/HDC/QMP，没有写 source/out 或共享 SDK/cache/signing；root 执行实际构建与新包行为验证后才能补齐结论。源码交接后冻结；后续 research-* 为官方可交付 provider 只读研究，不纳入这份 producer source freeze。
