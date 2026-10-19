# Apps 缺口盘点 373

34 个唯一 ID 仍在正式未闭合清单中；本轮新增正式销项 **0**。34=系统应用与入口27+无障碍3+能力声明/插件4，与 r51、当前计划、root 82 去重总表完全一致。当前修复源为 `a0d62155747253f203952878594e21976c12a92c`；最新真实17-06包仍是 `2f0fcedae7d2e832abf42024bc637be6303f1b30`。本报告未执行候选或任何运行验收。

|分类|条数|含义|
|---|---:|---|
|已有修复，待本包完整行为验收|11|已有源码修复/部分旧包正例，仍缺当前包完整正常、边界、回归、清理|
|基础实现或集成仍不完整|13|有现有服务/界面/候选基础，但协议、接线、生命周期或真实依赖尚不完整|
|明确尚无完整实现交付|6|明确尚无完整实现交付；按finding ID计数的已知下界|
|证据不足，需重新判定|4|聚合、旧支持判断或名称变更尚不能据现证据定为缺实现或已修|

**不能把34都称为纯未实现，也不能把11项待验收视作已经销项。** 已知完整实现缺口下界是6个finding ID：reader、caption、desktop lyrics、expanded menu、text plugins聚合、号码身份/风控数据服务聚合。其余13项也含真实剩余源码/协议工作，不能只安排跑测试。外部peer/ASR模型/合法号码数据等是原ID的依赖，不增加ID。

六个旧SysCap名称聚合列入待判定：`device_contract.py` 已要求实际注册表 abandoned、SDK非必需且API无引用，不能照旧“少六个字符串”断言六个后端都没实现；这个窄机制本身也不关闭用户要求的实际服务/API或此finding。

R50的start/stopBlinking和Settings导航分别有真实旧archive单项重放通过；保留其价值，不能迁移为F同包完整通过。Selection342队列实际exit0/cleanup true，但其两个合同不在82/本34里，扣减数为0。当前host365为a0d源码实际exit0且`ledger_closed=false`；host不是新包行为证明。

Location privacy仅由apps主账计1。canonical PrivacyCenter payload/scan/crypto/image基础已交付，E crypto13成功不证明BMS/UI；E用户入口尝试曾因控制器身份合同中止。354是staged只读inventory，372是未执行的有限路径源码候选；均不证明实际image inode、loaded role、CFI编译或隐私UI/会话闭环。Location agent提供native技术支持，不重复计本ID。

Settings/Share的可测性需保留真实API边界：SDK105 `loadContent` 是void/同步native，host模拟旧Promise延迟reject不是实际可达门；Settings config真实异步路径可达，但确定性pending/onDestroy/旧continuation仍缺请求级屏障和完整计数。普通导航、ScreenBlink成功、force-stop杀环境均不能冒充race覆盖。

|ID|分类|当前剩余|
|---|---|---|
|`arkts_export:@ohos.accessibility.config:startBlinking`|已有修复，待本包完整行为验收|已有真实 NAPI/client/IPC/AAMS/WM 后端；R50 单项实际冷重放通过，不能移植为 F 同包完整输入/像素/节点/调用者退出验收。|
|`arkts_export:@ohos.accessibility.config:stopBlinking`|已有修复，待本包完整行为验收|同一真实后端；重复 stop、caller 死亡、关闭总开关、账户/显示切换及服务重启仍需本包完整回归。|
|`behavior:phone-published-capabilities-not-declared`|证据不足，需重新判定|当前 device_contract.py 对六个文档名已有严格 registry abandoned、非 SDK 必需、无 API 引用的窄证据机制；旧暂存 canIUse=false 不能证明六个当前服务都缺，也不能据此正式删除此 finding。需同包逐名称/真实 API/服务重新核对。|
|`behavior:phone-avinputcast-not-declared`|基础实现或集成仍不完整|phone profile 明确启用 AVInputCast upstream service/NAPI 声明，故不再简单等同于未声明；真实 provider/会话协议、发送接收 peer、媒体挑战/取消/退出和新包 canIUse 尚无完整证明。|
|`behavior:accessibility-qemu-input-e2e`|已有修复，待本包完整行为验收|已有 QEMU accessibility 输入、节点与 ScreenBlink 后端；广义输入/像素/多实例/退出回归及 Settings 通知动作不能由两个 export 单项通过替代。|
|`behavior:api26-runtime-export-mismatches-phone`|证据不足，需重新判定|约40 SysCap 的聚合 finding，多个域已补 API；缺当前代表包完整 export/value/behavior 刷新，无法按 source patch 或 Selection 两合同数量扣减。|
|`behavior:intelligent-scene-notification-query-fails`|证据不足，需重新判定|已有 provider payload 不能证明两种 DND query 的旧 35200001 已消失；无当前完整初始化/数据/拒绝/重启原始观测，先复测定位。|
|`behavior:shortkey-empty-launch-config`|已有修复，待本包完整行为验收|已存在 qemu.settings/Meta+I 配置与保留键修复；仍需本包 businessId/setKeyDownDuration、短按/错误修饰键、普通权限拒绝及重启。|
|`behavior:certificate-dialog-device-result`|证据不足，需重新判定|既有 CertificateManager/MainExtensionAbility/CertPickerUIExtAbility 基础不等于支持判定正确；supportsCACertDialog=false 需真实选择/空列表/取消/拒绝/device 分支定位，不能直接称缺 HAP。|
|`behavior:ability-share-picker-system-provider-missing`|基础实现或集成仍不完整|已有 Settings sysPicker/share 真 modal/原 caller 委托候选；旧 ACTION_CHOOSE 的独立 PickerDialog UIAbility 仍缺，URI/普通 caller/结果/取消/退出与多画像证明不足。SDK105 loadContent 为 void/同步 native，host 延迟 Promise reject 不是实际可达 race 门。|
|`behavior:ability-send-data-action-has-no-enabled-handler`|基础实现或集成仍不完整|已有 MMS text/plain 接收/收件人草稿候选，未据此声称发送；MMS UTD/文件附件授权及 Bluetooth/HMS ShareExtension 协议仍缺，需真实用户操作与取消不发送。|
|`behavior:avcast-media-controller-provider-mismatch`|基础实现或集成仍不完整|已有 com.hmos.mediacontroller payload/UIExtAbility 不自动等于实际 AVCast picker 协议；bundle/入口/结果/会话接线和 peer 正例尚不完整，不能靠改名验收。|
|`behavior:media-control-volume-provider-activation`|基础实现或集成仍不完整|已有 AVVolumeExtension payload，但 phone 启用、真实音量读改与权限/取消/关闭/重启合同仍无完整闭环。|
|`behavior:distributed-hardware-ui-preinstall-path-mismatch`|已有修复，待本包完整行为验收|已有实际目录 preinstall 修复；仍需同包 BMS/AMS 注册、真实发起/取消/错误/退出及相应 peer，不由暂存路径一致关闭。|
|`behavior:photo-provider-not-activated-2in1`|已有修复，待本包完整行为验收|已有源码构建 Photos、Recent*/DefaultAlbum/FACard/初始化修复；需新包真实数据/授权/取消/退出/cloud 协议，phone 证明仍不能替代 2in1 独立画像。|
|`behavior:enterprise-provisioning-provider-missing`|已有修复，待本包完整行为验收|已有真实 AdminProvisioning source provider 与 SDK 候选；原 normal APL/ACL 保持，仍需新包普通管理员 enable/disable、持久状态、super 拒绝、取消/双请求/退出/重启。|
|`behavior:wallpaper-ui-provider-missing`|已有修复，待本包完整行为验收|F 已补首次真实 desktop public set 后有界 renderer 恢复及 stock 常量 guard；旧 E 在 baseline guest pidof=1 前中止不能变通过。仍需本包两次 desktop/lock 挑战、真实 connected PID/DSO/UID/boot、像素与默认还原/created assets 公共清理。|
|`behavior:accessibility-screen-reader-provider-missing`|明确尚无完整实现交付|尚无完整 screen-reader provider 交付：可访问焦点/手势→真实 TTS 内容、设置启停、生命周期/关闭静默均不能由任意 ability enable 命令或 Settings 页替代。|
|`behavior:accessibility-caption-provider-missing`|明确尚无完整实现交付|尚无完整实时 caption provider/合法 ASR 引擎模型交付；CaptionsManager 状态或空 AiCaption ability 不提供音频订阅→识别→字幕/权限/停止。|
|`behavior:vpn-dialog-provider-prefix-mismatch`|已有修复，待本包完整行为验收|已有精确 com.ohos.vpndialog bundle 修复；需同包真实授权允许/拒绝/取消、caller 返回、断连/重启，不由 OpenVPN 无法连通 loopback 的窄清理证明关闭。|
|`behavior:network-policy-settings-providers-missing`|基础实现或集成仍不完整|已有 Settings/CommunicationsSetting 基础但非目标 NetAccessPolicySettingUIExtension 完整协议；需真实策略编辑/结果、持久化、通知跳转和权限。|
|`behavior:telephony-apn-settings-provider-missing`|基础实现或集成仍不完整|已有 CallSetting 的其他入口不能代替 GeneralCallSettingDialogAbility/APN Want/结果/权限合同；需实际 APN 增删改、取消/持久化，网络生效另依赖 modem。|
|`behavior:wifi-system-ui-providers-not-activated`|基础实现或集成仍不完整|已有 Wifi/HotSpot/LocationDialog/Portal payload 基础；精确签名/预装/BMS 目标、STA/AP/portal 真实挑战、取消/退出仍不足，后端/peer 与 network 共用但此入口 ID 不重复计。|
|`behavior:camera-picker-entrypoint-missing-phone`|基础实现或集成仍不完整|已有 product/picker 真实模块但 phone 默认 PickerAbility 与已启用入口合同尚需构建/签名/预装接线；必须真实输入、结果 URI 授权、取消/异常退出，不能改普通 MainAbility 冒充。|
|`behavior:notification-extension-settings-entrypoint-missing`|基础实现或集成仍不完整|已有 SceneBoard 其他模块不提供完整 NotificationAccessGrantUIExtensionAbility；仍需真实 grant UI/调用者结果、允许/拒绝/取消/退出/重启。|
|`behavior:accessibility-settings-entrypoints-unavailable`|基础实现或集成仍不完整|已有 Settings service 声明及真实异步 action await/queue/epoch 修复；已发 native 操作不承诺取消，安全 idle-stop/cache listener 重同步尚未完整。确定性 pending/onDestroy/late continuation 缺请求级屏障/全调用计数，普通导航/force-stop 不替代。|
|`behavior:notification-manager-settings-provider-missing-phone`|基础实现或集成仍不完整|已有 SceneBoard NotificationManangerUIExtensionAbility payload，但 phone 唯一 provider/模块启用、真实 notification mutation/返回/权限/取消/退出合同仍需完整接线/验证。|
|`behavior:avsession-desktop-lyrics-provider-missing`|明确尚无完整实现交付|尚无 DesktopLyricAbility 完整实现交付；实际会话歌词订阅、显示/隐藏/关闭/重启不能由类似 mediacontroller bundle 重命名替代。|
|`behavior:location-privacy-ui-providers-unavailable`|基础实现或集成仍不完整|已补 canonical PrivacyCenter HAP/scan entry/精确 crypto/image verifier；旧 E crypto/image=0 仅来源证明。实际 LocationPrivacy/details/用户会话闭环尚未通过；354 staged inventory 及372有限路径候选不证明 actual ext4/loaded role/CFI 编译。主账仅 apps 计1。|
|`behavior:telephony-number-identity-provider-missing`|明确尚无完整实现交付|尚无 numberlocation/numbermark、NumberIdentity、SpamShield、HSDR 完整合法数据/服务交付；必须真实更新/离线/未知/错误/权限，不能固定分类/空表。外部合法数据依赖属此ID，不再另加一个缺口。|
|`behavior:settings-navigation-provider-mismatch`|已有修复，待本包完整行为验收|已有 navigation/provider bundle/真实页面修复且 R50 24phase/1060command 单项重放通过；F 同包公开方法/UI/controller、2in1 implicit app-info 与权限/取消/退出/重启完整验收仍缺。|
|`behavior:contacts-picker-entrypoint-missing-phone`|已有修复，待本包完整行为验收|F 已补 Ability-local/shared LocalStorage/nonce continuation 隔离及 actual singleton user0 provider UID 严格绑定；旧 E seed JSON.parse 空串在 journal/perms/CRUD 前失败，不能推为 provider 失败。需新包真实205/100分批、所有overload、双session、600000ms deadline/Home dismiss/退出重开和公共数据清理。|
|`behavior:arkui-expanded-text-menu-providers-missing`|明确尚无完整实现交付|尚无 libexpanded_menu.z.so 的真实 dlopen ABI/动作映射完整实现交付；search/share/URL/email/phone/address/date 还依赖真实 handler/URI 授权与取消退出。|
|`behavior:arkui-text-service-runtime-plugins-missing`|明确尚无完整实现交付|尚无 systemshare_innerkits、ai_text_translation_innerapi、ai_text_analyzer_innerapi 三种真实插件/服务完整交付；真实有内容分享/翻译/识别、模型/数据/handler 与取消释放不可由空符号/fallback 关闭。此聚合只计1。|

逐项原始下一步、历史finding、当前源码引用见 `requirements.json`；小收据的实际范围及旧包/源码/正式账本区别见 `SCOPED_OBSERVATIONS.json`；全部输入SHA见 `SOURCE_PINS.json`。

正式销项仍应由原validator在同包/同boot/来源、签名、权限、原始UI/数据、边界和owned状态清理完整证明后登记。现有四族注册入口只有Contacts/WP分别可映射此域一个ID；尚未观察到本轮新正式逐ID登记。没有降低gate、添加排除、减去Selection，或把资源处置当公共状态清理。

执行范围：仅标准库读取JSON/源码文本及SHA，报告只写本新目录；未import/执行候选、tests、Git、SDK、crypto、编译、Docker、VM/HDC/QMP、debugfs，未读大包/镜像、135MB inventory或actual source/out/cache/key。原369/372及旧证据未改。全部报告成员一次性列入本manifest；冻结后不再追加。
