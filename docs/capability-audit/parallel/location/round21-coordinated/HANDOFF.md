# 定位与电话：协调批次交接

本批交付 location API 26 runtime 的第 7 补丁，修复真实 GNSS producer 的无效输入/UTC 使用，以及 fusion WLAN 观察者的扫描代际。22 条基线需求仍全部开放：2 条已有实现待新包验收，20 条仍依赖真实 provider、硬件或对端，同时保留下述仓库内生命周期缺口。没有把 host 双替身、旧对象构建或既有包当作运行时闭环。

## 修改与可复现反例

- `GnssEventCallback::ReportLocation` 原先把缺少 latitude/longitude/horizontalAccuracy 有效位的默认值和 NaN/Inf/越界数据直接标记为真实 GNSS 位置，继而送入 locator 缓存、普通回调、skiing 和 fusion。第 7 补丁要求三项必需有效位与合法数值；合法的极点、经度 ±180 和 0 精度仍可通过，保留实际字段/validity 位。该门控只覆盖 normal HDI `ReportLocation`，未声称审核了所有缓存/RTK producer。
- 原函数在 UTC 有效位缺失、时间为 0 或负数时仍调用 `SetGpsTime`。修后仅在 `GNSS_LOCATION_TIME_VALID` 与正 UTC 时间同时满足时向时钟接口提供样本；位置本身仍允许没有可用 UTC 的有效测量。
- `OnFusionFenceWifi` 原先无扫描代际，重复/旧完成快照可覆盖新状态并生成反向 enter/exit。修后增加私有 `wifiScanTime`，按完成时间接受严格递增快照。AP 观测时间继续决定 freshness，且允许在新扫描中保持相同值；不能用最旧 AP 时间直接去重。取消/同名重注册仍使用原 record 生命周期，旧 record 回调保持静默。
- 新测试先对实际 `prefix_6` 函数执行 3 类 GNSS/时钟反例与 WLAN 重放反例，全部得到预期断言失败；随后对同一函数的第 7 补丁版本验证通过。测试没有实现或伪造 GNSS、WLAN、modem、IMS 对端。

上游仅改两个已有完整文件：`services/location_gnss/gnss/source/gnss_event_callback.cpp` 与 `services/location_locator/locator/source/locator_ability.cpp`。没有新增 GN、IPC、产品配置、init、SELinux 或 SDK 接线。`source_states.json` 保留此前所有状态/补丁哈希，把原 final 保存为 `prefix_6`，仅更新上述两个 final 完整文件哈希并登记第 7 补丁。

## 轻量验证与证据边界

环境：Darwin 24.1.0 arm64，Homebrew clang 21.1.2，Python 3.13.7。locale 固定为 C；实际 C++ 函数采用 ASan/UBSan。完整命令与结果见 `result.json` 和 `host-checks.log`。新增 producer 测试 4 项通过；相邻 GNSS、fusion 生命周期及 3 项 source guard 共 5 项通过。最终审查将 enum 明确限定到真实 HDI 命名空间后，受影响的 GNSS producer、相邻 GNSS 与全部合法前缀 3 项复核也通过。未重跑全 suite，未读写共享 source/out，未启动 SDK、容器构建、VM 或包矩阵。

沿用而未重做既有 `round8-full-rust.json`（完整 Rust dylib 编译/链接证据）与 `round7-communication-build-map.json`（实际通信生成/链接元数据）。这些仍是相应旧输入的证据，不证明本批新归档运行结果。现有 `.tmp/parallel-capability-20261016/run_location*` 和外部 r52 构建失败材料均未修改。

## 向 root 的集成与新包验收请求

1. 收齐其它域修复后，由 root 用现有 component apply 流程准备源。无需新增 patch-plan 项；目录内第 7 补丁按排序自动应用。现有合法原始/前缀/final guard 的公开语义保持。重新编译本批两个完整 TU 并记录实际产物，不以 host harness 替代平台构建。
2. 只制作一个新 `arm64_virt phone` 代表归档，记录包路径、SHA-256、环境、命令和结果。先完成新包行为验收，再决定其它五包；本 agent 没有制作包，也没有关闭账本。
3. 通过 root 独立受控 GNSS 轨迹经 vendor → HDI → `ReportLocation` 验证：必需位逐项缺失、NaN/Inf、经纬界外、精度负值均不产生普通位置回调/缓存/skiing 点/fusion 事件；±90/±180 与 0 精度合法。有效位置缺少 UTC 或 UTC ≤ 0 时不提供时钟样本；合法 UTC 仍实际到达时钟服务。恢复有效流后继续回调，无进程/服务异常。
4. 同一新包覆盖 icon 的真实 PrivacyKit start/stop、普通/系统查询、freeze/account/switch/revoke；skiing 的 SPORT-only、真实几何/高度/速度/方向、增量读取、24h 保留、owner/delegation、停止与晚样本。新输入门控不能成为只测错误分支的理由。
5. 在真实 HCI/WLAN/CELL 条件具备后验证 fusion：相同完成扫描不二次改变状态，旧完成回调不能覆盖新状态；更新完成扫描即使保留仍新鲜的 AP 时间仍可更新状态。撤权、同名重注册、退出与 provider 静默后的 expiry/PrivacyKit retry 同时覆盖。当前 host 证据不能替代真实扫描结果。

## 剩余依赖与审查发现

22 条逐项分类、相应 producer、依赖、下一步见 `result.json` 的 `requirements_review`。本批不降低任何要求或用直接数据库写入制造成功。

- fusion 的 GNSS 子路由已有请求/owner/fine-use 实现，但真实 WLAN/CELL 与 BLE bitmap 8（目前明确返回 801）仍不构成全能力闭环。
- geocoder 仍需真实、受配置/签名且有行政区边界来源的 reverse-geocoder provider；BLE search 仍需实际 HCI/controller 广告与 BleCentralManager 通路。
- RTT 的 10 个 API 已有现存 IMS/回调生命周期实现与 host 检查，实际 IMS 协商会话和独立文本/modify/error 对端仍缺。`+OHOS5A` 不能替代 RTT、SIM、电话、SMS 或数据网络。
- communication 的显式 5A producer/registry/NAPI/ANI 代际已经存在，当前完整冻结 `TelRilCallback::RadioStateUpdated` 只通知 modem 模块，`communicationStates_` 没有 radio-off/reset 失效接线。这是已确认的仓库内后续缺口，不能仅补真实 modem 后关账。需先由 root 授权获取实际 radio enum/producer reset 契约的窄上游只读快照，再修正确的失效语义并验证不会在 unknown 启动时合成 false。本批未猜枚举值。
- CELL 聚合跨多个 slot；不应照搬 WLAN 去重把最旧 cell 时间当整批代际，否则其它 slot 的合法更新会丢失。后续如修并发/重放须携带真实 poll generation 或独立 per-cell identity/时间，补同时间多 slot 更新、断连/旧响应和无有效样本边界。

所有修改均位于本 agent 独占的 location prefixes；Git index/commit、共享 verifier/runner/ledger、source/out、SDK、QEMU 与包装验收仍由 root 独占。工作槽位可释放。
