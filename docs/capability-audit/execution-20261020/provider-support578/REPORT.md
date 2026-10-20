当前 fixed7 默认纯 QEMU 产品没有完整可交付的蜂窝 modem/SIM/IMS RTT 提供者，也没有接通 OpenHarmony vendor ABI 的蓝牙 controller/peer 提供者。建议将这些**完整正向会话**限定为当前产品不支持；这不是公共 API 方法缺失，也不能把电话13与蓝牙2整个原 ID 一起免验。逐 ID 的支持范围、仍需镜像验证的行为和输入列在 [PER-ID.json](PER-ID.json)。现有 nine unsupported 表未改，本轮不新增整 ID 排除。

电话的明确边界：

- SIG 文档明确 IMS 只提供框架，服务由芯片厂商实现，见固定社区文档[第26行](https://gitcode.com/openharmony/community/blob/e1c6afd655a02cb52b853a8f5055a832b3e007eb/sig/sig_telephony/sig_telephony_cn.md#L26)。fixed cellular_call 的 vendor/ims 确实存在；[Dial 第38–51行](https://github.com/openharmony/telephony_cellular_call/blob/4e644b8a8f5e7c6be04261bd128fc71dfe9fa09c/vendor/ims/services/ims_call/src/ims_call.cpp#L38)是本地默认 callback 的 demo，不是完整 IMS 网络/peer。其类未实现 RTT vendor override，不能用它冒充 RTT 服务。
- fixed RIL [vendor_adapter.c 第339–370行](https://github.com/openharmony/telephony_ril_adapter/blob/81fac83292857fcd9bee90808a81d8ad7224b4e0/services/vendor/src/vendor_adapter.c#L339)会实际打开配置的 AT 设备并运行读循环和 ModemInit；reference AT 库不是虚拟 modem、SIM、网络或完整 IMS。
- fixed call_manager [头文件第29–31行](https://github.com/openharmony/telephony_call_manager/blob/42f264011d0a44a300e3e8b825863754916cb6a8/services/rtt_call/include/ims_rtt_manager.h#L29)及[InitRtt 第43–58行](https://github.com/openharmony/telephony_call_manager/blob/42f264011d0a44a300e3e8b825863754916cb6a8/services/rtt_call/src/ims_rtt_manager.cpp#L43)要求 `/dev/voice_proxy_rtt`，后续真实 read/write/ioctl；缺失时返回错误。feature 开关、框架和 SDK 不能提供这个媒体设备协议。
- 因而 RTT10 的真实协商、peer 文本、修改/错误事件正例缺完整当前 QEMU 后端；权限、参数、on/off、无会话错误、设置本地 capability 和退出清理仍需真实新镜像验收。`behavior:telephony-no-modem-or-sim` 的无设备状态和失败语义尤其不能排除。
- observer2 有现存真实 AT→HRil→HDI→core→registry→公共 callback 链，见本仓库 `patches/common/base/telephony/state_registry/communication_state/README.md:3–24`。它们不宜仅因没有完整运营商网络而判 API 不支持。可在同一原 Owner 下用配置的真实 AT 端点和受控 peer 发送明确标注虚拟来源的独立 `+OHOS5A: 1/0`，保留 wire/AT/HDI/public 原始关联；还要验证 slot、非法 URC、权限、off 队列静默和 reset。此处是可执行输入边界，并未证明当前镜像已接通或通过。

蓝牙的明确边界：

- fixed service [bluetooth_hdi.cpp 第25–45行](https://github.com/openharmony/communication_bluetooth_service/blob/c489d0aabf77624a4f5ca80ab8b5adefd2d5cfbf/services/bluetooth/hardware/src/bluetooth_hdi.cpp#L25)依赖真实 IHciInterface。fixed drivers [vendor_interface.cpp 第65–167行](https://raw.githubusercontent.com/openharmony/drivers_peripheral/69094b77aa2200160207b1b06b3c0b586ae2157c/bluetooth/hci/hdi_service/implement/vendor_interface.cpp)要求 vendor 库导出 ABI、init/power/channel-open，并从实际 fd 收发 H4/MCT；[第170–197行同文件](https://raw.githubusercontent.com/openharmony/drivers_peripheral/69094b77aa2200160207b1b06b3c0b586ae2157c/bluetooth/hci/hdi_service/implement/vendor_interface.cpp)是实际关闭/断电清理。
- QEMU vendor [HCS 第44–54行](https://github.com/openharmony/vendor_ohemu/blob/b56c5a95ec590543691278b85afe9fe228744163/virt/hdf_config/uhdf/device_info.hcs#L44)只选择通用 HCI HDI loader。完整 fixed device_qemu/vendor_ohemu 树和内容查询未提供该 vendor ABI/controller 实现；SIG QEMU [manifest 第6–8行](https://gitcode.com/openharmony-sig/manifest/blob/d679e50d1ed091d9e07fc28d3ab7ceba5d385bc3/chipsets/qemu/qemu.xml#L6)也是这两个产品仓库。泛型 transport、内核 USB/HCI 选项或物理芯片样例不等于完整 QEMU 控制器移植。
- `startPairOutOfBand` 的有效 controller/peer 配对正例因此限定不支持于当前默认产品。已有 GAP/HCI 代码仍有公共权限/参数/关机错误、C/R 消耗、失败取消和清理职责；本仓库 OOB README 的 LE legacy P192、缺 R、virtual alias、local generation 限制必须精确保留，不能把所有 OOB 形式统一扩大成 801。
- `behavior:bluetooth-state-transition-false-success` 在缺 controller 的镜像中仍可且必须验：enable 失败后真实最终 OFF、无假 ON/paired/data、重复关闭及退出清理。它不应被完整排除。USB 的可虚拟设备枚举/热插拔完全不在本结论排除范围。

现有源的实际集成方向是接入真实 modem/SIM + 厂商完整 IMS/RTT 媒体设备 + 网络/peer，或者完成一个真实虚拟 modem/IMS/RTT 协议后端；蓝牙是实现上述 vendor ABI 到真实 HCI 控制器及独立 peer 的整条通路。这些都不是已存在、只待开关的完整默认 QEMU 后端。当前批次不应为它们伪造成功桩或直接公共 callback。若以后提供了完整可分发后端，当前产品限定应重新审查。

取证范围是 root 的417 XML/8110行 SIG catalog 选取相关项目、九个相关项目的完整 current 树、四份 OH7 分支树、六个相关项目的完整 fixed 树，以及 fixed drivers 的三份直接依赖源。`FINDINGS.json` 给出14项精确版本/路径/行范围，`SOURCE-EVIDENCE.json` 给出完整原始源字节身份；`SOURCE-QUERIES.json` 保留完整产品查询及 exit1 的有限含义。GitCode fixed-SHA 拉取失败及 GitHub tree API 403均只记录为取证限制，没有用来证明能力不存在。drivers fixed 全树获取未完成，已核的 exact-SHA 三源和 OH7/master 完整树分开标记；并未把分支头重标 fixed。

本轮只有源获取、读取和分析，无宿主测试、SDK、编译、Owner、Docker、Orb、QEMU、HDC、签名或验收。没有读取新镜像的 vendor 文件/设备/服务状态，所有新镜像行为结果为 null。唯一验收仍是父方原 Owner 下实际新 QEMU 镜像；源码支持范围不充当 guest 通过或正式账本关闭。
