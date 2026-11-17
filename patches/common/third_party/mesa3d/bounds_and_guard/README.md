# Mesa 21.3.3 `llvmpipe` 4x4 Partial-Stamp Bounds Clip & KMS Tail Guard VMA

Historical Mesa 21.3.3 backport extracted from `scripts/apply_qemu_mesa_bounds_fix.py` (Issue [#35](https://github.com/harmony-contrib/ohos-qemu/issues/35), PR #39):

1. `0001-clip-llvmpipe-partial-4x4-edge-stamps.patch`: Clamps right/bottom edge `4x4` MSAA JIT fragment shader stamps in `lp_rast_priv.h`, `lp_rast.c`, and `lp_rast_linear_fallback.c` using a 16-byte-aligned scratch bounce buffer (`LP_QEMU_4X4_BOUNDS_CLIP_V1`).
2. `0002-reserve-kms-dumb-bo-tail-guard-vma.patch`: Reserves anonymous matching-protection guard tail pages via `MAP_FIXED` overlay in `kms_dri_sw_winsys.c` (`KMS_QEMU_GUARD_MAP_V1`), layered cleanly on top of `kms_mapping_synchronization`.
