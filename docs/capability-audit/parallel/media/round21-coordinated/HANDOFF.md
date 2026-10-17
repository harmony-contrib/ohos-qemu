# 媒体 round21：AudioHaptic 生命周期修复候选

基线为 root 分配的 `ddfabb4`；本 agent 仅写媒体独占路径，没有 git add/commit、
Docker/source/out/SDK构建、VM或重包操作。共享 ledger、patch plan、runner、产品
BUILD/init/SELinux 均交 root 集成。本批不能核销任何能力ID。

## 七条现状

沿用 `parallel/system/round17-open-ledger-handoff/open-items.json` 的逐项归类；
原报告是候选快照，不是当前新包通过证据。

| ID | 当前主阻塞 | 本批/下一步 |
| --- | --- | --- |
| `arkts_export:@ohos.file.photoAccessHelper:KnowledgeContent` | 已有修复，待新包运行 | round20真实SDK105四角色、官方CN2026日历、22操作协议候选仍需root实跑；其他people/label/geographic producer及跨账号覆盖不能从HOLIDAY推断。 |
| `behavior:audio-capture-and-dependent-pipelines` | 已有修复，待新包运行 | 新包真实外部challenge→ES1370/ALSA→普通授权HAP及PCM独立相关性；MIDI/voice/playback capture各子模式仍需逐项覆盖。 |
| `behavior:media-recording-input-backends-missing` | 已有修复，待新包运行 | 普通HAP真实输入，AAC/AVC fresh输出独立解码、PTS、pause/stop/reset/release/recreate、权限边界。 |
| `behavior:audio-interrupt-haptic-renderer-dependency` | 尚有仓库实现/验收缺口 | 本批修真实normal准备和first-frame等待生命周期；双UID焦点与真实音频/VDI同步仍需新包运行。 |
| `behavior:media-codec-base-partial` | 尚有仓库实现缺口 | 已有AVC layout/offset候选需新包；HEVC/P010及完整公开格式矩阵未由本批实现。 |
| `behavior:audio-vivid-metadata-runtime-plugin-missing` | 缺真实外部实现及许可 | 真正AudioVivid格式/算法factory ABI与合法来源；保持真实unsupported，不能造空builder。 |
| `behavior:video-encoder-dependent-media-pipelines` | 已有修复，待新包运行 | 新包逐录制/录屏/转码走真实producer/encoder，独立解码挑战、PTS、取消/中断/坏输入/释放。 |

计数：4条已有候选待新包，2条仍有实现工作，1条真实外部依赖；7条全部open。

## 实际修复

新增组件：
`patches/common/foundation/multimedia/player_framework/audio_haptic_lifecycle/`。
只改真正上游的两个CPP，通过编号patch交付，原始整文件SHA和配对后SHA由
`verify_source.py`限定，公共exact installer拒绝未知/部分/符号链接状态。

1. `AudioHapticSoundNormalImpl::ResetAVPlayer`保留实际Reset错误；每次新的
   PrepareAsync前在prepareMutex下清除旧isPrepared_/isUnsupportedFile_。
   原代码Stop→Start可因旧成功立刻返回，或由旧unsupported污染新成功。
2. `AudioHapticPlayerImpl::Start`保留真实StartSound返回值和事件错误码；失败时
   StopVibrate回收等待首帧的线程，使下一次Start重新创建等待状态。
3. `ResetVibrateState`在等待锁下清除旧canStartVibrate_/audioLatency_；
   `NotifyStartVibrate`在同锁下忽略已经停止时到达的首帧回调。
4. `AHSoundNormalCallback::HandleAudioFirstFrameEvent`仅接受真实存在且非负的
   AUDIO_FIRST_FRAME值；缺字段/负值不再被当作0或UINT64_MAX触发振动延时。

没有替换真实Player、codec、音频、VDI/provider；未改弱验收。仍没有完整的
播放generation ID协议：如果上一次的callback在下一轮已经rearm之后才到达，
现有回调载荷没有generation，本批不宣称完全解决这类跨轮晚回调。

## 源码和host证据

真实源码来自root提供的只读导出：
`/Volumes/PSSD/qemu/validation/first-20261005/issue-20-20261006/r52-Audio-first-frame-source-01/`。
`ci/capability-audit/fixtures/batch_media/audio_haptic/baseline.json`保存来源evidence SHA、
实际两个原始CPP的压缩字节和前/后整文件SHA；没有再次访问容器上游源码。

已运行的唯一新测试组：

```sh
/Volumes/PSSD/qemu/validation/first-20261005/host-regression-venv/bin/python \
  -m unittest discover -s ci/capability-audit \
  -p 'test_batch_media_audio_haptic_lifecycle.py' -v
```

结果为3项测试全部通过，原始输出保留`host-tests.log`。四个ASan/UBSan程序分别
执行原始/修后player和normal的九个真实函数；旧错行为被显式重现，再验证修后
错误传播、fresh prepare、失败线程回收、retry、callback、stop、rearm及延时载荷。
另外覆盖整组件安装、重复应用、未知编辑、混合状态及符号链接拒绝，失败时保留
全部文件。编译器仅为host clang++，依赖为可控桩；这不是产品TU/链接或运行验收。

## 随批普通caller候选及限制

新增源码`ci/capability-audit/fixtures/batch_media/audio_haptic/AudioHapticProbe.ets`，
未做SDK构建/签名/安装。导入真实`@ohos.multimedia.audioHaptic`和音频/文件/身份API；
提供`new AudioHapticProbe(context.filesDir, freshRunId, actualBootId)`和
`await probe.step(request)`。root在实际普通UI HAP中持有同一个实例，每次真实按钮
驱动一个新operation_id；busy/重复nonce被拒绝。没有自启动、授予权限或替代provider。

request字段是schema_version=1、run_id、boot_id、operation_id、action、audio_path、
haptic_path、fast、mute_audio、mute_haptics、loop、volume。非当前action所用字段
也请完整提供。action为access/register/create/start/stop/loop/volume/release/unregister。
create内部按真实manager设置latency、MUSIC stream usage、createPlayer并订阅真实
endOfStream/audioInterrupt，读取实际isMuted；不调用system-only接口。

caller将实际uid/token、player_epoch、当前operation、时间、API返回/原始BusinessError
写入私有`audio-haptic-RUN.jsonl`。异步callback记录其创建时的player_epoch和回调
发生时的active operation，不能把该operation字段直接当作callback来源证明。
release后保留对象用于真实post-release start/stop边界；成功release后create可替换。
调用失败会保留日志并抛Error；清理需root用新操作显式stop/release/unregister。

真实SDK105声明位置是
`provider-sdk-26-full/26.0.0/ets/api/@ohos.multimedia.audioHaptic.d.ts`：
registerSource/createPlayer/setAudioLatencyMode/setStreamUsage/start/stop/release/setLoop/
setVolume/isMuted和两个事件均存在。公开API没有first-frame回调，也没有通用error
事件；不能伪造。普通带VIBRATE声明、normal APL、空ACL的caller和不声明VIBRATE的
denied caller需root真实签名并独立验证实际BMS/token。Audio-only变体显式muteHaptics=true。

## root集成请求和新包验收

1. 共享patch plan加入新组件，使用标准`apply.sh --source-root ROOT --product arm64_virt`。
   与既有tone enum/Recorder组件改不同文件；先真实产品两个CPP/TU与最终DSO链接，
   同批收齐其他agent修复再创建代表归档。保留归档path/SHA、boot、环境、命令与原始结果。
2. 用真实SDK105构建普通caller UI宿主并将本源码纳入source/ABC/HAP绑定。路径输入使用
   普通HAP可读私有文件；fresh audio为独立生成且有SHA的PCM/WAV挑战（建议4秒、
   48kHz stereo、双声道不同burst时间），haptic为真实上游decoder接受的带SHA自定义
   JSON时间效果。沿用真实格式样本，不能猜JSON schema或让caller制造成功输出。
3. 同一caller按access→register→create(normal,unmuted)→loop(false)→volume→start；
   独立读真正QEMU音频输出，核对挑战声道/时间；同时采集真实Renderer
   OnFirstFrameWriting→HiPlayer NotifyAudioFirstFrame→AHSoundNormal
   HandleAudioFirstFrameEvent→StartVibrate的带时间日志，以及真实HDI V2_0
   IsVibratorRunning(device0,vibrator0)的只读单调时间采样，比较实际音频/振动起止。
4. 在EOS前stop，再立即start，重复多轮；校验每轮新的异步prepare、真实首帧和独立
   音频/VDI变化。覆盖EOS后start、loop true/false、stop/release后静默、重复stop、
   release/recreate、退出/重启。Audio-only、muteAudio和muteHaptics组合分别验收。
5. 真实缺文件/坏WAV/坏haptic JSON及无VIBRATE caller必须保留实际错误；先验失败
   后同caller创建合法资源可用。StartSound即刻失败/中途音频服务断开若需故障注入，
   由root对新QA guest做实际注入并绑定证据，不能靠host桩或手写journal核销。
   同步错误不能留下仍会在旧首帧后触发的线程/VDI；root记录进程线程与晚回调。
6. 焦点仍复用现有双普通UID前后台协议，独立证明真实interrupt、fresh PCM、task与
   permission；普通Renderer PCM成功不能代替AudioHaptic同步成功。

资源互斥：现有`ci/capability-audit/probes/vibrator_hdi.cpp`会主动Start/Stop，因此
不能与AudioHaptic同步测试并发；只读HDI watcher目前未随批实现，由root提供。
同一QA guest同一时段只能有一个音频/振动producer；禁用其他主动探针后再采样，
这是验收隔离，不是跳过能力。已有QEMU VDI是时间状态后端，不是实体马达；真实
JSON→TransformTime→EnableCompositeEffect及IsVibratorRunning可验，HD/intensity/
frequency仍按实际unsupported记录。本批未改该VDI或扩大它的能力。

首个新归档完整运行门通过前，不启动其余五包；旧包和host结果不能替代此门。
