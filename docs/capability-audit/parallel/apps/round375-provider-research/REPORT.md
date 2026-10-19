# 四项官方 provider 可交付性研究（冻结、有限范围）

结论：本次核查没有取得这四项所需的、可直接交付到当前 QEMU 的完整 provider 源码或经核验预编译 artifact。建议本次产品范围将四个精确功能声明为 unsupported，保留一般 Accessibility、AVSession、ArkUI 框架能力。此结论不是“全网不存在”，不是四项实现完成，也不产生 runtime PASS 或 ledger closure。caption/号码研究由 network 负责，不在本报告重复计数。

| 精确 finding | 已确认可复用材料 | 当前可交付建议 |
|---|---|---|
| `behavior:accessibility-screen-reader-provider-missing` | 无障碍 manager/config/Extension 框架；固定目标 `com.ohos.screenreader/AccessibilityExtAbility` | ScreenReader 完整朗读反馈 unsupported；缺完整 provider、真实 TTS engine/音色模型/许可和焦点手势→内容→中断/关闭静默链 |
| `behavior:avsession-desktop-lyrics-provider-missing` | AVSession 的连接、状态、IPC consumer | DesktopLyricAbility unsupported；缺准确 bundle/ability 的 extension 后端、真实 session 歌词订阅/桌面窗口及重启释放 |
| `behavior:arkui-expanded-text-menu-providers-missing` | expanded-menu loader、ACE 内部类型及函数签名 | 扩展文本菜单 provider unsupported；缺真实 `.so` 与各动作对应真实 handler/授权/取消退出 |
| `behavior:arkui-text-service-runtime-plugins-missing` | share/translation/analyzer 三类 loader、interface、fallback | 三插件聚合仍只计 1 项；缺真实工厂/析构、内容处理服务/模型/数据及匹配 ABI 的可交付 artifact |

## 精确源码依据和 ABI 边界

以下 revision 是本次公网观察的 upstream snapshot，不是当前 prepared 产品 revision。完整下载正文、URL、SHA、行号在 `source-pins.json`；其余网页观察与限制在 `web-observations.json`。未经 actual product source vector 比较，不能据这些新 master 快照断言当前 image 已安装或可加载。

* Accessibility `3ffbe3513f07cb1df2bd98d74089582dff5eb33a`：`services/aams/src/accessibility_account_data.cpp:62,73` 固定 ScreenReader 身份。完整 tree 1055 项包含框架、配置和测试，未发现完整 app 的 `module.json5`/HAP provider。具备 extension API、enable 命令或读取 enabled 状态，不等于实现朗读。Intelligent Voice `19188608475123695def986a399641bfa64a49f7` README:7,18-25,53 的主要能力是注册/唤醒与 DSP；AI Engine `2bfc731e1661cc64c0169c88075e34bd48e896f8` 的通用 IPlugin/关键词唤醒示例也未建立 TTS 合成引擎和 voice 数据交付。[Accessibility 源](https://github.com/openharmony/accessibility/blob/3ffbe3513f07cb1df2bd98d74089582dff5eb33a/services/aams/src/accessibility_account_data.cpp#L62)、[Intelligent Voice](https://github.com/openharmony/ai_intelligent_voice_framework/blob/19188608475123695def986a399641bfa64a49f7/README.md)、[AI Engine](https://github.com/openharmony/ai_engine/blob/2bfc731e1661cc64c0169c88075e34bd48e896f8/README.md)。
* AVSession `000ed1e3b8dc9e2cdb44aabd9a91807fecd6ff9e`，`services/session/adapter/extension_connect_helper.cpp:30-61,246-278` 要求 `com.ohos.mediacontroller/DesktopLyricAbility`，传 `sessionId`，连接后以 remote 的真实 interface descriptor 发 token，再发 String16 sessionId/handler，以 sceneCode SendRequest 并读取 Int32 reply。不能把相似名称的音乐 app 或普通 controller UI 当这个服务；官方 AVSession MediaController sample 的网页 README 仅展示 API10 RK3568 的控制/歌词交互，未建立上述 extension/IPC 后端。[精确 consumer](https://github.com/openharmony/multimedia_av_session/blob/000ed1e3b8dc9e2cdb44aabd9a91807fecd6ff9e/services/session/adapter/extension_connect_helper.cpp#L30)、[官方 sample](https://gitcode.com/openharmony/applications_app_samples/tree/master/code/SystemFeature/Media/AVSession/MediaController)。
* ACE `21b150e7bb1d5308846f8e5be8ef0482fb433315` 的 `expanded_menu_plugin_loader.h:31-41,54-60,79,99` 选择 `/system/lib64/expanded_menu/libexpanded_menu.z.so`（aarch64/x86_64）或 lib，要求 `CreateDeviceMenu`、`GetStoreUrlFront`、`GetAPPName`。函数参数含 `RefPtr<FrameNode>`、`shared_ptr<SelectOverlayInfo>`、`TextDataDetectType`，不是任意同名 ELF 就兼容；需要匹配实际 ACE 类型/编译器/CFI、生命周期及真实动作 handler。完整 ACE tree 33700 项可见 loader/interface/default，不构成这些外部 provider 已交付证明。[loader](https://github.com/openharmony/arkui_ace_engine/blob/21b150e7bb1d5308846f8e5be8ef0482fb433315/frameworks/core/components_ng/pattern/select_overlay/expanded_menu_plugin_loader.h#L31)。
* 同一 ACE snapshot 的三个 `adapter/ohos/osal/*_loader.cpp` 分别要求成对符号 `OHOS_ACE_CreateTextShareInterface`/`OHOS_ACE_DestroyTextShareInterface`、`OHOS_ACE_createTextTranslationInstance`/`OHOS_ACE_destroyTextTranslationInstance`、`OHOS_ACE_createDataDetectorInstance`/`OHOS_ACE_destroyDataDetectorInstance`（大小写不可混用）。literal 路径为 `system/lib64/...`（aarch64）或 `system/lib/...`（else），实际正文没有前导 `/`；不能自行修写为已验证路径或推断 x86_64 选择 lib64。接口分别传 context/Rect/window/content、翻译文本/矩形、检测 callback/entity-menu；默认 false/-1/空结果不算 provider。当前 Settings Share/Picker 成功也不会自动生成这三个 ABI 实现。[share](https://github.com/openharmony/arkui_ace_engine/blob/21b150e7bb1d5308846f8e5be8ef0482fb433315/adapter/ohos/osal/text_share_loader.cpp)、[translation](https://github.com/openharmony/arkui_ace_engine/blob/21b150e7bb1d5308846f8e5be8ef0482fb433315/adapter/ohos/osal/text_translation_loader.cpp)、[analyzer](https://github.com/openharmony/arkui_ace_engine/blob/21b150e7bb1d5308846f8e5be8ef0482fb433315/adapter/ohos/osal/data_detector_loader.cpp)。

## 官方预编译 HAP 不是被忽略的替代来源

官方 `applications_hap@fd2c78258466076118c8a9bf1a97fdbcec06a5c8` 完整 recursive tree 为 60 项、`truncated=false`。没有 ScreenReader、MediaController/DesktopLyric 的同名 HAP，也没有 expanded_menu 或三个插件 `.so` 的路径；`pipline.md` 永久归档表也没有这些 provider 行。仓库 README 明确预编译 HAP 是正式分发方式，本报告认可“有完整 artifact 时不要求源码也可继续审计”，但本次未取得匹配目标。

仓库 LICENSE 为 Apache-2.0，包含对象再分发及 notice 条件；这个许可不能替未取得的外部 engine/voice/model 授权。实际抓取的 Music_Demo、Settings、SystemUI、Launcher、SecurityPrivacyCenter 五文件均严格是 3 行 Git-LFS pointer，object OID/声明 size 已保存；未下载这些无关大对象，未捏造其 bundle、ability、签名或 backend inventory。BUILD.gn 的安装映射分别是 `com.ohos.distributedmusicplayer`、`com.ohos.settings`、`com.ohos.systemui`、`com.ohos.launcher`、`com.ohos.security.privacycenter`，没有精确 ScreenReader/MediaController provider 映射。安装目录映射本身也不等同实际 ZIP 内 bundle/ability 已验证。不能把 Music 重命名成 mediacontroller、把 Settings 的入口当 TTS 服务。[官方目录](https://github.com/openharmony/applications_hap/tree/fd2c78258466076118c8a9bf1a97fdbcec06a5c8)、[BUILD](https://github.com/openharmony/applications_hap/blob/fd2c78258466076118c8a9bf1a97fdbcec06a5c8/BUILD.gn)、[许可](https://github.com/openharmony/applications_hap/blob/fd2c78258466076118c8a9bf1a97fdbcec06a5c8/LICENSE)、[永久归档索引](https://github.com/openharmony/applications_hap/blob/fd2c78258466076118c8a9bf1a97fdbcec06a5c8/pipline.md)。

## 范围限制与将来可接入的标准

SIG system_applications 的旧 Gitee README 指向 GitCode；本轮当前 GitCode 完整源获取受 SSL EOF、GitHub API rate limit 限制，明确保留 unknown，不能宣称 SIG 当前仓库无实现。public manifest `1168a5fe2568813e5f240f3e4ad7a12644060568` 的 default/ohos 清单检查只是有限来源索引，也不是整个生态存在性证明。

外部 `harmonyos-sdk-for-openharmony/docs` 广告 CoreSpeechKit/ShareKit 与 Wukong100 设备支持，是候选入口信息；其文档许可不建立 runtime 库/模型再分发权、实际下载物 revision 或 QEMU ABI。Flutter TTS wrapper/系统调用 sample 依赖设备已具备 TTS，不能替代引擎。本轮没有把这类材料计为 QEMU provider。[外部 SDK 文档](https://gitcode.com/harmonyos-sdk-for-openharmony/docs)、[TTS wrapper](https://gitcode.com/oh-flutter/text_to_speech)、[SIG 入口](https://gitcode.com/openharmony-sig/system_applications)。

后续若取得精确源码或合法完整 artifact，应先固定 revision/所有 payload/许可/模型、核对实际产品 ABI 和上列身份/符号/协议，再由 root 统一 SDK/native build、签名/安装、真实新包功能/拒绝/取消/死亡/关闭释放验收。不可写空 provider、伪内容、仅导出符号、保留成功布尔来缩减原请求能力。

本轮仅公网 HTTP/网页与本地静态文本/JSON/XML/tree/SHA 检查；无 SDK/native、签名/crypto、Docker、VM/HDC/QMP、测试/候选 import、source/out/cache、Git mutation。冻结后不追加成员；后续材料必须新目录。精确结果见 `result.json`。
