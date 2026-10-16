本批仅修改 Contacts host runtime verifier/driver/测试与 apps 报告，四份普通 caller ETS、种子/observer fixture、产品源、共享脚本均不改。没有 SDK/native 编译、QEMU/HDC 运行。

Contacts UIExtension 的 bundle 归属不能作为唯一提供方证明。固定只读源 `ohos-qemu-parallel-source-20261016-02:/ohos` 中，UITest `test/testfwk/arkxtest/uitest/server/element_node_iterator_impl.cpp:263` 直接使用 AccessibilityElementInfo.GetBundleName；Ace `adapter/ohos/osal/js_accessibility_manager.cpp:598` 将 provider 子树挂在 host UIExtensionComponent 下，`ConvertExtensionAccessibilityId` 包装远端 ID。`frameworks/core/components_ng/pattern/ui_extension/ui_extension_manager.h:49` 的当前最大包装 offset 为 100000000000。Contacts 真正公开 NAPI 已使用 CreateModalUIExtension，因此必须兼容这种通用 host 机制，但不能把它宣称为 Contacts 首包实测。

已有真实旧 Photos 文件：`/Volumes/PSSD/qemu/validation/first-20261005/issue-20-20261006/r18-photos-asset-diagnostic-03/007-actual-picker-read.log` SHA256 `f5f5809a389d5d985b2356af876d45c1d60e7e593d0ed704fa93aff09f20b898`。其 UIExtensionComponent accessibilityId=41/hostWindowId=29；子节点 Complete/currentSelectCount/Third_Select_PickerClose 没有显式 bundleName，继承 ordinary host `org.harmonycontrib.capabilityaudit`；远端 accessibilityId 为1099511627xxx。另 r14-photos-asset-diagnostic-05 同名原始文件 SHA256 `8f609fc06ca874dffd91dee55ead88a2ce2bb5856242b31cbd08358d3d964b5e` 同样如此。这两份文件均没有本批核验过的配对 AMS，不能冒称 Contacts 或当前新包运行证据。

本批收紧并使用真实 AMS 证据：

- driver 自动采实际 Contacts BMS（系统应用、当前 account100 UID），保留 caller Start 前 AMS；每次 picker 输入前验证真实 Contacts provider，完成输入后有界采 AMS 与即时布局。
- parser 严格消费 `ContactUiExtentionAbility`、`/com.ohos.contacts/entry/...数字` URI、AbilityRecord ID、root-host bundle/entry/EntryAbility、BMS provider/caller UID、真实 provider/host PID 与双向连接。foreign live extension、错 module/ability/UID/PID/host、重复 record、缺失或截断 dump 均拒绝。
- 每次 terminal 输入前后必须恰好关闭一个真实 live AMS session，其余 session 身份不变；记录 URI+AbilityRecord ID 不得用于多个 public invocation。双 session 验证真实 `2→1→0` 连续状态。没有假定 ArkUI UIExtension ID 等于 AMS record ID。固定 ui_extension_ability_manager.cpp:211/960 的 key 是 element URI+GetUIExtensionAbilityId；UIExtensionRecordFactory::NeedReuse 只有显式配置 UIEXTENSION_ABILITY_ID 才复用，普通新 modal 不配置。SYS_COMMON_UI 的 PROCESS_MODE_BUNDLE 允许共享进程，本 parser 并不要求两个 session 的 provider PID不同。关闭过程中进程记录暂时不齐只允许有界重采，最终原始证据仍须完整。exit/reopen 的 AMS host PID另须等于独立 AppMgr 真实进程 API 的对应 PID。
- host-owned 节点只在唯一 visible UIExtensionComponent 子树内接受 unique selectedText/doneButton、实际 hostWindowId、真实远端包装 accessibilityId；取消 ID 也须位于该子树、同一窗口且是远端节点。输入后同一 wrapper 必须不再可见，再由 AMS 唯一关闭差集绑定本次 session。普通 caller Column/子树外预览、混合窗口/local ID/重复控件、仍可见旧 wrapper 全拒绝。change-selection 还必须保持同一 host/window/wrapper。
- direct provider bundle 路径也必须具备同样 AMS/UID/session 证明，不能仅凭 UI 字段。driver 的选择、全选和完成输入均先验证 live provider；现有 caller journal、六种 overload、205条真实值及权限/清理检查保留；205计数必须真实显示205/205，不能把204/205中的limit当selected。

新增 host 正反例覆盖以上绑定；这些是 transport-model/parser 检查，不是运行证据。Contacts 当前实际 UI tree 与 AMS session 销毁时序仍须在代表新包首次 guest 验收中采集；不支持/不明确的布局会有界失败并保留 raw，不扩大排除。

MSDP 共享 checker 只读评审结果已由根接管修复：

1. 原 `check_inventory` 可接受两份仅64字节 ELF头（ELF64 little-endian ET_DYN/AArch64）、任意 graph/object hash、`not-a-compiler -c nonexistent -o nowhere`，只要 source/recipe 标成当前值且 DSO 自身 hash 匹配。没有 mock ELF/编译器；实际 host 调用曾返回成功。原 `elf(cfi=False)` 没有完整解析，packaged inventory 自选 CFI，source mode 也没有强制重建/链接见证。镜像比较只跟随同份 files_sha256，不能补足来源。最小反例保存在 msdp-original-counterexample.py。
2. 根新护栏的直接复核已真实拒绝原64byte反例：False→`all three standard MSDP products require cross-DSO CFI`；True→`MSDP ELF lacks complete program headers`。根已加入 raw GN/完整命令、强制移走9对象+2库的相关15项生成产物、真实完整日志、begin/finish witness 和镜像 hash。stamp 不是运行证明。本批未执行 begin/finish 或实际新包构建。
3. 发现新护栏会阻真包的动态符号要求：service 私有 RetireAlgo 被 singleton.versionscript 的 `local:*` 隐藏，不能要求它出现在 dynsym。真实固定旧 service DSO 的 `llvm-nm -D --defined-only` 仅14项（没有任何 DeviceStatusMsdpClientImpl 方法）；真实GN链接包含 singleton.versionscript，其 global 仅 _init/_fini/*delegator_E/*instance_E/*mutex_E。根已确认移除私有方法契约，不改产品导出。可用真实稳定业务导出为 `_ZN4OHOS4Msdp12DeviceStatus18DelayedSpSingletonINS1_19DeviceStatusServiceEE9instance_E`、对应 `_ZN4OHOS4Msdp12DeviceStatus18DelayedSpSingletonINS1_19DeviceStatusServiceEE6mutex_E` 与 __cfi_check。
4. 窄复核 actual GN AArch64 target 为 --target=aarch64-linux-ohos；unit_source 推导的9份真实 cpp 路径均在固定源存在，phone/2in1 sensor features 形状相同。暂未发现其他确定的 begin/finish/sourceHash shape 真包阻塞。下次完整真实 build/finish/image 仍由根验证，不能由 metadata 单测核销。

所有34 apps ID仍未核销，累计53真实 upstream target无新增；本批只补验收代码与报告。
