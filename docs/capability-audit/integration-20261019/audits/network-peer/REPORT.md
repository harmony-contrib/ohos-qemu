# 网络独有补丁合并审计 374

结论：**1b57a04 确有尚未纳入 a0d6215 的代码，应合入它自身的增量。旧 network scratch 未发现额外未提交的生产修复。** 本任务只读 Git/show/diff 和源码/小文件，不执行候选、测试或外部资源，不改旧树。

## 按文件的实际遗漏

| 路径 | a0d6215 状态 | 建议 |
| --- | --- | --- |
| ci/capability-audit/batch_network_peer_lan.py | 不存在 | 保留新增 422 行。实际两 guest 独立磁盘 staging、archive 对齐、独立 MAC/serial/UUID/HDC/QMP、later HDC 身份/直接 route/ping/neighbor 检查；仍是 L2 candidate。 |
| ci/capability-audit/test_batch_network_peer_lan.py | 不存在 | 保留新增 267 行、10 个 host 方法。后续 root 在合并源上运行；旧 host 成功不是新运行。 |
| scripts/package_standard_qemu.sh | 没有 peer hooks | 取原 commit 的 4 个新增块共 116 行：ensure_qemu_peer_lan_support 函数、common normalize 调用、环境 help、产物 README；保持现有 UTC/校验/PrivacyCenter 逻辑。 |
| docs/capability-audit/parallel/network/round16-peer-lan/README.md | 不存在 | 保留 scope/实际后续步骤。 |
| 同目录 host-backend-contract.json | 不存在 | 保留旧 Darwin binary/help/source 证据，不能当当前 Linux/guest 已通过。 |
| 同目录 host-tests.json、result.json | 不存在 | 保留历史 12 host tests 范围（10 peer + 1 kernel-log + 1 a11y）及 false gate。 |
| 同目录 3 个 test_*.log | 不存在 | 保留原始历史测试证据，不能重写当前源 hash。 |

原 commit 自身仅新增这些块，没有删当前修复。**不能把该旧分支的整个 packager 文件覆盖到当前分支**，两树完整 diff 会回退三组后来修复：RTC UTC 四行；全包递归 SHA256SUMS（旧版只覆盖 images/launch/顶层）；PrivacyCenter 实际 recipe revision 与 source_git_revision 的绑定及 image verifier。完整树 diff 和原 commit patch 已分别保存，供 root 真实合并时核对。

## 与现有 NAT 和 267 的关系

它保留 user NAT 作为管理网，显式开启 listen/connect 时再添加 stream Ethernet 数据 NIC，不把 NAT 模式本身称为能发现 peer。只支持三种 full POSIX product；Windows/minimal 没有新增支持。实际两 VM 未 boot、真实 UDID 独立性未证明、网络服务发现/账号信任/普通 caller 授权 nonce session/移除回调尚缺。prepare 会调用 QEMU help、短暂探端口、复制磁盘，observe 会直接 HDC 运行与可选 peer NIC 配置；这些未来动作必须由 root 接入实际 owner/租约，不能因代码合入直接执行。

267 的 peer 是 original15 的 **Docker OpenVPN TLS peer 与网络**所有者协议；本 commit 是 **两 QEMU guest 的 stream Ethernet**。两条路径互补且不是同一 runner。它不修 267 的 actual constructor ledger/producer、macOS setuid ps UID 接线或原严格 cleanup，267 也不会让两个 guest 自动建立 L2/SoftBus session。

## 旧 network scratch 核对

只读枚举 645 个文件、7,572,695 bytes。BT NAPI 两文件、OOB 服务/GAP 最终 12 文件、broker 最终 10 文件精确 SHA 对应当前 a0 补丁 postimage；额外 bluetooth_host_stub 是原 committed fixture 未改源。callback/session 文件是已记录的较旧 postimage/preimage，直接复制会回退后续 broker 修复。最新 callback/health emitted C++ 的 SHA 精确等于 committed network result 的当前 probe hash，其他 native 目录是旧 emission。OpenVPN extraction 的五个当前 patch target 仍精确包含原 patch preimage 文本，不是漏提交新 port。

edit/fetch/generate 脚本是上述已提交补丁的制作材料，另有日志、header/base64、单一 include 样本与锁。**没有识别出需要并入开发分支的独有生产修复。** 不应把这些 645 文件作为代码全部提交；删除旧 worktree 前可整体保留为可恢复历史附件。scratch 内 broker-source/.git 和 session-source/.git 是嵌入仓库，可能使 managed archive_worktree 拒绝；本任务不移动、不删除、不执行它们。逐文件 hash/来源匹配见 scratch-inventory.json。

合入后建议 root 一次运行 peer 的 10 host tests 及现有 kernel-log、a11y、RTC/完整 checksum/PrivacyCenter 相关既有回归，确认包源合并没有回退。host/source 合并通过后仍遵守先代表包、实际运行验收、再余五包。
