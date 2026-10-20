源码研究交接，实际字幕产品由根另派 communications578 在自己的路径实现。本目录不写字幕provider，不执行native库、模型推理、SDK或QEMU。

官方SIG： https://gitcode.com/openharmony-sig/applications_ai_model_samples.git
根对象库 H/root-ai-model579-upstream-source，固定HEAD2b768749568a9cff787c2f822913bfe5e9c78684。

AsrAndTts/entry/src/main/ets/workers/NonStreamingAsrWithVadWorker.ets 是真实离线推理流：16kHz Float32 PCM -> Silero VAD -> OfflineRecognizer.createStream/acceptWaveform/decode/getResult -> text。NonStreamingAsrModels.ets的type15实际选SenseVoice模型+tokens；不存在云key调用或强制RK NPU。它目前是普通HAP worker，尚未接系统实时字幕SPI、权限/cancel/session状态，也尚未证明端到端实时识别。

依赖固定 sherpa_onnx1.11.2。公开OHPM原包已按source URL读取到本目录 sherpa_onnx-1.11.2.har，13894230字节，SHA256 d196941c571f4bd7dd98e6c03097aa4873b9a934ceced64800fb85b25892e6a0；实际SHA512与SIG lockfile完整相同。包manifest声明Apache2.0/SDK>=10，源码指向 https://github.com/k2-fsa/sherpa-onnx/tree/master/harmony-os/SherpaOnnxHar 。包内源码/ELF内容只读，所有8库的机器码、DT_NEEDED与SHA在ASR-HAR-CONTENTS.json。现成ARM64及x86_64完整ONNXRuntime/sherpa C API/NAPI/libc++，没有ARMv7预编译。

模型仍只是固定SIG Git LFS主来源指针，未取实际模型字节：

- AsrAndTts/entry/src/main/resources/rawfile/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17/model.int8.onnx：oid c71f0ce00bec95b07744e116345e33d8cbbe08cef896382cf907bf4b51a2cd51，239233841字节。
- rawfile/silero_vad.onnx：oid a35ebf52fd3ce5f1469b2a36158dba761bc47b973ea3382b3186ca15b1f5af28，1807522字节。

模型目录LICENSE只引用FunASR许可页面；不能把HAR Apache或SenseVoice代码MIT代替模型许可。实际primary读取 [FunASR模型协议](https://github.com/modelscope/FunASR/blob/main/MODEL_LICENSE) 为单独Model License1.1；[SenseVoice代码LICENSE](https://github.com/FunAudioLLM/SenseVoice/blob/main/LICENSE)当前MIT。负责集成agent已接手固定具体模型许可/转换来源与notice核对。此研究仅撤销“没有任何本地ASR实现”的推断，不声明字幕通过或发布许可已经确认。
