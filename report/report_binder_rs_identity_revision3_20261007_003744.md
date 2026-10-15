# OpenHarmony 稳定性代码审查报告

**检视目标**: `patches/common/kernel/linux/linux_6_6/binder_async_sender`、`patches/common/foundation/communication/ipc/binder_connector_initialization`、`patches/common/foundation/communication/ipc/binder_object_safety`、`patches/common/foundation/graphic/graphic_2d/async_caller_identity`  
**检视时间**: `2026-10-07 00:37:44 +0800`  
**检视框架版本**: OpenHarmony Stability Code Review Framework `0.1.0`  
**检出问题总数**: `10`  
**严重程度分布**: CRITICAL(1), HIGH(6), MEDIUM(3), LOW(0)  
**规则覆盖**: `57` 条规则（`9` 个稳定性分类）

---

## 检视概览

### 代码信息

- **代码路径**: Docker `ohos-qemu-capability-inspect` 内的冻结候选，以及固定 OpenHarmony 7.0 Release 真源中的直接调用链。RS 候选根为 `/tmp/render-connection-reply-compile-1i7db9zv/foundation/graphic/graphic_2d`；IPC 对象候选根为 `/tmp/render-connection-reply-compile-f74pxkrd/foundation/communication/ipc`；connector 候选根为 `/tmp/render-connection-reply-compile-82n4anwb/foundation/communication/ipc`；内核候选根为 `/tmp/binder-async-three-abi-02/source/kernel/linux/linux-6.6`。主源码/out 只读，host 同名目录不是本轮真源。
- **代码行数**: 17468 行，11 个候选生产文件；范围为修改及直接身份、事务、对象、资源、调度链，不是完整 graphic/IPC 全仓扫描。
- **功能描述**: 第三轮复核可信异步身份、请求作用域、单例发布、ashmem 私有快照、对象表边界、FD/FDR 接收端所有权、合法四字节 Binder 对齐、SFC 主线程转交与内核 PID 引用。kernel HEAD `14c77f1541a53e814d89ad6dea5f7f211f9895a6`；graphic HEAD `81cc9ca9509bccd86c435064136fe45591d29eeb`；IPC HEAD `b8d3e96cfcf382c8fae54502679ac8b3d827b428`。
- 11 个冻结文件的检视前后 SHA-256 一致：stub.cpp `68fd941836f1f8a85d7aae646347619c5b366df42eb2f57ac581a4c2aa6c1da3`；stub.h `87d649d5dd35390aa28f32dc10e3978a56084881a574fcb40ca115e9b4b72b55`；connection.cpp `ff0a630a19a82a53dd2915533fde0eab4630d0a99cbbfc11d311265c04dde863`；ashmem.cpp `91913591ff9f63243b679b54a928ecb5d2f5545c87ef4623d60169c267684a46`；transaction.cpp `6032bb30c7863c0b8d861d24add0e73f578f752754e88309fa8265921dca3ede`；pipeline.cpp `1063afbf85036770590610949a8d08b37ef2bec10abae0d0cd83f7991cf33801`；invoker.cpp `69712745d700f4c424efb10b59a9857bcbb3407fb5af75932ab5ee65871e4e85`；parcel.cpp `475d32feb3bdd697456a8ba19181a43cae2d5c2744bca717d7cf3fbb0b7ef397`；connector.cpp `5bcf46aaaf0d6614c511b143dfc76e3c65d68ce181060490d6c4428d0f28fe57`；binder.c `e0d365c6c671b47f054f7d0af1162162a17e6b7d8b3a80a5d97eda8e5565a1cd`；binder_internal.h `deea4d03ca9b0284fdf024963c93db2d32b8a6e81ef7901acd37fbdf35a7b2ea`。
- 9 个独立分类检视均完成。Memory 的三个资源问题与 Resource 去重；Exception 的入队失败问题并入队列边界；Graphics 的委托权限观察经直接链核实并入 Exception。前两轮已修复问题不重复计数。
- 不将 `-fno-exceptions` 产品中的不可达 catch、智能指针控制块共享、带独立锁的 UIExtension 查询或合法四字节对象偏移误报。`hasCommand=0` 不加入 payload，未证明 delegate 的空命令循环外部可达，不计缺陷。`GetPixelmap` 的另一线程节点查询是范围外观察，应在其 API 验证中另处理。
- 本报告是只读检视快照，以下建议尚未完成；不证明完整共享库、新包普通应用像素、ArkWeb、Vulkan 或六包通过。首包行为门槛为 false。问题1涉及私有对象编码的客户端/服务端配套修复，已请求用户确认；不能以原身份修复批准代替新编码批准。

### 问题统计

| 严重程度 | 检出问题数 | 占比 | 说明 |
|---------|---------|------|------|
| CRITICAL | 1 | 10% | 外部字节被解释为引用计数指针 |
| HIGH | 6 | 60% | 线程身份、资源、队列和委托权限直接链 |
| MEDIUM | 3 | 30% | 原子计数、FD0哨兵、条件性错误类型转换 |
| **总计** | **10** | **100%** | **/** |

### 分类问题分布

| 分类名称 | 规则数量（已检视/总数） | 检出问题数 | 严重程度 |
|---------|---------|-----------|---------|
| 异常处理 | 3/3 | 1 | HIGH 1；入队返回值并入边界问题 |
| 并发稳定性 | 5/5 | 3 | HIGH 2、MEDIUM 1 |
| 性能稳定性 | 2/2 | 0 | 递归规则未检出，不代表循环无成本 |
| 资源管理 | 7/7 | 4 | HIGH 2、MEDIUM 2 |
| 初始化顺序 | 1/1 | 0 | — |
| 边界条件 | 18/18 | 2 | CRITICAL 1、HIGH 1 |
| 生命周期 | 2/2 | 0 | — |
| 内存稳定性 | 7/7 | 0 | 三项与资源分类合并 |
| 图形稳定性 | 12/12 | 0 | 委托权限补充与异常分类合并 |
| **总计** | **57/57** | **10** | **CRITICAL 1、HIGH 6、MEDIUM 3** |

---

## 检出问题详情

### CRITICAL 级别问题（1 个）

#### 问题 1: 已注册应用绘制命令将 Parcel 字节解释为 sptr 指针

**分类**: 边界条件  
**规则**: StabilityCodeReview_BoundaryCondition_016 - 内存操作越界风险 - CRITICAL；关联 BoundaryCondition_014  
**位置**: `foundation/graphic/graphic_2d/rosen/modules/render_service_base/include/transaction/rs_marshalling_helper.h:142`  
**函数**: `RSMarshallingHelper::Unmarshalling<T>`

**关键源码片段**:

```cpp
127 | template<typename T>
128 | using is_not_pointer_or_shared_ptr =
      std::enable_if_t<!std::is_pointer<T>::value && !is_shared_ptr<T>::value, bool>;
135 | template<typename T, typename = is_not_pointer_or_shared_ptr<T>>
136 | static bool Unmarshalling(Parcel& parcel, T& val)
137 | {
138 |     if (const uint8_t* buff = parcel.ReadUnpadBuffer(sizeof(T))) {
142 |         val = *(reinterpret_cast<const T*>(buff));
143 |         return true;
144 |     }
145 |     return false;
146 | }
```

**问题描述**: 泛型排除了 raw pointer/std::shared_ptr，却没有排除 OHOS::sptr。实际注册 type3/subtype11 的 APP 命令参数包含 `sptr<IRemoteObject>`，type3/subtype53 包含 `sptr<RSIBufferAvailableCallback>`；真实 ARM64 command factory 对象具有这些实例。`sptr` 复制赋值会调用外部字节指定地址的 IncStrongRef，早于命令 PID/权限过滤。私有快照与 FD 对齐修复不能消除这个解释过程。

**风险流分析（RiskFlow）**:

```text
风险来源: 应用绘制命令参数字节
    ↓
传播路径: 已注册命令 → 泛型 Unmarshalling<sptr<T>> → 引用计数访问
    ↓
影响点: RS 在未经认证的进程地址访问内存
```

**影响分析 (ImpactAnalysis)**:

```text
触发条件: 非空无效指针值；正常发送方地址也不是接收方有效地址
    ↓
传播方式: sptr 赋值调用 IncStrongRef
    ↓
后果: 崩溃或内存破坏；本轮未运行 guest 攻击验证
```

**修复建议**: 排除所有 sptr 的原始内存编码，为 remote object/callback 使用明确 Binder 编码。ashmem 对象也必须通过外层 Binder 翻译后恢复，不能直接信任快照中的 handle/cookie/PTR。客户端/服务端配套更新；不能只改成 memcpy。三 ABI 的实际 invoker argv 均无 CONFIG_IPC_SINGLE，不能以 target 名称排除 DBinder/PTR 分支。

```cpp
1 | // 示意，须完成可空语义、callback类型和ashmem配套验证。
2 | static bool Unmarshalling(Parcel& parcel, sptr<IRemoteObject>& object)
3 | {
4 |     object = static_cast<MessageParcel&>(parcel).ReadRemoteObject();
5 |     return object != nullptr;
6 | }
```

---

### HIGH 级别问题（6 个）

#### 问题 2: worker 的最终析构线程不保证是建立 FD TLS 的线程

**分类**: 并发稳定性  
**规则**: StabilityCodeReview_ConcurrencyStability_001 - 多线程场景线程安全设计缺失 - HIGH  
**位置**: `foundation/graphic/graphic_2d/rosen/modules/render_service_base/src/platform/ohos/rs_ashmem_helper.cpp:427`  
**函数**: `AshmemFdWorker::~AshmemFdWorker`；直接链 `RSUnmarshalThread::RecvParcel`

**关键源码片段**:

```cpp
415 | AshmemFdWorker::~AshmemFdWorker()
416 | {
417 |     if (needManualCloseFds_) {
418 |         for (const int fd : fdsToBeClosed_) {
419 |             if (fd >= 0) {
420 |                 ::close(fd);
421 |             }
422 |         }
423 |     }
424 |     if (!isFdContainerUpdated_) {
425 |         return;
426 |     }
427 |     AshmemFdContainer::Instance().Clear();
428 | }
```

**问题描述**: 容器是 thread_local；PostTask/ParallelTask 接收 const function& 并复制闭包。执行任务可以比 producer 局部闭包更早释放，因此 worker 最后在 producer 析构，关闭 FD 并清理错误线程的容器。unmarshal 线程留下过期、可能已复用的 FD 映射；ReadSafeFd 发现数字不一致只警告，仍 dup containerFd。

**风险流分析（RiskFlow）**:

```text
风险来源: 异步闭包副本造成不确定最终析构线程
    ↓
传播路径: unmarshal 建立 TLS → producer 最终关闭FD并清理其自己的TLS
    ↓
影响点: 原执行线程残留旧映射
```

**影响分析 (ImpactAnalysis)**:

```text
触发条件: 快速执行、部分解析失败或FD未全部消费
    ↓
传播方式: 后续普通复制事务在同一执行线程读到旧FD
    ↓
后果: 解析失败或读取不属于本次事务的已复用FD
```

**修复建议**: 在执行闭包内建立/清理同线程作用域，覆盖所有出口；worker 析构只关闭已接管 FD。取消的未执行任务不能清理其它 TLS；嵌套作用域恢复前值。

```cpp
1 | // 示意：scope须在实际执行线程构造，不在producer构造。
2 | ScopedAshmemFdContainer scope(ashmemFdWorker.get());
3 | auto transData = RSBaseRenderUtil::ParseTransactionData(*parcel, parcelNumber);
4 | // 所有return由scope恢复该线程状态。
5 | // worker最终析构只负责receiver-owned FD。
```

---

#### 问题 3: 当前线程 token 查询使用无锁共享成员

**分类**: 并发稳定性  
**规则**: StabilityCodeReview_ConcurrencyStability_001 - 多线程场景线程安全设计缺失 - HIGH  
**位置**: `foundation/communication/ipc/ipc/native/src/core/invoker/source/binder_connector.cpp:194`  
**函数**: `BinderConnector::GetSelfTokenID`

**关键源码片段**:

```cpp
194 | int ret = ioctl(fd, ACCESS_TOKENID_GET_TOKENID, &selfTokenID_);
195 | if (ret != 0) {
196 |     selfTokenID_ = 0;
197 | }
198 | (void)fclose(fp);
199 | return selfTokenID_;
```

**问题描述**: 单例中的普通 uint64_t 被多个查询线程写入。内核 ioctl 返回 current->token，不是进程共享缓存；某成功查询可被其它线程成功/失败覆盖，再返回错误身份。GetInstance 的发布锁不保护此方法。真实 ResetCallingIdentity 链使用这个结果。

**风险流分析（RiskFlow）**:

```text
风险来源: 本线程查询结果保存到共享成员
    ↓
传播路径: 并发ioctl或失败置零 → 另一个线程读取该成员
    ↓
影响点: ResetCallingIdentity 使用错误token
```

**影响分析 (ImpactAnalysis)**:

```text
触发条件: 并发成功/失败查询交错
    ↓
传播方式: 查询结果被其它线程覆盖
    ↓
后果: 身份重置及后续权限判断不可靠；未声称新镜像复现
```

**修复建议**: 改用局部 uint64_t ioctl 输出，保持失败返回0、成员布局、公开签名和内核权限不变。

```cpp
194 | uint64_t token = 0;
195 | int ret = ioctl(fd, ACCESS_TOKENID_GET_TOKENID, &token);
196 | if (ret != 0) {
197 |     token = 0;
198 | }
199 | (void)fclose(fp);
200 | return token;
```

---

#### 问题 4: 分配失败或接管前拒绝未完整回收 Binder 事务

**分类**: 资源管理  
**规则**: StabilityCodeReview_ResourceManagement_005 - 文件描述符泄漏 - HIGH；关联 MemoryStability_004  
**位置**: `foundation/communication/ipc/ipc/native/src/core/invoker/source/binder_invoker.cpp:984`  
**函数**: `BinderInvoker::Transaction`、`BinderInvoker::HandleReply`

**关键源码片段**:

```cpp
981 | void BinderInvoker::Transaction(binder_transaction_data_secctx& trSecctx)
982 | {
983 |     binder_transaction_data& tr = trSecctx.transaction_data;
984 |     auto binderAllocator = new (std::nothrow) BinderAllocator();
985 |     if (binderAllocator == nullptr) {
986 |         ZLOGE(LABEL, "BinderAllocator Creation failed");
987 |         return;
988 |     }
989 |     auto data = std::make_unique<MessageParcel>(binderAllocator);
990 |     data->ParseFrom(tr.data.ptr.buffer, tr.data_size);
```

**问题描述**: 真实 kernel 已交付缓冲区并安装普通 FD；nothrow new 失败时既没有 Parcel 接管，也不 FreeBuffer/close。HandleReply 的无需回复、分配失败、SetAllocator 失败虽 FreeBuffer，却没有关闭普通 FD。这是既有直接链问题，不是新身份字段引入。

**风险流分析（RiskFlow）**:

```text
风险来源: 已送达的内核事务及接收端普通FD
    ↓
传播路径: 接管前失败 → 没有后续资源所有者
    ↓
影响点: Binder缓冲区及FD持续占用
```

**影响分析 (ImpactAnalysis)**:

```text
触发条件: nothrow分配失败或接管前拒绝
    ↓
传播方式: 每次失败遗留缓冲区/FD
    ↓
后果: 重复失败可耗尽资源；未做guest耗尽测试
```

**修复建议**: 以不依赖堆分配的 helper 校验 kernel-delivered 对象范围，字节复制读普通 FD 并关闭，再 FreeBuffer。只主动关闭 BINDER_TYPE_FD；FDA 在 kernel binder.c:2079–2152 由释放缓冲区时的 deferred close 负责，不能重复关。FDR 是用户态私有类型，kernel binder_get_object 不识别，不能相信其自报号码。

```cpp
984 | auto binderAllocator = new (std::nothrow) BinderAllocator();
985 | if (binderAllocator == nullptr) {
986 |     ZLOGE(LABEL, "BinderAllocator Creation failed");
987 |     ReleaseUndispatchedTransaction(tr);
988 |     return;
989 | }
```

---

#### 问题 5: ReadAshmem 对象分配失败遗漏关闭 duplicate

**分类**: 资源管理  
**规则**: StabilityCodeReview_ResourceManagement_005 - 文件描述符泄漏 - HIGH；关联 MemoryStability_004  
**位置**: `foundation/communication/ipc/ipc/native/src/core/framework/source/message_parcel.cpp:566`  
**函数**: `MessageParcel::ReadAshmem`

**关键源码片段**:

```cpp
561 | int32_t size = ReadInt32();
562 | if (size <= 0) {
563 |     ::close(fd);
564 |     return nullptr;
565 | }
566 | return new (std::nothrow) Ashmem(fd, size);
567 | }
```

**问题描述**: ReadFileDescriptor 已 dup 出新 FD。尺寸失败会关闭，但 Ashmem 的 nothrow new 失败返回 nullptr 时没有所有者；不是空指针解引用，也不是与 IPCFileDescriptor 析构双关。

**风险流分析（RiskFlow）**:

```text
风险来源: 成功取得新duplicate
    ↓
传播路径: size合法 → Ashmem分配失败 → nullptr返回
    ↓
影响点: 内部FD无法由调用方回收
```

**影响分析 (ImpactAnalysis)**:

```text
触发条件: 读取FD成功后nothrow分配失败
    ↓
传播方式: 返回空对象且丢失内部FD
    ↓
后果: 重复故障可耗尽FD；未进行目标故障注入
```

**修复建议**: 判空并在失败时关闭本次 duplicate，成功时维持原接管语义。

```cpp
566 | sptr<Ashmem> ashmem = new (std::nothrow) Ashmem(fd, size);
567 | if (ashmem == nullptr) {
568 |     ::close(fd);
569 | }
570 | return ashmem;
```

---

#### 问题 6: 新主线程转交队列缺少容量边界且丢失入队失败状态

**分类**: 边界条件  
**规则**: StabilityCodeReview_BoundaryCondition_004 - 容器size增长的对外接口应限制上限 - HIGH；关联 ExceptionHandling_003（返回值子项 MEDIUM）  
**位置**: `foundation/graphic/graphic_2d/rosen/modules/render_service/core/rs_render_pipeline_agent.cpp:177`  
**函数**: `RSRenderPipelineAgent::CommitTransaction`

**关键源码片段**:

```cpp
175 | // Keep the commit asynchronous, but never inspect or mutate the node map
176 | // from the Binder thread. The queued task owns its transaction on cancel.
177 | pipeline->ScheduleMainThreadTask([pipeline, data = std::move(transactionData)]() mutable {
178 |     auto* mainThread = pipeline->GetMainThread();
179 |     if (mainThread == nullptr || data == nullptr) {
180 |         return;
181 |     }
... |     // DVSync / SFC / RecvRSTransactionData
190 | });
191 | return ERR_OK;
```

**问题描述**: 每个事务独立排队并持有完整数据，没有每PID/全局 count/bytes 预算。现有统计仅加command/draw op数，合法零命令事务增量0，且只有启用终止并 KillApp 成功才 drop；inline Parcel 不受 ashmem流控。实际 EventQueue/FFRT 没有队列容量保护。另实际 EventHandler::PostTask 返回 bool，其 InnerEvent nothrow 分配失败会返回false；RSMainThread::PostTask 的 void 层忽略结果，Commit仍ERR_OK。取消销毁会释放资源，因此不重复报泄漏。

**风险流分析（RiskFlow）**:

```text
风险来源: 外部事务持续生产或实际入队失败
    ↓
传播路径: Binder消费 → 独立主线程任务持有数据；false被void丢弃
    ↓
影响点: 队列/内存持续增长，或更新未执行却被内部报告成功
```

**影响分析 (ImpactAnalysis)**:

```text
触发条件: 主线程消费慢于生产；或可恢复的入队分配失败
    ↓
传播方式: 无限积压；或move后的事务随未入队任务销毁
    ↓
后果: 资源耗尽/延迟或缺帧；未声称实测OOM
```

**修复建议**: 入队前共享原子预算同时限制 count/bytes，每PID及全局均检查；执行、取消、失败由 RAII 精确释放。新增内部 bool TryPost 包装，保留旧void入口与异步协议；失败返回现有错误，不在 Binder 线程回退执行，不等待 future。合法绘制不能任意丢弃或未经语义验证合并。

```cpp
1 | auto reservation = budget.TryReserve(callingPid, transactionBytes, 1);
2 | if (!reservation) {
3 |     return ERR_INVALID_STATE;
4 | }
5 | if (!pipeline->TryScheduleMainThreadTask(MakeOwnedTask(std::move(reservation)))) {
6 |     return ERR_INVALID_STATE;
7 | }
8 | return ERR_OK;
```

---

#### 问题 7: 委托合成撤销并绕过已经失败的命令权限校验

**分类**: 异常处理  
**规则**: StabilityCodeReview_ExceptionHandling_002 - 异常分支应正确处理 - HIGH（规则默认MEDIUM，按已证明权限影响升级）  
**位置**: `foundation/graphic/graphic_2d/rosen/modules/render_service_base/src/feature/delegate_composite/rs_delegate_composite_callback_manager.cpp:473`  
**函数**: `RsDelegateCompositeCallbackManager::PrepareDelegateCompositeCommand`

**关键源码片段**:

```cpp
460 | if (!transactionData ||
461 |     !CheckSurfaceTransactionIdentity(transactionData->GetSendingPid(), transactionData->GetSendingTid())) {
462 |     return;
463 | }
466 | auto& processPayload = transactionData->GetPayload();
467 | std::queue<std::unique_ptr<RSCommand>> cmdQueue;
468 | for (auto it = processPayload.begin(); it != processPayload.end();) {
469 |     auto& command = std::get<2>(*it);
470 |     if (!command) {
471 |         continue;
472 |     }
473 |     command->SetCallingPidValid(true);
474 |     cmdQueue.push(std::move(command));
475 |     it = processPayload.erase(it);
```

**问题描述**: 普通HAP可注册listener，注册接口没有特殊permission，common verifier无条件true，exclusive默认true。同步/小inline事务先由IsCallingPidValid把系统/越界节点命令mark false，stub失败只记录日志后继续；Prepare按用户提供的交易pid/tid匹配表，无条件重设true。真实主线程最终ProcessEachCommandQueue直接cmd->Process，不检查valid。使用应用自己的PID/TID也能触发系统命令绕过，故仅核对注册PID不够。是既有直接链漏洞，未执行guest利用。

**风险流分析（RiskFlow）**:

```text
风险来源: 普通HAP注册信息及无权限命令
    ↓
传播路径: 失败仅日志 → Prepare撤销保护 → 委托命令队列
    ↓
影响点: RS执行原本被拒绝的系统/节点命令
```

**影响分析 (ImpactAnalysis)**:

```text
触发条件: 注册listener后提交匹配pid/tid的无权限命令
    ↓
传播方式: 已拒绝标记被强制true，最终执行不再过滤
    ↓
后果: 系统命令禁令及节点归属保护失效
```

**修复建议**: 注册/执行绑定可信caller、connection及服务端授权的节点范围；listener不是权限豁免。普通HAP系统命令继续拒绝，合法跨进程APP委托仍应可用；入队与执行均过滤，不将整个delegate接口改为系统专用。

```cpp
1 | if (!command) {
2 |     ++it;
3 |     continue;
4 | }
5 | if (!IsCommandAllowedByTrustedDelegation(*command, trustedDelegation)) {
6 |     ++it;
7 |     continue;
8 | }
9 | // 不得无条件 SetCallingPidValid(true)。
```

---

### MEDIUM 级别问题（3 个）

#### 问题 8: 非等待任务计数注册晚于发布且回收资格不匹配

**分类**: 并发稳定性  
**规则**: StabilityCodeReview_ConcurrencyStability_003 - std::atomic时序问题 - MEDIUM  
**位置**: `foundation/graphic/graphic_2d/rosen/modules/render_service/core/transaction/rs_unmarshal_thread.cpp:186`  
**函数**: `RSUnmarshalThread::RecvParcel`

**关键源码片段**:

```cpp
186 | if (noNeedWaitTaskNum_ > 0) {
187 |     noNeedWaitTaskNum_--;
188 | }
193 | unmarshalParallel ? PostParallelTask(task) : PostTask(task);
203 | if (!waitUnmarshalling) {
204 |     noNeedWaitTaskNum_++;
205 | }
```

**问题描述**: 发布前没有登记；快速任务先完成后producer加1会残留计数。闭包不捕获wait资格，等待型任务可消耗别的非等待计数；解析失败/drop/取消又漏减。独立的>0和--不能保证原子配对，seq_cst不能修复事件顺序。真实主线程据此跳过等待并请求VSync。

**风险流分析（RiskFlow）**:

```text
风险来源: 发布/计数登记顺序及任务资格错误
    ↓
传播路径: 快速执行、并行/等待混合、提前返回或取消
    ↓
影响点: 聚合计数偏离实际待解析任务集合
```

**影响分析 (ImpactAnalysis)**:

```text
触发条件: 上述确定性时序
    ↓
传播方式: 残留正计数或消耗另一任务资格
    ↓
后果: 跳过等待、额外VSync及帧时序异常；未证明崩溃
```

**修复建议**: 非等待任务在发布前持有独立回收凭证；执行/失败/取消精确释放一次，等待型任务不修改其它任务计数。

```cpp
1 | auto permit = !waitUnmarshalling ? MakeNoWaitTaskPermit(noNeedWaitTaskNum_) : nullptr;
2 | RSTaskMessage::RSTask task = [permit /* 其它值捕获 */] {
3 |     ScopedPermitCompletion complete(permit);
4 |     // 任何return均结束本任务资格。
5 | };
6 | PostTask(task);
```

---

#### 问题 9: rawData 的真实 FD0 与远端状态哨兵混用

**分类**: 资源管理  
**规则**: StabilityCodeReview_ResourceManagement_005 - 文件描述符泄漏 - MEDIUM；关联 MemoryStability_004  
**位置**: `foundation/communication/ipc/ipc/native/src/core/framework/source/message_parcel.cpp:109`  
**函数**: `MessageParcel::~MessageParcel`、`RestoreRawData`、`ReadRawDataInner`

**关键源码片段**:

```cpp
109 | if (readRawDataFd_ > 0) {
110 |     ::fdsan_close_with_tag(readRawDataFd_, IPC_FD_TAG);
111 |     readRawDataFd_ = -1;
112 | }
113 | if (writeRawDataFd_ > 0) {
114 |     ::fdsan_close_with_tag(writeRawDataFd_, IPC_FD_TAG);
115 |     writeRawDataFd_ = -1;
116 | }
431 | writeRawDataFd_ = 0; // RestoreRawData：并非真实持有FD
438 | if (rawData_ != nullptr && writeRawDataFd_ == 0) {
```

**问题描述**: 真实AshmemCreate/dup可返回0，>0遗漏关闭；但把两个条件直接改≥0会把远端状态的0错误当stdin关闭。因此必须先分离状态。按合法FD0条件性影响并入资源MEDIUM，不重复按Memory默认HIGH计数。

**风险流分析（RiskFlow）**:

```text
风险来源: 相同字段值同时表示资源和远端状态
    ↓
传播路径: >0漏清理；粗暴≥0修复误关stdin
    ↓
影响点: FD生命周期不正确
```

**影响分析 (ImpactAnalysis)**:

```text
触发条件: stdin已关闭且真实FD0被分配，或RestoreRawData远端状态
    ↓
传播方式: 析构无法只凭0区分所有者
    ↓
后果: FD0泄漏，或不完整修复误关无关FD
```

**修复建议**: 使用独立负值远端哨兵，所有状态判断同步修改；真实FD≥0清理，保持布局/API不变。测试在隔离child中验证真实read/write FD0及远端状态保留stdin。

```cpp
1 | constexpr int REMOTE_RAW_DATA_FD = -2;
2 | if (writeRawDataFd_ >= 0) {
3 |     ::fdsan_close_with_tag(writeRawDataFd_, IPC_FD_TAG);
4 | }
5 | writeRawDataFd_ = REMOTE_RAW_DATA_FD; // RestoreRawData
6 | // ReadRawDataInner同步检查REMOTE_RAW_DATA_FD。
```

---

#### 问题 10: FreezeScreen 未认证父节点实际类型

**分类**: 资源管理  
**规则**: StabilityCodeReview_ResourceManagement_004 - 谨慎使用static_pointer_cast - MEDIUM  
**位置**: `foundation/graphic/graphic_2d/rosen/modules/render_service/core/rs_render_pipeline_agent.cpp:725`  
**函数**: `RSRenderPipelineAgent::FreezeScreen`

**关键源码片段**:

```cpp
723 | auto displayNode = RSBaseRenderNode::ReinterpretCast<RSLogicalDisplayRenderNode>(
724 |     renderPipeline->GetMainThread()->GetContext().GetNodeMap().GetRenderNode(id));
725 | auto screenNode = displayNode == nullptr ? nullptr :
726 |     std::static_pointer_cast<RSScreenRenderNode>(displayNode->GetParent().lock());
727 | if (!screenNode) {
728 |     RS_LOGE("%{public}s failed, screenNode is nullptr", __func__);
729 |     return;
730 | }
731 | screenNode->SetForceFreeze(isFreeze);
```

**问题描述**: display类型已验证，parent却直接static cast。实际AddChild/SetParent不保证screen类型；错误层级会把非screen对象用于screen参数处理。接口需系统调用，未证明普通HAP可直接触发，按条件性风险MEDIUM。

**风险流分析（RiskFlow）**:

```text
风险来源: 异常或重组后的节点父子类型
    ↓
传播路径: parent非空 → 无类型认证的static cast
    ↓
影响点: 非screen对象执行screen逻辑
```

**影响分析 (ImpactAnalysis)**:

```text
触发条件: logical display的parent不是真实screen节点
    ↓
传播方式: 非空指针通过检查但实际类型错误
    ↓
后果: 错误类型访问及冻结行为异常；未证明默认镜像触发
```

**修复建议**: 用既有RSBaseRenderNode::ReinterpretCast的IsInstanceOf检查，保留空指针拒绝、系统权限和主线程路径。

```cpp
1 | auto screenNode = displayNode == nullptr ? nullptr :
2 |     RSBaseRenderNode::ReinterpretCast<RSScreenRenderNode>(displayNode->GetParent().lock());
3 | if (!screenNode) {
4 |     return;
5 | }
6 | screenNode->SetForceFreeze(isFreeze);
```

---

## 修复优先级建议

根据严重程度和影响范围，建议按以下优先级修复：

### 第一优先级（CRITICAL，1个）

1. **对象编码**: 同时修复客户端/服务端强引用对象及ashmem传递；取得协议修复确认后实施。

### 第二优先级（HIGH，6个）

1. **身份/权限**: token局部查询与委托授权过滤（2个）；合法应用/ArkWeb委托必须回归。
2. **线程/调度**: 同线程FD scope与有限队列/真实入队结果（2个）。
3. **失败资源**: kernel普通FD与FDA责任分离、ReadAshmem故障回收（2个）。

### 第三优先级（MEDIUM，3个）

1. **计数与生命周期**: noWait凭证、rawFD0/远端哨兵、父节点类型验证（3个）。
2. 三ABI编译/主机sanitizer之后仍须完整链接、新代表archive启动、普通应用与Web/Vulkan真实像素、退出/权限/边界回归；首包门槛通过后才构建其余五包。

---

## 附录

### 白名单过滤

- 文件路径: 技能包 `config/whitelist.yaml`。
- 测试、生成文件、build/out路径不作生产问题；冻结候选在/tmp但按真实生产相对路径分类，11个文件无白名单命中。
- 技能metadata.version为0.1.0，npm包版本0.1.1；报告严格使用metadata版本。主agent及9分类agent进行人工规则检视，不是自动扫描器。
- PARCEL、FD cleanup、内核引用互斥释放等既有修复在当前限定静态链未检出原问题复现；不代替真实客体运行验证，不保证全部OHOS能力已修复。

---

**报告生成时间**: `2026-10-07 00:42:03 +0800`  
**报告生成者**: Agent
