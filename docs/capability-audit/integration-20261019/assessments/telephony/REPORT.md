# 整合后电话 13 项剩余审计

**13 个原 ID 仍未正式销项；12 个接口已有实现/修复与构建接线，不能记作 13 个未实现 API。** 源快照 d60fcd0b97f134744615f970b93b5d6982200b6d，唯一开发分支由 root 指定为 codex/ohos7-integrated-development。

| 当前源码分类 | 数量 |
| --- | ---: |
| RTT listener 已修复，待新包/真实 IMS | 6 |
| RTT 原有操作，phone feature gates 已接通 | 4 |
| communicationState 显式生产链已实现/接入 | 2 |
| 当前设备后端证据不足，需实际接线/行为确认 | 1 |

## 逐 ID 核对

| 原 ID | 已有实现/修复 | 仍需完成 |
| --- | --- | --- |
| arkts_export:@ohos.telephony.call:offReceiveRttMessage | 固定源在 SUPPORT_RTT_CALL 下已有真实 NAPI descriptor 与 call.js 转发；保留真实 IMS event route。 | 未从当前补丁发现还缺本公共方法体；真实 modem/SIM/IMS transport/session 与 provider event 接线不是 callback 补丁所提供，需 root 实际确认。 |
| arkts_export:@ohos.telephony.call:offRttErrCause | 固定源在 SUPPORT_RTT_CALL 下已有真实 NAPI descriptor 与 call.js 转发；保留真实 IMS event route。 | 未从当前补丁发现还缺本公共方法体；真实 modem/SIM/IMS transport/session 与 provider event 接线不是 callback 补丁所提供，需 root 实际确认。 |
| arkts_export:@ohos.telephony.call:offRttModifyInd | 固定源在 SUPPORT_RTT_CALL 下已有真实 NAPI descriptor 与 call.js 转发；保留真实 IMS event route。 | 未从当前补丁发现还缺本公共方法体；真实 modem/SIM/IMS transport/session 与 provider event 接线不是 callback 补丁所提供，需 root 实际确认。 |
| arkts_export:@ohos.telephony.call:onReceiveRttMessage | 固定源在 SUPPORT_RTT_CALL 下已有真实 NAPI descriptor 与 call.js 转发；保留真实 IMS event route。 | 未从当前补丁发现还缺本公共方法体；真实 modem/SIM/IMS transport/session 与 provider event 接线不是 callback 补丁所提供，需 root 实际确认。 |
| arkts_export:@ohos.telephony.call:onRttErrCause | 固定源在 SUPPORT_RTT_CALL 下已有真实 NAPI descriptor 与 call.js 转发；保留真实 IMS event route。 | 未从当前补丁发现还缺本公共方法体；真实 modem/SIM/IMS transport/session 与 provider event 接线不是 callback 补丁所提供，需 root 实际确认。 |
| arkts_export:@ohos.telephony.call:onRttModifyInd | 固定源在 SUPPORT_RTT_CALL 下已有真实 NAPI descriptor 与 call.js 转发；保留真实 IMS event route。 | 未从当前补丁发现还缺本公共方法体；真实 modem/SIM/IMS transport/session 与 provider event 接线不是 callback 补丁所提供，需 root 实际确认。 |
| arkts_export:@ohos.telephony.call:sendRttMessage | 固定源已有真实 NAPI descriptor 与 public call.js；phone profile 同时启用 call_manager_feature_support_rtt 和 cellular_call_support_rtt。 | 未证实当前公共方法体缺失；仍要真实 modem/SIM/IMS session transport/peer 接入。 |
| arkts_export:@ohos.telephony.call:setRttCapability | 固定源已有真实 NAPI descriptor 与 public call.js；phone profile 同时启用 call_manager_feature_support_rtt 和 cellular_call_support_rtt。 | 未证实当前公共方法体缺失；仍要真实 modem/SIM/IMS session transport/peer 接入。 |
| arkts_export:@ohos.telephony.call:startRtt | 固定源已有真实 NAPI descriptor 与 public call.js；phone profile 同时启用 call_manager_feature_support_rtt 和 cellular_call_support_rtt。 | 未证实当前公共方法体缺失；仍要真实 modem/SIM/IMS session transport/peer 接入。 |
| arkts_export:@ohos.telephony.call:stopRtt | 固定源已有真实 NAPI descriptor 与 public call.js；phone profile 同时启用 call_manager_feature_support_rtt 和 cellular_call_support_rtt。 | 未证实当前公共方法体缺失；仍要真实 modem/SIM/IMS session transport/peer 接入。 |
| arkts_export:@ohos.telephony.observer:offCommunicationStateChange | 严格实际 AT +OHOS5A 0/1→HRil notification1412→RIL V1_5 callback162→core→registry IPC14→observer callback13→dynamic NAPI 与 ANI bool/slot。没有 NR 推断或初始 false。 | interface/producer 代码不缺。真实 AT/radio peer 的独立0/1 URC、inherited HDI ABI/ANI 与产品集成、provider false/shutdown/reset discipline 必须在当前包证明。 |
| arkts_export:@ohos.telephony.observer:onCommunicationStateChange | 严格实际 AT +OHOS5A 0/1→HRil notification1412→RIL V1_5 callback162→core→registry IPC14→observer callback13→dynamic NAPI 与 ANI bool/slot。没有 NR 推断或初始 false。 | interface/producer 代码不缺。真实 AT/radio peer 的独立0/1 URC、inherited HDI ABI/ANI 与产品集成、provider false/shutdown/reset discipline 必须在当前包证明。 |
| behavior:telephony-no-modem-or-sim | framework/state query、reference AT/RIL 路由、phone RTT 和真实显式5A生产链都已有源码；它们本身不提供 modem/SIM/radio/IMS 设备。 | 需要实际核对当前 AT device/vendor HDI/radio/SIM/network/IMS identities 与接线，对当下确实不存在的 provider 再实现；本审计未观察实际当前 image/boot/AT/IMS，所以纯缺实现任务数未知。 |

RTT 现有10项 NAPI 和 call.js 并非空导出；phone 的 call_manager/cellular_call 两端 gate 与 shared ICU/provider/history accessor 已接入。6个listener生命周期补丁同时保留真实 IMS route。另两项 communicationState 有严格真实 AT→HRil→HDI→core→registry→NAPI/ANI bool/slot 数据链；shared builder 第3106–3109行已接入 IDL preparation/component，不应照旧认为这一整条 producer 仍待从零实现。

这些接口仍需真正新包公共导出/权限/参数、modem/IMS事件、真实会话数据与off/退出/撤权静默。communication off 需要 mandatory callback+optional slot，不能混用 RTT optional callback off 语义。具体每 ID pending assertions、源 patch/hash/行号在 INVENTORY.json。

历史两完整 ARM64 RTT TU 与通信完整 Rust dylib pass 只证明所注明源/诊断范围，不能销本新包 ID。广义 no-modem/SIM finding 尚无当前设备 AT/HDI/SIM/IMS 观测；其实际缺实现任务数未知，不能据旧无SIM结果宣称新源码仍缺，也不能据 framework/source plumbing 通过宣称 radio/network已存在。

仅计入 owner=location 的电话13项，Location9 和 apps 的 APN/number identity 不重复计数。phone gates 不推及其他五包；所读2in1 profile无对应显式RTT assignment，后续各profile仍须独立核对。

本任务只读主树/固定 Git objects/小JSON；无候选 import、测试、SDK/编译/签名/Docker/VM/HDC 或 Git/产品修改。旧 network 工作区未访问。
