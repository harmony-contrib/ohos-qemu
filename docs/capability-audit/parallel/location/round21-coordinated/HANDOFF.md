# 定位与电话：协调批次交接

本批交付 location API 26 runtime 的第 7 补丁，修复真实 GNSS producer 的无效输入/UTC 使用，以及 fusion WLAN 观察者的扫描代际。22 条基线需求仍全部开放：2 条已有实现待新包验收，20 条仍依赖真实 provider、硬件或对端，同时保留下述仓库内生命周期缺口。没有把 host 双替身、旧对象构建或既有包当作运行时闭环。

## 修改与可复现反例

- `GnssEventCallback::ReportLocation` 原先把缺少 latitude/longitude 有效位的默认值和 NaN/Inf/越界坐标直接标记为真实 GNSS 位置。第 7 补丁只要求这两个坐标有效位；horizontalAccuracy 是独立可选字段，仅在其有效位置位时校验有限/非负。缺少 accuracy 位时保留其原始数值（包括默认、旧值或 NaN）与清零的位，普通坐标继续转发，不补造精度。合法极点、经度 ±180 和有有效位的 0 精度仍通过。该 producer 门控只覆盖 normal HDI `ReportLocation`，未声称审核了所有缓存/RTK producer。
- **核心审查纠正**：已提交的初始候选 `cf32293` 把可选 accuracy 设为必需，这一限制没有明文 HDI/consumer 契约支持，已在本次修正。真实 `Location::GetFieldValidity() const` 返回 `int32_t`，copy/Parcel 保留该位；默认 accuracy=0、validity=0 不能代表已测得 0 误差。`RecordSkiingTrack` 和 `OnFusionFenceLocation` 现在直接检查保留的 accuracy 位，未知精度对这两个 consumer 静默。新增测试实际复现 cf32293 拒绝合法无 accuracy 坐标，以及旧 consumer 把未知 0 精度用于轨迹/围栏的反例。没有关闭任何 ID。
- 原函数在 UTC 有效位缺失、时间为 0 或负数时仍调用 `SetGpsTime`。修后仅在 `GNSS_LOCATION_TIME_VALID` 与正 UTC 时间同时满足时向时钟接口提供样本；位置本身仍允许没有可用 UTC 的有效测量。
- `OnFusionFenceWifi` 原先无扫描代际，重复/旧完成快照可覆盖新状态并生成反向 enter/exit。修后增加私有 `wifiScanTime`，按完成时间接受严格递增快照。AP 观测时间继续决定 freshness，且允许在新扫描中保持相同值；不能用最旧 AP 时间直接去重。取消/同名重注册仍使用原 record 生命周期，旧 record 回调保持静默。
- 新测试先对实际 `prefix_6` 函数执行 3 类 GNSS/时钟反例与 WLAN 重放反例，全部得到预期断言失败；随后对同一函数的第 7 补丁版本验证通过。测试没有实现或伪造 GNSS、WLAN、modem、IMS 对端。

上游仅改四个已有 component target：`interfaces/inner_api/include/constant_definition.h`、`services/location_gnss/gnss/source/gnss_event_callback.cpp`、`services/location_locator/locator/source/report_manager.cpp`、`services/location_locator/locator/source/locator_ability.cpp`。没有新增 GN、IPC、产品配置、init、SELinux、SDK 接线或 source target。`source_states.json` 保留 original/prefix1..6 状态及前六补丁哈希，更新四个 final 完整文件哈希和修订后的第 7 补丁哈希。cf32293 旧 strict 候选不是本修订的合法前缀，guard 会拒绝并保留源；root 应从已知 prefix6 或干净固定源准备。

## 轻量验证与证据边界

环境：Darwin 24.1.0 arm64，Homebrew clang 21.1.2，Python 3.13.7。locale 固定为 C；实际 C++ 函数采用 ASan/UBSan。修正后的定向 14 项全部通过（33.890 秒），含新旧反例、actual HDI bit 契约、普通回调/两个 precision consumer、WLAN replay、已有 skiing/fusion 生命周期、全部合法前缀/idempotence 与未知/过期 strict 候选拒绝。随后将过期候选 fixture 加强为重建完整 cf32293 两个已改 target，单项复核也通过（0.961 秒）。原初始候选的 host 记录保留为历史，不当作当前兼容行为证明。完整命令与原始日志见 `result.json` 和 `core-review-correction-host.log`。

获 root 窄只读租约后，仅在现存 `ohos-qemu-parallel-source-20261016-02` 容器核对 Location 声明/实现、GNSS callback、ReportManager、fusion 与相关头部；读取完已报告释放。未写 source/out、未读 out/SDK，未启动新容器、SDK、构建、VM 或包矩阵。实际 Location 声明 SHA-256 与 getter/位保留契约保存在 `fixtures/batch_location/location_accuracy_compatibility_before.json`。

沿用而未重做既有 `round8-full-rust.json`（完整 Rust dylib 编译/链接证据）与 `round7-communication-build-map.json`（实际通信生成/链接元数据）。这些仍是相应旧输入的证据，不证明本批新归档运行结果。现有 `.tmp/parallel-capability-20261016/run_location*` 和外部 r52 构建失败材料均未修改。

## 向 root 的集成与新包验收请求

1. 收齐其它域修复后，由 root 用现有 component apply 流程准备源。无需新增 patch-plan 项；目录内第 7 补丁按排序自动应用。现有合法原始/前缀/final guard 的公开语义保持。重新编译本批三个完整 TU（GNSS callback、ReportManager、LocatorAbility），并让常量头部的正常依赖构建生效；记录实际产物，不以 host harness 替代平台构建。
2. 只制作一个新 `arm64_virt phone` 代表归档，记录包路径、SHA-256、环境、命令和结果。先完成新包行为验收，再决定其它五包；本 agent 没有制作包，也没有关闭账本。
3. 通过 root 独立受控 GNSS 轨迹经 vendor → HDI → `ReportLocation` 验证：LAT/LONG 逐项缺失、NaN/Inf 坐标、经纬界外不产生普通位置回调/缓存/skiing 点/fusion 事件；accuracy 位置位时其 NaN/Inf/负值拒绝。LAT/LONG 有效但 accuracy 位清零时，原坐标、原字段与位必须普通转发，包括 accuracy 原始 0/旧值/NaN；skiing/fusion 不据未知精度添加点/边界结论。±90/±180 与有效 0 精度合法。有效位置缺少 UTC 或 UTC ≤ 0 时不提供时钟样本；合法 UTC 仍实际到达时钟服务。恢复有效精度后继续处理，无进程/服务异常。
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
