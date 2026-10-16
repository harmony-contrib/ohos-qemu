# 当前82个未核销ID逐条交付表

基点 `43a4c43991d3a5a9fe60c50c302d10daae592f99`；每ID只出现一次。A/B/C是主阻塞归类，U明确待核查；不是核销状态。

## A — 已有修复候选，待新包运行（25）

| Finding ID | 唯一owner / 共用工程包 | 具体下一步 |
| --- | --- | --- |
| `arkts_export:@ohos.accessibility.config:startBlinking` | apps / `accessibility-input-blink` | 同一新包完成真实输入、窗口像素/可访问节点、重复停止/调用者退出/重启及系统/普通权限边界；保留R50旧单项与本次完整结果的区别。 |
| `arkts_export:@ohos.accessibility.config:stopBlinking` | apps / `accessibility-input-blink` | 同一新包完成真实输入、窗口像素/可访问节点、重复停止/调用者退出/重启及系统/普通权限边界；保留R50旧单项与本次完整结果的区别。 |
| `behavior:accessibility-qemu-input-e2e` | apps / `accessibility-input-blink` | 同一新包完成真实输入、窗口像素/可访问节点、重复停止/调用者退出/重启及系统/普通权限边界；保留R50旧单项与本次完整结果的区别。 |
| `behavior:shortkey-empty-launch-config` | apps / `shortkey-settings` | 新包验证businessId/setKeyDownDuration、Meta+I、短按/错误修饰键、普通caller拒绝及重启。 |
| `behavior:distributed-hardware-ui-preinstall-path-mismatch` | apps / `distributed-hardware-ui` | 新包核对DHardwareUIAbility/Mech扩展BMS注册与真实发起/取消/错误/退出；与共同peer工程复用，不另造分布式后端通过结论。 |
| `behavior:photo-provider-not-activated-2in1` | apps / `photos-provider` | 验证真实Recent组件/Info/DefaultAlbum、授权/取消/退出、FA-card数据变更及cloud协议；首ARM64 phone后仍需2in1独立画像接受。 |
| `behavior:enterprise-provisioning-provider-missing` | apps / `admin-provisioning` | 复核已交实际SDK候选及原normal APL/ACL精确签名预装；新包真实enableAdmin/disableAdmin和状态持久化、super拒绝、取消/错误/双请求/退出/重启。 |
| `behavior:wallpaper-ui-provider-missing` | apps / `wallpaper-static-ui-renderer` | 使用当前严格wallpaper family验证Settings真实PhotoPicker授权、两次挑战图home/lock持久数据及屏幕、native fallback/真实renderer连接、默认还原/取消/策略/重启。 |
| `behavior:vpn-dialog-provider-prefix-mismatch` | apps / `vpn-service-broker` | 同新包验证实际com.ohos.vpndialog允许/拒绝/取消、真实caller结果与断连/重启；复用VPN真实TLS/多owner工程。 |
| `behavior:settings-navigation-provider-mismatch` | apps / `settings-navigation` | 运行全部公开navigation、实际UI/controller、2in1隐式app-info、权限拒绝/取消/退出/重启。 |
| `behavior:contacts-picker-entrypoint-missing-phone` | apps / `contacts-picker` | 使用严格contacts-picker family完整边界：普通normal零联系人权限签名caller、真实205选择/100分批聚合、取消/错误/双session/超时/退出后重开；同时保留JS→ABC→blob→native→image witness。 |
| `arkts_export:@ohos.net.vpn:getConnectedSysVpnConfig` | network / `vpn-service-broker` | 同新包跑多owner真实TLS对端/数据、TUN/netId/DNS/IPv4/IPv6/路由/UID隔离、可空getter与回调、重放/断连/worker-broker死后清理；不要把未来persist-tun/split-DNS/metric不支持写成通过。 |
| `arkts_export:@ohos.net.vpn:getConnectedVpnAppInfo` | network / `vpn-service-broker` | 同新包跑多owner真实TLS对端/数据、TUN/netId/DNS/IPv4/IPv6/路由/UID隔离、可空getter与回调、重放/断连/worker-broker死后清理；不要把未来persist-tun/split-DNS/metric不支持写成通过。 |
| `behavior:netmanager-ebpf-backend` | network / `netmanager-ebpf` | 新归档内核验证BPF syscall、实际program/map load/attach、UID计数/策略执行、拒绝与卸载；三个defconfig候选不是运行证明。 |
| `behavior:vpn-runtime-export-gaps` | network / `vpn-service-broker` | 同新包跑多owner真实TLS对端/数据、TUN/netId/DNS/IPv4/IPv6/路由/UID隔离、可空getter与回调、重放/断连/worker-broker死后清理；不要把未来persist-tun/split-DNS/metric不支持写成通过。 |
| `arkts_export:@ohos.geoLocationManager:getLocationIconStatus` | location / `location-privacy-icon` | 新包实测正常/系统caller query、start/stop/freeze/user/switch/revoke与真实PrivacyKit计账；不存在HD provider不能据普通GNSS推断HD状态。 |
| `arkts_export:@ohos.geoLocationManager:getPostProcessingTrack` | location / `gnss-skiing-track` | 使用root独立受控轨迹经vendor→HDI→定位业务，验证SPORT-only、实际坐标/高度/速度/方向、历史增量/24h保留、owner/delegation/撤权/停止/晚样本。 |
| `arkts_export:@ohos.file.photoAccessHelper:KnowledgeContent` | media / `knowledge-data-index` | 当前b1aa03c已纳入官方CN/2026 ICS及来源，正式launcher已有只读输入和变量转发；核对真实source/package选中正式asset SHA及范围sidecar，然后实际producer解析、新包photo/date/alias/ranking/account/VISITOR/三角色/revoke与更新删除验收。 |
| `behavior:audio-capture-and-dependent-pipelines` | media / `audio-real-pcm` | 根正式suite外部音频challenge→真实ES1370/ALSA→普通已授权HAP，独立PCM相关性/时间/声道采样、撤权/中断/重建；先记录所有模式实际覆盖。 |
| `behavior:media-recording-input-backends-missing` | media / `media-recording` | 新包普通签名HAP真实音视频输入、pause/stop/reset/release/recreate/权限，保留fresh输出并独立ffprobe/ffmpeg解码核对挑战/PTS/格式。 |
| `behavior:video-encoder-dependent-media-pipelines` | media / `encoded-video-pipelines` | 在同新包逐录制/录屏/转码走真实producer和encoder；独立解码挑战像素/音频/metadata/PTS，验取消/中断/重建/坏输入和surface释放；复用codec矩阵证据。 |
| `behavior:access-token-api26-kernel-abi` | system / `appspawn-child-identity` | 新包真实GET_ALL_PERMISSIONS/taskUID、普通HAP父子token/UID/帐号关系和冒用拒绝；可用legacy fallback时不把optional SPM不支持当缺陷。 |
| `behavior:native-child-process-phone-boundary` | system / `appspawn-child-identity` | 新包enabled profile跑实际AppMgr/AppSpawn/IPC、回调重入/重复/先通知、child PID/UID/token/FD/参数/退出/kill/重建及disabled phone拒绝；共用身份工程。 |
| `behavior:session-manager-profile-gap` | system / `sceneboard-session` | 核对新SDK/默认/实际image SysCap一致，运行窗口/session/PiP/floating，分别验phone和2in1；首包需RS稳定与真实sleep/wake。 |
| `behavior:graphics3d-scene-manager-unavailable` | system / `graphics3d-scene` | 新包实际Scene.load有效asset→render→destroy/recreate，验证缺插件/导入失败/retry/队列清理和稳定RenderService/Mesa；已有host/完整TU/link不替代实际显示。 |

## B — 尚缺实现或接线，可继续仓库修复（23）

| Finding ID | 唯一owner / 共用工程包 | 具体下一步 |
| --- | --- | --- |
| `behavior:phone-published-capabilities-not-declared` | apps / `published-syscaps` | 逐项确认DistributedFile/HiDumper/DataTransitManager/DeviceAuth/DeviceSecurityLevel/PinAuth的真实选件、插件和权限，再同步SDK/声明/实际镜像canIUse；不能只添六个字符串。 |
| `behavior:ability-share-picker-system-provider-missing` | apps / `share-picker` | 完成已交Settings modal路径的真实普通caller/URI委托验收；另实现旧ACTION_CHOOSE所需真实PickerDialog UIAbility与取消/结果协议，其他画像逐项验收。 |
| `behavior:ability-send-data-action-has-no-enabled-handler` | apps / `mms-senddata` | 先跑已构建/签名MMS text/plain收件人/草稿UI和取消不发送；按真实UTD/文件URI授权补附件链，Bluetooth/HMS后端缺失须另定合法实现。 |
| `behavior:avcast-media-controller-provider-mismatch` | apps / `cast-controller-volume` | 核对真实Want/结果和会话/音量协议，选唯一bundle/Ability并准确构建签名预装；新包验证选择/调整/拒绝/取消/关闭，cast正例共用独立peer。 |
| `behavior:media-control-volume-provider-activation` | apps / `cast-controller-volume` | 核对真实Want/结果和会话/音量协议，选唯一bundle/Ability并准确构建签名预装；新包验证选择/调整/拒绝/取消/关闭，cast正例共用独立peer。 |
| `behavior:accessibility-screen-reader-provider-missing` | apps / `screen-reader` | 实现可访问焦点/手势到真实TTS的reader生命周期、唯一bundle和设置启停协议；验证朗读内容/焦点变化及关闭后静默。 |
| `behavior:accessibility-caption-provider-missing` | apps / `live-caption` | 先确认可复用的真实ASR引擎/模型与许可，再实现音频订阅、识别、字幕UI/权限/停止/重启；不能仅安装AiCaptionServiceExtAbility空壳。 |
| `behavior:network-policy-settings-providers-missing` | apps / `network-policy-ui` | 按netpolicy模型实现NetAccessPolicySettingUIExtension真实UI/结果、通知跳转/权限/持久化；不能用普通Settings页替代协议。 |
| `behavior:telephony-apn-settings-provider-missing` | apps / `apn-settings-ui` | 定位真实APN Want/结果/权限并实现对应入口及增删改、取消/持久化；无线实际生效与modem工程共用。 |
| `behavior:wifi-system-ui-providers-not-activated` | apps / `wifi-system-ui` | 接线LocationDialog/PortalLogin准确签名和预装目录；实际STA/AP/portal挑战共用WiFi对端工程，验证取消/退出和通知目标。 |
| `behavior:camera-picker-entrypoint-missing-phone` | apps / `camera-picker` | 把已有product/picker真实模块接入phone构建/签名/预装而非替换MainAbility；实际camera输入、结果URI授权、取消/异常退出单独验收。 |
| `behavior:notification-extension-settings-entrypoint-missing` | apps / `notification-extension-grant-ui` | 补真实NotificationAccessGrantUIExtensionAbility与调用者结果契约，验证允许/拒绝/取消/caller退出/重启。 |
| `behavior:accessibility-settings-entrypoints-unavailable` | apps / `accessibility-settings-service` | 先验已修Promise/请求队列/真实四类notification action；继续实现安全idle-stop与新请求/销毁/重启边界，不能用提前成功或无startId terminateSelf结束。 |
| `behavior:notification-manager-settings-provider-missing-phone` | apps / `notification-management-ui` | 明确phone到底选用哪个实际provider和UIExtension契约，接真实模块/配置并验证通知修改、返回、权限、取消/退出。 |
| `behavior:avsession-desktop-lyrics-provider-missing` | apps / `desktop-lyrics` | 实现DesktopLyricAbility、真实会话歌词订阅/显示/隐藏/关闭/重启；不靠bundle别名声称已有UI。 |
| `behavior:location-privacy-ui-providers-unavailable` | apps / `location-privacy-ui` | 接线实际LocationPrivacyExtAbility签名预装并补缺失detail协议；验证同意/拒绝/详情/取消/caller退出，区分PermissionManager前台系统权限弹窗。 |
| `behavior:arkui-expanded-text-menu-providers-missing` | apps / `expanded-text-menu` | 实现与真实dlopen ABI匹配的expanded_menu和动作映射，复用Browser/Calendar/Maps/share真实handler，验文本/URI安全授权与取消/退出。 |
| `behavior:arkui-text-service-runtime-plugins-missing` | apps / `text-service-plugins` | 按真实systemshare/translation/analyzer ABI补实际服务与有内容结果、取消/释放；先确定模型/数据/handler来源，不造空符号。 |
| `behavior:peer-device-user-nat-isolation` | network / `peer-networking` | root实现显式bridge/tap/唯一MAC/端口/设备身份，再用同一已包装代表归档的两个实例做发现/帐号认证/数据/peer移除；不需要先构建其余五包。 |
| `behavior:audio-interrupt-haptic-renderer-dependency` | media / `audio-focus-haptic` | 运行已交双UID前后台/fresh-PCM真实焦点协议；另补明确的AudioHapticPlayer音频与实际vibrator同步/失败/停止证据和必要实现，不能只测Renderer PCM。 |
| `behavior:media-codec-base-partial` | media / `codec-format-matrix` | 先验已有AVC stride/plane/offset修复；按真实公开能力矩阵补HEVC/P010等未实现路径或诚实错误，不用改变声明/跳过格式缩范围核销；独立SPS/IDR/码率/PTS/EOS验证。 |
| `behavior:msdp-device-status-mock-or-missing-clients` | system / `msdp-modalities` | 先用已交external-inputs ordinary HAP验证VDI→HDI→SensorAgent→算法→公开still；再逐公开类型/客户端补真实实现，relativeStill等仍缺，不能整条由still子集核销。 |
| `behavior:calendar-lifecycle-device-difference` | system / `calendar-full-lifecycle` | 先新包真实BMS/普通无日历权限editEvent用户Save/Cancel和lower/whole CRUD；继续补Calendar MainAbility/URI提醒路由及提醒/重复规则/重启生命周期。 |

## C — 真实供应方/硬件/凭据/对端数据仍缺（30）

| Finding ID | 唯一owner / 共用工程包 | 具体下一步 |
| --- | --- | --- |
| `behavior:phone-avinputcast-not-declared` | apps / `cast-input-peer` | 先确认新phone声明及provider协议，再提供实际发送端/接收端和共享可发现网络，以随机媒体挑战验证会话、数据、取消及清理。 |
| `behavior:telephony-number-identity-provider-missing` | apps / `telephone-identity-data` | 分别指定numberlocation/numbermark DataShare、NumberIdentity、SpamShield、HSDR实际owner和合法数据/服务；验证更新/离线/未知号码/错误/权限，不能填固定分类。 |
| `arkts_export:@ohos.bluetooth.connection:startPairOutOfBand` | network / `bluetooth-controller-peer` | 先接libbt_vendor真实H4通道和独立controller/peer；验证经典P192/P256及LE SC C/R、最终enable/disable、配对/数据、取消/重放/超时/off/unplug。 |
| `behavior:bluetooth-state-transition-false-success` | network / `bluetooth-controller-peer` | 先接libbt_vendor真实H4通道和独立controller/peer；验证经典P192/P256及LE SC C/R、最终enable/disable、配对/数据、取消/重放/超时/off/unplug。 |
| `behavior:wifi-sta-backend-unavailable` | network / `wifi-radio-peer` | 使用新包实际mac80211_hwsim/virt_wifi、WPA和监管配置；提供独立兼容STA/AP，对真实DHCP/包传输/P2P、设备变化/失败/清理作挑战。 |
| `behavior:usb-manager-device-query` | network / `usb-host-udc-mtp` | 先选QEMU设备/受控passthrough并明确device-mode真实UDC/configfs，另接准确MtpService；验descriptor/query/open/权限/数据/unplug。 |
| `arkts_export:@ohos.geoLocationManager:addFusionFence` | location / `fusion-fence-inputs` | 复用新GNSS provider和真实Request/WorkRecord，补实际WLAN扫描/实时CELL peer；逐shape/bitmap/owner/权限/截止/队列验证，BLE bitmap8明确801，不伪装支持。 |
| `arkts_export:@ohos.geoLocationManager:getCurrentDistrict` | location / `reverse-geocoder` | 按已交真实Binder peer ABI部署受配置/签名的能力，输入有来源/许可行政区边界或真实服务；对GNSS点/locale作实际查询、无覆盖/超时/断连/缓存/权限挑战。 |
| `arkts_export:@ohos.geoLocationManager:isFusionFenceSupported` | location / `fusion-fence-inputs` | 复用新GNSS provider和真实Request/WorkRecord，补实际WLAN扫描/实时CELL peer；逐shape/bitmap/owner/权限/截止/队列验证，BLE bitmap8明确801，不伪装支持。 |
| `arkts_export:@ohos.geoLocationManager:removeFusionFence` | location / `fusion-fence-inputs` | 复用新GNSS provider和真实Request/WorkRecord，补实际WLAN扫描/实时CELL peer；逐shape/bitmap/owner/权限/截止/队列验证，BLE bitmap8明确801，不伪装支持。 |
| `arkts_export:@ohos.geoLocationManager:startBluetoothSearch` | location / `bluetooth-controller-peer` | 接真实HCI/controller后让BleCentralManager解析独立广告ID/RSSI/payload，经真实service/NAPI验证过滤、启动失败、队列/注销/撤权/用户切换；不能直接注入NAPI回调。 |
| `arkts_export:@ohos.geoLocationManager:stopBluetoothSearch` | location / `bluetooth-controller-peer` | 接真实HCI/controller后让BleCentralManager解析独立广告ID/RSSI/payload，经真实service/NAPI验证过滤、启动失败、队列/注销/撤权/用户切换；不能直接注入NAPI回调。 |
| `arkts_export:@ohos.telephony.call:offReceiveRttMessage` | location / `ims-rtt-session` | 按实际ImsCoreServiceInterface/PROXY_IMS_CALL提供协商会话与独立RTT peer，逐方法验证文本/modify/error、模式/权限、off静默/会话退出/重连；AT注册不能替代IMS。 |
| `arkts_export:@ohos.telephony.call:offRttErrCause` | location / `ims-rtt-session` | 按实际ImsCoreServiceInterface/PROXY_IMS_CALL提供协商会话与独立RTT peer，逐方法验证文本/modify/error、模式/权限、off静默/会话退出/重连；AT注册不能替代IMS。 |
| `arkts_export:@ohos.telephony.call:offRttModifyInd` | location / `ims-rtt-session` | 按实际ImsCoreServiceInterface/PROXY_IMS_CALL提供协商会话与独立RTT peer，逐方法验证文本/modify/error、模式/权限、off静默/会话退出/重连；AT注册不能替代IMS。 |
| `arkts_export:@ohos.telephony.call:onReceiveRttMessage` | location / `ims-rtt-session` | 按实际ImsCoreServiceInterface/PROXY_IMS_CALL提供协商会话与独立RTT peer，逐方法验证文本/modify/error、模式/权限、off静默/会话退出/重连；AT注册不能替代IMS。 |
| `arkts_export:@ohos.telephony.call:onRttErrCause` | location / `ims-rtt-session` | 按实际ImsCoreServiceInterface/PROXY_IMS_CALL提供协商会话与独立RTT peer，逐方法验证文本/modify/error、模式/权限、off静默/会话退出/重连；AT注册不能替代IMS。 |
| `arkts_export:@ohos.telephony.call:onRttModifyInd` | location / `ims-rtt-session` | 按实际ImsCoreServiceInterface/PROXY_IMS_CALL提供协商会话与独立RTT peer，逐方法验证文本/modify/error、模式/权限、off静默/会话退出/重连；AT注册不能替代IMS。 |
| `arkts_export:@ohos.telephony.call:sendRttMessage` | location / `ims-rtt-session` | 按实际ImsCoreServiceInterface/PROXY_IMS_CALL提供协商会话与独立RTT peer，逐方法验证文本/modify/error、模式/权限、off静默/会话退出/重连；AT注册不能替代IMS。 |
| `arkts_export:@ohos.telephony.call:setRttCapability` | location / `ims-rtt-session` | 按实际ImsCoreServiceInterface/PROXY_IMS_CALL提供协商会话与独立RTT peer，逐方法验证文本/modify/error、模式/权限、off静默/会话退出/重连；AT注册不能替代IMS。 |
| `arkts_export:@ohos.telephony.call:startRtt` | location / `ims-rtt-session` | 按实际ImsCoreServiceInterface/PROXY_IMS_CALL提供协商会话与独立RTT peer，逐方法验证文本/modify/error、模式/权限、off静默/会话退出/重连；AT注册不能替代IMS。 |
| `arkts_export:@ohos.telephony.call:stopRtt` | location / `ims-rtt-session` | 按实际ImsCoreServiceInterface/PROXY_IMS_CALL提供协商会话与独立RTT peer，逐方法验证文本/modify/error、模式/权限、off静默/会话退出/重连；AT注册不能替代IMS。 |
| `arkts_export:@ohos.telephony.observer:offCommunicationStateChange` | location / `at-modem-5a` | 先建立实际参考AT vendor/tty/radio/SIM状态；独立peer发+OHOS5A:0/1，校验unknown/去重/slot/权限/队列/off/env清理与radio reset回false。 |
| `arkts_export:@ohos.telephony.observer:onCommunicationStateChange` | location / `at-modem-5a` | 先建立实际参考AT vendor/tty/radio/SIM状态；独立peer发+OHOS5A:0/1，校验unknown/去重/slot/权限/队列/off/env清理与radio reset回false。 |
| `behavior:location-provider-backends-missing` | location / `location-provider-composition` | 组合GNSS、真实geocoder、HCI/WLAN/CELL各独立证据，再复核公共定位/帐号/权限/开关；GNSS子集通过不能核销其他producer。 |
| `behavior:telephony-no-modem-or-sim` | location / `at-modem-5a` | 配置真实RilInitOps厂商库/AT tty并接受受控modem独立SIM、radio、注册/呼叫/SMS/data挑战；RTT另依赖真实IMS，不能由+OHOS5A构造全套modem能力。 |
| `behavior:audio-vivid-metadata-runtime-plugin-missing` | media / `audio-vivid-plugin` | 取得合法格式/算法/实现及许可，按真实Create/Destroy factory ABI构建libAudioVividMetaBuilder.z.so；测对象位置/增益元数据序列化往返、坏输入/生命周期。 |
| `behavior:device-attest-uninitialized` | system / `oem-attestation` | 向可信OEM取得产品身份、密钥安全provisioning和真实验证服务/信任链配置；不在报告粘贴secret。新包验证初始化/auth/software/detail真实ticket及失效/失败。 |
| `behavior:advertising-service-provider-missing` | system / `advertising-provider` | 先取得真实provider源码或签名包/ABI/入口与合法广告内容/服务，再补providerApiAbilityName等准确配置并按原签名权限安装；实际load/render/callback/取消失败验收。 |
| `behavior:security-guard-empty-model-config` | system / `security-guard-model` | 先确定产品真实modelName/事件/collector/判定语义和合法实现/数据再配置；getModelResult(capability-audit)的401只能是未知模型反例，不能改空成功或冒充真实风险输出。 |

## U — 证据不足，待核查（4）

| Finding ID | 唯一owner / 共用工程包 | 具体下一步 |
| --- | --- | --- |
| `behavior:api26-runtime-export-mismatches-phone` | apps / `api26-surface-refresh` | 在新归档重采arkts-export-surface，按模块把仍缺的实际成员/值/行为分派唯一owner；引用既有分模块修复，不能按候选数量扣减此聚合ID。 |
| `behavior:intelligent-scene-notification-query-fails` | apps / `intelligent-scene-query` | 新包复测isDoNotDisturbEnabled和isNotifyAllowedInDoNotDisturb，保存真实初始化/数据/调用者/重启路径，再按具体失败决定源码修复。 |
| `behavior:certificate-dialog-device-result` | apps / `certificate-dialog-review` | 沿certificate_manager支持判断运行证书选择/取消/拒绝/空列表/device分支；先保留supportsCACertDialog原始值和实际BMS目标。 |
| `behavior:app-domain-verification-extension-missing` | system / `domain-association` | 用实际可控HTTPS association及匹配/不匹配签名安装bundle验证native VerifyTask fallback、refresh/cache/路由；若empty TargetInfo确实导致失败再修真实选包，不猜target。 |
