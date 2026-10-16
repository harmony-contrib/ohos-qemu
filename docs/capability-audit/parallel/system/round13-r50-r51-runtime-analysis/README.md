# R50 HiTrace / R51 RenderService：只读故障复核

本批只读既有日志、当前仓库和只读 inspector 中的窄范围固定源码。没有启动 native/SDK/GN/Ninja/QEMU/HDC，没有改共享源码、权限、超时或健康门禁。`first_artifact_behavior_gate_passed=false`，核销 0 项。R50、R51 是不同归档、不同 boot，不能合并当作一次运行。

当前能定位的故障链比原 round8 更具体；仍没有足够证据给出一个已经验证的产品根因修复。

## R50：90 秒是调用方完成超时，已分离三个 PID

归档 SHA `879933a2fca5e8bdf6fb21705e95f97ce7ed1e95f85bb038cf86f6ec30a73370`；失败 boot `17fcc26b-ed41-41e8-a2ec-726b095cf0ba`。`aa start` 的真实退出码为 0，日志为 `start ability successfully.`。首末轮结果读取均只有命令结束标记，没有当前 nonce 的调用日志；两个读取标签的 monotonic_ns 相差 90.570261875 秒。不能据此认定已经进入某个 HiTrace API 后死锁。

`071-failure-hilog.log` 现在足以确认原先未确定的进程归属：

| 客体时间 | 原日志行 | 确定观察 |
| --- | --- | --- |
| 11:52:41.635 | 1776–1777 | `org.harmonycontrib.capabilityaudit` 的旧普通应用 PID **22958**、UID20010044 在前台。 |
| 11:53:49.197 | 2435–2438 | SceneBoard 请求该旧应用退后台，同时启动 HiTrace 场景。 |
| 11:53:55.392 / 58.373 | 2644–2678 / 3025–3044 | 被转储的主线程明确是 `capabilityaudit` 22958；native 栈等候同步 Binder，既有提取分析对应 GoBackground → NotifyAfterBackground → SetMainFrameRateLinkerEnable → SyncFrameRateRange。它不是 HiTrace 新调用方栈。 |
| 11:53:58.201 | 2823–2829 | 22958 上报 THREAD_BLOCK_6S，processExit=1。 |
| 11:54:01.712 | 3213–3215 | AMS 明确因 APP_FREEZE 杀死 22958。 |
| 11:54:10.004 | 3868–3871 | RS 才记录 SyncFrameRateRange 的非法调用，linker ID98603859181569，callingPid=0；其 ID 高32位确为22958、低32位1。该日志晚于旧应用被杀，不能把它直接解读为 HiTrace 新进程的身份缺陷。 |
| 11:54:10.006–.011 | 3875–3881 / 3902–3904 | HiTrace **23526**（UID20010045）的 spawn 初始化记录后，连接1 OnDisConnect/OnClose，appspawn 明确 Kill process。 |
| 11:54:10.011–.017 | 3943–3951 / 3996–4003 | HiTrace第二次尝试 **23854**，连接4同样断开并被杀，随后真实 SIGKILL=9 退出记录。 |

固定真源 `base/startup/appspawn/standard/appspawn_service.c:232–282` 确认这个 Kill process 分支：连接关闭时，匹配仍在 spawning 的 context，向 ctx->pid 发 SIGKILL，再执行 spawn-abort hook 并释放 context。日志没有交代客户端为何关闭这两个连接；缺少当时 appspawn/client 的用户态栈、完整请求超时/错误返回和调度轨迹。不能把可选 mount ENOENT 或标注 ignore 的 XPM ioctl 单独定为致命错误。

当前真源保留明确的同步依赖：

- `rs_ui_display_soloist.cpp:596–606`：退后台禁用主帧率 linker 时立即更新 range。
- `rs_client_to_service_connection_proxy.cpp:1216–1249`：SyncFrameRateRange 使用 TF_SYNC / SendRequest。
- `main/render_server/transaction/rs_client_to_service_connection.cpp:769–778`：服务端 ScheduleTask(...).wait()。
- 对应 stub `:893–926` 仍执行 ID 内 PID 与 kernel callingPid 校验。

所以一个慢的服务队列可以阻塞应用退后台；这是确定的依赖关系，不是已证明 R50 队列慢的原因。现有 async identity/backpressure 修复面向异步提交，README 明确同步调用不变；不能把已死同步调用的 `callingPid=0` 用 wire PID 回填。当前 Mesa LLVM 候选有机会减轻绘制耗时，但没有同 boot 证据把 R50 的服务等待归因为 TGSI，也没有证据证明已经修复。

当前 `run_hitrace_diagnostic.py:131–159` 保留 90 秒完成门槛并调用独立 failure snapshot；`hitrace_failure_snapshot.py` 已补 journal、trace、进程、ability、服务各线程等待和故障目录。R50 原始轮没有这些新增快照，且其 failure-hilog 抓取被原报告记为 diagnostic_error；保存下来的部分日志不能视作完整故障现场。后来单独 boot `d0a0da9f-c8f2-4b9e-a617-6fcd1d6ea627` 的短诊断通过，不补足 R50 原完整序列。

## R51：慢帧 + 唤醒后的检查/恢复链，不能叫正常退出

归档 SHA `6b27a2062a8b4361255d26499d1fcf86685d0f0f4d686dfd3965acdede28fbfe`；boot `a1f293cc-5726-4630-8965-2b31b25407e7`。PID快照 **665→2574**，kernel boot ID相同；功能门禁尚未执行。

| 证据 | 确定观察 |
| --- | --- |
| qemu.log:18613 / 18668 | 第一次 s2idle entry46.614365s / exit60.859343s，跨度14.244978s。 |
| SERVICE_WARNING:4,18 | 07:41:46.924，当前 vSyncTask 从07:41:29.947一直未完成。 |
| SERVICE_BLOCK:4,14–18 | 07:41:46.935，同一个 vSyncTask；与 warning 只差 **11ms**，ReportCount从1到2。日志文字是“blocked5s, report twice instead of exiting process”。这不是一次实测连续 awake5s/10s 的凭证。 |
| warning/block:95–104 | 两次 main665 都在相同 RSDrawFrame::PostAndWait / condition_variable 等待栈。 |
| warning/block:217–225 | RSUniRender822 都为 R，utime597→598 ticks（clk100），PC有变化；真实符号绑定到 softpipe/TGSI fragment 执行，说明采样间仍执行，不能只据同一函数断言永久死循环。 |
| qemu.log:18807 / 18876–18880 | 再次 s2idle entry61.862124s；91.718662s init记录665 exit0并立即重启2574。91.733870s才打印PM suspend exit。 |

真实 Build-ID 绑定的旧 Mesa 符号显示 `tgsi_exec_machine_run → exec_vector_binary/get_index_registers → shade_quad/exec_run → Skia glDrawArrays`；RS 主线程通过 PostAndWait 等待。旧 Mesa 已是 debugoptimized/-O2、LLVM disabled/draw-use-llvm false。故“补-O2”或“只有 shader compilation 慢”都不符合现有证据。具体 shader、绘制面积/循环、调度竞争和长帧的完整耗时仍未保存。

### exit0 有兼容的真源机制，原 boot 缺最后出口证明

不能按“report twice”字面推断永不退出。当前只读真源：

1. `watchdog_task.cpp:483–507` 写 SERVICE_BLOCK 后仍调用 `KillPeerBinderProcess(description)`。
2. `watchdog_inner.cpp:1889–1897` 只有 foundation UID5523先尝试专门恢复；RS UID1003走 `LeftTimeExitProcess`。
3. `:1854–1866` 排除debug后 `DelayBeforeExit(10)`，写reason/日志，然后 `_exit(0)`。
4. `xcollie_utils.cpp:437–441` 是处理被信号中断的真实 sleep 循环。

这解释了为什么正常 Watchdog 恢复也可能呈现 init exit0，绝非健康退出证明。R51 没保存该次 `_exit` reason HiLog，也没有该次打包 libhicollie 的 Build-ID/源码绑定，本批不将当前源码推断冒充已捕获的实际退出调用栈。s2idle期间用户进程被冻结，sleep到期线程可在唤醒后才被调度；仅凭串口打印顺序也不能证明是wake动作自身破坏RS。

## 已有 suspend-aware 开关：可做候选，但不能声称覆盖所有 s2idle

精确已有参数是 `hicollie_suspend_check_enable`：`hicollie.gni:18–23` 的 declare_args 默认 **false**；`frameworks/native/BUILD.gn:73–75` 在true时加 `SUSPEND_CHECK_ENABLE`，没有其他布尔依赖或新增lib/权限。当前混合 out 的 `libhicollie_source.ninja` 确实没有该宏，只能证明当前暂存图，不能反推 R51 原制品。

宏完整效果如下，不能只看函数名：

- `watchdog_task.cpp:62–137` 各个 task 构造函数保存 BOOTTIME/MONOTONIC 初值；两个额外私有字段也由同一宏控制（watchdog_task.h）。应完整重编该 source_set，不能仅重编一个cpp。
- `IsInSleep`（watchdog_inner.cpp:1357–1373）排除 appspawn、未初始化时间和 kick任务，再计算两种时钟各自的 elapsed。绝对差 **>=2000ms** 才返回true。没有“所有进程刚wake就跳过”的逻辑。
- `Start:1505–1514` 返回true仅跳过本次 `task.Run(now)`；仍执行 ReInsertTaskIfNeed。`:1458–1474` 把 due 加 interval 并重取双时钟，不清除 pending HandlerChecker / taskSlow_。
- `watchdog_task.cpp:184–195` 还有独立效果：迟到超过固定 **5000ms** 时重置nextTickTime并返回；未启用宏时阈值为2×checkInterval（RS5000的阈值为10000ms）。它不把5000ms改成更长。
- 若没有真实睡眠差且按时检查，HandlerChecker 仍经历 half→full，SERVICE_BLOCK、10秒诊断等待和_exit0恢复链全部保留。

**s2idle限制有真实内核依据。** `kernel/linux/linux-6.6/kernel/power/suspend.c:433–436` 走s2idle_loop后直接goto Platform_wake，跳过`:447`的syscore_suspend；`kernel/time/timekeeping.c:1909–1916` 将timekeeping suspend/resume注册为syscore操作，正常睡眠offset注入在`:1688–1701,1794–1828`。这条s2idle路径没有同样的timekeeping挂起/恢复调用；不能假定它一定把睡眠变为BOOTTIME与MONOTONIC的差值。若二者在s2idle都前进相同时间，IsInSleep会返回false。必须在真实新guest测双时钟；不能由PM日志反推该差值。

`replay_watchdog_schedule.py` 只复放冻结源码的算术机制：假设检查迟到8000ms，默认10秒阈值允许同一个now连续half/full；启用宏的5秒阈值先重置due，下一次等5000ms。正常awake按时的pending checker仍half/full。这个例子与R51的11ms相邻报告相容，但原日志没有now/nextTickTime，**不是历史根因复现、native测试或guest修复证明**。BOOTTIME/MONOTONIC相同前进的例子也明确不会skip。

最小已有GN启用语法（仅说明合同，本批未执行）：

```sh
./build.sh --product-name arm64_virt --gn-args 'hicollie_suspend_check_enable=true' ...
```

根仓库 `scripts/build_standard_qemu_in_docker.sh:1570–1610` 自建build_args；目前没有外部GN_ARGS透传。若root决定启用，应在load-only和正式images两次共用的build_args创建处，像现有concurrent_links参数一样追加上述精确GN布尔，或在真实产品hicollie feature中启用，并冻结/核实最终参数、ninja宏和实际DSO。仅设置宿主GN_ARGS环境变量无已证实作用。本批未建议改变全局默认、未改脚本或产品。

## 同批处理和首包验收顺序

1. root完成当前已在运行的M144依赖任务并保留结果，再合批当前真实修复；不插入新的产品构建。Mesa LLVM/llvmpipe是针对R51实际TGSI热路径的候选；保留软后端兼容不等于运行时已经选择llvmpipe。需绑定新包实际DSO与RS加载映射/renderer，独立GLES probe不能代替RS本体。
2. 若选择启用HiCollie现有布尔，先收齐真实完整TU/链接与宏绑定证据。新guest同时测实际s2idle前后双时钟，保存warning/full时刻、due/now（若加诊断）和准确进程。必须验证普通awake卡顿仍触发既有恢复、正常awake不误报；不能禁Watchdog、增加90秒或绕过RS PID健康检查。
3. 同一新包先通过原boot quiet/suspend/wake门禁，保持RS PID存活；再按原完整工作负载及原顺序跑普通HiTrace。保留当前nonce调用journal、真实kernel trace、旧应用转后台、新应用实际PID和spawn完成。失败快照如仍缺活体用户态栈/退出reason，应继续保留为失败；不把短单独boot结果替换完整门禁。
4. R50若仍出现spawn disconnect，需收集客户端请求/连接close根因和appspawn当时的栈/调度；当前没有证据支持一个安全且确定的appspawn源码改动。RS若仍在TGSI/llvmpipe长帧，需收集实际shader/workload与调度数据后再合批修复。

这些是核心owner的集成/诊断请求，没有分配新源码所有权，也不核销10个system需求或其他组需求。剩余5包仍等待首个代表包完整真实行为门禁通过。

## 本批文件和复核

- `evidence-index.json`：21个历史原始证据与6个当前repo文件的实际字节数/SHA；归档SHA取原控制器，本批没有重读巨大tar包。
- `raw-excerpts.json`：带原文件SHA和原行号的窄范围实际日志摘录。
- `source-review.json` / `source-query.py.txt`：17份只读源码/当前暂存ninja的SHA、精确行号和原查询；**不是旧归档源码绑定**。
- `replay_watchdog_schedule.py` / `replay.json`：纯Python源码算术例，断言冻结片段后运行；没有native/guest运行。
- `result.json`：明确结论、剩余缺口、集成请求和本批轻检查，不改累计ledger。
