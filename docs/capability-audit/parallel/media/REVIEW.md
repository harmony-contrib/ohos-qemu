# Media 首轮复核与候选修复（2026-10-16）

基线 `2aa40c0cdaa9710c9d330814211f10c686ddd431`，media 组逐项复核 7 项，
本轮核销 **0 项**。所有修改仅在 media worktree；Docker 仅在获准的
`ohos-qemu-parallel-source-20261015-01:/ohos` 做小范围只读查询，没有访问 out
作为产物证据，没有编译、QEMU、HDC、重启或清理共享资源。
`source-review.json` 记录固定项目 revision、源文件 SHA256 和具体契约摘录。

| 要求 | 复核结果与本轮处理 | 仍需的实际能力/证据 |
| --- | --- | --- |
| KnowledgeContent | 固定 SDK 有静态两方法；固定 media_library 的 4066 个相关源码/配置文件中三精确类/方法标识均无命中；现有地理知识表不能直接冒充这个 API。见下方真实数据契约。 | NAPI/IPC、权限、实体映射/排序/建议查询及索引更新/删除闭环；非空数据与三角色新包验证。 |
| audio-capture-and-dependent-pipelines | ALSA 捕获实际调用 snd_pcm_open/readi；仓库已有 ES1370/ALSA/policy 准备，历史 Renderer 单项有真实 PCM 回调，所以原“无设备”文字只作历史失败，不能据此断言当前包仍无节点。没有新增 Capturer/依赖管线数据证明。 | 可挑战的真实输入注入→普通 HAP Capturer→数据回读、权限/中断/退出；MIDI、智能语音、回放捕获和相关服务不能由 Renderer 代替。 |
| media-recording-input-backends-missing | 真实 audio/video capture filters 仍依赖输入/Surface；既有 Camera/Vivid 与软件 AVC 准备不等于 AVRecorder。新候选修正共享 AVC 输入范围、偏移与布局处理。 | AVRecorder 真实音视频输入、可解码录制文件、时间戳、暂停/停止/释放/重建与权限拒绝。 |
| audio-interrupt-haptic-renderer-dependency | AudioHapticPlayerImpl 的 Start 会启动实际 audioPlayer；已有 Renderer 成功仅证明其自身 PCM 回调，不证明焦点竞争、interrupt 或同步振动。 | 两调用方实际抢占/回调、停止/重建，以及实际声音/振动同步；不能将对象创建当通过。 |
| media-codec-base-partial | 固定软件 AVC 的表面输入有真实错误：RGBA 字节 stride、UV 尾部/平面索引、P010 当 8 位、AVMemory offset 被忽略。新组件给出有界修复及实际函数回归，保留原后端。 | 完整 TU/真实产品编译、新包默认/软件创建及挑战编解码、PTS/EOS、边界与恢复；不是全 codec 枚举完成。 |
| audio-vivid-metadata-runtime-plugin-missing | 固定 media_foundation loader 明确 dlopen libAudioVividMetaBuilder.z.so 并要求 Create/DestroyAudioVividMetaBuilder。没有获得真实格式实现/插件，未造空 builder。 | 真实算法/比特流格式插件及许可来源、构建装配、带对象位置/增益的 metadata 往返/边界/释放；不得用简单 JSON 或固定字节冒充 Audio Vivid。 |
| video-encoder-dependent-media-pipelines | 新组件处理共享编码入口的数据/错误/资源问题，未添加假编码器。已有软件 AVC 与去除不存在 RK 硬件广告的准备仍不证明调用方录屏/转码。 | 真实 Surface/音视频源→编码→输出文件→独立解码，以及屏幕挑战像素、转码元数据/时间戳、取消/中断/退出和权限。 |

## KnowledgeContent 真实数据与索引契约

固定 `interface/sdk-js @ 43e34facc58b9c0f15c58571554ddd7eaa004455` 的
`api/@ohos.file.photoAccessHelper.d.ts` 定义：

- `getRelatedEntity(topic, context, option?) -> Promise<Entity[]>`；
  context.topicField 是 FieldType 数组，Options 有 rankingMethod、recommendationCount、
  suggestionFields；返回实体必须带实际 id/name/field/alias。
- `getSearchSuggestion(types) -> Promise<SearchSuggestionResult[]>`；请求 1–7 个有效类型，
  返回 type/value/count，其中 count 是该建议对应的实际照片数量。
- 两方法均是 system API，要求 READ_IMAGEVIDEO；普通应用拒绝 202，系统无权限拒绝 201；
  参数和内部失败使用 SDK 指定的数字 BusinessError，不以空数组吞掉错误。

固定 media_library 已有 `tab_analysis_geo_knowledge`、`knowledge_index` 和城市/位置键索引名；
`GetPhotoAndKnowledgeConnection()` 将实际 Photos.latitude/longitude 关联到地理知识表。
这仅证明已有地理数据关系，不是通用实体 id/alias、FieldType、排序或七类搜索建议的实现。
本轮没有擅自定义不兼容的数据库 schema，也没有写入随机实体或填空对象。

要实现该能力，需要明确真实资产/分析结果到 Entity 的稳定标识与字段映射，并以已有
provider/事务维护索引：导入真实带时间/位置/标签/人脸数据的媒体后，结果必须能追溯到
实际资产；更新、删除、隐藏/回收及跨账号可见性变化后，实体建议及照片计数同步变化。
应由非空挑战数据验证 topicField/suggestionFields、排名/数量边界、同名实体、非 ASCII
文本、无匹配结果、重启后持久性和删除后消失。输入使用参数绑定，不拼接 SQL。
不能把只有 geo 表或已有 dictionary 表等同完整 KnowledgeContent；实体分析 producer
和所需数据来源目前仍缺明确实现，本轮保留全部缺口。

## 候选与验证界限

`avc_surface_layout` 只改两个经主 agent 分配的完整上游路径：

- `foundation/multimedia/av_codec/services/engine/codec/video/avcencoder/avc_encoder.cpp`
- `foundation/multimedia/av_codec/services/engine/codec/video/avcencoder/avc_encoder_util.cpp`

新回归从原始固定源提取真实函数，旧代码复现偏移忽略、NV21 两物理平面偏移错误、RGBA
过小 stride 被接受、P010 错映射；修复后执行实际 scalar RGB/NV 转换器逐像素回读，覆盖
stride padding、UV gap、exact end、截断、uint64 offset、INT_MAX stride/尺寸、未知格式、
不支持布局以及实际 SendFrame 拒绝分支的 acquired-surface 归还。Memory/Surface/callback/
backend 在宿主回归中只是契约夹具和调用计数，不能据此声称真实后端编码成功；ARM64
NEON、HDI/Surface IPC、SDK、完整 TU 和新包运行仍未验证。

`host-checks-01.log` 的缺 manifest 与 macOS 不支持 LeakSanitizer 失败保留；补上源 fixture
manifest，macOS 保留 ASan+UBSan 并只关闭其不支持的 leak detector。`host-checks-03.log`
为最终候选 5 项通过、123357 个真实函数/像素断言；已有 AVC 33 项与严格 verifier 11 项回归也通过。
`source-review-01.failure.json` 保留初次只读 git path 查询失败及修正，源未改变。

主 agent 需要集中接线：在既有 software_avc 后应用新组件、纳入冻结输入与主机测试，
再用真实产品命令编译两个 TU。新包普通 HAP 增加公开 AVBuffer 非零 offset 挑战和 Surface
RGBA/YUV 布局/错误恢复用例；旧 EOS/默认选择/动态码率/IDR/Surface/像素验证保持。
本轮没有打包，不改变 R49 281/199/82、R50/R51 失败或其余五包门槛。
