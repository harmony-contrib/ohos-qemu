# Subsystem Adaptations and Technical Reference

This document archives the key engineering adaptations and root-cause fixes required to bring OpenHarmony 7.0 Release (`OpenHarmony-7.0-Release`, API 26) and Chromium/ArkWeb M144 to full functional parity on QEMU (`arm64_virt`, `x86_64_virt`, and `armv7a_virt` across `phone` and `2in1` device profiles).

---

## 1. Graphics, Mesa 3D, Vulkan 1.1 & Video Encoding

### 1.1 Mesa 21.3.3 `kms_swrast` & Private LLVM 10 (`gallivm`)
- **Problem**: QEMU `virtio-gpu-pci` without host Virgl 3D requires a software DRM/KMS gallium driver (`kms_swrast_dri.so`) that supports `EGL_KHR_image_base`, DMA-BUF import/export, and LLVM-accelerated `llvmpipe` shader execution for `render_service`.
- **Adaptation**:
  - [`patches/common/third_party/mesa3d/llvm_backend`](../patches/common/third_party/mesa3d/llvm_backend) and [`patches/common/device/qemu/gpu_mesa`](../patches/common/device/qemu/gpu_mesa) build Mesa 21.3.3 (`995d2506d18924b48db0cf40e6ad7de04fc4e558`) against a static `libllvm.a` (LLVM 10.0.0 built from M144 SwiftShader sources via [`scripts/build_qemu_mesa_llvm.py`](../scripts/build_qemu_mesa_llvm.py)).
  - Fixes the `va_list` formatting bug in `ohos_logger` on 64-bit targets and packages `kms_swrast_dri.so` with hardlinks/aliases for `virtio_gpu_dri.so` and `swrast_dri.so`.

### 1.2 SwiftShader M144 Vulkan 1.1 ICD
- **Problem**: Vulkan 1.1 applications and `OH_NativeWindow` / `vkCreateSwapchainKHR` workflows fail in QEMU when no physical Vulkan GPU is present.
- **Adaptation**:
  - [`scripts/build_m144_swiftshader.sh`](../scripts/build_m144_swiftshader.sh) compiles `libvk_swiftshader.so` from the pinned Chromium M144 SwiftShader tree for `arm64`, `x86_64`, and `arm`.
  - [`patches/common/foundation/graphic/graphic_2d/vulkan_swiftshader`](../patches/common/foundation/graphic/graphic_2d/vulkan_swiftshader) registers the SwiftShader ICD in the guest Vulkan loader and bridges OpenHarmony `OHNativeWindow` buffers (`VK_OHOS_surface` / `VK_EXT_headless_surface`) so swapchain presentation and `RenderService` composition work out-of-the-box.

### 1.3 OpenH264 M144 Software AVC Encoder
- **Problem**: Screen recording (`AVScreenCapture`), camera video recording, and `OH_AVCodec` H.264 encoding require an `av_codec` H.264 encoder backend, which is missing when hardware V4L2/OMX encoders are absent.
- **Adaptation**:
  - [`scripts/build_m144_avc_encoder.sh`](../scripts/build_m144_avc_encoder.sh) builds `libopenh264.so` from Chromium M144's OpenH264 source tree.
  - [`patches/common/foundation/multimedia/av_codec/h264_sw_encode`](../patches/common/foundation/multimedia/av_codec/h264_sw_encode) wires `libopenh264.so` into OpenHarmony's `av_codec` HCodec/fcodec pipeline across `arm64`, `x86_64`, and `armv7a`.

---

## 2. ArkWeb M144 & JSVM V8 Engine

### 2.1 Source-Built `ArkWebCore.hap` (`com.ohos.arkwebcore`)
- **Problem**: OpenHarmony 7.0 Release requires a matching M144 `ArkWebCore.hap` for every target architecture (`arm64-v8a`, `x86_64`, `armeabi-v7a`) signed with a valid system distribution certificate, plus matching `webview` NWeb adapter interfaces.
- **Adaptation**:
  - [`scripts/build_m144_arkweb_core_in_docker.sh`](../scripts/build_m144_arkweb_core_in_docker.sh) and [`scripts/package_m144_arkweb_core_in_docker.sh`](../scripts/package_m144_arkweb_core_in_docker.sh) compile `libarkweb_engine.so`, `libarkweb_render.so`, and V8 snapshots from the 156-project M144 source lock and package `ArkWebCore.hap`.
  - [`patches/common/web/arkweb`](../patches/common/web/arkweb) and [`patches/common/web/webview`](../patches/common/web/webview) align the NWeb C++/ArkTS bridge, sandbox flags, and `system/app/com.ohos.arkwebcore` preinstall configuration.

### 2.2 JSVM (`libjsvm.so`) Backed by M144 `libv8_shared.so`
- **Problem**: `OH_JSVM_*` C-API calls require a real V8 shared library linked against OpenHarmony's `libc++_shared.so` ABI (`__n1`), with ARM64 PAC/BTI compatibility on `arm64_virt`.
- **Adaptation**:
  - [`scripts/build_m144_v8_in_docker.sh`](../scripts/build_m144_v8_in_docker.sh) and [`scripts/build_m144_sdk_bti_runtimes.py`](../scripts/build_m144_sdk_bti_runtimes.py) build `libv8_shared.so` against the OpenHarmony sysroot and BTI-enabled CRT objects.
  - [`patches/common/arkcompiler/jsvm`](../patches/common/arkcompiler/jsvm) links `libjsvm.so` directly against `libv8_shared.so` and installs both into `/system/lib64` (or `/system/lib` on `armv7a`).

---

## 3. `2in1` SceneBoard Desktop Windowing & Boot Unlock

### 3.1 `usual.event.SCREEN_UNLOCKED` & Headless Boot Unlock
- **Problem**: In OpenHarmony 7.0, `AbilityManagerService` removes its first-boot UI ability interceptor only after receiving both `usual.event.USER_UNLOCKED` and `usual.event.SCREEN_UNLOCKED` for user `100`. Upstream SceneBoard prebuilts emit the legacy `common.event.UNLOCK_SCREEN` event name, leaving `2in1` guests unable to launch UI abilities.
- **Adaptation**:
  - [`scripts/patch_sceneboard_unlock_event.py`](../scripts/patch_sceneboard_unlock_event.py) rewrites the common-event string inside `SceneBoard.hap` to `usual.event.SCREEN_UNLOCKED` and re-signs the HAP.
  - [`patches/2in1/sceneboard_runtime`](../patches/2in1/sceneboard_runtime) installs a `2in1` boot-unlock service triggered on `bootevent.boot.completed=true` that publishes both `USER_UNLOCKED` and `SCREEN_UNLOCKED` (with `userId=100`) so headless QEMU boots unlock deterministically without manual swipe input.
  - Registers `SceneBoard`, `NotificationManagement`, `ThemeService`, `ThemeComponent`, and `SecurityPrivacyCenter` in `install_list.json` and `install_list_capability.json`.

### 3.2 FreeForm Multi-Window & TCG Timeout Scaling
- **Adaptation**:
  - Enables `/etc/sceneboard.config` (`ENABLED`), `const.window.multiWindowUIType=FreeFormMultiWindow`, `persist.sceneboard.ispcmode=true`, and `const.bms.supportAppTypes=2in1,phone,default,tablet`.
  - [`scripts/configure_sceneboard_runtime.py`](../scripts/configure_sceneboard_runtime.py) sets `persist.sys.abilityms.timeout_unit_time_ratio = 10` in `/system/etc/param/appfwk.para` so UIAbility and UIExtension startup does not time out under software TCG emulation (`x86_64_virt` and `armv7a_virt` on Apple Silicon).

---

## 4. Ability Runtime, Native Child Process & ArkUI

- **Native Child Process** ([`patches/common/foundation/ability/ability_runtime/native_child_process`](../patches/common/foundation/ability/ability_runtime/native_child_process)):
  - Enables `OH_Ability_CreateNativeChildProcess` and `OH_Ability_StartNativeChildProcess` across both `phone` and `2in1` (`persist.sys.abilityms.start_native_child_process = true`), fixes argument marshalling up to the 150 KiB boundary, and repairs child process death-recipient cleanup.
- **ArkUI Cross-DSO CFI & Symbol Exports** ([`patches/common/foundation/arkui/ace_engine/cfi_coverage`](../patches/common/foundation/arkui/ace_engine/cfi_coverage), [`native_dso_exports579`](../patches/common/foundation/arkui/ace_engine/native_dso_exports579)):
  - Resolves cross-DSO Control Flow Integrity (`-fsanitize=cfi-cross-dso`) traps when loading ArkUI plugins and exports all SDK-declared NDK symbols (`libace_ndk.z.so`, `libnative_drawing_ndk.z.so`, `libudmf.z.so`, `libpasteboard.z.so`).

---

## 5. Multimedia, MediaLibrary & Clean Process Exit

- **MediaLibrary RDB Schema & `PhotoAlbum` Compatibility**:
  - Fixes case-sensitive column lookups (`IsTemp` vs `is_temp`) in `MediaLibraryRdbStore` / result-set helpers and relaxes `lcd_size` / `thumb_size` mandatory column projections on `PhotoAlbum` table queries so `photoAccessHelper.getAlbums` and `createAsset` succeed on fresh QEMU images.
- **Clean Native Process Exit (`AVPlayer`, `UDMF`, `Pasteboard`)**:
  - Fixes process-exit hangs (`_exit` / `exit(0)` deadlock or SIGSEGV during static C++ destructor teardown) in `AVPlayer` (`player_framework`), `UDMF` (`udmf_client`), and `Pasteboard` (`pasteboard_client`) by guarding SystemAbility proxy death recipients and detached IPC worker threads during process termination.
- **Audio & Camera Stacks**:
  - **Audio**: Virtual capture loopback ([`capture_loopback`](../patches/common/drivers/peripheral/audio/capture_loopback)), ALSA config ([`alsa_runtime`](../patches/common/third_party/alsa-lib/alsa_runtime)), AudioSuite software DSP ([`audio_suite_dsp`](../patches/common/foundation/multimedia/audio_framework/audio_suite_dsp)), OpenAL spatial audio ([`qemu_spatial`](../patches/common/drivers/peripheral/intelligent_voice/cpu_provider)), and AudioHaptic player lifecycle ([`audio_haptic_lifecycle`](../patches/common/foundation/multimedia/player_framework/audio_haptic_lifecycle)).
  - **Camera**: Virtual camera capture-end signaling ([`capture_end`](../patches/common/drivers/peripheral/camera/capture_end)) and EXIF/JPEG rotation ([`jpeg_rotation`](../patches/common/drivers/peripheral/camera/jpeg_rotation)) with `libjpeg-turbo` 3.1.0.

---

## 6. Connectivity, VPN, Peripherals & System Providers

- **Standard VPN & OpenVPN** ([`patches/common/standard_vpn`](../patches/common/standard_vpn), [`scripts/build_openvpn_ohos.py`](../scripts/build_openvpn_ohos.py)):
  - Enables `/dev/tun`, IPv4/IPv6 policy routing, F2FS `fs-verity` (`FS_IOC_ENABLE_CODE_SIGN`), `VpnDialog.hap`, and the OpenVPN 2.6.12 backend across all three architectures.
- **QEMU Virtual Peripherals**:
  - **GNSS**: [`patches/common/drivers/peripheral/gnss/qemu_provider`](../patches/common/drivers/peripheral/gnss/qemu_provider) & [`scripts/prepare_qemu_gnss_runtime.py`](../scripts/prepare_qemu_gnss_runtime.py).
  - **Sensors & MSDP**: [`patches/common/drivers/peripheral/sensor/qemu_external`](../patches/common/drivers/peripheral/sensor/qemu_external) & [`patches/common/base/msdp/device_status/sensor_input`](../patches/common/base/msdp/device_status/sensor_input).
  - **Vibrator**: [`patches/common/drivers/peripheral/vibrator`](../patches/common/drivers/peripheral/vibrator).
  - **USB MIDI & 2in1 Serial**: [`patches/common/device/qemu/usb_midi_shared_device`](../patches/common/device/qemu/usb_midi_shared_device) & [`patches/2in1/serial_manager`](../patches/2in1/serial_manager).
  - **Intelligent Voice & Live Captions**: [`patches/common/drivers/peripheral/intelligent_voice/cpu_provider`](../patches/common/drivers/peripheral/intelligent_voice/cpu_provider), [`patches/lib/livecaptions_provider.py`](../patches/lib/livecaptions_provider.py), and [`scripts/prepare_armv7a_sherpa_inputs.py`](../scripts/prepare_armv7a_sherpa_inputs.py) providing offline Whisper-tiny.en + Silero VAD speech recognition across `arm64-v8a`, `x86_64`, and `armeabi-v7a`.
- **System Providers & Dialogs**:
  - [`scripts/apply_additional579_product.py`](../scripts/apply_additional579_product.py) and [`scripts/apply_media579_hap_identity.py`](../scripts/apply_media579_hap_identity.py) build and sign all system data providers and UIExtension dialogs (`SettingsData`, `ContactsData`, `CalendarData`, `MmsData`, `Photos`, `NotePad`, `FilePicker`, `CallSetting`, `CertManager`, `CommunicationSetting`) with the unified OpenHarmony platform distribution certificate so cross-bundle IPC and `DataShare` permission checks succeed at runtime.
