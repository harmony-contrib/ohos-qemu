# Capturer first-artifact wiring: read-only review

Reviewed frozen root `f82275e38321b10fc6429d2727d3ea9c90f8f44a`. No confirmed incompatible old HAP/API call was found in the default ARM64 phone capture path. Current Capturer sources and SDK files match the specified **r52-public-Capturer-HAP-02** successful actual build. Recompiling fresh nonce-bearing callers/tools is the intended current flow and is not a failure; no prebuilt consumption mechanism is proposed. Signing/BMS/real PCM and new-package acceptance remain unverified by this review.

`read-only-evidence.json` contains actual retained artifact paths/SHA, all20 SDK file comparisons, current source hashes and the known token source difference. This batch only reads host files and writes this report; it executes no compiler, SDK tool, signature verifier, Docker/source/out/VM/HDC operation or runtime test.

## Actual call chain

- `run_packaged_qemu_suite.py:611–649` invokes `run_normal_hap_probe.py --persona audio-capture` for grant/deny/grant on the same archive/boot and then independently verifies the batch. `audio-stream` is a separate later persona; its renderer-only probe does not substitute for capture.
- `run_normal_hap_probe.py:278–301` creates a fresh project using `build_hap_probe.py --audio-capture-only`, actual arch/SDK/UDID, fresh32hex run ID and explicit denied flag for the middle case. It does not point at an old HAP path or auto-discover earlier diagnostic HAPs.
- `build_hap_probe.py:2290` uses the current MIC ETS/native templates and exact MICROPHONE manifest. `audio_capture_contract.compile_command` supplies the public OHAudio native compile/link. At2456–2468 this persona still takes the actual `ARKDOWN`/`arkdown build --target hap --mode debug` route. The explicit host-Hvigor branch is limited to `arkui-components`; setting `QEMU_TEST_HVIGOR_HOME` alone does not reroute MIC compilation.
- The ordinary minimal HAP leaves the builder unsigned. The normal runner separately signs it for the actual new guest UDID in the configured Docker image, installs it as the normal bundle and checks actual BMS identity. The ETS calls `requestPermissionsFromUser(MICROPHONE)` before native capture. Runtime operates the real dialog and independently queries the token; it does not grant the permission through an API.
- `CaptureRuntime.prepare` builds current `alsa_inject` and `audio_capture_token` from source/product libraries, binds deployed tools to their compile receipts and checks the actual guest library runtime identities. It generates host-random PCM in a root-only directory. The producer writes real `hw:CARD=QemuCapture,DEV=1,SUBDEV=0`; the normal Capturer reads the HDI capture side. Current ordinary capture uses48000Hz/two-channel S16LE,20 repeats and30s native producer deadline. The independent verifier checks PCM correlation/channel separation, actual callbacks, timestamps, lifecycle, token/UI and cleanup evidence. These runtime results cannot be inferred offline.

## Specified actual HAP-02 comparison

Source evidence directory:

`/Volumes/PSSD/qemu/validation/first-20261005/issue-20-20261006/r52-public-Capturer-HAP-02`

The actual unsigned HAP at `project/entry/build/default/outputs/default/entry-default-unsigned.hap` exists, is1305219B and matches recorded SHA `8770670d422a22bad0e3756cc5474c63e3c29a192be63302dccfb02c3aefcd94`. Its original build exit was0. Retained compiled-HAP contract check is explicitly unsigned module/MIC permission/native PT_LOAD identity only, with no runtime claim. The historical nonce is `abb2542e07222371df7844cd6ee7f15e`; its UDID is an all-zero compile placeholder and cannot replace new-guest signing/fresh nonce cases.

All three current source SHA values exactly match its original compiled inputs:

| Current source | SHA256 |
|---|---|
| batch_media_audio_capture_probe.ets |`c18a71191f3698ef5fd390f7b54bbd1a3a81991fe154d3aefb9915512a65f293`|
| batch_media_audio_capture_hap.cpp |`fd6cb8f7f9a7c0afbcba7fca93e53ad0a2de85bb9b5c08aa83a5274916b91a7a`|
| batch_media_audio_capture_probe.cpp |`759d7a3d5fe7b0d1b61a90e2887c02234a21525aa15002a3f33472fca4eb7b38`|

`audio_capture_contract.py` is also unchanged (`b2d3ab6649268f69d34894e961570176c3b09560155f050a8bf32116b22b4e0e`). Every one of the20 recorded SDK headers/metadata files still has its original SHA. Native and ETS metadata both identify API26 Release **26.0.0.105**. The SDK105 path is therefore the actual previously successful capture test direction, not evidence of an incompatible caller by itself; it is distinct from the OS/native SDK39 used elsewhere.

The general `build_hap_probe.py` changed from original SHA `a02dcd522eacd2ccf40bd86432c9f6f9f8a452d1b44bd65f8c86a7f919379664` to current `6d882a964b7b1a41d797e251e4a965008a3ee60b618ca22b9e8f88fb14c207db`, including additional Recorder/audio-event branches. The current Capturer contract, source generation and native compile-command function are unchanged. This whole-builder difference is not a confirmed capture incompatibility; current dynamic builds emit current builder-bound receipts. Historical HAP-02 is not directly interchangeable with a current fresh contract, so it should remain historical evidence.

## Actual tools-02 comparison

`/Volumes/PSSD/qemu/validation/first-20261005/issue-20-20261006/r52-Capturer-independent-tools-02/artifacts/tools/build.json` is retained actual compile/link-only success for ARM64. Builder SHA `c2fcd3757e51488af325ef6ee6424f489d4892eb4539834a8c168205bc3a36df` is unchanged. Producer source SHA `066975e65dccd8931b92cd57147cbde93f5f924b601a7fcff97feb37429049ae` is unchanged; actual old binary SHA is `6789bdd4fc5e9c30f3cdf930da6fabd48cb316819d468051bf28738fad4f3d44`.

The old token binary SHA is `d9696273d35aead6e63c4403f4e579aafc080446feb4afd29a7b7b61177a5d12`. Its source SHA was `35f3ff387819116e00aeac7c667cd2bc7914ee2fe9dd898b6a3c3886b49ad7ce`; current source is `a94b1a10c7b5a4024712ddddd02debc64a6faeaa734a362511bb5c72db020203`. The change adds the second permitted focus bundle and `query-background`/KEEP_BACKGROUND_RUNNING handling. The AccessTokenKit method set remains exactly GetHapTokenID/GetHapTokenInfo/VerifyAccessToken/RevokePermission, and the default four-argument MIC `query` path keeps its prior schema. This is a real source/provenance difference, not a demonstrated new API compile failure. The suite's existing fresh compilation handles it; do not relabel the older token binary as a current-source proof. The new package's library binding and actual token permissions still require guest execution.

## Real environment/path requirements

| Setting | Actual current behavior/path |
|---|---|
| `QEMU_TEST_SDK_HOME` | Set explicitly to `/Volumes/PSSD/qemu/validation/first-20261005/provider-sdk-26-full/26.0.0` to select the same20-file API26/SDK105 test SDK. Suite checks this first, then `OHOS_SDK_HOME`, then existing fallback paths. This is the parent SDK root containing native and ETS. |
| `ARKDOWN` / `PATH` | Builder reads `ARKDOWN`, default `arkdown`. This review's host PATH resolves `/Users/ranger/.volta/bin/arkdown`; that file exists. Historical evidence does not pin its executable SHA, so no historical/current binary equality is asserted. Preserve root's known working tool environment; no caller/source switch is needed. |
| `HDC` | Existing path `/Applications/DevEco-Studio.app/Contents/sdk/default/openharmony/toolchains/hdc`; suite resolves it and passes the real per-boot target to children. |
| Host `JAVA_HOME` / `PATH` | Root's already verified compatible host crypto setup is `/Library/Java/JavaVirtualMachines/zulu-8.jdk/Contents/Home` and its `bin` first in PATH. Existing release file reads1.8.0_382. Retained root evidence `docs/capability-audit/parallel/core/round2/shared-provider-theme-and-host-crypto.json` documents actual JDK17 ZIP64 failure and JDK8 success for the three OS-signed provider HAPs; that finding is not automatically a Capturer signing failure. |
| `QEMU_TEST_HVIGOR_HOME` | Existing `/Applications/DevEco-Studio.app/Contents/tools/hvigor`; its `bin/hvigorw` exists. The MIC branch does not explicitly invoke it; keep it available for the suite's other explicit-Hvigor callers. |
| `QEMU_TEST_NODE_HOME` | Existing `/Applications/DevEco-Studio.app/Contents/tools/node`; its `bin/node` exists. The HAP-02 CPU-cap file is retained at `<HAP02>/cpu-cap.cjs`, SHA `266d23f40729d1015060cec0afffb0edfff466fc21b626b3c1d842ae43eac03b`, limits Node CPUs/availableParallelism to2. The old receipt records this file's hash, not the complete historical NODE_OPTIONS string. |
| `DOCKER_SOURCE_VOLUME` | Suite uses this exact name, default `ohos-qemu-7_0-release-source`; it is forwarded as `--source-volume`. `QEMU_TEST_SOURCE_VOLUME` is not the selector. |
| Output volume | Audio normal runner has `--out-volume`, default `ohos-qemu-7_0-release-out`. The suite does not forward a custom `DOCKER_OUT_VOLUME` into this microphone child, although other helper paths use that variable. Default-volume ARM64 execution has no conflict from this fact; a custom-volume run would need the correct explicit child binding. No custom-volume assumption was made for the frozen attempt. |
| `QEMU_TEST_DOCKER_IMAGE` | Suite forwards it, default `ohos-qemu-m144-build-env:7.0-release`; tool build and ordinary signing occur inside that image with source/out read-only. |

Host JAVA_HOME/PATH is **not automatically injected into Docker** by the microphone signing command. The M144 host preparation recipe installs OpenJDK17; this read-only audit does not observe the current container's selected Java. No Capturer actual signing/BMS failure was reproduced. Root should preserve actual signer logs if its first real invocation fails; no speculative signing change or disabled ZIP validation is proposed.

The existing suite still dynamically compiles the probe and helpers; there is no environment variable that imports the old HAP/tools receipts. That is intentional current orchestration, not an acceptance gap. Current basic capture direction has prior actual source/SDK build support, but all true grant/deny/grant PCM/token/UI results, root producer completion and complete representative-package gates remain pending the newly built artifact. No code or test was changed or run, and no requirement is closed.
