# AudioVivid 元数据的官方实现边界（2026-10-19）

结论：在已核对的 OpenHarmony 官方公开实现和对应 Media SIG 部件中，能够交付的是
元数据 API 封装、抽象接口和可选库加载协议，没有找到可构建、可交付的真实
MetaBuilder 插件。按本轮约定，该能力列为当前开源实现不支持；不再用一个
“仍待编写”的假插件无限延长修复。新镜像是否装有供应商库仍需运行时实测，二者分开记录。

官方 `multimedia_media_foundation` 的 master 固定于
`66033b04243cdf3f973a5ebdb4afa2cddd17c207`（提交时间 2026-10-15 UTC）。
[API 实现](https://github.com/openharmony/multimedia_media_foundation/blob/66033b04243cdf3f973a5ebdb4afa2cddd17c207/src/capi/native_audio_vivid.cpp#L164)
通过 `dlopen` 加载 `libAudioVividMetaBuilder.z.so`，再寻找实际工厂和析构导出；
缺库时返回 `AV_ERR_UNSUPPORT`。这些导出仅是动态查找字符串，不是该文件中的实现。

[内部接口](https://github.com/openharmony/multimedia_media_foundation/blob/66033b04243cdf3f973a5ebdb4afa2cddd17c207/interface/inner_api/meta/meta_audio_vivid.h#L26)
提供 `AudioMetaBuilderBase` 的纯虚操作，包括初始化、对象位置/增益、序列化与对象管理。
[C API 构建目标](https://github.com/openharmony/multimedia_media_foundation/blob/66033b04243cdf3f973a5ebdb4afa2cddd17c207/src/capi/BUILD.gn#L56)
编译的是 `native_media_core` 中的 API 封装。完整非截断仓库 tree 加全部 66 个 GN/GNI
及 5 个 AudioVivid 路径的核对，没有找到 MetaBuilder 插件构建目标。
逐文件 URL/SHA 和匹配位置保存在 `official-native-meta-build-scan.json`。

官方[单元测试](https://github.com/openharmony/multimedia_media_foundation/blob/66033b04243cdf3f973a5ebdb4afa2cddd17c207/tests/unittest/audio_vivid/audio_vivid_unit_test.cpp#L98)
单独覆盖库不可加载时的创建结果：返回不支持，输出 builder 保持空。这是官方允许的
能力边界；不是要求伪造一个成功 builder。

官方 [Media SIG 清单](https://github.com/openharmony/community/blob/af4dba4f7c432befe4f20ee2a7a4ac734781f1c3/sig/sig_media/sig_media_cn.md)
列出的对应核心部件是 `multimedia_media_foundation`、`multimedia_audio_framework`、
`multimedia_av_codec` 等，没有列独立 MetaBuilder 仓。面向 OpenHarmony 和
OpenHarmony-SIG 的公开精确名称搜索也没有返回可交付插件。Gitee/GitCode 的
SIG 全仓 API 读取遇到 TLS 失败；GitHub 不存在同名 SIG 组织。这些失败记录已保留，
不能据此声称穷尽了整个 SIG 组织或证明所有私有/供应商库不存在。

`libaudio_integration_mcr.z.so` 是另一条空间声道转换插件，不是 MetaBuilder。
本轮 `audio_vivid_integrity` 只修真实 sink 的数据/元数据边界，不增加上述任一插件，
也不证明 AudioVivid 编解码或空间渲染成功。元数据构建、解码和空间转换三种能力
不能由一个公共头文件、一次 PCM 复制或一个库名互相替代。
