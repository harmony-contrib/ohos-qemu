# 媒体 round 375 冻结交接

本批交付两项具体修复：三 UID AudioHaptic coordinator 的真实身份/资源协议整合，
以及真实 AudioSink 的 AudioVivid 数据/元数据完整性修复。原 6 个广义媒体 finding
没有新增 guest 闭合；首个新包和其余五包仍由 root 统一构建与验收。

## 三 UID coordinator

- 移除 `HapTokenInfo.uid == BMS UID` 的错误前提。当前 parcel 不传该 UID；BMS 是 UID
  来源，独立 AccessToken tuple 与原始 BMS accessTokenId 对齐。每次查询由原始
  `bm dump -n` 前后夹持，复核 guest 命令、原始成功 stdout、顺序和实例稳定性。
- 独立 `audio-haptic-three-uid/375-v1` TIME 协议，保留实际容量/getter，增加 realtime /
  monotonic 同括号观测、实际 boot、root-owned stop 和 native exit frame。
  旧 round 22 / 当前 74-phase 的原始日志不改，也不混用 envelope。
- `run` 必须传 `--root-lease`、`--root-lease-nonce`、`--root-config`、`--root-output`，
  继承 parent 的 `OHOS_ROOT_LEASE_FD` 和私有 HDC 环境。调用冻结 owner12.verify，
  shell、transport、QMP 前重验 live 父、锁 inode/config/nonce/HDC。没有 JSON bool
  授权、自获父 flock 或无 owner fallback。coordinator 不负责 boot/install/build/sign。
- 新 prepared 记录同时锁 coordinator 与 protocol SHA。root 必须重新 prepare、使用真实
  SDK/产品库编译 observer，构建/签名/安装三个普通 HAP；旧 token/observer 二进制不可复用。

当前 public AudioHaptic 没有 renderer stream/session/frame timestamp 查询；上游正常和
低延时 first-frame 回调只传 latency。AudioRenderer native 有实际时间/位置接口，但
没有接到这个 public player 的流身份，因此现有 first-frame 日志、Promise、文件增长、
host 时间均不能成为输出 onset anchor。coordinator 仍保持 `accepted=false`，既不伪造
同步证明，也不覆盖较新的 74-phase PCM/VDI 主验收方案。

## AudioSink 产品修复

精确上游方法：
`bool AudioSink::CopyAudioVividBufferData(AudioStandard::BufferDesc &, std::shared_ptr<AVBuffer> &, size_t &, size_t &, int64_t &)`。
真实 prepared av_codec HEAD 是 `e5c525670d1f6622d441c9e5bf975ea0579ea177`，完整前像
SHA 为 `aff7c42c7c3f388fb8bfd03787e60a9b7a90b02046ee0977ded4d688c72cfa46`。
payload 仅改此函数；其余整文件字节保持前像。组件 manifest 锁定完整前后像，未知改动、
链接路径、错误 payload 均拒绝，原像回放和再应用通过。

先校验真实 AVMemory offset/used/capacity、源 cursor、完整 frame、目的实际剩余容量和
queue counter；Vivid 路径先校验实际 metadata 对象、typed GetData、目标缓冲和精确长度，
两次复制成功后才提交 PTS、dataLength、剩余长度、queue counter/cursor。失败不提交这些状态。
secure copy 失败可能触碰目的内存，失败 descriptor 不作为有效输出发布。共享此函数的
compressed pass-through 不要求 Vivid metadata，继续保持真实 syncFramePts 行为。
EOS 由原调用者在进入函数前处理。

实际 ABI 对照（root 提供只读 prepared export，SHA 见 SOURCE_EVIDENCE.json）：

- `BufferDesc` 的 PCM/meta 指针为 `uint8_t *`，长度为 `size_t`，position/time/syncFramePts 为 `uint64_t`。
- `AVMemory::GetCapacity/GetOffset/GetSize` 返回 `int32_t`；`GetAddr` 返回 base `uint8_t *`。
- `Meta::GetData(Tag, std::vector<uint8_t> &)` 返回 `bool`。
- `currentQueuedBufferOffset_` 为 `int32_t`，`availDataSize_` 为 `std::atomic<size_t>`。

已有 30 个实际方法体的 controlled dependency native 场景：空对象/源址、负/溢出范围、
部分/超长 frame、目的尾边界、queue underflow、缺/错长 metadata、两次 secure copy
失败、offset 正向内容、重复消费、两个 pass-through PTS 分支。root 首次编译反馈暴露
harness 将不同底层无符号类型放进同一 `auto` 声明；现已只拆 sync 声明，所有断言保留。
agent 未运行 native 编译；root 运行 sanitizer 后补其正式证据。

root 原生验证命令（在 `ci/capability-audit`）：

```sh
OHOS_MEDIA375_NATIVE=1 /Volumes/PSSD/qemu/validation/first-20261005/host-regression-venv/bin/python -m unittest -v test_batch_media375_audio_vivid
```

共享 builder、组件注册和 common verifier 归 root；本 agent 未改这些路径。该修复不是
MetaBuilder 实现。官方实现边界和 SIG 检索范围见 OFFICIAL-IMPLEMENTATION-BOUNDARY.md；
按本轮范围规则，缺少公开完整插件的元数据构建列当前开源实现不支持，镜像库存在性另测。

## 已运行与未运行

最终独立 host 检查：39 tests，38 pass，1 native 明确 skip。命令：
`PY -m unittest -v test_batch_media375_protocol test_batch_media_audio_haptic_coordinator test_batch_media375_audio_vivid`。
日志为 `.tmp/parallel-capability-20261016/round375-media/host-tests.log`，
SHA `9385836df3c30ff1b204908cf5265e409b14ed9418a03c1c0722a17fee95070a`。
包含 source-only 的真实 SDK declaration/preparation 检查，没有 SDK 编译、签名或 HAP 运行。
全新 guest 的 capture/recorder/revoke/focus、广义 codec/video 管线与包内 binary/source
身份仍由 root 核验。没有启动/终止 shared Docker、native compiler、QEMU、HDC、QMP，
没有 Git stage/commit/branch/worktree 操作。

精确交付文件及 SHA 见 FROZEN_FILES.json。后续实际编译/guest 失败由 root 收齐后合批反馈；
冻结后本 agent 停止修改代码。
