# Calendar 专用运行验收工具交接

本批仅新增 QA 工具、fixture、本文档；没有修改生产 patch、共享 runner/helper、冻结文件、Git index，没有运行 Docker、SDK/native 编译、签名、安装、VM、重包。主机检查不代表运行通过。所有命令由 root 在自己的资源租约内串行执行。

## 交付与结论

- `batch_system_calendar_runtime_project.py`：真实 SDK105 声明校验、不可变三角色项目清单、随机 run/operation nonce。normal 项目移除 notification/WantAgent 系统 API 导入及实现。
- `..._build.py`：未来由 root 显式执行的 SDK105 编译入口，生成真实 `source_files`、Hvigor 完整日志和 HAP 清单；私有缓存、禁 daemon/parallel/incremental、2 CPU worker discovery。旧 r53 SDK receipt 不适用，禁止补造 inventory。
- `..._sign.py`：复用固定签名器，三种精确身份；不安装或授予权限。
- `..._helper.py`：仅本进程扩展 `HELPERS`，复用实际 APP/TOKEN Ninja anchors、product sysroot/LTO/CFI/link；`--verify-spec` 校验真实产物。共享 helper 文件不需修改。
- `..._archive.py`：从新的 archive 核对 system.img 字节，读取实际 CalendarData.hap、签名/profile、编译 metadata 和冻结 build-inputs；不依赖历史 SDK HAP。
- `..._capture.py`：复用 owned guest 与真实 UITest，采集公开 API journal、BMS/token/权限定义、已安装 HAP 字节、真实通知/WantAgent、通知实际节点点击、页面 tree/pixels、独立 observer 读值、AMS/hilog。不会启动/安装/关闭 VM。
- `..._protocol.py` / `..._verify.py`：重放实际带退出标记的 HDC/UITest 原始输出，核对 archive/boot/run/nonce/UID/token、真实未来提醒时间、DSO、独立读值和页面；直接 `aa start` 只能计为 URI 边界。
- `..._tests.py` / `host.cjs`：仅主机协议与实际新 ETS 源码的内存 API doubles，绝不生成可提交验收的 guest journal。

工具可以在真实材料齐备时核对核心 API→provider→consumer 通知→实际点击→MainAbility→独立读回/UI 的一条链；**当前没有任何 guest 链通过**。`full_calendar_lifecycle_verified`、`first_artifact_behavior_gate_passed` 和 `ledger_closed` 始终 false。完整生命周期见后述 gap，不能仅凭 core_chain_verified 放行其他五包。

## 权限身份边界

| 角色 | 配置 | 运行职责 |
|---|---|---|
| producer | normal、hos_normal_app、空 allowed/restricted ACL、仅 READ_CALENDAR/WRITE_CALENDAR | 真实用户弹窗授权/拒绝后，通过公开 CalendarManager 创建唯一 LOCAL 日历、4 个未来普通 event，reminderTime=[0]；仅更新/删除本 run 数据 |
| denied | normal、hos_normal_app、无 requested permission、空 ACL | 公开 Calendar 访问的拒绝边界 |
| observer | **候选** system_basic、hos_system_app、READ_WHOLE_CALENDAR + NOTIFICATION_CONTROLLER；仅后者进入精确 allowed/restricted ACL | 用户授权 whole-read 后独立只读 Calendar；只读 getAllActiveNotifications 和实际 WantAgent，不创建 event、不发布提醒、不触发 provider |

历史只读权限注册表导出见 `permission-definition-reference.json`：READ_WHOLE_CALENDAR availableLevel=2、grantMode=0；NOTIFICATION_CONTROLLER availableLevel=3、grantMode=1；二者 provisionEnable=true。这里的 level 2/3 对应 system_basic/system_core。这表明 NOTIFICATION_CONTROLLER 的默认最低 APL 为 system_core；system_basic+provision ACL 是否可用仍须**本轮新包**精确签名、真实 BMS 安装、GetDefPermission 和 VerifyAccessToken 证明。SDK 声明只说明接口存在，不能证明此候选身份足够。

采集器严格要求 observer 实际 NOTIFICATION_CONTROLLER grant=0，否则保留失败；不会提高 APL、增加权限、伪造 observer JSON 或跳过 BMS/token。READ_WHOLE 必须走真实用户弹窗；provider MainAbility 的 READ_WHOLE 同样须单独 allow/deny。若系统不接受候选 profile，保存真实失败为 gap，不能临时把 observer 提到 system_core。

native helper 会通过实际产品 AccessTokenKit 读取五个权限的定义和授予状态，AppMgrClient 只读进程，记录真实 CLOCK_REALTIME/CLOCK_BOOTTIME。helper 无授予、改时钟或数据写入路径。其源码尚未实际编译，API/ABI/CFI/链接以 root 新产品编译为准。

## Root 执行顺序与资源

所有路径均为绝对路径。以下 `$QA`、`$SDK`、`$NODE` 等是 root 设置的任务变量，示例不是证据。Python 运行采集/重放需 Pillow；本机默认 python3 无 Pillow，`--help`/host tests 不需要安装它。真实 SDK 构建需 Node18.20.1、官方 OHPM/Hvigor、已准备的私有可复制缓存；缺缓存会保留失败，不下载未声明依赖。native helper 需新代表产品只读 source/out、产品 clang/DSO，不用 NDK 或禁 CFI。

1. root 得到新 ARM64 phone archive 后，先保留 archive SHA、同归档解出的 system.img、完整 package build-inputs/manifest；只启动其 owned guest，保留 acceptance boot JSON（真实 QEMU pid/boot UUID/UDID）。本工具不启动新 VM。不要并行其他 SDK/native/VM 任务。

2. 生成新随机 challenge 和三项目（约几十 KiB，无编译）：

```sh
python3 ci/capability-audit/batch_system_calendar_runtime_project.py challenge --output "$QA/challenge"
python3 ci/capability-audit/batch_system_calendar_runtime_project.py project --role producer --challenge "$QA/challenge/challenge.json" --sdk "$SDK" --output "$QA/producer"
python3 ci/capability-audit/batch_system_calendar_runtime_project.py project --role observer --challenge "$QA/challenge/challenge.json" --sdk "$SDK" --output "$QA/observer"
python3 ci/capability-audit/batch_system_calendar_runtime_project.py project --role denied --challenge "$QA/challenge/challenge.json" --sdk "$SDK" --output "$QA/denied"
python3 ci/capability-audit/batch_system_calendar_runtime_build.py --execute-sdk-build --sdk "$SDK" --node "$NODE" --ohpm "$OHPM" --hvigor "$HVIGOR" --hvigor-cache "$HVIGOR_CACHE" --ohpm-cache "$OHPM_CACHE" --project "producer=$QA/producer" --project "observer=$QA/observer" --project "denied=$QA/denied" --output "$QA/sdk-build"
```

`$SDK` 指向 `.../26.0.0`，不是其父目录。不得把历史 r53 provider HAP 当本轮 provider。编译失败保留 evidence/logs；尚未执行的项目没有成功 inventory。每个实际角色 unsigned HAP 的 source manifest/receipt/HAP 都进入 plan。

3. root 读取真实 guest UDID 后，分别精确签名，保存输出日志和签名 HAP；用 root 既有安装流程真实安装，不做 pm/bm grant 或 root 代替 caller 发布。例如 producer：

```sh
python3 ci/capability-audit/batch_system_calendar_runtime_sign.py --role producer --udid "$UDID" --signer-dist "$SIGNER_DIST" --jar "$SIGNER_JAR" --unsigned "$QA/producer/entry/build/default/outputs/default/entry-default-unsigned.hap" --output "$QA/producer-signed.hap"
```

observer/denied 使用各自 `--role` 和独立输入/输出文件；`--output` 是新的签名 HAP 文件，旁边保存 signing.json。签名成功、安装成功、token grant 均分开留证。

4. root 在产品只读租约里构建 helper，复制实际 binary/receipt/完整日志，部署其 exact binary 到 owned guest `/data/local/tmp/calendar_runtime_observer`；同时提供实际 link trace 所读 APP/TOKEN DSO 的宿主 artifact 和 guest 路径。可在 root 的 Linux product 环境执行：

```sh
python3 ci/capability-audit/batch_system_calendar_runtime_helper.py --source-root /ohos --output /evidence/helpers/calendar-runtime
python3 ci/capability-audit/batch_system_calendar_runtime_helper.py --verify-spec "$QA/helper-spec.json"
python3 ci/capability-audit/batch_system_calendar_runtime_archive.py --archive "$ARCHIVE" --system-image "$SYSTEM_IMAGE" --signer-jar "$SIGNER_JAR" --output "$QA/archive-binding"
```

`--plan-only` 仍查询产品 Ninja graph，不是本轮已运行命令；必须等 root source/out 读租约。不能把计划 receipt 传给运行采集器。helper receipt 必须包含本进程 extension SHA，当前 builder SHA、真实 CFI/link/ELF 和已链接 DSO；guest DSO 字节不同立即失败。

5. 准备 `plan.json`（下面只描述 schema，不提供伪 hash/observer output）：

```text
signer: {dist: ABS_FIXED_DIST, jar: {path: ABS_JAR, sha256: REAL_SHA}}
helper: {
  binary: ARTIFACT, receipt: ARTIFACT, remote: /data/local/tmp/calendar_runtime_observer,
  path_map: {/work: ABS_REPO, /evidence/helpers: ABS_COPIED_HELPERS},
  guest_dsos: {
    libapp_manager.z.so: {artifact: ACTUAL_LINK_INPUT_ARTIFACT, remote: ACTUAL_SYSTEM_DSO},
    libaccesstoken_sdk.z.so: {artifact: ACTUAL_LINK_INPUT_ARTIFACT, remote: ACTUAL_SYSTEM_DSO}
  }
}
provider: {archive_binding: ARTIFACT_OF_archive-provider.json}
roles: {
  producer/observer/denied: {
    sdk: {sdk_evidence: ARTIFACT_OF_sdk-build/evidence.json, sdk_project: ROLE,
          source_project: ABS_ROLE_PROJECT, unsigned_hap: ARTIFACT},
    source_manifest: ARTIFACT_OF_calendar-source-manifest.json, signed_hap: ARTIFACT
  }
}
optional: permission_bundle, allow_texts, deny_texts, notification_bundle
ARTIFACT = {path: ABS_ACTUAL_REGULAR_FILE, sha256: SHA256_OF_THAT_FILE}
```

path_map 可省略（所有路径原样可读时），否则只接受 /work 与 /evidence/helpers 的映射；输入代码/hash必须和 receipt 一致。root 复制 helper 文件时保留目录布局。UI bundle/文字必须来自实际 UI，不用自造许可页。

6. 每个 stage 使用同一 archive/challenge/plan 和当前真实 boot JSON，独立新输出目录；共同参数：

```text
--archive ARCHIVE --boot ACTUAL_BOOT_JSON --hdc ABS_HDC
--challenge QA/challenge/challenge.json --plan QA/plan.json --output FRESH_STAGE_DIRECTORY
```

调用 `batch_system_calendar_runtime_capture.py` 的 stage 顺序：

| 场景 | 额外参数与真实操作 |
|---|---|
| 普通 caller 拒绝/允许 | `--stage operation --role producer --action permission --case permission-deny --permission-decision deny`；再次实际 allow（分别检查 READ/WRITE 结果）。缺弹窗不能手填结果。|
| 空权限边界 | `--stage operation --role denied --action read --case no-permission`，保留真实错误或最小可见数据边界。|
| 观察方授权 | `--stage operation --role observer --action permission --case observer-allow --permission-decision allow`。|
| 创建唯一四事件 | `--stage operation --role producer --action create --case create --lead-minutes 10 --spacing-minutes 10`；留出重复签名/BMS采集耗时。范围2..30分钟，真实等待，不改 guest 时间。保存 create/capture.json 作为 seed。|
| 独立读回 | `--stage operation --role observer --action read --case read-before-click`，保存 read/capture.json；读到真实 row 和 guest locale 时间后才能比 UI。|
| 到期通知只读 | 到真实事件 startTime 后 `--stage operation --role observer --action notifications --case due-cold-allow`；未到期、未收到或缺 WantAgent 均失败/gap，不伪造通知。|
| 真通知点击 | `--stage notification-click --case cold-allow --seed CREATE_CAPTURE --notification NOTIFICATION_CAPTURE --readback CURRENT_READ_CAPTURE --expect persisted --permission-decision allow`；实际 shade→唯一标题节点→tap→provider MainAbility。|
| provider 拒绝 | 对 cold-deny 事件准备实际未授权 provider 状态，等其真实到期、观察通知，执行上一行但 `--case cold-deny --expect blank --permission-decision deny`；要求实际拒绝 UI、token=-1、敏感事件字段空。|
| warm/重启后 | 对 warm/after-restart 各自真实到期事件重复独立 read/notifications/click，root 保留真实 foreground/back/退出/重启操作与 AMS/hilog。标签不证明启动模式。|
| legacy URI 与坏/缺 ID | `--stage uri --case cold-allow --seed CREATE_CAPTURE --readback CURRENT_READ_CAPTURE --uri-case valid --expect persisted`；坏 URI/缺 ID/0 ID 分别 `--uri-case bad-uri/missing-id/bad-id --expect blank`。此 stage 的 aa start 只验 URI。|
| 更新/删除刷新 | producer `--action update/delete --case cold-allow`；observer 再真实 read。root 用实际 `calendar-main-refresh` 节点或实际 foreground 触发刷新后 `--stage snapshot --case cold-allow --seed CREATE_CAPTURE --readback CURRENT_READ_CAPTURE --expect persisted/blank`；完整刷新因果仍需 root 实际操作 witness，当前重放不会自动判为通过。|
| 已删除 ID | `--stage uri --uri-case deleted-id --deleted ACTUAL_DELETE_CAPTURE --case cold-allow --seed CREATE_CAPTURE --expect blank`，核对真正被本 run 删除的 ID。|
| cleanup | producer `--stage operation --action cleanup --case cleanup`；只能删除保存的本 run 唯一日历，随后 observer 独立 read 验 accounts=[]，保留日志后再卸载 QA 包。|

冷/热/退出状态、Settings 权限重置和 guest 重启由 root 在同 owned guest 生命周期内实际操作并留证；当前工具不代替这些资源操作。四事件只能各点击一次，准备不及时导致到期/被清除时该 run 保留失败并通过公开 cleanup 清理，不改 clock 重造旧到期证据。

7. 汇总必须包括所有依赖的原始 create、observer read、notification、click 和边界 capture；不能只交点击摘要：

```sh
python3 ci/capability-audit/batch_system_calendar_runtime_verify.py --challenge "$QA/challenge/challenge.json" --capture "$QA/create/capture.json" --capture "$QA/read/capture.json" --capture "$QA/notifications/capture.json" --capture "$QA/click/capture.json" --capture "$QA/producer-allow/capture.json" --output "$QA/calendar-verification.json"
```

按实际证据重复 `--capture` 补其他 stage。exit=0 仅表示真实核心链达到专用判据，仍不关闭完整 Calendar/包验收。

## 必须保留的未验证项

- 本批三角色实际 SDK 编译、精确签名、BMS 安装、candidate observer APL/ACL、product helper TU/CFI/link、runtime DSO 以及任何 VM 阶段均未执行。无新 archive 可绑定，故 archive binder 也未执行。历史 SDK105 provider 编译仅历史旁证。
- 单个普通 caller `startAbility` 连续两次不能保证系统向某个既有 standard MainAbility 调用 onNewWant；公开 SDK 未见可由 normal caller 使用的 reuse/singleton flags。源码 routes 会真实尝试并保留背景启动错误，**不会**计为 onNewWant 验收。system startRecentAbility 是另一个权限边界，不增加 START_RECENT_ABILITY 绕过它。
- 仅 AMS 文本存在/两个进程/两个事件页面不能证明独立 Ability 实例。快速双事件、晚读回不覆盖新请求、独立实例 LocalStorage 以及 cold/warm 需 root 的真实 mission/Ability 生命周期 witness；当前明确 gap。
- snapshot 可核对真实 UI 内容，但更新/删除刷新因果、退出/恢复与跨 reboot 连续性当前无自动 lifecycle 解析；保留实际 root 操作、boot UUID 切换、持久 userdata 与独立读回，不能靠手写场景字段放行。unknown **正整数且全局确实不存在** event ID 还没有独立证明路径，0 ID 只覆盖坏 ID。
- cleanup producer 报告不替代 observer 最终空读。当前 validator 明确保留 independent-final-read-required，不自动关闭此项。
- 实际通知结构若未提供 SDK 声明中的 creatorBundleName/creatorUid 或 WantAgent 无法反查，严格 validator 会失败；保留公开接口缺口，不靠 observer 发替代通知。
- 实际 SystemUI/权限页需真实唯一节点；截图保留像素但未做 OCR 与人工视觉语义复核。当前主机环境缺 Pillow，root 需选已有带 Pillow 的受控 Python 后再运行采集/重放。
- 实际 provider metadata 只记录新 archive 的安装形态；host 测试的 ohos/hmos key、1/2 version 解析边界绝不算另一个 provider 的运行覆盖。提醒取消/重复/snooze/多账户等其他 Calendar 生命周期仍属于原系统域真实缺口。

资源与文件租约：本批轻量 host 检查完成后立即释放全部新文件范围，不占 SDK/source/out/Docker/VM 资源。精确源码 SHA、主机结果和未验证项见 `result.json`；root 可审查后统一接线/提交并等待代表03结果，不增加单项重包轮次。
