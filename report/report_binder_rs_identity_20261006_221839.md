# OpenHarmony 稳定性代码审查报告

**检视目标**: `patches/common/kernel/linux/linux_6_6/binder_async_sender`、`patches/common/foundation/graphic/graphic_2d/async_caller_identity`  
**检视时间**: `2026-10-06 22:18:39 +0800`  
**检视框架版本**: OpenHarmony Stability Code Review Framework `0.1.0`  
**检出问题总数**: `7`  
**严重程度分布**: CRITICAL(3), HIGH(3), MEDIUM(1), LOW(0)  
**规则覆盖**: `57` 条规则（`9` 个稳定性分类）

---

## 检视概览

### 代码信息

- **代码路径**: 两个组件应用到固定 Release 真源的只读候选，以及其直接 IPC 身份、事务反序列化、清理调用链。
- **代码行数**: 9605 行（三个直接修改文件：binder.c 6965、binder_internal.h 582、RS stub 2058；依赖链另作定向阅读，不代表全仓扫描）。
- **功能描述**: 保留异步 wire PID=0，内核持有真实发送任务 TGID 引用；RS 仅对异步 COMMIT 的零 PID 使用内核身份。kernel HEAD `14c77f1541a53e814d89ad6dea5f7f211f9895a6`；graphic HEAD `81cc9ca9509bccd86c435064136fe45591d29eeb`；IPC HEAD `b8d3e96cfcf382c8fae54502679ac8b3d827b428`。候选 binder.c SHA-256 `63c44d8b611ea9992eb0f6882d4323b08a5d69464f49033b53252bf7959d4e9a`；候选 stub SHA-256 `dbcad168e6055c8fd4e5ab36874c48f30cbbb135b04d345889eb94c3b9da368f`。这是修复前的检视快照：问题 4 为本次新增，其余为直接链继承问题。未修改检视对象；未证明新包启动、UI、Vulkan 像素或六包验收通过。

### 问题统计

| 严重程度 | 检出问题数 | 占比 | 说明 |
|---------|---------|------|------|
| CRITICAL | 3 | 42.86% | OOM 空指针与 ashmem 边界越界风险 |
| HIGH | 3 | 42.86% | 身份引用泄漏、单例发布竞争、返回值丢失 |
| MEDIUM | 1 | 14.28% | 未定义协议枚举值被接受 |
| **总计** | **7** | **100%** | **/** |

### 分类问题分布

| 分类名称 | 规则数量（已检视/总数） | 检出问题数 | 严重程度 |
|---------|---------|-----------|---------|
| 异常处理 | 3/3 | 1 | HIGH 1 |
| 并发稳定性 | 5/5 | 1 | HIGH 1 |
| 性能稳定性 | 2/2 | 0 | — |
| 资源管理 | 7/7 | 0 | 泄漏与内存分类去重 |
| 初始化顺序 | 1/1 | 0 | — |
| 边界条件 | 18/18 | 3 | CRITICAL 2、MEDIUM 1 |
| 生命周期 | 2/2 | 0 | — |
| 内存稳定性 | 7/7 | 2 | CRITICAL 1、HIGH 1 |
| 图形稳定性 | 12/12 | 0 | — |
| **总计** | **57/57** | **7** | **CRITICAL 3、HIGH 3、MEDIUM 1** |

---

## 检出问题详情

### CRITICAL 级别问题（3 个）

#### 问题 1: 拷贝 Parcel 未检查偏移表注入失败便解引用

**分类**: 内存稳定性  
**规则**: StabilityCodeReview_MemoryStability_002 - 指针解引用前判空 - CRITICAL  
**位置**: `foundation/graphic/graphic_2d/rosen/modules/render_service/core/transaction/zidl/rs_client_to_render_connection_stub.cpp:148`  
**函数**: `CopyFileDescriptor` / `CopyParcelIfNeed`

**关键源码片段**:

```cpp
138 | binder_size_t* object = reinterpret_cast<binder_size_t*>(old.GetObjectOffsets());
139 | binder_size_t* copiedObject = reinterpret_cast<binder_size_t*>(copied.GetObjectOffsets());
141 | size_t objectNum = old.GetOffsetsSize();
143 | uintptr_t data = old.GetData();
144 | uintptr_t copiedData = copied.GetData();
146 | for (size_t i = 0; i < objectNum; i++) {
147 |     const flat_binder_object* flat = reinterpret_cast<const flat_binder_object*>(data + object[i]);
148 |     flat_binder_object* copiedFlat = reinterpret_cast<flat_binder_object*>(copiedData + copiedObject[i]);
```

**问题描述**: 继承问题。c_utils `Parcel::InjectOffsets:314–325` 返回 void；`EnsureObjectsCapacity:692–694` 的 realloc 失败会静默跳过对象。首个对象失败时 copiedObject 可为空，部分失败时数量也不匹配；调用者仍以原数量复制 FD。成功 ParseFrom 后 base 已归 Parcel 所有，后续错误分支的手工 free 也应移除，但其可达性未独立证明，未另计 double-free 问题。

**风险流分析（RiskFlow）**:

```text
风险来源: 复制普通事务时偏移表分配失败
    ↓
传播路径: void InjectOffsets 静默失败 → 按原对象数量 CopyFileDescriptor
    ↓
影响点: copiedObject[i] 空指针或表外访问
```

**影响分析 (ImpactAnalysis)**:

```text
触发条件: 大事务或较多 FD 触发复制且对象表 OOM
    ↓
传播方式: RS 在复制 FD 之前未检查已注入对象表
    ↓
后果: RS 崩溃；尚未运行故障注入验证
```

**修复建议**: 注入后确认数量和地址；失败时先 FlushBuffer 清除尚未 dup 的借用 FD 元数据，再返回，避免析构误关原 FD。成功 ParseFrom 后由 Parcel 唯一释放 base。

```cpp
205 | parcelCopied->InjectOffsets(old.GetObjectOffsets(), objectNum);
206 | if (parcelCopied->GetOffsetsSize() != objectNum || parcelCopied->GetObjectOffsets() == 0) {
207 |     parcelCopied->FlushBuffer();
208 |     return nullptr;
209 | }
210 | CopyFileDescriptor(old, *parcelCopied);
```

---

#### 问题 2: ARM32 ashmem 偏移数量乘法回绕

**分类**: 边界条件  
**规则**: StabilityCodeReview_BoundaryCondition_016 - 内存操作越界风险 - CRITICAL  
**位置**: `foundation/graphic/graphic_2d/rosen/modules/render_service_base/src/platform/ohos/rs_ashmem_helper.cpp:474`  
**函数**: `RSAshmemHelper::ParseFromAshmemParcel`

**关键源码片段**:

```cpp
472 | int32_t offsetSize = ashmemParcel->ReadInt32();
473 | if (offsetSize > 0) {
474 |     auto* offsets = ashmemParcel->ReadBuffer(sizeof(binder_size_t) * offsetSize);
475 |     if (offsets == nullptr) {
476 |         ROSEN_LOGE("ParseFromAshmemParcel: read object offsets failed");
477 |         return nullptr;
478 |     }
480 |     dataParcel->InjectOffsets(reinterpret_cast<binder_size_t>(offsets), offsetSize);
482 |     InjectFileDescriptor(dataParcel, ashmemParcel, ashmemFdWorker, callingPid);
483 | }
```

**问题描述**: 继承问题，关联 BoundaryCondition_001/011/015。ARM32 size_t 为 32 位；W=sizeof(binder_size_t) 时数量 `2^32/W+1` 让 ReadBuffer 长度回绕为 W，InjectOffsets 仍按原巨大数量读取。实际 ARM32 Binder64 协议 W=8，种子 `0x20000001`；不能假定 Binder32。ReadBuffer 只验证已回绕长度，ashmem dataSize 流控不限制偏移数量。

**风险流分析（RiskFlow）**:

```text
风险来源: 外层 Parcel 中的正 int32 偏移数量
    ↓
传播路径: 32 位长度乘法回绕 → 读取短表 → 按原数量注入
    ↓
影响点: 偏移表越界读及无效扩容
```

**影响分析 (ImpactAnalysis)**:

```text
触发条件: ARM32、小可映射 ashmem、巨大偏移数量和短表
    ↓
传播方式: InjectOffsets 循环超出实际可读缓冲区
    ↓
后果: RS 崩溃或资源耗尽；未证明攻击可利用性
```

**修复建议**: 用成功读取、非负检查、对象上限及除法边界约束数量，然后乘法；注入完成后再确认对象表完整。

```cpp
472 | int32_t offsetSize = 0;
473 | if (!ashmemParcel->ReadInt32(offsetSize) || offsetSize < 0) { return nullptr; }
474 | const size_t count = static_cast<size_t>(offsetSize);
475 | if (count > MAX_OBJECTNUM ||
476 |     count > ashmemParcel->GetReadableBytes() / sizeof(binder_size_t)) { return nullptr; }
477 | const size_t bytes = count * sizeof(binder_size_t);
```

---

#### 问题 3: ashmem 对象偏移加法回绕绕过范围校验

**分类**: 边界条件  
**规则**: StabilityCodeReview_BoundaryCondition_016 - 内存操作越界风险 - CRITICAL  
**位置**: `foundation/graphic/graphic_2d/rosen/modules/render_service_base/src/platform/ohos/rs_ashmem_helper.cpp:377`  
**函数**: `RSAshmemHelper::InjectFileDescriptor`

**关键源码片段**:

```cpp
372 | binder_size_t* object = reinterpret_cast<binder_size_t*>(dataParcel->GetObjectOffsets());
373 | size_t objectNum = dataParcel->GetOffsetsSize();
374 | uintptr_t data = dataParcel->GetData();
375 | for (size_t i = 0; i < objectNum; i++) {
376 |     binder_size_t offset = object[i];
377 |     if (offset + sizeof(flat_binder_object) > dataParcel->GetDataSize()) {
378 |         ROSEN_LOGW("RSAshmemHelper::InjectFileDescriptor offset invalid");
379 |         continue;
380 |     }
381 |     flat_binder_object* flat = reinterpret_cast<flat_binder_object*>(data + offset);
382 |     if (flat->hdr.type == BINDER_TYPE_FD || flat->hdr.type == BINDER_TYPE_FDR) {
```

**问题描述**: 继承问题，关联 BoundaryCondition_011/015。偏移从外层 Parcel 原样注入，接近 binder_size_t 最大值时加法回绕；随后 data+offset 访问缓冲区外对象。仅一个恶意偏移即可触发，不依赖问题 2；内层 interface token 检查发生在此后。未声称任意地址写或权限绕过已实测。

**风险流分析（RiskFlow）**:

```text
风险来源: 未验证的 ashmem 对象偏移
    ↓
传播路径: 对象末端加法回绕 → 范围判断通过 → 指针访问
    ↓
影响点: hdr 越界读，类型命中时 handle 越界写
```

**影响分析 (ImpactAnalysis)**:

```text
触发条件: 可映射 ashmem 及接近整数最大值的偏移
    ↓
传播方式: 先读取非法对象头，再有条件修改 handle
    ↓
后果: RS 崩溃或内存破坏风险；没有运行时利用证明
```

**修复建议**: 在注入/访问前校验整张表，使用减法边界及协议对齐，非法表拒绝整个 Parcel；错误清理不得遍历无效对象表或关闭借用 FD。

```cpp
376 | const binder_size_t offset = object[i];
377 | const size_t dataSize = dataParcel->GetDataSize();
378 | if (offset > dataSize ||
379 |     sizeof(flat_binder_object) > dataSize - static_cast<size_t>(offset) ||
380 |     offset % alignof(flat_binder_object) != 0) {
381 |     return false;
382 | }
```

---

### HIGH 级别问题（3 个）

#### 问题 4: 冻结更新事务销毁路径遗漏身份引用释放

**分类**: 内存稳定性  
**规则**: StabilityCodeReview_MemoryStability_004 - 多返回路径资源泄漏 - HIGH  
**位置**: `kernel/linux/linux-6.6/drivers/android/binder.c:2875`  
**函数**: `binder_proc_transaction`

**关键源码片段**:

```cpp
2867 | if (t_outdated) {
2868 |     struct binder_buffer *buffer = t_outdated->buffer;
2870 |     t_outdated->buffer = NULL;
2871 |     buffer->transaction = NULL;
2872 |     trace_binder_transaction_update_buffer_release(buffer);
2873 |     binder_release_entire_buffer(proc, NULL, buffer, false);
2874 |     binder_alloc_free_buf(&proc->alloc, buffer);
2875 |     kfree(t_outdated);
2876 |     binder_stats_deleted(BINDER_STAT_TRANSACTION);
2877 | }
```

**问题描述**: 本次新增。get_task_pid 得到的引用在普通销毁和分配/翻译错误路径释放，但冻结接收者的 TF_UPDATE_TXN 会销毁同发送者/节点/code/flags 的旧事务，直接 kfree 未 put_pid。三类事务销毁形态必须全部覆盖。引用保活 struct pid 并不保证数字 PID 不复用；未证明 UAF 或节点归属绕过。资源管理分类交叉确认并在此去重。

**风险流分析（RiskFlow）**:

```text
风险来源: 每个 one-way 事务取得一个真实 TGID 引用
    ↓
传播路径: 冻结期间更新事务替换旧队列项 → 直接 kfree
    ↓
影响点: 旧事务的 struct pid 引用永不释放
```

**影响分析 (ImpactAnalysis)**:

```text
触发条件: frozen 接收者和连续 TF_ONE_WAY|TF_UPDATE_TXN
    ↓
传播方式: 被替换事务累计遗留引用
    ↓
后果: 内核资源泄漏；已静态确认，尚未测量真实引用计数
```

**修复建议**: 在旧事务专属销毁路径加对称 put_pid；不要调用 binder_free_transaction，因为 outstanding_txns 已在队列移除时减过。

```cpp
2874 | binder_alloc_free_buf(&proc->alloc, buffer);
2875 | #ifdef CONFIG_BINDER_SENDER_INFO
2876 | put_pid(t_outdated->async_sender_pid);
2877 | #endif
2878 | kfree(t_outdated);
```

---

#### 问题 5: BinderConnector 单例双重检查使用未同步裸指针

**分类**: 并发稳定性  
**规则**: StabilityCodeReview_ConcurrencyStability_001 - 多线程场景线程安全设计缺失 - HIGH  
**位置**: `foundation/communication/ipc/ipc/native/src/core/invoker/source/binder_connector.cpp:244`  
**函数**: `BinderConnector::GetInstance`

**关键源码片段**:

```cpp
242 | BinderConnector *BinderConnector::GetInstance()
243 | {
244 |     if (instance_ == nullptr) {
245 |         std::lock_guard<std::mutex> lockGuard(skeletonMutex);
246 |         if (instance_ == nullptr) {
247 |             BinderConnector *temp = new (std::nothrow) BinderConnector(BINDER_DRIVER_DEFAULT);
248 |             if (temp == nullptr) {
249 |                 ZLOGE(LOG_LABEL, "create BinderConnector failed");
250 |                 return nullptr;
251 |             }
```

**问题描述**: 继承 IPC 基线问题。instance_ 是普通裸指针，外层读不持有发布写使用的 skeletonMutex。IPCProcessSkeleton 首次初始化会先启动 pthread 工作线程，该线程和首次 IPC 调用者均可构建各自 TLS BinderInvoker 并进入 GetInstance，没有共同初始化锁保证。

**风险流分析（RiskFlow）**:

```text
风险来源: 首次 IPC 的工作线程与调用者同时初始化
    ↓
传播路径: 未锁 instance_ 读取与持锁写入并发
    ↓
影响点: 单例发布产生 C++ 数据竞争
```

**影响分析 (ImpactAnalysis)**:

```text
触发条件: 首次 Binder 初始化并发
    ↓
传播方式: 未同步发布构造后的 connector
    ↓
后果: 不可靠单例状态；未执行目标平台并发复现
```

**修复建议**: 统一锁住所有 GetInstance 读写，保留 OpenDriver 失败后的重试语义；不能以一次性 call_once 隐藏失败。

```cpp
244 | std::lock_guard<std::mutex> lockGuard(skeletonMutex);
245 | if (instance_ == nullptr) {
246 |     // 原有创建及 OpenDriver 成败处理保持不变。
247 | }
248 | return instance_;
```

---

#### 问题 6: COMMIT 分支丢弃提交错误码

**分类**: 异常处理  
**规则**: StabilityCodeReview_ExceptionHandling_003 - 需校验函数返回值 - HIGH  
**位置**: `foundation/graphic/graphic_2d/rosen/modules/render_service/core/transaction/zidl/rs_client_to_render_connection_stub.cpp:394`  
**函数**: `RSClientToRenderConnectionStub::OnRemoteRequest`

**关键源码片段**:

```cpp
386 | auto transactionData = ParseTransactionData(dataParcel.get());
387 | if (transactionData && isNonSystemApp) {
389 |     if (!transactionData->IsCallingPidValid(callingPid, nodeMap)) {
390 |         ROSEN_LOGE("RSClientToRenderConnectionStub invalid calling pid");
391 |     }
392 | }
394 | CommitTransaction(transactionData);
395 | break;
```

**问题描述**: 继承问题；同分支 :429 合并。CommitTransaction 在缺失 pipeline agent 或数据丢弃时返回 ERR_INVALID_VALUE，但 Stub 的 ret 保持 ERR_NONE。正常客户端 TF_ASYNC 不读取这个处理返回值，因此不能宣称异步客户端错误回复、崩溃或已执行拒绝命令；真正影响是服务端/直接同步调用的错误传播。IsCallingPidValid 会标记无效命令，Process 会跳过，校验未被绕过。

**风险流分析（RiskFlow）**:

```text
风险来源: 无有效 agent 或提交数据被丢弃
    ↓
传播路径: CommitTransaction 错误被忽略 → OnRemoteRequest 返回默认成功
    ↓
影响点: 服务端及直接同步提交的错误信息失真
```

**影响分析 (ImpactAnalysis)**:

```text
触发条件: 提交函数明确返回失败
    ↓
传播方式: Stub 不保存返回值
    ↓
后果: 错误诊断及同步结果不可靠；不声称改变异步 wire 协议
```

**修复建议**: 两处直接提交均保存现有错误码，不增加异步 reply、不更改权限检查。

```cpp
394 | ret = CommitTransaction(transactionData);
395 | break;
```

---

### MEDIUM 级别问题（1 个）

#### 问题 7: 事务 scene 和 followType 接受协议未定义枚举值

**分类**: 边界条件  
**规则**: StabilityCodeReview_BoundaryCondition_005 - Parcel整数转枚举需校验有效性 - MEDIUM  
**位置**: `foundation/graphic/graphic_2d/rosen/modules/render_service_base/src/transaction/rs_transaction_data.cpp:440`  
**函数**: `RSTransactionData::UnmarshallingCommand`

**关键源码片段**:

```cpp
430 | int32_t pid;
431 | uint8_t scene = 0;
432 | int32_t tid = -1;
433 | bool flag = parcel.ReadBool(needSync_) && parcel.ReadBool(needCloseSync_) &&
437 |     parcel.ReadUint64(index_) && parcel.ReadUint64(syncId_) && parcel.ReadInt32(parentPid_) &&
438 |     parcel.ReadBool(dvsyncTimeUpdate_) && parcel.ReadUint64(dvsyncTime_) &&
439 |     parcel.ReadUint8(scene);
440 | scene_ = static_cast<RSTransactionDataScenes>(scene);
```

**问题描述**: 继承问题。scene 仅 Default=0/Rebuild=1；非 uni 分支 :424 的 FollowType 仅 0/1/2。其他 uint8 值未被拒绝，下游将非法 scene 当普通事务、非法 followType 当 SELF 路由。固定 uint8_t 底层枚举转换不等于 C++ 未定义行为，未证明崩溃或越权。

**风险流分析（RiskFlow）**:

```text
风险来源: Parcel 中完整但协议未定义的枚举数值
    ↓
传播路径: 直接转换 → 下游部分枚举比较
    ↓
影响点: 非法事务状态仍被接受并路由
```

**影响分析 (ImpactAnalysis)**:

```text
触发条件: scene>1 或非 uni followType>2
    ↓
传播方式: 反序列化保持成功
    ↓
后果: 协议校验与事务分类不一致
```

**修复建议**: 读取成功后验证定义值域；在 payload/scene_ 赋值前返回失败。

```cpp
440 | if (!flag ||
441 |     (scene != static_cast<uint8_t>(RSTransactionDataScenes::Default) &&
442 |      scene != static_cast<uint8_t>(RSTransactionDataScenes::Rebuild))) {
443 |     return false;
444 | }
445 | scene_ = static_cast<RSTransactionDataScenes>(scene);
```

---

## 修复优先级建议

根据严重程度和影响范围，建议按以下优先级修复：

### 第一优先级（CRITICAL，3 个）

1. **内存稳定性**: 偏移表 OOM 后拒绝不完整复制并正确清理所有权（1 个）。
2. **边界条件**: 先校验数量、单项偏移和对齐，再注入 ashmem 对象表（2 个）。

### 第二优先级（HIGH，3 个）

1. **内存稳定性**: 补全 frozen TF_UPDATE_TXN 销毁引用释放（1 个，新增补丁缺陷，必须先修）。
2. **并发稳定性**: 统一锁住 connector 单例读写，保持驱动打开失败重试（1 个）。
3. **异常处理**: 保留两处 CommitTransaction 错误码（1 个）。

### 第三优先级（MEDIUM，1 个）

1. **边界条件**: 拒绝未知 scene/followType，增加合法及非法协议回归（1 个）。

---

## 附录

### 白名单过滤

- 文件路径: 两个候选组件直接修改的生产文件及其直接调用链均未匹配白名单。
- 全局路径: `test/`、`tests/`、`unittest/`、`mock/`、`mocks/`、`example/`、`examples/`、`samples/`、`build/`、`out/`、`.git/`；测试及生成文件只用于定位，不作为生产缺陷。
- 文件模式: `*_test.cpp/h`、`*_unittest.cpp/h`、`*_fuzztest.cpp/h`、`*.pb.cc/h`、`*.generated.*`、`*.auto.*`；无启用的规则级白名单。
- 九个分类由九个独立检视任务遍历，主检视完整读取全部 57 规则并复核去重。图形分类排除了已加锁的 UIExtension 节点集合和异步远端 callback 误报；初始化分类核验 kzalloc、TLS 和嵌套身份恢复；性能分类确认读取 real PID 使用已缓存 ioctl 身份，没有新增查询或等待。
- 身份传播局限: RS 直接 CommitTransaction 下游重新 GetCallingPid，统计仍可能合并为 PID 0。该值用于事务数量统计，不是重新授权；需要独立实现阶段补全可信身份传播，不能因本报告声称 UI 已修复。
- 检视工具版本: npm 包 `@ohos-graphics/stability-code-review@0.1.1`，SKILL metadata.version `0.1.0`，status `trial`。包内 CLI 是技能安装器，并非已运行的自动 C++ 扫描器。本报告为按规则文档人工辅助只读检视。
- 新包门槛: false。三 ABI 对象编译、35 项旧私有内核诊断和本检视都不满足 AGENTS.md 的新代表包启动验收要求。

---

**报告生成时间**: `2026-10-06 22:18:39 +0800`  
**报告生成者**: Agent
