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

---

## 7. Multi-Architecture (`x86_64` & 32-bit `armv7a`) Build Compatibility

- **32-bit ARM PLT Verification in Mesa `kms_swrast_dri.so`** ([`patches/common/third_party/mesa3d/llvm_backend/files/build_qemu_mesa_llvm.py`](../patches/common/third_party/mesa3d/llvm_backend/files/build_qemu_mesa_llvm.py)):
  - Decodes ARM32 modified-immediate rotation fields (`ror = 2 * imm[11:8]`) in `add ip, pc, #imm` / `add ip, ip, #imm` PLT stubs (`arm_plt_got_slot_with_ror`) so large `.plt` -> `.got` displacements (e.g. `8 MiB = #8, #20`) resolve accurately when verifying that `kms_swrast_dri.so` carries zero `libLLVM.so` dynamic relocations.
- **32-bit `armeabi-v7a` Sherpa-ONNX & LiveCaptions Prebuilt Reconstruction** ([`scripts/prepare_armv7a_sherpa_inputs.py`](../scripts/prepare_armv7a_sherpa_inputs.py), [`patches/lib/livecaptions579_inputs.py`](../patches/lib/livecaptions579_inputs.py)):
  - Resolves `Napi::Array::operator[](uint32_t)` overload ambiguity on 32-bit ARM (`size_t == uint32_t`), disables ThinLTO on `libsherpa-onnx-c-api.so` so `ld.lld` emits proper `EF_ARM_ABI_FLOAT_SOFT` ELF headers instead of `0x5000000`, deduplicates `-Wl,-rpath,$ORIGIN`, and normalizes host-vs-container `CACHE_ROOT` artifact paths.
- **ARMv7 NEON Intrinsics & 32-bit `HiLog` Format Portability** ([`scripts/build_standard_qemu_in_docker.sh`](../scripts/build_standard_qemu_in_docker.sh)):
  - Guards `PNG_ARM_NEON` in `third_party/libpng/BUILD.gn` to `target_cpu == "arm64"` so AArch64-only `vaddlvq_u8` intrinsics are not compiled on `armv7a`, adds C++11 user-defined literal spacing around `PRIu64` in `onset579_clock_domain.h`, and normalizes `size_t` / `int64_t` / `uint64_t` `HiLog` format specifiers (`%zu`, `%lld`, `%llu`) across `netfirewall_intercept_recorder.cpp` and `base/telephony/number_identity` to prevent `-Werror,-Wformat` failures and 32-bit variadic stack misalignment.

---

## 8. Issue #20 & Issue #23 Runtime Stability, DRM/EGL/Mesa & Power/ScreenLock Adaptations

### 8.1 Power HDI Userspace-Only Suspend & Default Display Timeout on `virt`
- **Problem** ([Issue #20](https://github.com/harmony-contrib/ohos-qemu/issues/20)):
  - Upstream `drivers/peripheral/power` (`PowerInterfaceImpl::AutoSuspendLoop`) writes `"mem"` to `/sys/power/state` when the screen-off timer expires. On QEMU `virt` (`x86_64` Q35 ACPI S3 / `arm` PSCI suspend), kernel suspend halts guest vCPUs (`QMP status: suspended`), disconnecting `hdc` and freezing automated test suites after ~35 seconds.
- **Adaptation** ([`patches/common/drivers/peripheral/power/virt_userspace_suspend`](../patches/common/drivers/peripheral/power/virt_userspace_suspend), [`scripts/package_standard_qemu.sh`](../scripts/package_standard_qemu.sh)):
  - Configures `persist.sys.power.screenofftime=9000000` (`2.5 hours`) on QEMU `virt` images so untouched boots remain `AWAKE` without requiring `power-shell setmode 602` or `power-shell timeout`.
  - Guards `AutoSuspendLoop()` in `power_interface_impl.cpp` on `ohos.boot.hardware=virt` so explicit `power-shell suspend` transitions keep userspace display state off (`DISPLAY_OFF`) while waiting in userspace instead of writing `"mem"` to `/sys/power/state`, preserving `QMP status: running` and live `hdc` connectivity.

### 8.2 Deterministic Boot & Wakeup Auto-Unlock Without Nested Binder Deadlocks
- **Problem** ([Issue #20](https://github.com/harmony-contrib/ohos-qemu/issues/20)):
  - On fresh boot or after `power-shell suspend` -> `power-shell wakeup`, `SCBScreenLock` locks the screen (`screenLocked = true`) and calls `PowerMgrClient::OverrideScreenOffTime(10000)`. Launching abilities via `aa start` without manual `uitest uiInput swipe` fails with `10106102` or re-enters sleep after 10 seconds. Furthermore, calling `PowerMgrClient` synchronously inside `ScreenLockSystemAbility::OnWakeUp` / `OnScreenOn` re-enters `PowerMgrStub::OnRemoteRequest` on the same `powermgr` Binder thread (`DeviceStateAction::SetDisplayState` -> `DisplayManagerLiteProxy::WakeUpBegin`) while `PowerStateMachine::StateController::TransitTo` holds a non-recursive `ffrt::mutex`, causing `sysfreeze-SCREEN_ON_TIMEOUT`.
- **Adaptation** ([`patches/common/base/theme/screenlock_mgr/virt_boot_unlock`](../patches/common/base/theme/screenlock_mgr/virt_boot_unlock), [`patches/common/foundation/ability/ability_runtime/unlock_screen_timeout_scale`](../patches/common/foundation/ability/ability_runtime/unlock_screen_timeout_scale), [`patches/lib/sceneboard_profile.py`](../patches/lib/sceneboard_profile.py), [`scripts/configure_sceneboard_runtime.py`](../scripts/configure_sceneboard_runtime.py)):
  - Extends `ScreenLockSystemAbility` on `ohos.boot.hardware=virt` to schedule asynchronous auto-unlock and `PowerMgrClient::RestoreScreenOffTime()` exclusively on `ScreenLockSystemAbility::queue_` (`ffrt::queue`) via `ScheduleVirtAutoUnlock` (`300 ms` delay) and `SubmitVirtQueueTask`, never invoking synchronous `PowerMgrClient` Binder calls on incoming `OnWakeUp`, `OnScreenOn`, or `UnlockScreenEvent` callback threads.
  - Publishes `usual.event.USER_UNLOCKED` and `usual.event.SCREEN_UNLOCKED` as sticky common events (`cem publish -e ... -s` with `ohos.permission.COMMONEVENT_STICKY`) in `/etc/init/qemu_sceneboard_unlock.cfg` so `SceneBoard` receives the unlock state deterministically on cold boot even under heavy TCG load when `SCBScreenLock` registers its subscriber after `bootevent.boot.completed=true`.
  - Scales `AbilityManagerService`'s developer screen-unlock timeout by `persist.sys.abilityms.timeout_unit_time_ratio` so `aa start` during screen unlock never races on TCG targets.
  - Configures `launch/qemu_run.sh` in [`scripts/package_standard_qemu.sh`](../scripts/package_standard_qemu.sh) to auto-select `-display cocoa` on macOS when `sdl`/`gtk`/`auto` is requested, forward serial output (`-monitor none -serial file:/dev/fd/1`) in windowed modes across `arm64`/`armv7a`, and disable macOS App Nap (`NSAppSleepDisabled=YES` and `taskpolicy -B`) so background Cocoa windows are never throttled to `PRIO_DARWIN_BG`.

### 8.3 `virtio-gpu` DRM/GBM Gralloc, `kms_swrast` EGL Fallback, GLES Wrapper & `llvmpipe` Signal/Stack Isolation
- **Problem** ([Issue #20](https://github.com/harmony-contrib/ohos-qemu/issues/20), [Issue #23](https://github.com/harmony-contrib/ohos-qemu/issues/23)):
  - `allocator_host` and `composer_host` raced on DRM Master (`EBUSY`), DMA-BUF sync, and fence ownership on `/dev/dri/card0`, while `allocator_host`'s XCollie timer killed `allocator_host` under heavy multi-threaded allocation load.
  - Mesa's `platform_ohos.c` exited after failing `virtio_gpu_dri.so` when host Virgl 3D was absent instead of falling back to `kms_swrast_dri.so`, and did not release `dri2_surf->base.NativeWindow` on surface teardown.
  - `libGLESv2.so` / `libGLESv1_CM.so` resolved `gHookTable` from a duplicate TLS/global copy instead of `libEGL.so`, breaking `surfman` / `eglGetProcAddress` dispatch when `libGLESv3.so` or `libGLESv2.so` was loaded dynamically.
  - Mesa `u_thread.h` (`u_thread_create`) blocked all signals (`sigfillset`) before `pthread_create`, causing `llvmpipe-*` worker threads in `render_service` to block musl's signal `38` (`SIGDUMP` / `MUSL_SIGNAL_SAMPLE_STACK`), freezing `processdump` (`SERVICE_BLOCK` in `foundation` / `render_service`).
  - On 32-bit `armv7a_virt`, musl defaults `pthread_attr_t` stack size to `128 KB`, causing LLVM 10 `DAGTypeLegalizer` / `SelectionDAGISel` inside `gallivm_compile_module` and `gallivm_jit_function` to overflow `RSUniRenderThre`'s stack (`SIGSEGV` in `kms_swrast_dri.so`).
- **Adaptation**:
  - **DRM & Display HDI** ([`patches/common/device/qemu/display_gralloc_and_dpms`](../patches/common/device/qemu/display_gralloc_and_dpms), [`patches/common/device/qemu/display_modes`](../patches/common/device/qemu/display_modes), [`patches/common/drivers/peripheral/display/allocator_xcollie_noop`](../patches/common/drivers/peripheral/display/allocator_xcollie_noop)): Fixes GBM gralloc DMA-BUF sync, DRM master `EBUSY` retry, fence ownership, first-frame DPMS/backlight state, and disables suicidal XCollie recovery in `allocator_host`.
  - **GLES Wrapper Hook Table** ([`patches/common/foundation/graphic/graphic_2d/gles_wrapper_hook_table`](../patches/common/foundation/graphic/graphic_2d/gles_wrapper_hook_table)): Resolves `libGLESv1_CM` and `libGLESv2` hook tables directly from `libEGL.so` so `eglMakeCurrent` populates the active dispatch table across all GLESv2/GLESv3 callers.
  - **Mesa 21.3.3 Runtime Fixes & `x86_64` Emulated TLS** ([`patches/common/third_party/mesa3d/llvm_backend/files/build_qemu_mesa_llvm.py`](../patches/common/third_party/mesa3d/llvm_backend/files/build_qemu_mesa_llvm.py), [`scripts/build_standard_qemu_in_docker.sh`](../scripts/build_standard_qemu_in_docker.sh)):
    1. Leaves all signals unblocked in `u_thread_create` so `llvmpipe-*` threads never block OpenHarmony DFX `SIGDUMP` (`signal 38`) or synchronous crash signals.
    2. Adds `dri2_fallback_to_software()` in `src/egl/drivers/dri2/platform_ohos.c` (`virtio_gpu` -> `kms_swrast`) and balances `NativeWindow` reference counting.
    3. Executes `gallivm_compile_module` and `gallivm_jit_function` in `src/gallium/auxiliary/gallivm/lp_bld_init.c` on a dedicated helper `pthread` with an explicit `8 MiB` stack (`GALLIVM_JIT_THREAD_STACK_SIZE`) so 32-bit `armv7a` `RSUniRenderThre` threads (`128 KB` stack) never overflow during LLVM JIT compilation.
    4. Exports `__emutls_get_address` and `__emutls_register_common` from `libc++.so` on `x86_64_virt` so Rust/C++ NAPI cdylibs (e.g. Servo `libservoshell.so` and `ohos-native-bindings`) load without missing-symbol errors.

### 8.4 Sensor NDK Null-Buffer Query, Cross-DSO CFI & Watchdog Timeout Scaling
- **Problem** ([Issue #23](https://github.com/harmony-contrib/ohos-qemu/issues/23)):
  - Calling `OH_Sensor_GetInfos(nullptr, &count)` failed or crashed when sensor metadata strings were uninitialized in the `qemu_external` sensor HDI.
  - `com.ohos.wallpaper` (`WallpaperExtension`) and `selection_service` (`SystemAbilityLoadCallbackStub`) triggered cross-DSO CFI traps (`SIGILL`), while `HiCollie` watchdog timers fired prematurely under TCG load, and `accessibility` did not refresh newly installed bundle abilities on miss.
- **Adaptation**:
  - **Sensor HDI & NDK Contract** ([`patches/common/drivers/peripheral/sensor/qemu_external`](../patches/common/drivers/peripheral/sensor/qemu_external)): Populates non-null `sensorName`, `vendorName`, `firmwareVersion`, and `hardwareVersion` metadata for all virtual sensors so `OH_Sensor_GetInfos(nullptr, &count)` and subsequent `OH_Sensor_GetInfos(infos, &count)` queries return `SENSOR_SUCCESS (0)` with `count = 6`.
  - **Cross-DSO CFI, Watchdog & Accessibility** ([`patches/common/base/theme/wallpaper_mgr/extension_context_cfi`](../patches/common/base/theme/wallpaper_mgr/extension_context_cfi), [`patches/common/foundation/systemabilitymgr/samgr/load_callback_cfi`](../patches/common/foundation/systemabilitymgr/samgr/load_callback_cfi), [`patches/common/base/hiviewdfx/hicollie/watchdog_timeout_scale`](../patches/common/base/hiviewdfx/hicollie/watchdog_timeout_scale), [`patches/common/foundation/barrierfree/accessibility/refresh_installed_abilities`](../patches/common/foundation/barrierfree/accessibility/refresh_installed_abilities)): Fixes cross-DSO CFI type matching in `WallpaperExtension` and `SystemAbilityLoadCallbackStub`, scales `HiCollie` watchdog timeouts by `persist.sys.abilityms.timeout_unit_time_ratio`, and refreshes installed accessibility abilities on cache miss and bundle change.

### 8.5 Six-Package Matrix Runtime Validation Evidence (`issue20-23-matrix`)

All 6 packages in `/Volumes/PSSD/qemu/packages/issue20-23-matrix/` were built from `OpenHarmony-7.0-Release` (`f079c4ad9848f9cc4a9a4b3a3613ad8fbb142549`) on branch `codex/ohos7-integrated-development` and passed the 5-phase runtime gate (`EXIT_CODE=0`, 0 failures: untouched `>95s` `AWAKE` & `screenLocked=false`, `ScreenOffTime=9000000ms`, `llvmpipe-*` `SigBlk` clean, `power-shell suspend`/`wakeup` round-trip with `QMP running: true` and `awake_14s=true`, 4 rounds of 4-thread GLESv3/GLESv2 + GBM + `OH_NativeBuffer` + `OH_Sensor_GetInfos` stress, zero `cppcrash`/`jscrash`/`appfreeze`/`sysfreeze`, zero defunct zombies, identical system service PIDs, and live `snapshot_display` JPEG output):

| Target Architecture | Device Profile | Package Filename | SHA-256 Checksum | Runtime Gate Status (`--headless`, `cocoa`, `--userdata-size 8G` & Full 15-Capability Suite) |
| :--- | :--- | :--- | :--- | :--- |
| `arm64_virt` | `phone` | `openharmony-qemu-arm64-arm64_virt-phone.tar.gz` | `6676d2a4c26c3c4ff8adf29a4168a7b00fdde8e339868cce5cc3a61c8e65e6d8` | **PASS (`EXIT_CODE=0`, Headless + Cocoa + Full 15-Capability Suite, 0 Crashes)** |
| `arm64_virt` | `2in1` | `openharmony-qemu-arm64-arm64_virt-2in1.tar.gz` | `aaab1713c9b45b02691d641fd112068c5e4d0a9adbaab7ba15ff2bff016565f2` | **PASS (`EXIT_CODE=0`, Headless + Cocoa + Full 15-Capability Suite, 0 Crashes)** |
| `x86_64_virt` | `phone` | `openharmony-qemu-x86_64-x86_64_virt-phone.tar.gz` | `2a2bbc0bc3c8b9491f8b206cf8e8437a12e24135395f93cd8e9fba1772549ef1` | **PASS (`EXIT_CODE=0`, Headless + Cocoa + Full 15-Capability Suite, 0 Crashes)** |
| `x86_64_virt` | `2in1` | `openharmony-qemu-x86_64-x86_64_virt-2in1.tar.gz` | `da4bcaa3424fb228535e3e823f2b142ac35191701db5388235d57e413b4ce63b` | **PASS (`EXIT_CODE=0`, Headless + Cocoa + Full 15-Capability Suite, 0 Crashes)** |
| `armv7a_virt` | `phone` | `openharmony-qemu-armv7a-armv7a_virt-phone.tar.gz` | `8a63388f545740ef8d5e72993752822f7259d973eb65c14c94d8e1f6fe05993e` | **PASS (`EXIT_CODE=0`, Headless + Cocoa + Full 15-Capability Suite, 0 Crashes)** |
| `armv7a_virt` | `2in1` | `openharmony-qemu-armv7a-armv7a_virt-2in1.tar.gz` | `219c6c11c2d90f54f0b389efce60092d1280b1557c6306d399547abeae66f959` | **PASS (`EXIT_CODE=0`, Headless + Cocoa + Full 15-Capability Suite, 0 Crashes)** |

### 8.6 Dynamic `userdata.img` Sparse Expansion on Launch (`--userdata-size` / `QEMU_USERDATA_SIZE`) & `x86_64` `libf2fs` `va_list` Fix
- **Problem** ([Issue #27](https://github.com/harmony-contrib/ohos-qemu/issues/27)):
  - The packaged `images/userdata.img` defaults to `2 GiB`, which can be insufficient when installing large applications or test datasets on `/data`.
  - On `x86_64_virt`, `/system/bin/fsck.f2fs` and `/system/bin/resize.f2fs` crashed with `SIGSEGV` inside `libf2fs.z.so` (`SlogInitBuffer` in `third_party/f2fs-tools/lib/libf2fs_log.c`) whenever a formatted log message exceeded 63 bytes (such as `mount.c:1113` `Info: FSCK version`), because `SlogInitBuffer` started with `LOG_BUF_INITIAL_SIZE = 64` and called `vsnprintf_s(buf, size, size - 1, fmt, args)` a second time on buffer growth without `va_copy`, reusing a mutated `va_list` under the `x86_64` SysV ABI.
- **Adaptation** ([`scripts/package_standard_qemu.sh`](../scripts/package_standard_qemu.sh), [`scripts/build_standard_qemu_in_docker.sh`](../scripts/build_standard_qemu_in_docker.sh)):
  - Adds `--userdata-size SIZE` (and `--data-size SIZE`, Windows PowerShell `-UserdataSize SIZE`, and environment variable `QEMU_USERDATA_SIZE`) across `launch/linux.sh`, `launch/macos.command`, `launch/windows.ps1`, and `launch/qemu_run.sh`.
  - Accepts MiB values or `M`/`G` suffixes (e.g., `4096`, `4096M`, `4G`, `8G`), refuses unsafe downward truncation below the current `userdata.img` byte size, and sparsely expands `images/userdata.img` before QEMU starts.
  - Fixes `SlogInitBuffer` in `third_party/f2fs-tools/lib/libf2fs_log.c` to copy `va_list` with `va_copy` on each formatting pass and sets `LOG_BUF_INITIAL_SIZE` to `2048` (`LOG_BUF_SIZE_PROTECT_THRESHOLD`), ensuring `/system/bin/fsck.f2fs` and `/system/bin/resize.f2fs` succeed during `init` (`MountOneItem` in `fstab_mount.c`) and online-expand F2FS `/data` (with `usrquota,grpquota,prjquota` intact) on boot across `arm64_virt`, `x86_64_virt`, and `armv7a_virt`.

### 8.7 Direct QEMU Device Backends (Category 1), Virtual Bus/Service Integration (Category 2) & `x86_64` `libuv` `io_uring` Fork Safety
- **Problem**:
  - **Category 1 (Direct QEMU Device Backends)**:
    1. All packaged launch scripts (`launch/qemu_run.sh` and `launch/windows.ps1`) previously hardcoded `-audiodev none,id=ohos_audio`, muting host audio playback/capture even though `intel-hda`/`hda-duplex` (`arm64_virt`, `x86_64_virt`) and `ES1370` (`armv7a_virt`) were attached.
    2. Although the guest kernel compiled `CONFIG_NET_9P=y`, `CONFIG_NET_9P_VIRTIO=y`, `CONFIG_9P_FS=y`, `CONFIG_USB_XHCI_HCD=y`, `CONFIG_USB_XHCI_PCI=y`, `CONFIG_USB_STORAGE=y`, and `CONFIG_VIRTIO_BALLOON=y`, the launch scripts did not expose flags for VirtFS 9p host-guest shared directories (`virtio-9p-pci`), USB xHCI (`qemu-xhci`), virtual USB mass storage (`usb-storage`), USB host device passthrough (`usb-host`), or VirtIO memory ballooning (`virtio-balloon-pci`).
  - **Category 2 (QEMU Virtual Bus/Serial/Network + Guest/Host Service Integration)**:
    1. **Cellular RIL / Virtual SIM & AT Modem**: `riladapter_host` (`libril_vendor.z.so`) opened `const.telephony.ril.attty.path=/dev/ttyUSB0` in a retry loop (`ReadCallBack` in `drivers/peripheral/ril/interfaces/hdi_service/src/ril_impl.cpp`), failing because no `/dev/ttyUSB0` or AT modem responder existed in QEMU.
    2. **Bluetooth HCI Vendor Library**: `blue_host` (`libhci_interface_service_1.0.z.so`) attempted `dlopen("libbt_vendor.z.so", RTLD_NOW)` (`BLUETOOTH_VENDOR_LIB_INTERFACE` in `drivers/peripheral/bluetooth/hci/hdi_service/implement/vendor_interface.cpp`), failing because `/vendor/lib64/libbt_vendor.z.so` (`arm64_virt`, `x86_64_virt`) and `/vendor/lib/libbt_vendor.z.so` (`armv7a_virt`) were absent.
    3. **Virtual Wi-Fi Mode Selection**: `mac80211_hwsim.ko` and `virt_wifi.ko` could not be switched or disabled at launch time via a CLI flag, and `device/qemu/common/virt_full/kernel/BUILD.gn` hardcoded `part_name = "qemu_virt_full"` instead of `part_name = virt_part_name` for `group("virt_ko")`.
  - **TCG & `x86_64` Runtime Stability**:
    1. On `x86_64_virt`, `third_party/libuv/BUILD.gn` omitted `USE_OHOS_DFX` when `is_emulator=true`, leaving `uv__use_io_uring(0)` enabled in `uv__iou_init()` (`third_party/libuv/src/unix/linux.c`), whereas `arm64_virt` (`USE_OHOS_DFX`) and `armv7a_virt` (`__arm__ && __SIZEOF_POINTER__ == 4`) unconditionally disabled `libuv` `io_uring`. When `appspawn` forked child processes (such as `com.ohos.systemui`) without calling `uv_loop_fork()`, the inherited `MAP_SHARED` `io_uring` epoll-batching ring raced across processes and triggered `SIGABRT` in `uv__epoll_ctl_flush()`.
    2. Under slow TCG emulation (`x86_64_virt` and `armv7a_virt` on `arm64` macOS), `init`'s 60-second `bootevent` timeout set `bootevent.boot.completed=true` before `SceneBoard` reached `init.sceneboard.finish=true` and `SCBScreen.aboutToAppear()`. The unconditional `param:bootevent.boot.completed=true` job in `/etc/init/qemu_sceneboard_unlock.cfg` published sticky (`-s`) `USER_UNLOCKED` and `SCREEN_UNLOCKED` events prematurely, causing `SceneBoard` to receive them upon subscribing before `PhoneLauncherLayoutStyleConfig` was registered (`TypeError: Cannot read property setIsPad of undefined` at `LayoutViewModel.setDevice`).
- **Adaptation** ([`scripts/package_standard_qemu.sh`](../scripts/package_standard_qemu.sh), [`scripts/qemu_at_modem.py`](../scripts/qemu_at_modem.py), [`patches/lib/sceneboard_profile.py`](../patches/lib/sceneboard_profile.py), [`patches/common/device/qemu/kernel_build_dependencies/0001-track-prepared-inputs-and-certify-rebuilt-kernel.patch`](../patches/common/device/qemu/kernel_build_dependencies/0001-track-prepared-inputs-and-certify-rebuilt-kernel.patch)):
  - **Category 1 Launch Capabilities (`linux.sh`, `macos.command`, `windows.ps1`, `qemu_run.sh`)**:
    1. `--audio MODE` / `QEMU_AUDIO_BACKEND` / `-Audio MODE`: Supports `auto|none|coreaudio|pa|pipewire|alsa|sdl|dsound|oss|jack|wav[:PATH]`, probing the active QEMU binary's `-audiodev help` when `auto` is selected in windowed mode (`coreaudio` on macOS, `pa`/`pipewire`/`alsa`/`sdl` on Linux, `dsound` on Windows).
    2. `--shared-dir DIR[:TAG]` / `QEMU_SHARED_DIR` / `-SharedDir`: Attaches `-fsdev local,id=fsdev_hostshare,path=...,security_model=mapped-xattr -device virtio-9p-pci,fsdev=fsdev_hostshare,mount_tag=${TAG:-hostshare}` and passes `ohos.boot.qemu.share_tag=${TAG:-hostshare}`; `/vendor/bin/qemu-init-setup.sh` auto-mounts the 9p share at `/mnt/share` and bind-mounts `/mnt/share` to `/data/share`.
    3. `--usb`, `--usb-disk FILE`, `--usb-host VID:PID`, `--bt-usb VID:PID`, `--balloon` (`QEMU_USB`, `QEMU_USB_DISK`, `QEMU_USB_HOST`, `QEMU_BT_USB`, `QEMU_BALLOON`): Attaches `qemu-xhci`, `usb-storage`, `usb-host` passthrough, and `virtio-balloon-pci`.
  - **Category 2 Virtual Bus & Service Integration**:
    1. **Virtual AT Cellular Modem (`--ril-modem auto|on|off` / `QEMU_RIL_MODEM`)**: Launches [`scripts/qemu_at_modem.py`](../scripts/qemu_at_modem.py) (`tools/qemu_at_modem.py` in packaged archives) bound to a host UNIX socket connected to `-device virtio-serial-pci,id=virtio_serial_ril0 -chardev socket,id=char_ril0,path=...,server=off -device virtserialport,bus=virtio_serial_ril0.0,nr=1,chardev=char_ril0,id=port_ril0,name=ohos.ril.at0`. In the guest, `/vendor/bin/qemu-init-setup.sh` discovers the `ohos.ril.at0` virtio-serial port, creates `/dev/vport<N>p1` if needed, sets `radio:radio` ownership, and symlinks `/dev/ttyUSB0 -> /dev/vport<N>p1`. `qemu_at_modem.py` responds to `libril_vendor.z.so`'s full AT initialization, SIM (`+CPIN: READY`, `+CIMI: 460001380013800`, `+CRSM` USIM EF records), operator (`+COPS: 0,0,"OpenHarmony"`, `46000`), LTE registration (`+CREG`/`+CGREG: 2,1,"0001","00000101",7`), and signal strength (`^HCSQ: "LTE",55,50,150,25`, `+CSQ: 28,99`) commands so `riladapter_host` and `telephony` register on LTE and display 4G signal bars in the status bar.
    2. **Virtual HCI Bluetooth Vendor Library (`libbt_vendor.z.so`)**: Compiles and installs a freestanding `libbt_vendor.z.so` exporting `BLUETOOTH_VENDOR_LIB_INTERFACE` (`BtVendorInterfaceT`) into `/vendor/lib64/libbt_vendor.z.so` (`arm64_virt`, `x86_64_virt`) and `/vendor/lib/libbt_vendor.z.so` (`armv7a_virt`). Calling `op(BT_OP_HCI_CHANNEL_OPEN)` opens a `socketpair(AF_UNIX, SOCK_STREAM)` with an internal H4 HCI responder thread handling `HCI_Reset` (`0x0c03`), `Read_Local_Version_Info` (`0x1001`), `Read_BD_ADDR` (`0x1009`), `Read_Buffer_Size` (`0x1005`), `Read_Local_Supported_Commands` (`0x1002`), `Read_Local_Supported_Features` (`0x1003`), `LE_Read_Buffer_Size` (`0x2002`), and `LE_Read_Local_Supported_Features` (`0x2003`), then signals `init_cb(BTC_OP_RESULT_SUCCESS)` so `blue_host` and `bluetooth_service` initialize cleanly with zero crashes.
    3. **Virtual Wi-Fi Mode (`--wifi auto|hwsim|virt_wifi|off` / `QEMU_WIFI_MODE`)**: Passes `ohos.boot.qemu.wifi=${QEMU_WIFI_MODE}` on the kernel command line and configures `mac80211_hwsim` / `virt_wifi` in `/vendor/bin/qemu-init-setup.sh`, while updating `device/qemu/common/virt_full/kernel/BUILD.gn` to use `part_name = virt_part_name`.
  - **`x86_64` `libuv.so` `io_uring` Disablement & `SceneBoard` Unlock Synchronization**:
    1. Disables `uv__iou_init` (`io_uring` epoll batching) in `x86_64_virt` `/system/lib64/platformsdk/libuv.so` (matching `arm64_virt` and `armv7a_virt`) and writes `2` to `/proc/sys/kernel/io_uring_disabled` in `pre-init`, eliminating post-`appspawn` `uv__epoll_ctl_flush` `SIGABRT` crashes in `com.ohos.systemui` and other ArkTS system apps.
    2. Updates `boot_unlock_configuration()` in [`patches/lib/sceneboard_profile.py`](../patches/lib/sceneboard_profile.py) to use a single compound-condition job (`"condition": "bootevent.boot.completed=true && init.sceneboard.finish=true"` with a 5-second settle delay before `start qemu_sceneboard_user_unlock`), ensuring `SCBScreen.aboutToAppear()` -> `PhoneStage.onCreate()` always registers `PhoneLauncherLayoutStyleConfig` before `USER_UNLOCKED` and `SCREEN_UNLOCKED` are published on both HVF and TCG.

### 8.8 Dynamic Hardware Bridge (`qemu-hw-bridge` & `qemu_hw_controller.py`), External Storage (`--sdcard`, `--nvme-disk`), Battery/Thermal, Multi-Instance & Peer LAN
- **Problem**:
  - **Dynamic GPS & Sensor Injection**: Although the guest vendor layer compiled `vendorGnssAdapter.so` (`/dev/unix/socket/qemu_gnss/input`, `QGN1`/`QGF1` protocol) and `libqemu_sensor_external.z.so` (`/dev/unix/socket/qemu_sensor/{input,rotation,headposture}`, `QSN1`/`QSF1`, `QRS1`/`QRF1`, `QHP1`/`QHF1` protocols), no built-in guest daemon or launch option fed live GPS fixes or 3-axis accelerometer/rotation/head-posture frames from the host.
  - **Battery & Thermal Simulation (`armv7a_virt` `11%` Default Battery)**: On `armv7a_virt`, `battery_host` defaulted to `11%` capacity when `/data/service/el0/battery/battery/capacity` was unpopulated in `post-fs-data`, and neither battery level/charging state nor thermal sensor temperatures could be configured at boot or updated dynamically at runtime.
  - **External SD Card & NVMe Storage**: No launch flags existed to attach an external SD card (`--sdcard`) or NVMe disk (`--nvme-disk`) and auto-mount them at `/mnt/data/external/{sdcard,nvme}` (`/data/{sdcard,nvme}`) without shifting the existing `/dev/block/vda`..`vdf` VirtIO block partition mapping on `arm64_virt` and `armv7a_virt`.
  - **Multi-Instance Isolation & DSoftBus Peer LAN**: `ensure_qemu_peer_lan_support` in [`scripts/package_standard_qemu.sh`](../scripts/package_standard_qemu.sh) previously counted only `-device virtio-net-pci`, emitting `if [ 2 -ne 1 ]` on `arm64_virt` and `armv7a_virt` (which use `virtio-net-device`), and launchers lacked a `--instance ID` flag to automatically isolate writable disk images (`userdata.img`, `sys_prod.img`, `chip_prod.img`), MACs, UUID, guest serial, HDC port, and VNC display while disabling write locking (`file.locking=off`) on shared read-only images (`updater.img`, `system.img`, `vendor.img`).
  - **RTC Clock Sync, Watchdog, Camera Feed, Clipboard & TPM 2.0**: Launchers lacked CLI/runtime controls for host RTC synchronization (`--rtc`), hardware watchdog (`--watchdog`), live camera pattern switching (`--camera-feed`), host-guest clipboard synchronization (`--clipboard`), and TPM 2.0 (`--tpm`).
- **Adaptation** ([`scripts/qemu_hw_bridge.c`](../scripts/qemu_hw_bridge.c), [`scripts/qemu_hw_controller.py`](../scripts/qemu_hw_controller.py), [`scripts/package_standard_qemu.sh`](../scripts/package_standard_qemu.sh)):
  - **Guest Hardware Bridge Daemon (`/vendor/bin/qemu-hw-bridge`) & Host Controller (`tools/qemu_hw_controller.py`)**:
    1. Compiles [`scripts/qemu_hw_bridge.c`](../scripts/qemu_hw_bridge.c) for `aarch64-linux-ohos`, `x86_64-linux-ohos`, and `arm-linux-ohos` and installs it as `/vendor/bin/qemu-hw-bridge`, connected to [`scripts/qemu_hw_controller.py`](../scripts/qemu_hw_controller.py) on the host via `virtio-serial` port `ohos.hw.bridge0` (`/dev/qemu_hw_bridge`).
    2. Streams authenticated `QGF1` GNSS frames to `/dev/unix/socket/qemu_gnss/input` (and persists `/data/vendor/gnss/qemu_last_location.json` & `/data/vendor/gnss_state.json`), and streams authenticated `QSF1` (50 Hz 3-axis accelerometer), `QRF1` (rotation quaternion), and `QHF1` (head-posture quaternion) frames to `/dev/unix/socket/qemu_sensor/{input,rotation,headposture}` (persisting `/data/service/el1/public/qemu_sensor_state.json` & `/data/vendor/sensor_state.json`).
    3. Pre-populates `/data/service/el0/battery/battery/*` to `100%` (`Charging`) in `post-fs-data` before `battery_host` starts (fixing the `11%` default on `armv7a_virt`), and supports both boot-time (`--battery`, `--thermal`) and live runtime updates (`qemu_hw_controller.py battery/thermal`), updating `/data/service/el0/battery`, `/sys/module/test_power/parameters`, `/data/service/el0/thermal/sensor/*/temp`, and `hidumper -s 3302` (`--capacity` / `--unplugged` / `--status` / `--reset`) so the OpenHarmony status bar updates in real time.
    4. Synchronizes guest system clock (`settimeofday`) with the host epoch on connect, switches `/data/vendor/camera_scene.cfg` (`--camera-feed` / `qemu_hw_controller.py camera`), and bridges host-guest clipboard text (`/data/service/el1/public/qemu_clipboard.txt`).
  - **External Storage (`--sdcard FILE[:SIZE]`, `--nvme-disk FILE[:SIZE]`, `--usb-disk FILE[:SIZE]`)**:
    1. Auto-creates and ext4-formats image files when `:SIZE` is appended (e.g., `--sdcard /tmp/sd.img:64M`).
    2. Uses `sdhci-pci` + `sd-card` and `nvme` on `x86_64_virt`, and `virtio-scsi-pci` (`scsi-hd` with `product=SDCARD0`, `product=NVME0`, `product=USBDISK0`) on `arm64_virt`/`armv7a_virt` so `/dev/block/vda`..`vdf` partition ordering is never altered; creates `/dev/mmcblk0` and `/dev/nvme0n1` device nodes/symlinks and auto-mounts at `/mnt/data/external/{sdcard,nvme,usb}` and `/data/{sdcard,nvme,usb}`.
  - **Multi-Instance Isolation (`--instance ID`) & Peer LAN (`--peer off|listen[:PORT]|connect[:PORT]`)**:
    1. Fixes `ensure_qemu_peer_lan_support` to recognize both `virtio-net-pci` and `virtio-net-device`, and adds `--instance ID` (`1..999`) to clone per-instance writable images under `images/instances/instance-<ID>/` while adding `file.locking=off` to read-only drives (`updater.img`, `system.img`, `vendor.img`).
    2. Places `${QEMU_BOOT_EXTRAS}` after `ohos.required_mount.data` on the kernel `-append` command line so 32-bit `armv7a` (`COMMAND_LINE_SIZE = 1024`) never truncates `ohos.required_mount.*` parameters.
