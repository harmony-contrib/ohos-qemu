# 网络/外设/VPN 缺口盘点 373

按历史完整清单和当前分工逐 ID 对齐，本方向仍有 **9 个未销项 ID：VPN 3、网络与外设 6**。本新包新增广义 ID 闭合为 0。历史 199 个已闭合不可移植为当前同包同 boot 的结果，9 个 ID 也不等于 9 个完全未实现的功能。

| 只读结论 | 数量 | ID/内容 |
| --- | ---: | --- |
| 已有候选，当前包完整行为待验 | 4 | 两个 connected VPN getter、eBPF、WiFi |
| 源码/接线仍有明确未补齐点 | 3 | Bluetooth OOB、默认 NAT/peer 实际所有者接线、广义 VPN 的明确不支持选项 |
| 当前 backend 尚无新观测，不能断言当下仍缺实现 | 2 | Bluetooth 最终开关状态/真实控制器、USB UDC/设备模式/MTP |

每项已有源码、具体缺口、证据边界及引用见 inventory.json；其 9 个 ID 与权威清单分组、F 的 network assignment 完全相等，没有跨方向重复纳入。Bluetooth/USB 两项保留历史 open，建议先采集本包真实状态；没有据旧包缺失结果声称新源码必然未实现。

238 只准备新鲜 credentials/SDK/config 输入；其 host 通过不能充当实际 generic VPN 执行。267 是纯协议库，实际 constructor guard/ledger producer 未接入，并明确保留 macOS ps UID 身份阻塞；它不是 ready peer runner。Generic VPN 不可达 endpoint 的 setup/destroy/清理子集也不能替代成功 TLS/TUN、getter、完整 options 或广义分布式 peer。

并行建议：网络 agent 可独占 VPN/BT/WiFi 的各自源范围先分析和写候选，不能操作共享 kernel/BUILD/init/packager。USB MTP 的 HAP/provider 由应用/媒体 owner 给 root 接线建议，避免双改。root 串行管理 SDK、credentials、Docker、VM/HDC、共享网络/端口，先原始首包全门槛再其余五包。当前只读审计不创建资源、不运行候选或测试、不修改 Git/产品/旧证据。

源锚点 a0d6215 为 parent 提供；本任务未调用 Git。F-current-progress 顶层 source_commit 仍为历史 2f0，较后 batched_source_commit359 才记录 a0d6215，已保存本次原始快照而不把顶层旧值当当前源码。
