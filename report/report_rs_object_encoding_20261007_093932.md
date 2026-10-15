# OpenHarmony 稳定性代码审查报告

**检视目标**: `patches/common/foundation/graphic/graphic_2d/async_caller_identity/0009-encode-and-retain-real-binder-objects-in-rs-transactions.patch`  
**检视时间**: `2026-10-07 09:39:32 +0800`  
**检视框架版本**: OpenHarmony Stability Code Review Framework `0.1.0`  
**检出问题总数**: `0`  
**严重程度分布**: CRITICAL(0), HIGH(0), MEDIUM(0), LOW(0)  
**规则覆盖**: `57` 条规则（`9` 个稳定性分类）

---

## 检视概览

### 代码信息

- **代码路径**: Docker `ohos-qemu-capability-inspect` 内冻结 `exact-component-stacks-object-05` 的 `async_caller_identity/foundation/graphic/graphic_2d`。IPC 对象安全直链使用同一快照的 `binder_object_safety/foundation/communication/ipc`；其余必要直接调用链只读固定容器源码，不读取宿主同名 checkout。
- **代码行数**: 六个受 0009 修改的生产文件共 10907 行；范围为新增编码及必要 Binder、Parcel、profiler、解包/主线程队列调用链，不是 graphic/IPC 全仓审查。
- **功能描述**: 两类 sptr 标准 Binder 编码、普通异步 owning 副本、带真实对象的版本化 ashmem sidecar、DBinder PTR/strong pair、部分失败与跨线程取消时资源释放。
- 固定 graphic commit 为 `81cc9ca9509bccd86c435064136fe45591d29eeb`，IPC 为 `b8d3e96cfcf382c8fae54502679ac8b3d827b428`；manifest 为 `f079c4ad9848f9cc4a9a4b3a3613ad8fbb142549`。
- 使用已完整读取的 `@ohos-graphics/stability-code-review` package `0.1.1`；本报告框架版本严格采用 SKILL 元数据 `0.1.0`。该包的 CLI 是安装器，不冒充自动静态扫描。九分类独立只读审查后由主 agent 去重汇总，均返回空问题列表。
- 本报告不重新覆盖原身份修复的全部文件，也不把上一轮十项问题仅由“本轮零新问题”认定为 guest 已修复。完整统一栈编译、实际新包 Binder/UI、ArkWeb/Vulkan 和六包验收仍需单独证据。首包行为门槛为 false。

### 问题统计

| 严重程度 | 检出问题数 | 占比 | 说明 |
|---------|---------|------|------|
| CRITICAL | 0 | 0% | 未检出确定新增问题 |
| HIGH | 0 | 0% | 未检出确定新增问题 |
| MEDIUM | 0 | 0% | 未检出确定新增问题 |
| **总计** | **0** | **不适用** | **零问题时不计算分布比例** |

### 分类问题分布

| 分类名称 | 规则数量（已检视/总数） | 检出问题数 | 严重程度 |
|---------|---------|-----------|---------|
| 异常处理 | 3/3 | 0 | — |
| 并发稳定性 | 5/5 | 0 | — |
| 性能稳定性 | 2/2 | 0 | — |
| 资源管理 | 7/7 | 0 | — |
| 初始化顺序 | 1/1 | 0 | — |
| 边界条件 | 18/18 | 0 | — |
| 生命周期 | 2/2 | 0 | — |
| 内存稳定性 | 7/7 | 0 | — |
| 图形稳定性 | 12/12 | 0 | — |
| **总计** | **57/57** | **0** | **—** |

---

## 检出问题详情

### CRITICAL 级别问题（0 个）

无。

### HIGH 级别问题（0 个）

无。

### MEDIUM 级别问题（0 个）

无。

### 检视依据与限定

- 异常：新增路径无 try/catch/throw；对象/FD 写读、布局、还原和容量操作的失败会向上返回。部分 Parcel 构建由 RAII 清理，不用日志代替失败返回。
- 并发：重编码在原 Binder 请求有效期完成，发布后不继续写同一个 Parcel；队列按值捕获 owning shared_ptr。不同 shared_ptr 实例共享控制块不误报为同一实例读写竞争。新 ashmem worker 为 null，不跨线程 FlushBuffer/手动释放；既有 request TLS 和 once permit 保留。
- 性能：新 helper 为有界循环，无直接递归。DBinder 标准 writer 的间接再写使用 `IsProxyObject=false` 的 callback stub，只有额外一层。标准 HANDLE 首次读取可能有既有同步协议协商，不声称每次读取纯本地；callback 业务仍通过 TF_ASYNC。临时 dup、payload 重建有真实开销，未做性能实测。
- 资源/内存：快照只持 payload，不发布 offsets、不 AcquireObject、不解引用原始 cookie/PTR buffer。标准 writer 保留 sptr 与 DBinder backing；FD read 临时副本 A 在 writer 创建目标副本 B 后关闭，目标 Parcel 单独管理 B。FD 0 合法。malloc 的 ParseFrom 失败由调用者 free，成功仅 Parcel 管理，无双重 free。
- 初始化：slot 字段、计数/版本、对齐 object locals 和输出 sptr 均有明确初始化或标准零值语义；失败输出先复位。
- 边界：负数/大 count、乘加溢出、四字节合法偏移、对象跨度/重叠、PTR flags/length/相邻 strong pair、侧带 kind、读取完整性和 trailing bytes 均在发布前检查。原始 payload 中未登记的伪对象不能通过 Parcel::CheckOffsets；重编码跨度改变时重建后续字段与 offsets。
- 生命周期：原请求、侧带和重建 Parcel 各自拥有明确生存期；原请求销毁后队列仅持已重编码的真实对象，不借用输入地址。取消或最后持有者在另一线程析构仍由 owning Parcel 释放。
- 图形：新 helper 不持 GPU Surface/Image/VulkanCleanupHelper，不改 Drawable 执行职责。callback 标准解码经 iface_cast 创建 Proxy，再由 TF_ASYNC 发往持有者 Stub；不是在 RS 解引用应用指针。SyncFence 副本仍由既有 reader 接管，无新 fence 缓存或 semaphore FD 导出。
- 新包实际验证仍需两类命令、普通/ashmem、原请求返回后延迟解包、取消、持有者死亡，以及真实 callback 所在进程和实际 compositor pixels；静态审查与 fixture sanitizer 不替代这些行为。

---

## 修复优先级建议

### 第一优先级（CRITICAL，0 个）

本轮无新检出。

### 第二优先级（HIGH，0 个）

本轮无新检出。

### 第三优先级（MEDIUM，0 个）

本轮无新检出。继续完成真实三 ABI 编译及首包运行门槛，不由零问题报告放行其余五包。

---

## 附录

### 白名单过滤

- 六个目标生产文件均未匹配技能白名单；未用测试、fuzz 或示例文件代替生产直链证据。
- 各分类完整读取相应规则、问题模板及白名单；不适用项已核实新增路径不含相应对象/操作，而非跳过规则。

### 冻结输入校验

0009 patch SHA-256：`30e298da9b70d78fd62ba2ed3dc84f3bb61dcdaba9220d894c4127f0b07a8064`。
下表“前”为固定 pristine 在内存应用 0001–0008 后，“后”为审查的实际 05 快照。

| 文件（相对 graphic_2d） | 前 SHA-256 | 后 SHA-256 |
|---|---|---|
| rosen/modules/render_service/core/transaction/zidl/rs_client_to_render_connection_stub.cpp | a5253aab95399004410d6bee38c8678040f2221c16e794c538084d1b9b254d00 | 228baf8e2271551f22494fbf1535289fffd77af5da7cdf90f3dfa1ce98d92abb |
| rosen/modules/render_service/main/render_server/transaction/zidl/rs_client_to_service_connection_stub.cpp | cfb06dcb4dc05d13e03fa000ed627f148d4f0e7560e085938ba7d8c1fbdfa454 | 30dd8e172641dd1235ce64f0cec53b799d21607ae7e179663106919c05a39c78 |
| rosen/modules/render_service_base/src/platform/ohos/rs_ashmem_helper.cpp | dde9d016ac9f1f3b4a1008016b4ab9c0e707f6160ffe4ea24e180c9f1a612e74 | 7242e372b9905a6ea932c4f55dd98f2efaa040f84807d8878d56a334ff787019 |
| rosen/modules/render_service_base/include/transaction/rs_ashmem_helper.h | b240f668ad283c6a23b51e3bb923f264b219ee648e439e59a74806d83a227b2a | 0e823e9f6b5361258ddf09b444dcc05fce0fdafe4af61902909adb7e9d0abb10 |
| rosen/modules/render_service_base/include/transaction/rs_marshalling_helper.h | 75f1842940e2862632c1a66459bccda6c81fafc96f49040199bb24898fec59b6 | 336f6d89e82cb317fe122b46062221c89b204760d6522b5135823cb06e8bbbf7 |
| rosen/modules/render_service_base/src/platform/ohos/rs_marshalling_helper.cpp | 0761db50b4b13546e792bba0bbed30c3511598e7ed5e73ec61965eca6541f791 | 6c7dd5fd1224d04db09af75261b8c7a5460b9f6485620f0e1a3d499b73e141fe |

独立分类检视前后六文件哈希一致；没有源码、构建或 VM 写入。

---

**报告生成时间**: `2026-10-07 09:39:32 +0800`  
**报告生成者**: Agent
