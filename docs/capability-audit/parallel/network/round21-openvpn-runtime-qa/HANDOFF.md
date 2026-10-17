# OpenVPN Finish cleanup retry 的独立 guest QA 工具

本批只新增 4 个 `batch_network_openvpn_runtime_*.py`、2 个独占目录 ETS fixture 和本报告。没有修改生产代码、共享 runner、既有 fixture、Git index/HEAD；没有运行 SDK、Java/openssl 签名、Docker、VM、产品构建或 guest 操作，也没有读取 Docker 的实际 source/out。root 通知代表构建 05 已失败保全、没有新归档；这里不假定下一包版本或通过状态。

**已验证仅为主机源码/协议检查：9 项 unittest 通过，Python AST 解析通过。** 完整命令、主机平台、原始日志 SHA256、全部 6 个文件的绝对路径及 SHA256 见 [result.json](result.json) 和 [host-tests.log](host-tests.log)。单测中的 `UNIT ONLY` TLS 内容不是合法证书，只用于在禁止 subprocess 执行的临时目录内验证项目生成；未生成 SDK/native/runtime 成功证据。

## 文件与职责

| 新文件（均在 `ci/capability-audit/`） | 职责 |
| --- | --- |
| `batch_network_openvpn_runtime_project.py` | 只读真实 SDK105 声明，生成独立私有系统调用者项目和源清单；实际 build 结果必须与全部源/hash、原 profile、SDK、unsigned HAP 绑定 |
| `batch_network_openvpn_runtime_build.py` | root 显式 `--execute-sdk-build` 后才执行串行 Node/OHPM/Hvigor；复制私有 cache、保存真实日志/exit/HAP、通用 verifier 复核后生成 inputs |
| `batch_network_openvpn_runtime_collect.py` | 复用现有 owned acceptance guest、私有 HDC、签名与 BMS 机制；执行真实 API、进程/文件观察、故障注入及回滚，不启动或关闭 VM |
| `batch_network_openvpn_runtime_test.py` | 主机协议反例：错误 UID/父进程/PGID/路径/generation、额外 session、截断 argv、读不到的活 `/proc`、陈旧/重排/拒权 journal、连接 getter、签名权限漂移等 |
| `fixtures/batch_network/openvpn_runtime/EntryAbility.ets` | 实际 typed `vpn.OpenVpnConfig` → `VpnConnection.setUp()` / `destroy()`，实际 MANAGE_VPN grant 和 getters 记录；保留同一 Ability/PID/connection 对象 |
| `fixtures/batch_network/openvpn_runtime/Index.ets` | 简单可见 QA 页面 |

代码复用了 `batch_apps_contact_picker_runtime.prepare_project` 的基础 SDK 项目布局，随即删除**刚创建的私有项目**中的 Contact ETS，替换为本项目 fixture、bundle、名称与唯一权限。未调用或绕过 Calendar/Media 的固定 role guard。通用 `verify_sdk_project` 校验真实 source inventory、成功 assembleHap 日志和完整 unsigned HAP。新 build 入口仅复制 Media 的 `cpu-cap.cjs` 文件，并把复制后真实字节纳入工具 hash；不会调用 Media builder。签名复用 `sign_certificate_probe.sign(configure=本项目精确契约)` 的机制；未弱化共享 ordinary/system_basic verifier。

## API 与实证边界

SDK105 确实声明 `VpnConnection.setUp(config: VpnConfig): Promise<number>`、`OpenVpnConfig extends SysVpnConfig` 和 destroy/getters。只读主机 mirror 的 `setup_context.cpp` 确认：对象有 `vpnId` 时解析为 sys config，ExecSetUp 使用 `NetworkVpnClient::SetUpVpn(sysVpnConfig_)`。fixture 使用该真实分支，不直接调用私有 NotifyConnectStage。此为源码依据；导出、ArkTS 编译及实际授权尚未验证，失败必须留证。

必须先观察真实 `/system/bin/qemu_openvpn` exec 子进程，UID1098，精确 session config/generation argv，以及 init → UID1098 broker → 自有 PGID worker → 同 PGID client 的真实父子链；原始 `client.ovpn` 哈希必须等于本次准备的 profile。生产 `RunWorkerBody` 在真实 `NotifyConnectStage(claim)` 成功后才写 config/启动 client，因此这组证据是**生产控制流上的 claim 成功推断，不是直接 claim RPC 遥测**。没有该真实进程与 config 证据即失败，不使用假 HCI/WiFi/TUN 或 fake worker 兜底。

该项目只要求不可达受控 loopback UDP endpoint，所有阶段 `getConnectedSysVpnConfig()` 为 undefined、`getConnectedVpnAppInfo()` 为 []。`setUp()` resolve 仅记为请求被接受，绝不写作 CONNECTED。fixture 没有状态注入或伪造 TLS peer。

## root 的实际前置输入

1. **未来新鲜自有代表包**及其实际 acceptance boot receipt。receipt 必须由 `EnclosingAcceptanceGuest` 校验通过：包 SHA256、QEMU PID/精确启动命令、boot_id/UDID、私有 `127.0.0.1:port` HDC、架构与设备类型、串口无 fatal；原 owner 保持 VM 生命周期管理。此 runner 不接受旧包、诊断 kernel/辅助启动替换完整 gate。
2. 一次性、可丢弃且没有业务 VPN/其他验收的 guest；baseline 没有 worker/client/bridge，最多一个 init 子 broker；数据根为空/不存在或只有 backend.lock。默认尚无 broker PID 不是失败。
3. root 生成**新鲜自有测试 CA/client cert/private key**，保留仅供本轮的原 profile；不直接复用旧 r51 三天证书。需有效 inline `<ca>`、`<cert>`、`<key>`，不加加密 key/askpass、外部文件/脚本/代理/connection block。建议最小 profile 为 `client`、`proto udp4`、`remote 127.0.0.1 54123`、`nobind`、`resolv-retry infinite`、`connect-retry 1 5`、`remote-cert-tls server`、`verb 3` 和上述三个 inline 块。原生 OpenVPN 负责验证真实证书/语法；缺失/过期/不支持配置须真实失败。不要设置短期退出选项。supervisor 自己设置 dev/management/bridge。runner 会检查所选 UDP port 当时没有监听 socket；使用期间 root 独占此 guest/port，避免并发 listener 竞争。
4. SDK105/Node/OHPM/Hvigor 及只读 seed cache；root 已提供下列真实路径。没有 ohpm seed，空依赖使用离线 install。签名使用 root 给定固定 public QEMU signer 输入，jar SHA256 必须为 `a434b6747e6c5d0b14e73837a46b39f4816ab25b42d1833d6f767bf867cf616d`。子 agent 没有读 cache 或 key。
5. 由 root 提供实际私有 HDC 可执行路径。所有输出使用新的绝对目录并设 mode0700；HAP 本身包含本轮测试 profile，按临时自有 credentials 管理。

## 可执行命令（仅供 root 后续执行；本批未执行）

在仓库 `/Volumes/PSSD/code/ohos-rs/ohos-qemu` 执行，`TASK_QA` 必须选一个尚不存在的私有路径，先由 root 放入 `owned-current.ovpn`。下面的 profile、boot、archive、HDC 是必须提供的真实输入，不是已存在/已通过的声明。

```sh
TASK_QA=/absolute/new/private/openvpn-cleanup-attempt
TASK_SDK=/Volumes/PSSD/qemu/validation/first-20261005/provider-sdk-26-full/26.0.0
TASK_NODE=/Volumes/PSSD/qemu/openharmony/prebuilts/build-tools/common/nodejs/node-v18.20.1-darwin-arm64/bin/node
TASK_OHPM=/Volumes/PSSD/qemu/openharmony/prebuilts/tool/command-line-tools/ohpm/bin/pm-cli.js
TASK_HVIGOR=/Volumes/PSSD/qemu/openharmony/prebuilts/tool/command-line-tools/6.x/hvigor/bin/hvigorw.js
TASK_SEED=/Volumes/PSSD/qemu/validation/first-20261005/issue-20-20261006/r53-AudioHaptic-SDK105-01/hvigor-home

python3 ci/capability-audit/batch_network_openvpn_runtime_project.py \
  --output "$TASK_QA/project" --sdk "$TASK_SDK" \
  --profile "$TASK_QA/owned-current.ovpn" --port 54123

python3 ci/capability-audit/batch_network_openvpn_runtime_build.py \
  --execute-sdk-build --project "$TASK_QA/project" --sdk "$TASK_SDK" \
  --node "$TASK_NODE" --ohpm "$TASK_OHPM" --hvigor "$TASK_HVIGOR" \
  --hvigor-cache "$TASK_SEED" --output "$TASK_QA/build"
```

builder 的真实两步命令完整 argv 记录在 `build/evidence.json`，执行方式为 Node18.20.1 `--max-old-space-size=2048 --require <private>/cpu-cap.cjs` 后调用 OHPM `install --all --registry http://127.0.0.1:9 --fetch_timeout 10000 --retry_times 0`，再调用 Hvigor `assembleHap --mode module -p product=default -p module=entry -p debuggable=false -p hvigor-obfuscation=false --no-daemon --no-parallel --no-incremental --max-old-space-size 2048`。源码/输出不同目录，cache 只复制到该 attempt 私有目录，单步1200s限时；失败保存 exit/log，不产生成功 inputs。现有源码目录不可重跑覆盖，要保留失败并准备新目录。此 SDK HAP build 不等于产品 native build。

只有 build 成功且 inputs 严格绑定后，在真正 owned 新 guest 上由 root 串行执行：

```sh
TASK_BOOT=/absolute/new/owned/acceptance/boot/evidence.json
TASK_ARCHIVE=/absolute/new/representative-package.tar.gz
TASK_HDC=/absolute/root-owned/private-hdc
TASK_SIGNER=/Volumes/PSSD/qemu/validation/first-20261005/issue-20-20261006/r52-normal-signer-inputs-01
TASK_JAVA=/Library/Java/JavaVirtualMachines/zulu-8.jdk/Contents/Home

env JAVA_HOME="$TASK_JAVA" PATH="$TASK_JAVA/bin:$PATH" \
  python3 ci/capability-audit/batch_network_openvpn_runtime_collect.py run \
  --boot "$TASK_BOOT" --archive "$TASK_ARCHIVE" --hdc "$TASK_HDC" \
  --inputs "$TASK_QA/build/project-inputs.json" \
  --signer-dist "$TASK_SIGNER" --jar "$TASK_SIGNER/hap-sign-tool.jar" \
  --output "$TASK_QA/guest-collect"
```

collector 进程内共享机制最终执行真实签名/Java verify-app/profile CMS verify；签名契约只允许本 bundle `org.harmonycontrib.openvpncleanupqa`、system_core/hos_system_app、唯一 MANAGE_VPN ACL/restricted permission 和当前实际 UDID。HDC install 后核对真实 BMS system UID（account100）/token/APL 和安装 HAP SHA256。fixture 再读取真实 token 检查实际 grant。任一步失败均不得跳过。这些动作本批均未执行。

## source / SDK / HAP 绑定格式

`project/openvpn-runtime-source.json` 保存 schema、run_id（32hex）、等价 VPN UUID、port、bundle/permissions/system_core、原 profile 的绝对 path/SHA256、**加入本次 run 注释后的** profile SHA256、实际 SDK105 metadata/declaration/device-define 三份 path/SHA256、固定 ETS fixture hash、全部生成源文件的相对路径→SHA256。manifest 自身在 SDK build inventory 中再次绑定。

`build/evidence.json` 保存真实 `source_commit`（执行时 HEAD）、builder SHA256、SDK/tool path/hash、完整 commands（project/argv/cwd/log/exit_code/log SHA256）、`source_files.openvpn-cleanup`（包括 manifest 和 local.properties 的完整 source inventory）、唯一实际 unsigned HAP path/SHA256/bytes 和 failures。编译前拒绝额外/alias source、旧 build，编译后核对 source 未变；日志必须是真实 exit0 和 BUILD SUCCESSFUL。

成功后 `build/project-inputs.json` 的完整结构为：

```json
{
  "sdk_evidence": {"path": "/ABS/build/evidence.json", "sha256": "ACTUAL_SHA256"},
  "sdk_project": "openvpn-cleanup",
  "source_project": "/ABS/project",
  "source_manifest": {"path": "/ABS/project/openvpn-runtime-source.json", "sha256": "ACTUAL_SHA256"},
  "unsigned_hap": {"path": "/ABS/project/entry/build/default/outputs/default/entry-default-unsigned.hap", "sha256": "ACTUAL_SHA256"}
}
```

无需手工制造这些字段。build 入口只在通用实际 SDK verifier 与本项目 fixture/profile/HAP 校验全部通过后写 inputs。源、原 profile、SDK 声明、build receipt 或 HAP 后续任何变化均拒绝。collector 保存输入文件、boot/archive、签名 HAP、工具 SHA256，全部 host/guest argv 与原始日志/exit/hash，以及每阶段 journal、两次实际 client/worker/broker PID/PGID/starttime/generation/config hash。journal 绑定 run/boot/op/真实 UID/token/PID，顺序、grant、getter 或 caller PID 发生漂移即失败。

## 实际要执行和证明的窄边界

1. 本次授权 HAP 实际 setup resolve，然后观察真实 worker/client 与 config hash。没有实际 worker claim 依据则失败。
2. UID0 HDC shell 只在已确认属于本次 session 的目录创建独有 `qa-<run_id>`，`set -C` 拒绝覆盖；是常规非 alias、UID0/mode0600/nlink1、精确 marker 的未知文件。记录真实命令；若生产策略 EACCES，保留该层拒绝，不改 enforcing/label/ACL。
3. 真实 public destroy 应拒绝为2200003；全 `/proc` snapshot 证明旧 worker 整个 PGID 已无成员、原 session/自有阻碍仍在。再次真实 setup 应拒绝，且没有新 worker/client/session。这覆盖单 owner 保留和不能冲突重建；没有第二 owner 隔离结论。
4. 仅校验并移除本次自己的 marker；如文件不存在视作无剩余本次输入，如被改为 alias/链接/外来内容则不移除。等待真实 broker periodic Reap 删除旧 session。再真实 setup resolve，必须出现不同 generation、不同 worker starttime 的实际 client/worker。
5. 第二次真实 destroy resolve，两个旧 PGID 无成员、private root 只允许 backend.lock、无 worker/client/bridge后，才置 cleanup_verified。随后 force-stop/卸载自己的唯一 HAP并读取 BMS 确认移除。失败保留原始证据；只尝试自己的 marker 回滚和 public destroy，不全局 stop broker、递归删目录、杀其他 owner 或关闭 VM。清理无法证明时标记失败，guest 不可复用。

未来成功状态仅为 `pass_narrow_guest_cleanup_NOT_full_gate`，`first_artifact_behavior_gate_passed` 始终 false。此项应与 root 的完整新包边界验收合并判断，不能单独越过 AGENTS 的代表包 runtime gate。

## 明确保留的未验证范围

SDK/ArkTS 编译、真实 NAPI 导出和授权、真实 helper 启动/claim、Finish 清理失败与重试、实际签名/BMS/guest 都尚未执行。root 需先审查本工具，再按上面命令执行并保留所有失败。若权限/API/worker 实证不成立，此 runner 失败而不是跳过。

全 `/proc` 只能证明观察时旧 PGID 没有成员；没有生产 signal trace、强制 PID/PGID reuse 或跨 owner 隔离实证，**不能宣称完整 kernel 重用安全通过**。没有真实 TLS peer/CONNECTED、bridge/TUN 数据面、路由/DNS/断线重连/流量通过；没有真实 callback stream。需要真实 peer 的条目继续保留在现有能力缺口，不能以本批 host 单测或 future 单 owner 清理结果关账。正常 init start/stop 与 SessionStore 启动 stale-session 的旧配方仍独立，见前一批 `round21-guest-acceptance/HANDOFF.md`，不能相互替代。

本报告完成后释放所有本批新 QA 路径写租约；子 agent 停止修改，由 root 集中审查、实际执行与提交。
