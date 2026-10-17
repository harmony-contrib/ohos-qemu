# System round 21：Calendar 提醒入口与消费方身份

基线为 `ddfabb4`。本批只修改独占的 CalendarData 组件、新批准的 notification
`calendar_owner` 组件、system 自有测试/fixture/报告。没有操作 Git index/commit，
没有修改共享 scripts、provider guard、runner/verifier、全局账本或产品配置。
唯一 source 租约仅从已有容器读取三个窄文件，已归还；没有读写 out/SDK、编译
OpenHarmony、运行 VM 或构建归档。10 条仍全部 open，不增加核销。

## 可审查源码批次

1. `calendardata/main_ui` 在完整 source_provider → event_editor →
   editor_callback_dispatch 后应用。原 MainAbility 只加载空页面；现在通过真实
   CalendarManager 读取提醒 ID 对应的持久日程，展示实际标题/时间/备注。URI
   只用作经过严格校验的 ID 路由，URI 的时间不作为数据库事实。普通和重要提醒
   producer 都改为真实 `com.ohos.calendardata/MainAbility`。保留原 URI authority
   以兼容存量提醒，不创建假 `com.ohos.calendar` app。
2. MainAbility 使用每个 Ability 独立的 LocalStorage 和 revision。新 Want、同一
   URI 再次打开及 foreground 都能刷新；reader 对异步重入、旧结果和销毁做隔离。
   权限申请失败/拒绝、服务错误、已删除/不可见 ID 均无成功数据。
3. manifest 仅给原 READ_WHOLE_CALENDAR usedScene 增加 MainAbility，并且必须
   经用户授权再读。WRITE scene、DataShare lower/whole 权限、proxy、提醒服务
   UPDATE_CALENDAR_RRULE、system-core signer/ACL 不扩。导出 UI 不向发起方
   发送读取结果，不新增 caller 参数或自动写入通道。
4. `calendar_owner` 固定消费方 header 的 NAME，使发布 owner/UID、点击 Want 和
   卸载 reset 一致。旧消费者面对新的真实 producer bundle 会清空 URI；新的
   匹配 consumer 保留 URI，其他 bundle 仍按原规则拒绝。
5. 同组件修复 schema 协商：provider 使用 `ohos.calendardata.reminderDbVersion`，
   消费方过去只认 `hmos`，导致 version=0 跳过扩展提醒字段。现在兼容两个确切
   名字，继续只识别已有版本 1/2。

main_ui installer 对 app identity、全部 editor UI 及 native dispatch 前置状态做
精确哈希校验，暂存后发布；未知/部分/符号链接状态拒绝，后段发布故障回滚。
event_editor verifier 只接受这一完整后继，支持整栈重复 preparation。

## 定向验证

`calendar-host-tests.log`：8/8；`editor-regression.log`：4/4；
`dispatch-regression.log`：4/4。环境为 Darwin arm64、Python 3.13.7、
Node 24.14.0、Apple clang 16。全部是 host service doubles/真实函数体的定向
回归，不能替代 SDK/HAP 编译、真实平台链接或新 guest 运行。

覆盖实际 URI parser/reader、用户拒权、持久值而非 URI 值、找不到/错误/重复、
旧异步结果、销毁和并发实例；实际 Ability create/new-want/相同 URI/foreground；
实际 producer 普通/重要两分支；原/修后四个 native 函数 InitNormalInfo、
CheckWantAgent、UpdateCalendarUid、CancelAllReminders。旧代码重现不存在的 UID、
URI 被清空和 schema=0；修后通过 owner/schema/卸载 reset 的对应断言。
完整 provider/editor/dispatch/main/owner replay、权限不扩、未知源、partial、
symlink 和中途发布失败均有回归。取消删除本身仍由真实 guest 验证，host 只证明
实际清理函数绑定的身份条件。首次主机尝试发现原 index.ets 没有末尾换行造成
diff 生成错误，已修复并经最终三组回归；无产品构建尝试。

## Root 精确集成要求

- 在 `scripts/build_standard_qemu_in_docker.sh` 的 Calendar callback component
  之后、source HAP 编译之前顺序运行 `main_ui/apply.sh`、
  `calendar_owner/apply.sh`，同批更新当前实际 patch plan/组件准备清单。不要将
  后者单独放入缺少真实 MainAbility 的产品。
- `patches/lib/calendar_provider.py` 增加显式 strict reminder UI 模式。只接受
  完整 main_ui 精确后继、实际 app identity、两个一致的 producer/consumer owner
  以及原 URI/extension/signer/ACL。READ scene 仅增加 MainAbility；WRITE scene
  保持 editor 后继。必须校验 module 和真实编入 HAP 的 MainAbility/page/reader，
  不能只验一个 permission name。该文件由 root 修改。
- 重建实际 CalendarData HAP（全部原有 HAR），按既有 signing/preinstall 链签名；
  编译/链接 notification service 的完整 helper TU，保留真实 SDK 和平台错误。
  本批未执行这两个产品步骤。shared guard 原实现会拒绝新的 READ scene，root
  必须先接入精确模式，不能删除 guard。
- 五域已知修复合并后仅做一次代表 arm64 phone 包；完成新归档全部相关运行
  验收并记录路径、SHA256、环境、命令、结果，首包门禁通过后再处理其余五包。

## 新归档运行步骤和边界

1. 核对 BMS 实际注册 `com.ohos.calendardata`、MainAbility、Editor 和 reminder
   callback 的签名、权限、来源 HAP。保留 lower/whole 两种授权读写正/反例及
   普通无日历权限调用 editEvent 的用户 Save/Cancel、真实行、返回 ID 和清理。
2. 用真正授权的独立 caller 创建具有随机标题/备注/提醒时间的 NORMAL 日程，
   保存返回 eventId。让 provider 生成真实 CalendarAlerts，检查消费方 UID、
   owner、schema=2 和提醒字段。普通/重要分支分别触发真实通知，不由直接构造
   Want 代替通知投递链路。
3. 实际点击通知，授权 READ_WHOLE 后用 `calendar-main-*` 节点及像素核对同一
   持久行；拒权时不能显示内容。存量 URI 仍应可路由。可辅助用实际 guest CLI
   `aa start -b com.ohos.calendardata -a MainAbility -U
   'calendar://com.ohos.calendar?event_id=<ID>&start=<MS>&end=<MS>'` 检查显式
   入口，但该命令不能证明通知点击或合法 caller 权限。
4. 改动数据库后以相同 URI 再点、切后台/前台、同时两个 Ability、旧读取过程中
   新 Want、销毁/重建，都不得显示旧会话结果。已删除/不可见/未知 ID、错误
   scheme/重复参数/超大 ID/坏时间范围不得当成功。URI 传入的时间不替代实际行。
5. 实际取消/删除提醒与日程，确认通知和重启重建后均不会重新投递；单独验证
   帐号隔离、provider/notification restart、time/timezone 变更、repeat/exclusion、
   snooze/custom ring 真实字段。完整 recurrence occurrence 展示、通用日历浏览
   不是本批实现，仍需按原能力要求做剩余工程和完整验收。

## 10 条能力分类（维持 open）

| ID 后缀 | 分类 | 下一步 |
| --- | --- | --- |
| access-token-api26-kernel-abi | A 已有候选，待新包 | 内核权限/taskUID、普通 HAP 父子身份和冒用拒绝 |
| msdp-device-status-mock-or-missing-clients | B 仍缺实现 | 实际 Sensor→公开 still；relativeStill/其他多模态不能以子集核销 |
| native-child-process-phone-boundary | A | enabled 实际 IPC/FD/token/退出及 disabled phone 边界 |
| session-manager-profile-gap | A | 新 SDK/image SysCap 与 SceneBoard/窗口/PiP/sleep-wake |
| calendar-lifecycle-device-difference | B，本批部分源码修复 | SDK/BMS 与完整 CRUD/提醒/重复/重启；全功能仍 open |
| device-attest-uninitialized | C 真实供应材料 | 合法 OEM 产品身份、密钥 provisioning 和真实服务/信任链 |
| advertising-service-provider-missing | C | 真实 provider、协议、合法内容及实际 load/render/回调 |
| graphics3d-scene-manager-unavailable | A | 新 guest 实际 scene/load/render/destroy/retry |
| security-guard-empty-model-config | C | 有定义的真实模型/事件/collector/输出；未知模型 401 不能改成功 |
| app-domain-verification-extension-missing | U 待真实核查 | 可控 HTTPS association、签名匹配/不匹配、refresh/cache/路由 |

仅 OEM Attest 已确认需要可信授权身份材料；Ads/模型应先指定实际业务规范和合法
实现，不能推断必须购买 OEM 二进制。未编造凭据、广告、模型结果或 MSDP 输入。
分类数据和全部文件 SHA256 见 `result.json`。
