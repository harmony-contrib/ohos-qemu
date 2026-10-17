# Network round 21 handoff

2026-10-17，基线含 `3b627f0`。本批已冻结，供 root 审查和集中提交。未修改共享接线、scripts、产品 BUILD/init/SELinux、账本或 Git index；未使用 source/out、SDK、VM、容器或构建包。

## 真实修复

`broker_runtime.h` 存在两个实际反例，已先用真实 fork/进程信号/文件系统复现，见 `cleanup-before-fix.txt`：

1. worker 已退出并被回收，但 session 目录中存在不允许删除的未知文件。第一次 STOP 返回 EIO 后，下一次 Reap/STOP 仍向旧 PGID 发信号，然后因 ECHILD 无法再次清理；owner/interface 永久保留。
2. Shutdown 无论 Finish 是否失败都清空 jobs，导致尚有私密文件的清理任务丢失。

现在分别记录 SIGKILL 已发起和进程已回收两个阶段。首次发信号前，用 waitid/WNOWAIT 确认 leader 仍由本进程持有。开始回收后不再向该 PGID 发信号；目录删除失败只重试删除，继续保留 owner/interface 及 generation 防重放记录。Shutdown 保留失败项并返回 false，之后可以继续重试；supervisor 在显式 Shutdown 未完成时返回退出码 5。

未知文件仍然使删除失败，不扩大允许删除范围。不能把发出信号当作退出成功；实际 waitpid 回收与目录删除仍然决定完成状态。

源码只改已有动态源 `openvpn_backend/files/broker_runtime.h`、`supervisor.cpp`，补 README，新增独占测试 `ci/capability-audit/test_batch_network_vpn_broker_cleanup.py`。完整清单和 SHA256 在 `result.json`。

## 测试

最终定向回归 **4/4 PASS**，见 `broker-regression.txt`：两个新增清理反例、既有双 owner STOP 隔离/重放/清理、协议与 socket framing。新增用例还确认清理阻塞期间 owner/interface 继续拒绝冲突启动、foreign STOP 被拒绝、Identity 不再报告退出任务、清理解除后 STOP 幂等而旧 token 不能重启。编译使用 `-Wall -Wextra -Werror -fsanitize=address,undefined`。

执行目录 `ci/capability-audit`：

```sh
python3 -m unittest test_batch_network_vpn_broker_cleanup test_batch_network_vpn_broker.VpnBrokerTests.test_actual_broker_two_owners_stop_isolation_replay_and_cleanup test_batch_network_vpn_broker.VpnBrokerTests.test_actual_codec_roundtrip_owner_replay_and_socket_framing -v
```

环境为 Darwin 24.1.0 arm64、Python 3.13.7、Homebrew clang 21.1.2。macOS 仅缺失的 prctl 使用显式 no-op double，其余 fork、waitid/waitpid、组、信号和文件系统操作真实。signal 包装只计数并转发真实调用，没有替换退出结果；不能据此声称已实际复用 PID。初始 `/proc` starttime 断言仅在 Linux 运行。未跑实际 FFRT、VPN IPC、TLS 或 TUN。

root 已安排私有 Linux 容器，agent 没有自行启动。相同目录运行以下 **6 项**，补真实 prctl/subreaper/PDEATHSIG 和 `/proc` 语义：

```sh
python3 -m unittest test_batch_network_vpn_broker_cleanup test_batch_network_vpn_broker.VpnBrokerTests.test_actual_broker_two_owners_stop_isolation_replay_and_cleanup test_batch_network_vpn_broker.VpnBrokerTests.test_actual_codec_roundtrip_owner_replay_and_socket_framing test_batch_network_vpn_broker.VpnBrokerTests.test_linux_sigkill_broker_kills_all_descendants_and_reclaims_credentials test_batch_network_vpn_broker.VpnBrokerTests.test_linux_stop_reaps_worker_and_descendant_blocked_on_callback -v
```

## 九项分类

| 原始 ID | 当前分类 | 本批/下一步 |
| --- | --- | --- |
| `arkts_export:@ohos.bluetooth.connection:startPairOutOfBand` | 真实 controller/peer 依赖 | 保留既有真实 OOB 候选，需实际 HCI/vendor/H4 与经典 P192/P256、LE SC peer；不伪造外设 |
| `arkts_export:@ohos.net.vpn:getConnectedSysVpnConfig` | 既有修复待新包 + 本批退出清理修复 | 需真实多 owner TLS/TUN、nullable getter、权限/账号/退出反例 |
| `arkts_export:@ohos.net.vpn:getConnectedVpnAppInfo` | 同上 | 同上，并检查每 owner 身份与断开后可见性 |
| `behavior:netmanager-ebpf-backend` | 既有内核候选待新包 | 新归档实际 syscall、map/program load/attach、UID 统计与访问策略；root 持有内核路径 |
| `behavior:bluetooth-state-transition-false-success` | 真实 controller 依赖 | 确认实际最终 enable/disable、配对数据、off/unplug，而非请求受理 |
| `behavior:wifi-sta-backend-unavailable` | 新包 + 真实兼容 peer 依赖 | 已有 hwsim/virt_wifi/WPA 候选；需 STA/AP/P2P、DHCP/数据、监管与卸载 |
| `behavior:usb-manager-device-query` | 实际设备/UDC/provider 依赖 | 受控 host 设备、真实 UDC/configfs、准确 MtpService；跨域改动请求 root |
| `behavior:peer-device-user-nat-isolation` | 共享 launcher 实现仍缺失 | root 持有所有 scripts；需显式 bridge/tap、唯一 MAC/端口/设备身份及双实例真实发现/认证/数据 |
| `behavior:vpn-runtime-export-gaps` | 既有修复待新包 + 本批退出清理修复 | 完整公共 API、真实 callback/owner/always-on 生命周期；不能据 export 或本批 host PASS 关账 |

九项均保持 open。旧包或历史对象 receipts 不代表本次新包。persist-tun 更新、不可表示的 split/encrypted DNS、非零 route metric 仍未由本批实现。

## root 集成与新包边界验收

无需新增共享接线：既有 installer 应复制当前完整动态源，并重新编译、链接实际 `qemu_openvpn_service`。root 将其他能力域已知修复一次批入，先产 `arm64_virt phone` 代表归档，记录路径、SHA256、环境、命令与结果；完整首包 runtime gate 通过前不要构建余下五包。

新包在两个真实 TLS owner/peer 下检查独立 interface/netId、TUN、DNS、IPv4/IPv6、route、UID 数据隔离，nullable getter、callback、权限与账号边界。针对本批，在 netsys 所属测试 session 中受控加入未知文件，确认 worker/bridge/client 实际退出、STOP 失败保留该 owner/interface、没有向已回收 PGID 重发信号、其他 owner 数据持续可用；移除测试文件后确认周期 Reap 或相同 STOP 清理成功、owner/interface 释放、旧 generation 仍不能重放。不要为故障注入开放公共接口或放宽生产目录权限。

再验 graceful shutdown 清理受阻返回非零、broker SIGKILL 导致 worker/client/bridge parent-death、重启凭据清理与 reconnect，及 blocked descendant、迟到 CONNECTED 撤销、真实 FFRT/IPC 生命周期。peer-device 桥接可复用同一新归档的两个独立实例，无需先建六包。Bluetooth/WiFi/USB/BPF 分别按上表依赖验收；没有实际 peer/backend 的条目继续保持 open。
