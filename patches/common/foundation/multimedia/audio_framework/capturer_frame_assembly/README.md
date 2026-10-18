# Ordinary MIC real-frame assembly

This component is based on actual E source export
`r58-E-postcycle-native-readonly-export-14-01/public-source/exports.json`, SHA256
`fb7357c1823163f12e1eb5ce295b6e85777103bd411797bb92cb9117a0bf34ba`.
It is a new three-file component at audio_framework revision
`6932fa64335b8272ca4a59de7808ab0d6c9eae7a`.

E reads 8192 bytes (2048 stereo S16 frames) and produces 960-frame blocks.
After 17 reads and 36 complete outputs, 256 real frames remain. An empty/error
read used to send those bytes through DoProcessMicInner, which padded the other
704 frames with zeros. This exactly matches the retained pre-revoke E PCM zero
interval 34816..35519; it does not attribute that failure to permission revocation.

The ordinary HPAE_SOURCE_MIC path retains actual aligned short reads in the
private HpaeCaptureFrameAssembler and publishes only full output frames. Empty,
failed, over-capacity or unaligned results cannot publish. Bytes are neither
padded nor dropped at normal short-read boundaries. CaptureFrame runs outside
the assembler mutex. Its immutable read lease is checked before reading and
again when appending/publishing. Stop, Start, Flush, Reset, ResetAll and DeInit
retire leases and discard pre-boundary cached data. The explicit lifecycle
boundary is the only intentional cache retirement. EC, MICREF, OFFLOAD and the
combined EC/MIC processing functions retain their old byte-processing methods.

The output publication critical section contains only ConvertToFloat and the
default OutputPort::WriteDataToOutput. The actual E hpae_node.h implementation
only updates its local outputData_ vector on this default branch; it does not
invoke a downstream node, HDI or user callback. Actual graph lifecycle and
processing are serialized by the manager process thread. No HDI/API lock is
taken under the assembler mutex. There is no recovery, replacement clock or
frame-number advancement on a failed read. Lower QemuCapture XRUN recovery is
separately disabled by capture_loopback; an explicit lifecycle transition is
required to restart the cable after that error.

The installer recognizes only the complete exact E preimage and complete new
state. The new header must be absent before installation. Unknown/mixed members
and symlinks fail before changes. Every changed member is staged, verified and
rolled back on a controlled publication failure; rollback preserves a detected
foreign writer rather than overwriting it. Review patch text normalizes line
endings; SHA-bound payloads and manifest hashes define installed bytes.

Root commands after the entire source batch freezes:

```sh
bash patches/common/foundation/multimedia/audio_framework/capturer_frame_assembly/apply.sh \
  --source-root /absolute/ohos --product arm64_virt
python3 patches/common/foundation/multimedia/audio_framework/capturer_frame_assembly/verify_source.py \
  --source-root /absolute/ohos --require-patched
OHOS_QA_CXX=/absolute/host/compiler python3 -B ci/capability-audit/test_batch_media_capturer_frame_assembly.py
```

The host harness executes the actual production assembler class, including the
17-read boundary, exact nonzero bytes, varied short reads, empty/invalid reads,
geometry changes and barrier-controlled reads delayed across invalidation.
Installer tests cover complete upgrade/repeat, all three rollback points and
mixed/foreign/symlink inputs. Actual complete HPAE CPP/GN-object compilation,
graph scheduling, ALSA/HDI integration, ordinary Capturer/Recorder real PCM,
Stop/Flush/Release/reopen and EC/MICREF regression remain root-owned gates.
Nothing here establishes a guest pass or capability closure.
