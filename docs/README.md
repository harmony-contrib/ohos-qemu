# OpenHarmony 7.0 Release QEMU Adaptation Documentation

This directory archives the architecture, source baselines, build/packaging workflow, and subsystem adaptations for building complete OpenHarmony 7.0 Release (`OpenHarmony-7.0-Release`, API 26) standard-system QEMU images across all six target combinations (`phone` and `2in1` × `arm64_virt`, `x86_64_virt`, and `armv7a_virt`).

## Documentation Index

1. [**Architecture and Source Baseline**](./architecture-and-baseline.md)
   - Immutable source locks for OpenHarmony 7.0 Release (`f079c4ad9848f9cc4a9a4b3a3613ad8fbb142549`) and Chromium/ArkWeb M144.
   - GitHub mirror rewriting, 35-project fallback cache, and 77-object former-LFS asset restoration.
   - Ordered component patch stack (`patches/phone`, `patches/2in1`, `patches/common`, `patches/lib`).
   - Self-contained asset reconstruction (`prepare_sceneboard_runtime_assets.py` and `prepare_livecaptions_lottie_cache.py`) for from-zero builds on new machines.

2. [**From-Zero Build and Packaging Guide**](./build-and-packaging-guide.md)
   - Host prerequisites and Docker volume layout (`ohos-qemu-7_0-release-source` and `ohos-qemu-7_0-release-out`).
   - Step-by-step instructions to build all dependencies and QEMU packages from scratch (`0` to `6` archives).
   - Single-package builds (`scripts/run_2in1_full_build_docker.sh`) and full matrix builds (`scripts/run_device_type_matrix_build_docker.sh`).
   - Environment variables and resource tuning (`CCACHE_MAXSIZE`, `BUILD_JOBS`, `DOCKER_BUILD_CPUS`, `DOCKER_BUILD_MEMORY`).

3. [**Subsystem Adaptations and Technical Reference**](./subsystem-adaptations.md)
   - Graphics, Mesa 21.3.3 (`kms_swrast_dri.so` + LLVM 10.0.0), SwiftShader M144 Vulkan 1.1, and OpenH264 M144 AVC software encoding.
   - ArkWeb M144 (`ArkWebCore.hap` + WebView NWeb) and JSVM backed by Chromium M144 `libv8_shared.so`.
   - `2in1` SceneBoard desktop windowing, `usual.event.SCREEN_UNLOCKED` event correction, and headless boot unlock orchestration.
   - Ability Runtime Native Child Process (`OH_Ability_CreateNativeChildProcess`), ArkUI CFI cross-DSO closures, and TCG timeout scaling.
   - Multimedia (Audio loopback/ALSA/AudioSuite/Spatial/AudioHaptic, Camera V4L2/JPEG, MediaLibrary RDB schema & `PhotoAlbum` compatibility, AVSession, and clean process exit for AVPlayer/UDMF/Pasteboard).
   - Standard VPN (`VpnExtension`, F2FS `fs-verity`), OpenVPN, Wi-Fi/Bluetooth/Telephony, and virtualized peripherals (GNSS, Sensor, Vibrator, USB MIDI, Serial, Intelligent Voice, and Live Captions).
   - Multi-architecture (`x86_64` and 32-bit `armv7a`) build compatibility (ARM32 PLT immediate rotation verification, `armeabi-v7a` Sherpa-ONNX ELF/NAPI compatibility, ARMv7 NEON guards, and 32-bit `HiLog` format portability).
