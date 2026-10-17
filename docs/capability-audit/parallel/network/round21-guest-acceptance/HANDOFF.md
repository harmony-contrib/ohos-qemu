# 新归档 OpenVPN guest 验收命令与缺口

供 root 在第 05 代表构建及归档完成后执行。此次只读检查了仓库 runner/候选源、已有证据目录索引，以及获准读取的主机 init 镜像源码；没有读取 Docker 的 source/out，没有运行 SDK、Docker、VM、guest 命令或构建。生产文件及冻结 HEAD 未修改。本文件中的命令是待执行配方，不能记录为通过。

## 先固定新包与执行身份

由 root 从本次 owned acceptance boot receipt 取得 `ARCHIVE`、`TARGET`、`BOOT_ID`、`UDID`、`HDC`；记录本次归档 SHA256、QEMU PID/启动命令与串口日志路径。不能复用旧包的 boot_id/UDID 或旧 HAP 运行结果。

以下是 root 的 **UID 0 HDC shell 观察命令**，不需要 VPN peer：

```sh
"$HDC" -t "$TARGET" shell 'id; cat /proc/sys/kernel/random/boot_id; uname -m; param get const.product.devicetype'
"$HDC" -t "$TARGET" shell 'ls -lZ /system/bin/qemu_openvpn /system/bin/qemu_openvpn_service /system/bin/qemu_openvpn_tun; cat /system/etc/init/qemu_openvpn.cfg'
"$HDC" -t "$TARGET" shell 'param get startup.service.ctl.qemu_openvpn; begetctl dump_service qemu_openvpn; pidof qemu_openvpn_service'
"$HDC" -t "$TARGET" shell 'ls -ldZ /data/service/el1/public/vpn/qemu_openvpn; ls -lZ /dev/unix/socket/qemu_openvpn /dev/unix/socket/qemu_openvpn_tunfd'
```

服务是 `disabled: 1, once: 1`。默认未发起连接前没有 broker PID、尚未创建数据根目录，并不自动说明失败；先区分安装内容、init 注册状态与是否已经发起合法 START。记录缺失项和命令的真实 guest exit，不用 HDC 自己的 exit 0 代替 guest 命令结果。

## 不需要 peer 的 startup / shutdown

已从主机镜像确认：

- `base/startup/init/services/begetctl/service_control.c` 注册 `start_service`、`stop_service`，调用 ServiceControlWithExtra。
- `interfaces/innerkits/service_control/service_control.c` 最终写入的是 `ohos.ctl.start/stop`，值为服务名。
- 状态参数名是 `startup.service.ctl.qemu_openvpn`；2=STARTED，3=READY，5=STOPPED。
- begetctl 的 service_control 实现忽略 ServiceControl 返回值并返回 0。因此命令 exit 0 **不是**服务成功证据。

root 可在新的、没有任何 VPN owner 的 disposable guest 中请求：

```sh
"$HDC" -t "$TARGET" shell 'begetctl start_service qemu_openvpn'
"$HDC" -t "$TARGET" shell 'param get startup.service.ctl.qemu_openvpn; begetctl dump_service qemu_openvpn; pidof qemu_openvpn_service'
```

请求者是 UID 0 的 shell，实际 broker 应由 **init 以 UID 1098 / netsysnative、配置中的附加组与 netsysnative SELinux domain** 启动。对同一 PID 做至少两个间隔观察，记录 `/proc/PID/status`、`stat`、`cmdline`、`exe`、`attr/current` 和 FD 列表；核对真实 `/system/bin/qemu_openvpn_service`、父进程 init、UID 1098、正确 socket FD、数据根 0700 和 socket 0600/owner，而非短暂出现 PID 就算成功。broker 未创建 owner 时不应该产生 worker、OpenVPN client、bridge 或 TUN。

```sh
"$HDC" -t "$TARGET" shell 'begetctl stop_service qemu_openvpn'
"$HDC" -t "$TARGET" shell 'param get startup.service.ctl.qemu_openvpn; begetctl dump_service qemu_openvpn; pidof qemu_openvpn_service; pidof qemu_openvpn; pidof qemu_openvpn_tun'
```

停止后应到 STOPPED 且真实 PID 消失；保留 init/串口日志。只在本次测试没有其他 owner 时做该服务级 STOP。业务的单 owner destroy 不能用全局 STOP 代替。

**授权层限制：** 配方确认的是 CLI 名称，不保证 UID 0 shell 拥有这两个精确服务控制参数的 MAC 权限；生产授权包含 netsysnative 的专用控制键。若请求被 DAC/MAC 拒绝、CLI 仍返回 0，记录该层拒绝，不能把它写成 broker 启动失败，也不放宽 enforcing、label 或 ACL。成功路径应由真实授权的 NetworkVpnService/netsys 流程触发。仓库目前没有独立的该流程 guest runner。

不要使用裸 `ctl.start`；也不要猜测写入 `ohos.servicectrl.start.qemu_openvpn`。后者在本候选中用于转换后的 DAC/MAC 授权，不是这里核实的 START API 输入。

## exec 拒绝与 main 内 UID 检查分层

`qemu_openvpn_policy.te` 对除 init/netsysnative 外的 domain 有 helper/client execute neverallow。因此以下 **UID 0 shell 的负向尝试**，可能先在 exec 层得到 EACCES：

```sh
"$HDC" -t "$TARGET" shell '/system/bin/qemu_openvpn_service; task_vpn_rc=$?; printf "SERVICE_EXIT=%s\n" "$task_vpn_rc"'
"$HDC" -t "$TARGET" shell '/system/bin/qemu_openvpn_tun; task_vpn_rc=$?; printf "TUN_EXIT=%s\n" "$task_vpn_rc"'
```

EACCES 只证明该 caller 的 exec 策略拒绝；若策略本来允许进入 main，代码会因 UID/eUID 不是 1098 返回 2，这才证明 UID 检查。不得为取得 exit 2 临时降低 enforcing、修改 label 或绕过执行域。`qemu_openvpn --version` 同样受 execute 策略约束；shell 执行受拒绝不代表 native client 构建损坏。正向 init broker 持续运行，才覆盖其实际 loader/初始化路径。

## 可回滚的 stale-session 启动清理输入

这组不需要 peer、不需要创建真实 VPN owner，验收的是实际打包 broker 的 **SessionStore::Open 启动清理失败→重试**。它不等于本轮 `BrokerRuntime::Finish` 的活 owner / PGID 重试验收。

已逐项核对真实实现：

| 项目 | 约束 |
| --- | --- |
| 数据根 | `/data/service/el1/public/vpn/qemu_openvpn`；真实目录、UID 1098、mode 精确 0700、拒绝 symlink |
| 锁 | `backend.lock`；常规文件、UID 1098、mode 精确 0600、nlink=1；独占 flock |
| session 名 | **总长 14 字节**，`session-` 后恰好 **6 个 ASCII 字母或数字** |
| session 目录 | 真实目录、UID 1098、mode 精确 0700；GID不参与 PrivateOwned 判断，但 init 契约使用 netsysnative 组 |
| 唯一允许的内部名 | `client.ovpn`、`askpass`、`management`、`ready` |
| 未知项 | 先枚举校验；发现任何其他名字时不删除 known 文件，返回失败；不做递归删除 |
| namespace 边界 | 数据根中除 `backend.lock` 外的项都要通过上述 session 校验；存在其他真实 owner / 未知内容时不能进行本故障配方 |

**执行前置条件全部满足才继续：**

1. 新的自有 disposable guest；没有业务 VPN、其他验收正在使用 broker、worker/client/bridge。
2. 同一 UID 0 请求者已先完成上面的正常 init START、持续驻留和 STOP，证明控制请求及当前策略确实可用。停止后状态 5、所有相关 PID 已消失，数据根仅有合规 `backend.lock`。
3. root 只用现有真实权限操作自己的输入；若任一步 EACCES，保留为该层拒绝并停止，不能改生产根目录的 owner/mode/label/ACL。
4. 用 `id -u netsysnative` 确认 UID 1098，并记录该账号实际 GID。标签必须从当前真实策略自然得到并记录；不调用 restorecon/chcon 来补造本次成功条件。

下面给出一个精确示例输入。`Q7a9Bc` 是 6 个合法字符；root 应选本次独有的 6 字符值并在每阶段保持一致。若该路径已存在，包括 dangling symlink，换另一个名字，不能覆盖。

**仅创建本次自己的目录和两个非密钥 marker 文件：**

```sh
# 在同一次受控 guest shell 内执行；此处示例后缀在后续步骤也必须相同。
set -eu
task_vpn_root=/data/service/el1/public/vpn/qemu_openvpn
task_vpn_dir="$task_vpn_root/session-Q7a9Bc"
test "$(id -u netsysnative)" = 1098
test ! -L "$task_vpn_root"
test "$(stat -c '%u:%a' "$task_vpn_root")" = 1098:700
test ! -e "$task_vpn_dir" && test ! -L "$task_vpn_dir"
umask 077
mkdir -m 700 "$task_vpn_dir"
printf '%s\n' 'qemu-owned-stale-fixture-Q7a9Bc' > "$task_vpn_dir/askpass"
printf '%s\n' 'qemu-owned-foreign-fixture-Q7a9Bc' > "$task_vpn_dir/probe-foreign"
chown netsysnative:netsysnative "$task_vpn_dir" "$task_vpn_dir/askpass" "$task_vpn_dir/probe-foreign"
stat -c '%n %u:%g:%a:%h:%F' "$task_vpn_dir" "$task_vpn_dir/askpass" "$task_vpn_dir/probe-foreign"
ls -ldZ "$task_vpn_dir" "$task_vpn_dir/askpass" "$task_vpn_dir/probe-foreign"
sha256sum "$task_vpn_dir/askpass" "$task_vpn_dir/probe-foreign"
```

这不是 TLS credential 或 native build fixture。应确认两个文件 mode 0600、nlink=1、UID 1098，且 GID/标签符合真实 init 数据域；没有满足这些条件时不把后续拒绝归因于未知文件逻辑。`set -e` 中途失败时，按下方回滚要求核对已创建的自己的路径，不继续扩大权限。

随后 root 用现成 `begetctl start_service qemu_openvpn` 请求真实 init 启动并限时观察。预期不能持续驻留，init/串口显示实际启动失败；两个 marker 文件内容/hash 仍保持原样。若只有控制授权失败，或者 exec/目录权限错误，分别记在对应层，**不得**写成 SessionStore 未知项测试通过。保留 shell、init、PID/状态与目录元数据证据。

确认失败 broker 已退出，然后只移除本次自己创建、类型与 marker 都吻合的未知文件：

```sh
set -eu
task_vpn_dir=/data/service/el1/public/vpn/qemu_openvpn/session-Q7a9Bc
test -d "$task_vpn_dir" && test ! -L "$task_vpn_dir"
test "$(stat -c '%u:%a' "$task_vpn_dir")" = 1098:700
test -f "$task_vpn_dir/probe-foreign" && test ! -L "$task_vpn_dir/probe-foreign"
test "$(stat -c '%u:%a:%h' "$task_vpn_dir/probe-foreign")" = 1098:600:1
test "$(cat "$task_vpn_dir/probe-foreign")" = qemu-owned-foreign-fixture-Q7a9Bc
rm "$task_vpn_dir/probe-foreign"
```

再次真实 init START。预期 SessionStore 删除剩余 known `askpass` 和这个 session 目录，broker 驻留到状态 2/3、真实 UID/FD/监听正常；`backend.lock` 保留。使用实际路径不存在与持续 PID 证据，不以 `begetctl` 的 RC0 推断。最后在本测试无其他 owner 的条件下 STOP 自己启动的 broker。

**回滚：** 成功重试后输入已由真实 broker 清除。若由于真实策略/环境未能完成，在 broker 已停止且确认没有业务 owner 后，仅删除上述两个确实由本次创建的常规 marker 文件：逐个确认非 symlink、UID/mode/nlink 与保存的 hash/marker 相同，再 `rm` 各自精确文件路径并 `rmdir` 精确 session 路径。没有 `rm -rf`，不改 `backend.lock`，不扫删其他 session。类型/hash 不符或出现其他文件时停止并保留证据，不能把它们当作自己的残留。

## 无 peer 的现成 HAP runner

下面两条从仓库根目录执行；前置输入还包括实际 API26 Release `SDK`、签名工具/只读源码 volume、真实新 guest UDID、`SOURCE_VOL` 和 `DOCKER_IMAGE`。runner 内部会做 SDK 构建和 Docker 签名，必须由 root 在代表构建完成后串行租用资源；本 agent 没有执行。

```sh
python3 ci/capability-audit/run_always_on_vpn_probe.py --archive "$ARCHIVE" --sdk "$SDK" --output "$OUT/vpn-policy" --arch arm64 --device phone --target "$TARGET" --boot-id "$BOOT_ID" --udid "$UDID" --hdc "$HDC" --source-volume "$SOURCE_VOL" --docker-image "$DOCKER_IMAGE"
python3 ci/capability-audit/run_sys_vpn_store_probe.py --archive "$ARCHIVE" --sdk "$SDK" --output "$OUT/sys-vpn-store" --arch arm64 --device phone --target "$TARGET" --boot-id "$BOOT_ID" --udid "$UDID" --hdc "$HDC" --source-volume "$SOURCE_VOL" --docker-image "$DOCKER_IMAGE"
```

两者都要求新的 output 子目录及 fresh disposable store，都会安装同一个 `org.harmonycontrib.capabilityaudit` bundle。必须与所有其他使用该 bundle 的 HAP 验收串行；不应因为三 agent 独占源码而并发操作同一 guest 应用。角色为 normal、system-denied、system；预期权限拒绝分别为 202、201，非法输入 401，并核验实际签名/profile/UID、caller PID 真正变化与清理。它们覆盖 policy/CRUD，**都不调用真实 OpenVPN setUp，不证明 broker/CONNECTED/TUN**。`run_packaged_qemu_suite.py` 已接入这两组，root 跑完整套件时不要重复并行调用。

## 仍没有 runner 的边界

1. **private broker/TUN socket 鉴权：** 活 broker 下，需要实际 guest AF_UNIX probe 记录 UID/eUID、exe/argv、domain，以及 connect/服务端关闭/无 FD 返回结果。仓库只有 host parser/controller/SCM_RIGHTS 测试，没有该 guest runner。UID 0 shell 的 DAC/MAC 拒绝、同 UID 错 exe 的 peer 拒绝、正确 netsys `sa_main` 正向调用应分开。不能用 `nc -U` 假设 guest 工具支持，也不能用 `su/chcon` 绕过身份来伪造授权通过。
2. **本轮 Finish 活 owner / PGID 清理重试：** 无需真实 TLS peer 也可设计该负向测试，但需要真实授权的 system/extension owner、合法完整 OpenVPN profile（inline 自有测试 credentials，ovpnConfig 使用真实 Base64）、真实 setup/destroy 调用及结果记录。用不可达测试 endpoint 可以保持“没有 CONNECTED”，但仍须实证 worker 已启动/claim，再对该实际 session 注入自己未知文件，验证退出/reap、owner/interface 保留、其他 owner 不受影响、去除阻碍后周期 Reap 或原 STOP 成功，旧 generation 不可重放且不重发旧 PGID。现成 store runner 的 `audit-config-*` 是 CRUD 字段 fixture，不是这个合法 profile；旧 legacy VpnConnection.setUp 也不是此路径。
3. **CONNECTED / TUN 数据面：** 必须有实际可达 OpenVPN TLS server/peer、受控 CA/client/server credentials、正确时间/证书有效期、IPv4/IPv6/DNS/路由与流量 endpoint、至少两个独立 owner 的权限/UID 规则。需真实握手、TUN FD、数据、回调/getter、失败/重连、broker SIGKILL 与所有后代退出。没有 peer 时不能把 START 接受、PID 出现或 getter export 当作连接成功。

已有索引 `/Volumes/PSSD/qemu/validation/first-20261005/issue-20-20261006/r51-openvpn-owned-TLS-test-peer-01/` 有生成脚本、server.conf 和独立测试 CA/证书材料，其 evidence 的状态仅为 **prepared_OWN_local_TLS_test_peer_ONLY_NOT_started_or_VPN_runtime**；证书当时只生成 3 天有效期，复用前须检查实际有效期/时钟与可达 endpoint，不打印私钥。旧 r51 connected/TUN diagnostic 走 legacy VpnConnection，明确是旧包 diagnostic；r52/r53 Linux POSIX/FFRT/SCM_RIGHTS receipts 也不能补成新包 guest 通过。

最终将 startup、授权各层、SessionStore stale 重试、Finish 活 owner 重试、真实 TLS/TUN 分项记录；本 handoff 不关闭任一原始 VPN 能力账目，也不改变首包完整 runtime gate。
