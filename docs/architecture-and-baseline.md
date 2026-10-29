# Architecture and Source Baseline

## 1. Pinned Release Baselines

All six QEMU packages (`phone` and `2in1` across `arm64_virt`, `x86_64_virt`, and `armv7a_virt`) are built from deterministic, checksum-locked source trees rather than moving branches:

| Component | Lock File / Manifest | Revision / Scope |
| --- | --- | --- |
| OpenHarmony 7.0 Release | [`scripts/openharmony_7_0_release_source_lock.json`](../scripts/openharmony_7_0_release_source_lock.json) | Manifest commit `f079c4ad9848f9cc4a9a4b3a3613ad8fbb142549`, pinning all 519 project `HEAD` commits |
| GitHub/GitCode Fallback Map | [`scripts/openharmony_7_0_release_github_fallback.tsv`](../scripts/openharmony_7_0_release_github_fallback.tsv) | Exact peeled `OpenHarmony-v7.0-Release` commits for 35 repositories whose `OpenHarmony-7.0-Release` branch is absent on the read-only GitHub mirror |
| Former Git LFS Assets | [`patches/common/build/github_lfs_assets/assets.tsv`](../patches/common/build/github_lfs_assets/assets.tsv) | SHA-256 and byte-size map of 77 former-LFS binary assets (~724 MiB) replaced by pointer stubs on GitHub mirrors |
| Chromium / ArkWeb M144 | [`scripts/m144_release_source_lock.json`](../scripts/m144_release_source_lock.json) | Pins all 156 Chromium/ArkWeb M144 repositories (`ArkWebCore.hap`, `libv8_shared.so`, `libvk_swiftshader.so`, `libopenh264.so`) |
| M144 Host & HAP Toolchains | [`scripts/m144_hap_tools/release-tools-lock.json`](../scripts/m144_hap_tools/release-tools-lock.json) | Pinned Command Line Tools, Hvigor 6.0, Node 18/24, and SDK 26.0.0 metadata |
| QEMU Mesa 3D 21.3.3 | [`scripts/prepare_qemu_mesa_revision_cache.sh`](../scripts/prepare_qemu_mesa_revision_cache.sh) | Historical OpenHarmony `third_party_mesa3d` commit `995d2506d18924b48db0cf40e6ad7de04fc4e558` |
| QEMU Mesa Private LLVM 10 | [`scripts/qemu_mesa_llvm_artifacts.py`](../scripts/qemu_mesa_llvm_artifacts.py) | Built from M144 `src/third_party/swiftshader/third_party/llvm-10.0` (`libllvm.a` per target architecture) |
| OpenVPN Backend | [`scripts/openvpn_source_lock.json`](../scripts/openvpn_source_lock.json) | Pinned OpenVPN 2.6.12 + OpenSSL + LZO source archives for `ohos.permission.MANAGE_VPN` |

## 2. Dependency Recipe Versioning

Heavy external artifacts (Chromium M144 and Mesa LLVM) are versioned by content-addressed recipe hashes so unrelated OS patch edits never trigger redundant multi-hour Chromium rebuilds:

- **M144 Dependency Recipe** ([`scripts/m144_dependency_recipe.py`](../scripts/m144_dependency_recipe.py)):
  - Hashes `m144_release_source_lock.json`, `openharmony_7_0_release_source_lock.json`, `run_m144_release_build_docker.sh`, `docker/m144-build-env.Dockerfile`, all `scripts/*m144*` builders, `patches/common/web/arkweb/**`, and `patches/common/arkcompiler/jsvm/**`.
  - Default cache directories:
    - `${CACHE_ROOT}/artifacts/m144-7.0-dependencies/<recipe_sha256>/<arch>/{jsvm,swiftshader,avc}`
    - `${CACHE_ROOT}/artifacts/arkweb-m144-7.0/<recipe_sha256>`
- **Mesa LLVM Recipe** ([`scripts/qemu_mesa_llvm_artifacts.py`](../scripts/qemu_mesa_llvm_artifacts.py)):
  - Hashes `build_qemu_mesa_llvm.py`, `build_qemu_mesa_llvm_in_docker.sh`, `m144_release_source_lock.json`, and `openharmony_7_0_release_source_lock.json`.
  - Default cache directory:
    - `${CACHE_ROOT}/artifacts/qemu-mesa-llvm/<recipe_sha256>/<product>`

## 3. Self-Contained Asset Reconstruction (From-Zero Portability)

To ensure a fresh machine can build all six QEMU packages from scratch without pre-seeded local validation directories, two preparation scripts automatically materialize the required external asset caches under `${CACHE_ROOT}/artifacts/`:

1. **SceneBoard Runtime Assets (`2in1`)** — [`scripts/prepare_sceneboard_runtime_assets.py`](../scripts/prepare_sceneboard_runtime_assets.py):
   - Reconstructs `${CACHE_ROOT}/artifacts/sceneboard-runtime` (`SceneBoard.hap`, `NotificationManagement.hap`, `ThemeService.hap`, `ThemeComponent.hap`, and `SecurityPrivacyCenter.hap`, ~109 MiB total) by combining:
     - Base prebuilt HAPs from `${OHOS_LFS_ASSET_ROOT}` (`applications/standard/hap` LFS objects),
     - Compact delta assets in [`patches/assets/sceneboard-runtime-delta.tar.gz`](../patches/assets/sceneboard-runtime-delta.tar.gz) (228 KiB), and
     - Deterministic bytecode patching via [`scripts/patch_sceneboard_unlock_event.py`](../scripts/patch_sceneboard_unlock_event.py) (`common.event.UNLOCK_SCREEN` → `usual.event.SCREEN_UNLOCKED`).
   - Verifies exact SHA-256 digests of all five reconstructed HAPs before `2in1` builds begin.

2. **Live Captions & Lottie Cache (`phone` and `2in1`)** — [`scripts/prepare_livecaptions_lottie_cache.py`](../scripts/prepare_livecaptions_lottie_cache.py):
   - Downloads and verifies pinned Whisper-tiny.en INT8 ONNX models (`encoder`, `decoder`, `tokens`), Silero VAD (`silero_vad.onnx`), `@ohos/lottie` 2.0.25tgz, Sherpa-ONNX 1.11.2 HAR/sources, and `basic.ics` holiday calendar data into `${CACHE_ROOT}/artifacts/livecaptions-lottie-7.0`.
   - For `armv7a_virt`, [`scripts/prepare_armv7a_sherpa_inputs.py`](../scripts/prepare_armv7a_sherpa_inputs.py) compiles 32-bit `armeabi-v7a` Sherpa-ONNX C-API/NAPI libraries inside the Linux build container and merges them into a three-ABI HAR.

## 4. Component Patch Stack Architecture

Source modifications are organized as an ordered, idempotent component stack under [`patches/`](../patches):

```
patches/
├── phone/apply.sh          # Top-level entry for phone profile
├── 2in1/apply.sh           # Top-level entry for 2in1 profile
├── 2in1/                   # 2in1-only components (device_profile, sceneboard_runtime, serial_manager)
├── common/                 # Shared subsystem components organized by OpenHarmony repo path
├── assets/                 # Compact binary deltas (sceneboard-runtime-delta.tar.gz)
└── lib/                    # Shared patch application and source-vector guards
```

- [`patches/lib/apply_component_stack.py`](../patches/lib/apply_component_stack.py) defines the canonical `apply_qemu_capability_patch_plan` execution order.
- [`patches/lib/apply_patch.sh`](../patches/lib/apply_patch.sh) applies git patches idempotently: if a patch is already applied (`git apply --reverse --check`), it succeeds without re-patching.
- [`patches/lib/guarded_source_vector579.py`](../patches/lib/guarded_source_vector579.py) and [`scripts/apply_additional579_product.py`](../scripts/apply_additional579_product.py) apply and verify exact pre-image/post-image SHA-256 vectors for multi-repository C++ and ArkTS fixes.

## 5. Product Profile Inheritance (`phone` vs `2in1`)

Both `phone` and `2in1` builds start from the QEMU `vendor/ohemu/qemu_*_linux_min/config.json` + `productdefine/common/base/rich.json` base and inherit a current-tree-compatible projection of:
- `productdefine/common/inherit/phone.json` (when `DEVICE_TYPE=phone`), or
- `productdefine/common/inherit/2in1.json` (when `DEVICE_TYPE=2in1`).

This guarantees full subsystem coverage (ArkWeb, JSVM, Multimedia, Distributed Data, Telephony, Security, Accessibility, Window Manager, and System Applications) while retaining QEMU-specific board, VirtIO, and display drivers.
