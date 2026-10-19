本轮核对 4 个原始能力 ID。完整能力的当前交付结论为：字幕 provider、完整号码识别聚合、未 provision 的设备证明、默认风险模型均不能凭现有源码直接宣称通过。号码识别的本地用户标记、有限归属地和黄页具备可复用实现，应单独接入和验收。unsupported 是用户定义的交付范围状态，repaired/runtime-pass 均为 0。

| 原始 ID | 研究分类 | 可复用与缺失边界 |
| --- | --- | --- |
| `behavior:accessibility-caption-provider-missing` | product-dependent | 有离线 ASR sample；没有已确认完整实时 AiCaption provider，四必需资产仅 LFS 指针，依赖和资产许可未闭环 |
| `behavior:telephony-number-identity-provider-missing` | product-dependent | 有真实本地标记 CRUD/DataShare/归属地解析；完整数据、SpamShield/HSDR provider 未交付，且当前产品未接组件 |
| `behavior:device-attest-uninitialized` | product-dependent | 服务实现存在；真实认证云身份/token 无通用默认值，当前产品未 provision |
| `behavior:security-guard-empty-model-config` | absent（默认模型） | 框架/ABI 存在；7.0 与 master 生产 modelcfg 均空，无已确认完整默认风险模型 |

实际浏览了 OpenHarmony / SIG 官方主页和仓库。OpenHarmony 迁移公告将 GitCode 列为主仓、Gitee 列为镜像；部分 GitCode 文件受限时，以 OpenHarmony 官方 GitHub 镜像的不可变 commit 核对。下面是已实际从官方 API 核实的 `OpenHarmony-7.0-Release` pins；不是把 master 伪称为 7.0。

| 仓库 | 7.0 commit |
| --- | --- |
| applications_number_identity | `50e1330646432ce166e7981c577f25f46c90e7ac` |
| xts_device_attest | `edbf39f5ca115e6096a87909b39f29c4fcfdc553` |
| security_security_guard | `b6e82fc42cd88e675ff823d4a3031a5b62e9921d` |
| ai_intelligent_voice_framework | `630177fce145c5d811ed143fbd54b484ea9a6e4b` |

字幕：主树 `MindSporeLiteCDemoASR` 是文件识别示例；选 CPU、关闭 FP16，API14/Phone 示例没有证明 OHOS7 ARM64/x86 六包的原生 ABI、算子、实时性能。当前应用 sample 的 host 源码 commit 由 root 提供为 `9816293dbb701405719af072e226584ad47f91bc`，不代表新 prepared volume。当前四 LFS 对象共声明 **269,435,904 bytes**，实际文件仅 131–134 bytes；OID/size 在 result.json。不能据指针断言远端对象不存在，GitCode 文件/LFS与 SIG AsrAndTts 子目录本轮受限。[官方 ASR 指南](https://gitcode.com/openharmony/docs/blob/master/zh-cn/application-dev/ai/mindspore/mindspore-asr-based-native.md)、[对应 sample 源码](https://gitcode.com/openharmony/applications_app_samples/tree/9816293dbb701405719af072e226584ad47f91bc/code/DocsSample/MindSporeLiteKit/MindSporeLiteCDemoASR)、[SIG AI samples](https://gitcode.com/openharmony-sig/applications_ai_model_samples)。

代码与业务资产须分开看：app_samples 根 LICENSE 第 4、13、21、25–26 行将 Testing Materials 限于内部功能测试，禁止随产品/服务分发；sample 音频不能直接成为业务数据，模型也没有单独可验证来源和转换声明。原始 Whisper 代码及权重的 MIT 授权是公开可复用路线，不能证明 OH 三个转换后 ms 的身份、许可或完整实时字幕实现。[host 对应 LICENSE](https://gitcode.com/openharmony/applications_app_samples/blob/9816293dbb701405719af072e226584ad47f91bc/LICENSE)、[Whisper 不可变来源及许可](https://github.com/openai/whisper/blob/86098128c0b4f24f0e2aa2994de830614b474227/README.md#license)。智能语音框架主要提供注册/唤醒，不能代替 ASR。[7.0 README](https://github.com/openharmony/ai_intelligent_voice_framework/blob/630177fce145c5d811ed143fbd54b484ea9a6e4b/README_zh.md)。本研究停止在交付边界，不新增模型转换或实时字幕产品工程。

号码识别：官方 7.0 源码为 Apache-2.0，含系统 HAP/native DataShare 与用户标记实现；本地 `base/telephony/number_identity` 缺目录、manifest 缺该 repo。归属文本只有 11 行/10 个唯一号段，黄页仅 3 个运营商分组/6 个顶层号码条目，完整 dat 明确由产品准备。[7.0 README](https://github.com/openharmony/applications_number_identity/blob/50e1330646432ce166e7981c577f25f46c90e7ac/README_zh.md)、[预置数据目标](https://github.com/openharmony/applications_number_identity/blob/50e1330646432ce166e7981c577f25f46c90e7ac/etc/BUILD.gn)。

可实施的最小子能力是 **用户自身本地标记 CRUD/持久化、限定号段归属查询和有限黄页**，无需云骚扰数据。接入 component `number_identity`，至少部署 `NumberIdentity` HAP、`number_identity` native library、JS numberlookup/numberidentity、默认 etc:number_location 文本数据目标及 bundle 声明依赖；完整 target 与依赖清单见 result.json 的 `minimal_local_subcapability`。[部件定义](https://github.com/openharmony/applications_number_identity/blob/50e1330646432ce166e7981c577f25f46c90e7ac/bundle.json)。当前 caller 使用 `com.numberidentity` 和 `datashare:///numbermarkability`，新 provider 使用 `com.ohos.numberidentity` / `com.ohos.numbermarkability`，必须统一 bundle/authority/descriptor；不能只安装 HAP。其 service 仅接命令 0 导入，HSDR 源码仍只是 client，无法提供完整 SpamShield/HSDR 聚合行为。[service](https://github.com/openharmony/applications_number_identity/blob/50e1330646432ce166e7981c577f25f46c90e7ac/entry/src/main/ets/service/NumberIdentityService.ts)、[HSDR client](https://github.com/openharmony/applications_number_identity/blob/50e1330646432ce166e7981c577f25f46c90e7ac/shared/src/number_identity_hsdr_helper.cpp)。最小子能力接入后仍要真实包内 CRUD/重启/权限/未知号码验收，整个原始 ID 不能由此全关闭。

DeviceAttest：7.0 OEM adapter 与本地文件 hash 相同，ProductId/ProductKey 默认为空；官方流程要求企业登记、XTS审核、认证云 token 与产线烧录。Apache 服务源码、HAP 平台签名或任意设备 ID 均不提供真实认证身份。当前未 provision 产品建议明确 unsupported；以后具备合法身份再走真实初始化/认证及负例。[7.0 流程](https://github.com/openharmony/xts_device_attest/blob/edbf39f5ca115e6096a87909b39f29c4fcfdc553/README_zh.md)、[OEM adapter](https://github.com/openharmony/xts_device_attest/blob/edbf39f5ca115e6096a87909b39f29c4fcfdc553/services/oem_adapter/src/device_attest_oem_adapter.c)。

SecurityGuard：官方 7.0 和 master 的生产 modelcfg 均空。GetModelApi DSO 的 IModel ABI 包含 Init/GetResult/SubscribeResult/Release，cfg 还需真实路径/事件/权限和有限数值 modelId；填一条 JSON 或复制 unittest preset_model/libtest 不能产生真实风险检测。不推断必须商业 OEM key，但本轮未找到完整官方默认模型。当前产品默认风险模型建议 unsupported，保留框架本身。[7.0 默认配置](https://github.com/openharmony/security_security_guard/blob/b6e82fc42cd88e675ff823d4a3031a5b62e9921d/oem_property/hos/security_guard_model.cfg)、[实际模型加载](https://github.com/openharmony/security_security_guard/blob/b6e82fc42cd88e675ff823d4a3031a5b62e9921d/services/risk_classify/model_manager/src/model_manager.cpp)、[IModel ABI](https://github.com/openharmony/security_security_guard/blob/b6e82fc42cd88e675ff823d4a3031a5b62e9921d/interfaces/inner_api/classify/include/i_model.h)。

建议 root 按显式用户政策记录以上四个精确 ID 的当前完整能力 unsupported 范围，单独保留号码本地子能力的实现任务。该范围决定不增加 repaired/runtime-pass，不改现有 runtime verifier，不证明其他包或旧 image 行为。实际 source/hash、master/7.0 差异、LFS、接线和逐项限定保存在 result.json 与研究 inputs。所有本轮文件写入均限于获准研究目录；冻结后停止源树读取，没有产品代码变更或资源运行。
