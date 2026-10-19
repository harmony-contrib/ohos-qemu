媒体方向按能力 ID 计数，仍有 6 项未完成当前包的完整闭合，新增完整闭合为 0。基数来自 acceptance255 的历史 82 项目录，不是 a0d 新运行的 82 项结果。

| 类别 | 数量 | 精确 ID（均以 behavior: 开头） |
| --- | ---: | --- |
| 本轮有直接源修复，待新包真实行为复验；广义要求仍 open | 3 | audio-capture-and-dependent-pipelines；media-recording-input-backends-missing；audio-interrupt-haptic-renderer-dependency |
| 已有软件 AVC 等基础实现，完整相关行为和闭合链未齐 | 2 | media-codec-base-partial；video-encoder-dependent-media-pipelines |
| 历史插件缺失，当前未见对应实现修复/完整证明 | 1 | audio-vivid-metadata-runtime-plugin-missing |

前 3 项不能简单说“实现全部已修完”：完整 Capturer/依赖管线、录音/录像、Interrupt/AudioHaptic 的广义要求比本轮有限验证范围更大。后 2 项也不能简单说“没有实现”：F 已包含软件 AVC backend 与虚假硬件 codec 声明清理，其原 README 明确要求另外完成新镜像的数据、生命周期、screen capture/transcode 行为。AudioVivid 当前没有经本审计验证的镜像存在性/缺失证明，不能把历史 missing 直接当作当前二进制测量。

真实证据：312 在第一个 fresh HAP 构建处失败，MIC/Recorder/revoke/focus 行为没有启动。341 和 343 的 7 个 unsigned HAP 变体构建通过，signed=false、VM_started=false、capability_pass=false。222 虽采集 74 阶段，原独立验证失败；288 保留重放又在 caller realtime moved backward 处失败，尚未到 PCM/VDI 断言。a0d 的 UTC launcher 与 opaque hilog 修复需要新包重新运行，不能改写旧失败。当前六项没有可据以扣账的 scoped guest pass，也没有完整 registered closure。

Knowledge、Calendar、Wallpaper、媒体控制音量/歌词 provider 与 AVInputCast 声明分别归其他方向，不重复计入此 6 项。7 个构建变体、74 个阶段、26 段信号、主机测试数量都不是能力 ID 数量。

本目录只响应父 agent 的只读缺口统计优先级，暂停媒体候选扩展；未提供新的集成 patch。未 import/执行候选或测试，未运行 SDK/编译/native/crypto/签名/Docker/VM/HDC/QMP，未改 Git/F/MAIN/旧冻结包/旧证据，未读取 archive/image/PCM。精确 ID、逐项说明和输入 SHA 见 MEDIA_ID_STATUS.json。此包冻结后停止写入。
