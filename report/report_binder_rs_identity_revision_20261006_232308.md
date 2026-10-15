# OpenHarmony 稳定性代码审查报告

**检视目标**: `patches/common/kernel/linux/linux_6_6/binder_async_sender`、`patches/common/foundation/graphic/graphic_2d/async_caller_identity`、`patches/common/foundation/communication/ipc/binder_connector_initialization`  
**检视时间**: `2026-10-06 23:23:08 +0800`  
**检视框架版本**: OpenHarmony Stability Code Review Framework `0.1.0`  
**检出问题总数**: `5`  
**严重程度分布**: CRITICAL(0), HIGH(4), MEDIUM(1), LOW(0)  
**规则覆盖**: `57` 条规则（`9` 个稳定性分类）

---

## 检视概览

### 代码信息

- **代码路径**: 固定 Release 真源上的冻结候选及直接 IPC 身份、事务、Parcel、FD 清理链。候选来自 Docker `ohos-qemu-capability-inspect` 的 `/tmp/binder-async-three-abi-02/source`、`/tmp/render-connection-reply-compile-nqyborm_`、`/tmp/render-connection-reply-compile-82n4anwb`；主源码/out 为只读。
- **代码行数**: 11855 行（8个候选生产文件：binder.c 6968、binder_internal.h 582、RS stub.cpp 2064、stub.h 85、connection.cpp 820、ashmem.cpp 551、transaction.cpp 524、BinderConnector.cpp 261；直接依赖另作定向阅读，不是全仓扫描）。
- **功能描述**: 复核第一次检视后实现的可信异步身份、请求作用域、单例同步、offset 数量/几何/注入完整性、Parcel 单一所有权、枚举边界及 frozen PID 引用清理。kernel HEAD `14c77f1541a53e814d89ad6dea5f7f211f9895a6`；graphic HEAD `81cc9ca9509bccd86c435064136fe45591d29eeb`；IPC HEAD `b8d3e96cfcf382c8fae54502679ac8b3d827b428`。本轮5项均为直接链继承缺口，不是新增 PID 回退引入；上一轮7项在冻结候选中已实现，未重复计数。
- 候选 SHA-256：binder.c `e0d365c6c671b47f054f7d0af1162162a17e6b7d8b3a80a5d97eda8e5565a1cd`；binder_internal.h `deea4d03ca9b0284fdf024963c93db2d32b8a6e81ef7901acd37fbdf35a7b2ea`；RS stub.cpp `d16314523172dae1dfae1a91dbae09c6a22d79644db45a274daab3cb9ff93214`；stub.h `87d649d5dd35390aa28f32dc10e3978a56084881a574fcb40ca115e9b4b72b55`；connection.cpp `ff0a630a19a82a53dd2915533fde0eab4630d0a99cbbfc11d311265c04dde863`；ashmem.cpp `dcd234b2d1c274e41c2eee63d36ab87066d8151182771af60efd7d972dbce1b0`；transaction.cpp `9843033bff489fede94c7ce02fe28e7cd31177d9cf0f25474f48671e418ba611`；BinderConnector.cpp `5bcf46aaaf0d6614c511b143dfc76e3c65d68ce181060490d6c4428d0f28fe57`。
- 身份限制仍成立：仅异步 COMMIT、wire PID=0 读取内核身份，非正拒绝；其他请求置零 scope，嵌套析构恢复前值；stub/connection 在同一真实 DSO target；token、访问类型和普通命令节点归属检查保留。可信 PID 传给异步任务为值捕获，不以跨线程 TLS 获取。PID 引用有正常、错误、frozen 三处配对释放；不意味着数字 PID 永不复用或已测量运行时引用数。
- 本报告为只读检视完成时的快照，修复建议尚未实施；不证明新包、普通应用画面、Vulkan 像素或六包通过。工具输出是人工规则检视，不是自动 C++ scanner。

### 问题统计

| 严重程度 | 检出问题数 | 占比 | 说明 |
|---------|---------|------|------|
| CRITICAL | 0 | 0% | 无本轮独立检出 |
| HIGH | 4 | 80% | 共享元数据竞态、未对齐访问、FDR泄漏、条件性节点线程/归属风险 |
| MEDIUM | 1 | 20% | 合法fd0生命周期遗漏，未证明默认RS触发 |
| **总计** | **5** | **100%** | **/** |

### 分类问题分布

| 分类名称 | 规则数量（已检视/总数） | 检出问题数 | 严重程度 |
|---------|---------|-----------|---------|
| 异常处理 | 3/3 | 0 | — |
| 并发稳定性 | 5/5 | 1 | HIGH 1 |
| 性能稳定性 | 2/2 | 0 | 两条递归规则未检出，不代表所有循环低成本 |
| 资源管理 | 7/7 | 2 | HIGH 1、MEDIUM 1 |
| 初始化顺序 | 1/1 | 0 | — |
| 边界条件 | 18/18 | 1 | HIGH 1 |
| 生命周期 | 2/2 | 0 | — |
| 内存稳定性 | 7/7 | 0 | 共享数据/未对齐风险与其他分类去重 |
| 图形稳定性 | 12/12 | 1 | 条件性HIGH 1 |
| **总计** | **57/57** | **5** | **HIGH 4、MEDIUM 1** |

---

## 检出问题详情

### CRITICAL 级别问题（0 个）

无本轮独立检出。

---

### HIGH 级别问题（4 个）

#### 问题 1: ashmem FD 元数据仍可被发送方并发改写

**分类**: 并发稳定性  
**规则**: StabilityCodeReview_ConcurrencyStability_001 - 多线程场景线程安全设计缺失 - HIGH  
**位置**: `foundation/graphic/graphic_2d/rosen/modules/render_service_base/src/platform/ohos/rs_ashmem_helper.cpp:525`  
**函数**: `RSAshmemHelper::ParseFromAshmemParcel`

**关键源码片段**:

```cpp
519 | int fd = ashmemParcel->ReadFileDescriptor();
520 | auto ashmemAllocator = AshmemAllocator::CreateAshmemAllocatorWithFd(fd, dataSize, PROT_READ | PROT_WRITE);
521 | if (!ashmemAllocator) {
522 |     ROSEN_LOGE("ParseFromAshmemParcel failed, ashmemAllocator is nullptr");
523 |     return nullptr;
524 | }
525 | void* data = ashmemAllocator->GetData();
526 | auto dataParcel = std::make_shared<MessageParcel>(ashmemAllocator.release());
527 | if (!dataParcel->ParseFrom(reinterpret_cast<uintptr_t>(data), dataSize)) {
528 |     return nullptr;
529 | }
531 | if (!RestoreAshmemObjectOffsets(dataParcel, ashmemParcel, ashmemFdWorker, callingPid)) {
532 |     // Failed injection may hold borrowed FD numbers. Clear them before destruction.
533 |     dataParcel->FlushBuffer();
```

**问题描述**: offset 表已经私有复制，但 payload 仍使用 `MapAshmem` 的 MAP_SHARED 映射。发送方可保留可写映射，在 RS 注入 FD 后改变 hdr.type/handle；真实 MessageParcel 析构依 payload 重新读取 handle 并 close。可信身份、offset几何和节点校验不能防止使用期间的字段变化。静态链证明风险，未做 guest 利用实测。

**风险流分析（RiskFlow）**:

```text
风险来源: 发送方仍可写共享payload
    ↓
传播路径: RS直接解析共享数据 → 注入接收方FD → 发送方再次改写hdr/handle
    ↓
影响点: 解析或析构使用失真的FD元数据
```

**影响分析 (ImpactAnalysis)**:

```text
触发条件: 合法可达的ashmem COMMIT，发送方继续写共享区域
    ↓
传播方式: 检查后的object内容发生变化，offset私有副本无法保护payload
    ↓
后果: 可能错关RS其他FD或破坏事务解析；具体guest结果尚未验证
```

**修复建议**: 在校验/FD注入之前使用已有 CopyFromAshmem 建立接收方私有快照，以普通 MessageParcel 唯一接管 malloc buffer；本地 PROT_READ 不足以防止发送方已有可写映射。

```cpp
525 | auto dataParcel = std::make_shared<MessageParcel>();
526 | void* privateData = ashmemAllocator->CopyFromAshmem(dataSize);
527 | if (privateData == nullptr) {
528 |     return nullptr;
529 | }
530 | if (!dataParcel->ParseFrom(reinterpret_cast<uintptr_t>(privateData), dataSize)) {
531 |     free(privateData);
532 |     return nullptr;
533 | }
534 | // Validate and restore objects only in the receiver-owned snapshot.
```

---

#### 问题 2: 合法四字节 Binder 偏移仍通过未对齐结构体指针访问

**分类**: 边界条件  
**规则**: StabilityCodeReview_BoundaryCondition_014 - 类型强制转换需校验范围 - HIGH  
**位置**: `foundation/graphic/graphic_2d/rosen/modules/render_service_base/src/platform/ohos/rs_ashmem_helper.cpp:438`  
**函数**: `RSAshmemHelper::InjectFileDescriptor`

**关键源码片段**:

```cpp
433 | if (offset > dataParcel->GetDataSize() ||
434 |     sizeof(flat_binder_object) > dataParcel->GetDataSize() - static_cast<size_t>(offset)) {
435 |     ROSEN_LOGW("RSAshmemHelper::InjectFileDescriptor offset invalid");
436 |     continue;
437 | }
438 | flat_binder_object* flat = reinterpret_cast<flat_binder_object*>(data + offset);
439 | if (flat->hdr.type == BINDER_TYPE_FD || flat->hdr.type == BINDER_TYPE_FDR) {
440 |     int32_t val = ashmemParcel->ReadFileDescriptor();
441 |     if (val < 0) {
442 |         ROSEN_LOGW("RSAshmemHelper::InjectFileDescriptor failed, fd:%{public}d, handle:%{public}u", val,
443 |             flat->handle);
444 |     }
445 |     flat->handle = static_cast<uint32_t>(val);
```

**问题描述**: Linux Binder 的对象对齐为4字节；真实 sys_binder.h 的 Binder64 flat_binder_object 自然对齐可为8字节。offset模8为4合法通过后，typed flat*成员访问仍构成未对齐C++访问。offset列表的对齐副本不改变object自身地址。需要一并检查直接 IPC 解码、复制及析构；未声称目标guest已发生硬件异常。

**风险流分析（RiskFlow）**:

```text
风险来源: 合法4-byte对象偏移
    ↓
传播路径: 几何校验通过 → reinterpret_cast到8-byte对齐结构 → 成员解引用
    ↓
影响点: 未定义行为或严格对齐检查中止
```

**影响分析 (ImpactAnalysis)**:

```text
触发条件: offset模8为4且ABI要求flat对象8-byte对齐
    ↓
传播方式: FD恢复及后续解码/清理沿用typed对象指针
    ↓
后果: 对齐UB；当前validator主机测试没有执行这些实际消费者
```

**修复建议**: 保留4-byte协议合法性，字节复制到对齐局部对象，再字节写回handle；不要简单收紧为8-byte。直接下游 MessageParcel 和 BinderInvoker 也要消除同源访问。

```cpp
438 | flat_binder_object flat {};
439 | const auto* raw = reinterpret_cast<const uint8_t*>(data + offset);
440 | if (memcpy_s(&flat, sizeof(flat), raw, sizeof(flat)) != EOK) {
441 |     continue;
442 | }
443 | const int32_t val = ashmemParcel->ReadFileDescriptor();
444 | const uint32_t handle = static_cast<uint32_t>(val);
445 | auto* dest = reinterpret_cast<uint8_t*>(data + offset) + offsetof(flat_binder_object, handle);
446 | // Establish ownership before writing back; handle any failed write safely.
447 | memcpy_s(dest, sizeof(handle), &handle, sizeof(handle));
```

---

#### 问题 3: 恢复 FDR 创建的新 dup 没有关闭所有者

**分类**: 资源管理  
**规则**: StabilityCodeReview_ResourceManagement_005 - 文件描述符泄漏 - HIGH  
**位置**: `foundation/graphic/graphic_2d/rosen/modules/render_service_base/src/platform/ohos/rs_ashmem_helper.cpp:447`  
**函数**: `RSAshmemHelper::InjectFileDescriptor`

**关键源码片段**:

```cpp
438 | flat_binder_object* flat = reinterpret_cast<flat_binder_object*>(data + offset);
439 | if (flat->hdr.type == BINDER_TYPE_FD || flat->hdr.type == BINDER_TYPE_FDR) {
440 |     int32_t val = ashmemParcel->ReadFileDescriptor();
441 |     if (val < 0) {
442 |         ROSEN_LOGW("RSAshmemHelper::InjectFileDescriptor failed, fd:%{public}d, handle:%{public}u", val,
443 |             flat->handle);
444 |     }
445 |     flat->handle = static_cast<uint32_t>(val);
446 |     if (ashmemFdWorker) {
447 |         bool shouldCloseFd = flat->hdr.type == BINDER_TYPE_FD;
448 |         ashmemFdWorker->InsertFdWithOffset(val, offset, shouldCloseFd);
449 |     }
450 | }
```

**问题描述**: ReadFileDescriptor 执行真实 dup，FDR却未进入Worker待关闭集合，MessageParcel也只关闭FD。稳定payload即能产生此缺口，不依赖问题1的并发改写。普通发送helper只写FD不排除接收端已接受FDR、外层附正常FD的输入。

**风险流分析（RiskFlow）**:

```text
风险来源: 接收FDR并取得新receiver-owned dup
    ↓
传播路径: FDR标签导致Parcel不关闭，Worker未登记待关闭
    ↓
影响点: 消息结束后dup仍存活
```

**影响分析 (ImpactAnalysis)**:

```text
触发条件: 合法FDR offset与外层ReadFileDescriptor成功
    ↓
传播方式: token失败/同步解析/异步FlushBuffer及取消路径均缺关闭者
    ↓
后果: 重复输入可累积FD至服务限额；尚未在新包运行该边界
```

**修复建议**: 私有快照上恢复时，每个新dup都建立关闭责任，不依据发送方FD/FDR标签豁免。全部成功后规范为接收方拥有的FD，Parcel正常清理；异步FlushBuffer后才将责任交给Worker。以下为RAII方向示意，helper须真实实现，不能当作已修复代码。

```cpp
 1 | auto ownedFds = DuplicateValidatedFdObjects(ashmemParcel, privateObjects);
 2 | if (!ownedFds) {
 3 |     return false;
 4 | }
 5 | for (size_t i = 0; i < ownedFds->size(); ++i) {
 6 |     auto& flat = privateObjects[i];
 7 |     flat.handle = static_cast<uint32_t>((*ownedFds)[i].Get());
 8 |     flat.hdr.type = BINDER_TYPE_FD;
 9 |     ashmemFdWorker->InsertFdWithOffset((*ownedFds)[i].Get(), offsets[i], true);
10 | }
11 | for (auto& fd : *ownedFds) {
12 |     fd.Release();
13 | }
```

---

#### 问题 4: 单帧合成特殊分支非主线程访问节点且遗漏无效命令过滤

**分类**: 图形稳定性  
**规则**: StabilityCodeReview_GraphicsStability_009 - RSRenderNodeMap线程访问限制 - HIGH  
**位置**: `foundation/graphic/graphic_2d/rosen/modules/render_service_base/src/transaction/rs_transaction_data.cpp:211`  
**函数**: `RSTransactionData::ProcessBySingleFrameComposer`

**关键源码片段**:

```cpp
204 | void RSTransactionData::ProcessBySingleFrameComposer(RSContext& context)
205 | {
206 |     std::unique_lock<std::mutex> lock(commandMutex_);
207 |     for (auto& [nodeId, followType, command] : payload_) {
208 |         if (command != nullptr &&
209 |             command->GetType() == RSCommandType::CANVAS_NODE &&
210 |             command->GetSubType() == RSCanvasNodeCommandType::CANVAS_NODE_UPDATE_RECORDING) {
211 |             command->Process(context);
212 |         }
213 |     }
214 | }
```

**问题描述**: Binder线程的PipelineAgent::CommitTransaction直接调用MainThread的单帧分支。global开关开启时UpdateRecording无锁查主线程renderNodeMap，payload锁不是节点表锁。该Process也不跳过已被标为invalid的command，模板/UpdateRecording没有补充归属检查。persist.sys.graphic.singleFrameComposer默认0，本轮未证明当前QEMU开启或实际触发，须明确条件性风险。

**风险流分析（RiskFlow）**:

```text
风险来源: 开启单帧合成时Binder线程直接执行特殊命令
    ↓
传播路径: CommitTransaction → ProcessDataBySingleFrameComposer → ProcessBySingleFrameComposer
          → UpdateRecording → 无锁GetRenderNode
    ↓
影响点: 跨线程节点表访问，且invalid命令也可能执行
```

**影响分析 (ImpactAnalysis)**:

```text
触发条件: UniRender/global单帧开关与场景判断允许特殊分支
    ↓
传播方式: 主线程节点变化与Binder查找并行，归属invalid标志被特殊分支忽略
    ↓
后果: 条件性竞态/节点状态异常，或执行不属于调用方的Canvas更新
```

**修复建议**: 保持现有权限和协议，特殊分支也跳过invalid命令；由已有ScheduleMainThreadTask拥有事务，把场景判断/节点操作投递主线程，不能借调用方栈变量或仅加payload锁。该任务模板持有packaged_task，支持move-only事务捕获；实现后仍需验证顺序、取消和默认关闭/开启回归。

```cpp
179 | pipeline->ScheduleMainThreadTask([pipeline, data = std::move(transactionData)]() mutable {
180 |     auto* mainThread = pipeline->GetMainThread();
181 |     if (!mainThread || !data) {
182 |         return;
183 |     }
184 |     if (mainThread->IsNeedProcessBySingleFrameComposer(data)) {
185 |         mainThread->ProcessDataBySingleFrameComposer(data);
186 |     } else {
187 |         mainThread->RecvRSTransactionData(data);
188 |     }
189 | });
```

```cpp
207 | for (auto& [nodeId, followType, command] : payload_) {
208 |     if (command == nullptr || !command->IsCallingPidValid()) {
209 |         continue;
210 |     }
211 |     if (command->GetType() == RSCommandType::CANVAS_NODE &&
212 |         command->GetSubType() == RSCanvasNodeCommandType::CANVAS_NODE_UPDATE_RECORDING) {
213 |         command->Process(context);
214 |     }
215 | }
```

---

### MEDIUM 级别问题（1 个）

#### 问题 5: 合法 fd0 被接收后不能按当前生命周期释放

**分类**: 资源管理  
**规则**: StabilityCodeReview_ResourceManagement_005 - 文件描述符泄漏 - MEDIUM  
**位置**: `foundation/graphic/graphic_2d/rosen/modules/render_service_base/src/platform/ohos/rs_ashmem_helper.cpp:231`  
**函数**: `AshmemAllocator::Dealloc` / `AshmemFdWorker::~AshmemFdWorker` / `MessageParcel::ClearFileDescriptor`

**关键源码片段**:

```cpp
222 | void AshmemAllocator::Dealloc(void* data)
223 | {
224 |     if (data != data_) {
225 |         ROSEN_LOGW("AshmemAllocator::Dealloc data addr not match!");
226 |     }
227 |     if (data_ != nullptr) {
228 |         ::munmap(data_, size_);
229 |         data_ = nullptr;
230 |     }
231 |     if (fd_ > 0) {
232 |         ::close(fd_);
233 |         fd_ = -1;
234 |     }
235 | }
```

**问题描述**: 接收/创建仅拒绝负FD，ReadFileDescriptor使用普通dup，内核get_unused_fd_flags也允许0。但allocator、Worker、MessageParcel三个清理点使用>0，遗漏合法0。按具体影响降为MEDIUM，未改规则默认HIGH配置；未证明默认RS关闭stdin，也不能声称一个0号槽能重复累积至耗尽。

**风险流分析（RiskFlow）**:

```text
风险来源: fd0槽空闲时合法dup/接收返回0
    ↓
传播路径: 入口接受0 → 清理使用>0跳过
    ↓
影响点: 生命周期结束后资源及allocator fd_状态未清理
```

**影响分析 (ImpactAnalysis)**:

```text
触发条件: 执行进程fd0已空闲且分配到0
    ↓
传播方式: 三种对应清理路径遗漏该合法值
    ↓
后果: 单个资源生命周期无法闭合；不是已实测默认guest故障
```

**修复建议**: 以-1为无效值，关闭非负FD；uint32 handle先转换有符号值。用独立子进程实际占用/释放fd0测试，不关闭测试宿主stdin。

```cpp
 1 | if (fd_ >= 0) {
 2 |     ::close(fd_);
 3 |     fd_ = -1;
 4 | }
 5 | for (const int fd : fdsToBeClosed_) {
 6 |     if (fd >= 0) {
 7 |         ::close(fd);
 8 |     }
 9 | }
10 | const int fd = static_cast<int32_t>(flat.handle);
11 | if (flat.hdr.type == BINDER_TYPE_FD && fd >= 0) {
12 |     ::close(fd);
13 | }
```

---

## 修复优先级建议

### 第一优先级（CRITICAL，0个）

无本轮独立检出；上一轮CRITICAL实现仍需新包运行回归。

### 第二优先级（HIGH，4个）

1. **并发/边界/资源**: 私有payload、字节对象访问、每个新dup的唯一所有者必须一起闭环；覆盖FD/FDR混合、读取/dup失败、token失败、同步/异步/任务取消及发送方持续写原映射。
2. **图形**: 单帧场景判断和节点操作归主线程，保留invalid命令跳过、原token/归属例外；验证关闭/开启及并发节点销毁，不靠默认关闭忽略边界。
3. 重新编译受影响的三个ABI真实对象，完整链接并在新代表归档启动测试；当前诊断内核58项通过不代替RS或首包验收。

### 第三优先级（MEDIUM，1个）

1. **资源**: fd0实际子进程生命周期回归与三处清理一致修复；明确条件和未验证guest前置状态。

---

## 附录

### 白名单过滤

- 文件路径: 上述8个生产候选及直接调用链均按OpenHarmony相对源码路径判断，未命中全局路径/文件模式白名单，无规则级豁免。未因物理scratch路径误跳过生产代码。
- 排除测试、生成头、out与构建日志；不把主机mock或旧镜像检查当生产行为证明。
- 九个独立分类检视者：`rs_revision_exception`、`rs_revision_concurrency`、`rs_revision_performance`、`rs_revision_resource`、`rs_revision_initialization`、`rs_revision_boundary`、`rs_revision_lifecycle`、`rs_revision_memory`、`rs_revision_graphics`。所有启用规则已遍历；跨分类重复根因合并，保留条件性/未实测限界。
- 实际直接依赖 MessageParcel SHA `2f4d216c9a54534840b8c6ac7d81b9627fd9271bd9009b5289eb9a6ee0ce6349`、BinderInvoker `37165e4b4511ccadac7c80b9de88769ddccac4eb6242adb4b785ccb5a49e2704`、c_utils Parcel `f4296edd47f32475d6bb2b8c8a615ecc6f87fe3de2495cbef75cc59d326aac23`、RSUnmarshalThread `ed983812f72682a8541e696c205d5c0f7129ce84b753784b81bb6905f83aa026`、PipelineAgent `c112f8bb5af73a6a756abfb24b37c3af3354cf8fee0b1089414644e4900efde6`、RSMainThread `f5b9571b4753192b26f26976b19d7e7e57f3eb2e5d06a3a03d9353c81ee5a594`。
- 非递归性能观察：实际InjectOffsets逐项WriteObjectOffset去重会执行约n(n−1)/2次比较。几何有界不等于低成本；尚无基准或guest DoS证据，不作为两条递归规则独立检出，也不据此声明完整性能安全。
- 检视工具版本：再次实际npm view/npm ls确认registry及已安装package均`0.1.1`；SKILL metadata.version为`0.1.0`，标题依模板使用后者。CLI是安装器而非自动scanner，因此本轮由九个独立agent按57条规则只读检视。没有伪造自动扫描或guest利用结果。
- 这是检视完成时的失败快照；问题未闭合前不能提交/push或放行新首包/六包。

---

**报告生成时间**: `2026-10-06 23:29:02 +0800`  
**报告生成者**: Agent
