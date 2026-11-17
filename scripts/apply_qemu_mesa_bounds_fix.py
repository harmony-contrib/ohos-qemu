#!/usr/bin/env python3
"""Apply, rewind, and verify QEMU Issue #35 graphics bounds & 2in1 WM decor fixes.

Fixes batched for Issue #35 (`qcpainterbench` crash on OpenHarmony QEMU):

1. llvmpipe (`lp_rast_priv.h`, `lp_rast.c`, `lp_rast_linear_fallback.c`):
   Adds `lp_rast_call_fs_4x4_clipped` across all 5 JIT fragment shader call
   sites (`lp_rast_shade_quads_all`, `lp_rast_shade_tile`,
   `lp_rast_shade_quads_mask_sample`, `shade_quads_all`, `shade_quads_mask`).
   Whenever `!variant->key.resource_1d` and `(x + 4 > fb.width || y + 4 > fb.height)`,
   clips the 16-bit per-sample coverage mask to valid pixels, stages valid
   pixels per sample into a 16-byte-aligned 4x4 scratch buffer, runs
   `variant->jit_function[RAST_EDGE_TEST]`, and copies only valid pixels back.
2. `kms_dri_sw_winsys.c`:
   Tracks `mapped_size` / `ro_mapped_size` and reserves anonymous tail guard
   pages of matching protection immediately after page-aligned DRM BO mappings
   via `MAP_PRIVATE | MAP_ANONYMOUS` + `MAP_FIXED` overlay, preventing any SIMD
   tail access from crossing into an adjacent unrelated read-only VMA.
3. `device/qemu/common/virt_full/hardware/display/src/display_gralloc/hi_gbm_internal.h`
   (`libdisplay_buffer_vendor.z.so`):
   Raises `HEIGHT_ALIGN` from `2U` to `4U` (with retained marker
   `OHOS_QEMU_GBM_HEIGHT_ALIGN_4_V1`) without modifying `hi_gbm.cpp` or
   `display_gralloc_gbm.cpp`.
4. `foundation/window/window_manager/wm/src/{window_session_impl.cpp,window_scene_session_impl.cpp}`
   (`libwm.z.so`):
   Allows `SetTitleButtonVisible`, `SetWindowTitleMoveEnabled`, `SetWindowTitle`,
   and `Recover` to succeed gracefully when `!IsDecorEnable()` / Pad desktop mode
   (`persist.sceneboard.ispcmode=false` on `2in1`), preventing Qt 6.12
   `libqohos.so` from aborting with `This window state is abnormal` while
   preserving `WM_ERROR_DEVICE_NOT_SUPPORT` on `phone` where required.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys


DISPLAY_GRALLOC_HEADER_REL = (
    "device/qemu/common/virt_full/hardware/display/src/display_gralloc/hi_gbm_internal.h"
)
WM_SESSION_IMPL_REL = "foundation/window/window_manager/wm/src/window_session_impl.cpp"
WM_SCENE_SESSION_IMPL_REL = "foundation/window/window_manager/wm/src/window_scene_session_impl.cpp"
MESA_BUILDER_REL = "third_party/mesa3d/build_qemu_mesa_llvm.py"
MESA_HOOK_RECORD_REL = "third_party/mesa3d/qemu_llvm_recipe_hooks.json"
MESA_BOUNDS_HELPER_REL = "third_party/mesa3d/qemu_bounds_fix/apply_qemu_mesa_bounds_fix.py"


CLIPPED_HELPER = """/**
 * Execute a 4x4 fragment shader stamp while clamping out-of-bounds pixels on
 * right/bottom partial framebuffer edges via a 16-byte-aligned 4x4 scratch
 * bounce buffer.  llvmpipe JIT fragment shaders unconditionally load and store
 * full 4x4 unswizzled color blocks even when mask bits for out-of-bounds
 * rows/columns are zero; on linear KMS/OHOS DMA-BUF surfaces whose width or
 * height is not a multiple of 4, direct execution can read/write past the BO.
 */
static inline void
lp_rast_call_fs_4x4_clipped(const struct lp_scene *scene,
                            const struct lp_rast_state *state,
                            struct lp_rasterizer_task *task,
                            struct lp_fragment_shader_variant *variant,
                            unsigned rast_type,
                            unsigned x, unsigned y,
                            boolean frontfacing,
                            const void *a0,
                            const void *dadx,
                            const void *dady,
                            uint8_t **color,
                            uint8_t *depth,
                            uint64_t mask,
                            unsigned nr_cbufs,
                            unsigned *stride,
                            unsigned depth_stride,
                            unsigned *sample_stride,
                            unsigned depth_sample_stride)
{
   if (variant->key.resource_1d ||
       (x + 4u <= scene->fb.width && y + 4u <= scene->fb.height)) {
      BEGIN_JIT_CALL(state, task);
      variant->jit_function[rast_type](&state->jit_context,
                                       x, y,
                                       frontfacing,
                                       a0, dadx, dady,
                                       color,
                                       depth,
                                       mask,
                                       &task->thread_data,
                                       stride,
                                       depth_stride,
                                       sample_stride,
                                       depth_sample_stride);
      END_JIT_CALL();
      return;
   }

   if (x >= scene->fb.width || y >= scene->fb.height)
      return;

   const unsigned block_w = MIN2(4u, scene->fb.width - x);
   const unsigned block_h = MIN2(4u, scene->fb.height - y);
   const unsigned row_valid = (1u << block_w) - 1u;
   unsigned valid16 = 0;
   for (unsigned ry = 0; ry < block_h; ry++)
      valid16 |= row_valid << (ry * 4u);

   uint64_t valid_mask = 0;
   const unsigned num_samples = MAX2(1u, scene->fb_max_samples);
   for (unsigned s = 0; s < num_samples; s++)
      valid_mask |= (uint64_t)valid16 << (16u * s);

   mask &= valid_mask;
   if (!mask)
      return;

   PIPE_ALIGN_VAR(16) uint8_t scratch[PIPE_MAX_COLOR_BUFS][LP_MAX_SAMPLES * 4 * 64];
   uint8_t *bounce_color[PIPE_MAX_COLOR_BUFS];
   unsigned bounce_stride[PIPE_MAX_COLOR_BUFS];
   unsigned bounce_sample_stride[PIPE_MAX_COLOR_BUFS];

   for (unsigned i = 0; i < nr_cbufs; i++) {
      if (color[i]) {
         const unsigned fmt_bytes = scene->cbufs[i].format_bytes;
         const unsigned cb_samples =
            sample_stride ? MAX2(1u, scene->cbufs[i].nr_samples) : 1u;
         const unsigned src_stride = stride[i];
         const unsigned src_sstride = sample_stride ? sample_stride[i] : 0u;
         const unsigned sc_stride = MAX2(16u, 4u * fmt_bytes);
         const unsigned sc_sstride = 4u * sc_stride;

         assert(fmt_bytes > 0 && fmt_bytes <= 16u);
         assert(cb_samples <= LP_MAX_SAMPLES);
         memset(scratch[i], 0, cb_samples * sc_sstride);
         for (unsigned s = 0; s < cb_samples; s++) {
            const uint8_t *src_s = color[i] + (size_t)s * src_sstride;
            uint8_t *dst_s = scratch[i] + (size_t)s * sc_sstride;
            for (unsigned ry = 0; ry < block_h; ry++) {
               memcpy(dst_s + (size_t)ry * sc_stride,
                      src_s + (size_t)ry * src_stride,
                      (size_t)block_w * fmt_bytes);
            }
         }
         bounce_color[i] = scratch[i];
         bounce_stride[i] = sc_stride;
         bounce_sample_stride[i] = sc_sstride;
      } else {
         bounce_color[i] = NULL;
         bounce_stride[i] = 0;
         bounce_sample_stride[i] = 0;
      }
   }

   BEGIN_JIT_CALL(state, task);
   variant->jit_function[RAST_EDGE_TEST](
      &state->jit_context,
      x, y,
      frontfacing,
      a0, dadx, dady,
      bounce_color,
      depth,
      mask,
      &task->thread_data,
      bounce_stride,
      depth_stride,
      sample_stride ? bounce_sample_stride : NULL,
      depth_sample_stride);
   END_JIT_CALL();

   for (unsigned i = 0; i < nr_cbufs; i++) {
      if (!color[i])
         continue;
      const unsigned fmt_bytes = scene->cbufs[i].format_bytes;
      const unsigned cb_samples =
         sample_stride ? MAX2(1u, scene->cbufs[i].nr_samples) : 1u;
      const unsigned dst_stride = stride[i];
      const unsigned dst_sstride = sample_stride ? sample_stride[i] : 0u;
      const unsigned sc_stride = MAX2(16u, 4u * fmt_bytes);
      const unsigned sc_sstride = 4u * sc_stride;

      for (unsigned s = 0; s < cb_samples; s++) {
         uint8_t *dst_s = color[i] + (size_t)s * dst_sstride;
         const uint8_t *src_s = scratch[i] + (size_t)s * sc_sstride;
         for (unsigned ry = 0; ry < block_h; ry++) {
            memcpy(dst_s + (size_t)ry * dst_stride,
                   src_s + (size_t)ry * sc_stride,
                   (size_t)block_w * fmt_bytes);
         }
      }
   }
}"""


LP_RAST_PRIV_OLD = """/**
 * Shade all pixels in a 4x4 block.  The fragment code omits the
 * triangle in/out tests.
 * \\param x, y location of 4x4 block in window coords
 */
static inline void
lp_rast_shade_quads_all( struct lp_rasterizer_task *task,"""

LP_RAST_PRIV_NEW = CLIPPED_HELPER + "\n\n" + LP_RAST_PRIV_OLD

LP_RAST_PRIV_CALL_OLD = """      /* run shader on 4x4 block */
      BEGIN_JIT_CALL(state, task);
      variant->jit_function[RAST_WHOLE]( &state->jit_context,
                                         x, y,
                                         inputs->frontfacing,
                                         GET_A0(inputs),
                                         GET_DADX(inputs),
                                         GET_DADY(inputs),
                                         color,
                                         depth,
                                         mask,
                                         &task->thread_data,
                                         stride,
                                         depth_stride,
                                         sample_stride,
                                         depth_sample_stride);
      END_JIT_CALL();"""

LP_RAST_PRIV_CALL_NEW = """      /* run shader on 4x4 block */
      lp_rast_call_fs_4x4_clipped(scene, state, task, variant, RAST_WHOLE,
                                  x, y,
                                  inputs->frontfacing,
                                  GET_A0(inputs),
                                  GET_DADX(inputs),
                                  GET_DADY(inputs),
                                  color,
                                  depth,
                                  mask,
                                  scene->fb.nr_cbufs,
                                  stride,
                                  depth_stride,
                                  sample_stride,
                                  depth_sample_stride);"""

LP_RAST_TILE_OLD = """         /* run shader on 4x4 block */
         BEGIN_JIT_CALL(state, task);
         variant->jit_function[RAST_WHOLE]( &state->jit_context,
                                            tile_x + x, tile_y + y,
                                            inputs->frontfacing,
                                            GET_A0(inputs),
                                            GET_DADX(inputs),
                                            GET_DADY(inputs),
                                            color,
                                            depth,
                                            mask,
                                            &task->thread_data,
                                            stride,
                                            depth_stride,
                                            sample_stride,
                                            depth_sample_stride);
         END_JIT_CALL();"""

LP_RAST_TILE_NEW = """         /* run shader on 4x4 block */
         lp_rast_call_fs_4x4_clipped(scene, state, task, variant, RAST_WHOLE,
                                     tile_x + x, tile_y + y,
                                     inputs->frontfacing,
                                     GET_A0(inputs),
                                     GET_DADX(inputs),
                                     GET_DADY(inputs),
                                     color,
                                     depth,
                                     mask,
                                     scene->fb.nr_cbufs,
                                     stride,
                                     depth_stride,
                                     sample_stride,
                                     depth_sample_stride);"""

LP_RAST_MASK_OLD = """      /* run shader on 4x4 block */
      BEGIN_JIT_CALL(state, task);
      variant->jit_function[RAST_EDGE_TEST](&state->jit_context,
                                            x, y,
                                            inputs->frontfacing,
                                            GET_A0(inputs),
                                            GET_DADX(inputs),
                                            GET_DADY(inputs),
                                            color,
                                            depth,
                                            mask,
                                            &task->thread_data,
                                            stride,
                                            depth_stride,
                                            sample_stride,
                                            depth_sample_stride);
      END_JIT_CALL();"""

LP_RAST_MASK_NEW = """      /* run shader on 4x4 block */
      lp_rast_call_fs_4x4_clipped(scene, state, task, variant, RAST_EDGE_TEST,
                                  x, y,
                                  inputs->frontfacing,
                                  GET_A0(inputs),
                                  GET_DADX(inputs),
                                  GET_DADY(inputs),
                                  color,
                                  depth,
                                  mask,
                                  scene->fb.nr_cbufs,
                                  stride,
                                  depth_stride,
                                  sample_stride,
                                  depth_sample_stride);"""

LP_RAST_CREATE_OLD = """   rast = CALLOC_STRUCT(lp_rasterizer);
   if (!rast) {
      goto no_rast;
   }"""

LP_RAST_CREATE_NEW = """   (void)getenv("LP_QEMU_4X4_BOUNDS_CLIP_V1");
   rast = CALLOC_STRUCT(lp_rasterizer);
   if (!rast) {
      goto no_rast;
   }"""

LP_LINEAR_FB_WHOLE_OLD = """   /* run shader on 4x4 block */
   BEGIN_JIT_CALL(state, task);
   variant->jit_function[RAST_WHOLE]( &state->jit_context,
                                      x, y,
                                      1,
                                      (const float (*)[4])GET_A0(inputs),
                                      (const float (*)[4])GET_DADX(inputs),
                                      (const float (*)[4])GET_DADY(inputs),
                                      cbufs,
                                      NULL,
                                      0xffff,
                                      &task->thread_data,
                                      strides, 0, 0, 0 );
   END_JIT_CALL();"""

LP_LINEAR_FB_WHOLE_NEW = """   /* run shader on 4x4 block */
   lp_rast_call_fs_4x4_clipped(scene, state, task, variant, RAST_WHOLE,
                               x, y,
                               1,
                               (const float (*)[4])GET_A0(inputs),
                               (const float (*)[4])GET_DADX(inputs),
                               (const float (*)[4])GET_DADY(inputs),
                               cbufs,
                               NULL,
                               0xffff,
                               1,
                               strides, 0, NULL, 0);"""

LP_LINEAR_FB_MASK_OLD = """   /* run shader on 4x4 block */
   BEGIN_JIT_CALL(state, task);
   variant->jit_function[RAST_EDGE_TEST](&state->jit_context,
                                         x, y,
                                         1,
                                         (const float (*)[4])GET_A0(inputs),
                                         (const float (*)[4])GET_DADX(inputs),
                                         (const float (*)[4])GET_DADY(inputs),
                                         cbufs,
                                         NULL,
                                         mask,
                                         &task->thread_data,
                                         strides, 0, 0, 0);
   END_JIT_CALL();"""

LP_LINEAR_FB_MASK_NEW = """   /* run shader on 4x4 block */
   lp_rast_call_fs_4x4_clipped(scene, state, task, variant, RAST_EDGE_TEST,
                               x, y,
                               1,
                               (const float (*)[4])GET_A0(inputs),
                               (const float (*)[4])GET_DADX(inputs),
                               (const float (*)[4])GET_DADY(inputs),
                               cbufs,
                               NULL,
                               mask,
                               1,
                               strides, 0, NULL, 0);"""

KMS_DT_STRUCT_OLD = """   uint32_t handle;
   void *mapped;
   void *ro_mapped;"""

KMS_DT_STRUCT_NEW = """   uint32_t handle;
   void *mapped;
   void *ro_mapped;
   size_t mapped_size;
   size_t ro_mapped_size;"""

KMS_DESTROY_OLD = """   if (kms_sw_dt->map_count > 0) {
      DEBUG_PRINT("KMS-DEBUG: leaked map buffer %u\\n", kms_sw_dt->handle);
   }"""

KMS_DESTROY_NEW = """   if (kms_sw_dt->map_count > 0) {
      DEBUG_PRINT("KMS-DEBUG: leaked map buffer %u\\n", kms_sw_dt->handle);
      if (kms_sw_dt->mapped != MAP_FAILED) {
         munmap(kms_sw_dt->mapped,
                kms_sw_dt->mapped_size ? kms_sw_dt->mapped_size : kms_sw_dt->size);
         kms_sw_dt->mapped = MAP_FAILED;
         kms_sw_dt->mapped_size = 0;
      }
      if (kms_sw_dt->ro_mapped != MAP_FAILED) {
         munmap(kms_sw_dt->ro_mapped,
                kms_sw_dt->ro_mapped_size ? kms_sw_dt->ro_mapped_size : kms_sw_dt->size);
         kms_sw_dt->ro_mapped = MAP_FAILED;
         kms_sw_dt->ro_mapped_size = 0;
      }
   }"""

KMS_MAP_OLD = """static void *
kms_sw_displaytarget_map(struct sw_winsys *ws,
                         struct sw_displaytarget *dt,
                         unsigned flags)
{
   struct kms_sw_winsys *kms_sw = kms_sw_winsys(ws);
   struct kms_sw_plane *plane = kms_sw_plane(dt);
   struct kms_sw_displaytarget *kms_sw_dt = plane->dt;
   struct drm_mode_map_dumb map_req;
   int prot, ret;

   mtx_lock(&kms_sw_dt->map_lock);
   memset(&map_req, 0, sizeof map_req);
   map_req.handle = kms_sw_dt->handle;
   ret = drmIoctl(kms_sw->fd, DRM_IOCTL_MODE_MAP_DUMB, &map_req);
   if (ret)
      goto fail_locked;

   prot = (flags == PIPE_MAP_READ) ? PROT_READ : (PROT_READ | PROT_WRITE);
   void **ptr = (flags == PIPE_MAP_READ) ? &kms_sw_dt->ro_mapped : &kms_sw_dt->mapped;
   if (*ptr == MAP_FAILED) {
      void *tmp = mmap(0, kms_sw_dt->size, prot, MAP_SHARED,
                       kms_sw->fd, map_req.offset);
      if (tmp == MAP_FAILED)
         goto fail_locked;
      *ptr = tmp;
   }"""

KMS_MAP_NEW = """#ifndef MAP_ANONYMOUS
#define MAP_ANONYMOUS MAP_ANON
#endif

static size_t
kms_sw_compute_safe_map_size(const struct kms_sw_displaytarget *kms_sw_dt)
{
   long sc_page = sysconf(_SC_PAGESIZE);
   size_t page_size = (sc_page > 0) ? (size_t)sc_page : 4096u;
   size_t min_bytes = (size_t)kms_sw_dt->size;
   const struct kms_sw_plane *p;

   LIST_FOR_EACH_ENTRY(p, &kms_sw_dt->planes, link) {
      size_t aligned_h = ((size_t)p->height + 3u) & ~(size_t)3u;
      size_t plane_end = (size_t)p->offset + aligned_h * (size_t)p->stride + page_size;
      if (plane_end > min_bytes)
         min_bytes = plane_end;
   }
   if (min_bytes == (size_t)kms_sw_dt->size)
      min_bytes += page_size;
   return (min_bytes + page_size - 1u) & ~(page_size - 1u);
}

static void *
kms_sw_displaytarget_map(struct sw_winsys *ws,
                         struct sw_displaytarget *dt,
                         unsigned flags)
{
   struct kms_sw_winsys *kms_sw = kms_sw_winsys(ws);
   struct kms_sw_plane *plane = kms_sw_plane(dt);
   struct kms_sw_displaytarget *kms_sw_dt = plane->dt;
   struct drm_mode_map_dumb map_req;
   int prot, ret;

   mtx_lock(&kms_sw_dt->map_lock);
   memset(&map_req, 0, sizeof map_req);
   map_req.handle = kms_sw_dt->handle;
   ret = drmIoctl(kms_sw->fd, DRM_IOCTL_MODE_MAP_DUMB, &map_req);
   if (ret)
      goto fail_locked;

   prot = (flags == PIPE_MAP_READ) ? PROT_READ : (PROT_READ | PROT_WRITE);
   void **ptr = (flags == PIPE_MAP_READ) ? &kms_sw_dt->ro_mapped : &kms_sw_dt->mapped;
   size_t *mapped_sz_ptr =
      (flags == PIPE_MAP_READ) ? &kms_sw_dt->ro_mapped_size : &kms_sw_dt->mapped_size;
   if (*ptr == MAP_FAILED) {
      long sc_page = sysconf(_SC_PAGESIZE);
      size_t page_size = (sc_page > 0) ? (size_t)sc_page : 4096u;
      size_t bo_size = (size_t)kms_sw_dt->size;
      size_t safe_size = kms_sw_compute_safe_map_size(kms_sw_dt);
      void *tmp = MAP_FAILED;

      if (bo_size > 0 && (bo_size % page_size) == 0 && safe_size > bo_size) {
         void *reserve = mmap(0, safe_size, prot, MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
         if (reserve != MAP_FAILED) {
            tmp = mmap(reserve, bo_size, prot, MAP_SHARED | MAP_FIXED,
                       kms_sw->fd, map_req.offset);
            if (tmp == MAP_FAILED) {
               munmap(reserve, safe_size);
            } else {
               (void)getenv("KMS_QEMU_GUARD_MAP_V1");
               *ptr = reserve;
               *mapped_sz_ptr = safe_size;
            }
         }
      }
      if (*ptr == MAP_FAILED) {
         tmp = mmap(0, bo_size, prot, MAP_SHARED,
                    kms_sw->fd, map_req.offset);
         if (tmp == MAP_FAILED)
            goto fail_locked;
         *ptr = tmp;
         *mapped_sz_ptr = bo_size;
      }
   }"""

KMS_UNMAP_OLD = """   if (kms_sw_dt->mapped != MAP_FAILED) {
      munmap(kms_sw_dt->mapped, kms_sw_dt->size);
      kms_sw_dt->mapped = MAP_FAILED;
   }
   if (kms_sw_dt->ro_mapped != MAP_FAILED) {
      munmap(kms_sw_dt->ro_mapped, kms_sw_dt->size);
      kms_sw_dt->ro_mapped = MAP_FAILED;
   }"""

KMS_UNMAP_NEW = """   if (kms_sw_dt->mapped != MAP_FAILED) {
      munmap(kms_sw_dt->mapped,
             kms_sw_dt->mapped_size ? kms_sw_dt->mapped_size : kms_sw_dt->size);
      kms_sw_dt->mapped = MAP_FAILED;
      kms_sw_dt->mapped_size = 0;
   }
   if (kms_sw_dt->ro_mapped != MAP_FAILED) {
      munmap(kms_sw_dt->ro_mapped,
             kms_sw_dt->ro_mapped_size ? kms_sw_dt->ro_mapped_size : kms_sw_dt->size);
      kms_sw_dt->ro_mapped = MAP_FAILED;
      kms_sw_dt->ro_mapped_size = 0;
   }"""

HI_GBM_OLD = "const uint32_t HEIGHT_ALIGN = 2U;"
HI_GBM_NEW = """const uint32_t HEIGHT_ALIGN = 4U;
#if defined(__has_attribute) && __has_attribute(retain)
__attribute__((used, retain))
#elif defined(__GNUC__)
__attribute__((used))
#endif
static const char OHOS_QEMU_GBM_HEIGHT_ALIGN_MARKER[] = "OHOS_QEMU_GBM_HEIGHT_ALIGN_4_V1";"""

WM_TITLE_BTN_OLD = """    if (!IsPcOrFreeMultiWindowCapabilityEnabled()) {
        return WMError::WM_ERROR_DEVICE_NOT_SUPPORT;
    }
    if (GetUIContentSharedPtr() == nullptr || !IsDecorEnable()) {
        return WMError::WM_ERROR_INVALID_WINDOW;
    }
    windowTitleVisibleFlags_ = { isMaximizeVisible, isMinimizeVisible, isSplitVisible, isCloseVisible };
    UpdateTitleButtonVisibility();
    return WMError::WM_OK;"""

WM_TITLE_BTN_NEW = """    if (!IsPcOrFreeMultiWindowCapabilityEnabled()) {
        return WMError::WM_ERROR_DEVICE_NOT_SUPPORT;
    }
    if (GetUIContentSharedPtr() == nullptr) {
        return WMError::WM_ERROR_INVALID_WINDOW;
    }
#if defined(__has_attribute) && __has_attribute(retain)
    __attribute__((used, retain))
#elif defined(__GNUC__)
    __attribute__((used))
#endif
    static const char kQemuWmPadDecorCompatMarker[] = "OHOS_QEMU_WM_PAD_DECOR_COMPAT_V1";
    (void)kQemuWmPadDecorCompatMarker;
    windowTitleVisibleFlags_ = { isMaximizeVisible, isMinimizeVisible, isSplitVisible, isCloseVisible };
    if (!IsDecorEnable()) {
        return WMError::WM_OK;
    }
    UpdateTitleButtonVisibility();
    return WMError::WM_OK;"""

WM_TITLE_MOVE_OLD = """WMError WindowSessionImpl::SetWindowTitleMoveEnabled(bool enable)
{
    HITRACE_METER_NAME(HITRACE_TAG_WINDOW_MANAGER, "WindowSessionImpl::SetWindowTitleMoveEnabled");
    if (IsWindowSessionInvalid()) {
        return WMError::WM_ERROR_INVALID_WINDOW;
    }
    if (IsPadAndNotFreeMultiWindowCompatibleMode()) {
        TLOGE(WmsLogTag::WMS_DECOR, "The is PcAppInPad, not supported");
        return WMError::WM_OK;
    }
    if (!IsPcOrPadFreeMultiWindowMode()) {"""

WM_TITLE_MOVE_NEW = """WMError WindowSessionImpl::SetWindowTitleMoveEnabled(bool enable)
{
    HITRACE_METER_NAME(HITRACE_TAG_WINDOW_MANAGER, "WindowSessionImpl::SetWindowTitleMoveEnabled");
    if (IsWindowSessionInvalid()) {
        return WMError::WM_ERROR_INVALID_WINDOW;
    }
    if (IsPadAndNotFreeMultiWindowCompatibleMode() ||
        (IsPcOrFreeMultiWindowCapabilityEnabled() && !IsPcOrPadFreeMultiWindowMode())) {
        TLOGE(WmsLogTag::WMS_DECOR, "The is PcAppInPad, not supported");
        return WMError::WM_OK;
    }
    if (!IsPcOrPadFreeMultiWindowMode()) {"""

WM_SET_TITLE_OLD = """    if (GetUIContentSharedPtr() == nullptr) {
        TLOGE(WmsLogTag::WMS_DECOR, "uicontent is empty");
        return WMError::WM_OK;
    }
    if (!IsDecorEnable()) {
        TLOGE(WmsLogTag::WMS_DECOR, "DecorEnable is false");
        return WMError::WM_ERROR_INVALID_WINDOW;
    }
    if (WindowHelper::IsMainWindow(GetType())) {"""

WM_SET_TITLE_NEW = """    if (GetUIContentSharedPtr() == nullptr) {
        TLOGE(WmsLogTag::WMS_DECOR, "uicontent is empty");
        return WMError::WM_OK;
    }
    if (!IsDecorEnable()) {
        if (WindowHelper::IsMainWindow(GetType())) {
            auto abilityContext = AbilityRuntime::Context::ConvertTo<AbilityRuntime::AbilityContext>(GetContext());
            if (abilityContext != nullptr) {
                abilityContext->SetMissionLabel(title);
            }
        }
        return WMError::WM_OK;
    }
    if (WindowHelper::IsMainWindow(GetType())) {"""

WM_RECOVER_OLD = """    if (IsPadAndNotFreeMultiWindowCompatibleMode()) {
        TLOGE(WmsLogTag::WMS_LAYOUT_PC, "The device is not supported");
        return WMError::WM_OK;
    }

    WMError checkRet = CheckRecoverPreConditions();"""

WM_RECOVER_NEW = """    if (IsPadAndNotFreeMultiWindowCompatibleMode() ||
        (IsPcOrFreeMultiWindowCapabilityEnabled() && !IsPcOrPadFreeMultiWindowMode())) {
        TLOGE(WmsLogTag::WMS_LAYOUT_PC, "The device is not supported");
        return WMError::WM_OK;
    }

    WMError checkRet = CheckRecoverPreConditions();"""

MESA_BUILDER_CACHE_OLD = """        "build_id_backport": build_id_inputs,
    }"""

MESA_BUILDER_CACHE_NEW = """        "build_id_backport": build_id_inputs,
        "bounds_fix": digest(here / "qemu_bounds_fix/apply_qemu_mesa_bounds_fix.py"),
    }"""

MESA_BUILDER_CALL_OLD = """    subprocess.run([sys.executable, str(build_id / "apply_mesa_build_id.py"),
                    "--source-root", str(source)], check=True)"""

MESA_BUILDER_CALL_NEW = """    subprocess.run([sys.executable, str(build_id / "apply_mesa_build_id.py"),
                    "--source-root", str(source)], check=True)
    subprocess.run([sys.executable, str(here / "qemu_bounds_fix/apply_qemu_mesa_bounds_fix.py"),
                    "--mesa-source", str(source)], check=True)"""


def _read_raw_text(path: Path) -> str:
    with path.open("r", encoding="utf-8", newline="") as fh:
        return fh.read()


def _write_raw_text(path: Path, content: str, *, mode: int | None = None) -> None:
    with path.open("w", encoding="utf-8", newline="") as fh:
        fh.write(content)
    if mode is not None:
        os.chmod(path, mode)


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _transform_once(
    content: str,
    old: str,
    new: str,
    label: str,
    *,
    verify: bool = False,
    rewind: bool = False,
) -> tuple[str, bool]:
    pairs = [(old, new)]
    if "\r\n" in content:
        pairs.append((old.replace("\n", "\r\n"), new.replace("\n", "\r\n")))

    if rewind:
        for orig_blk, patched_blk in pairs:
            if patched_blk in content:
                if content.count(patched_blk) != 1:
                    raise RuntimeError(f"{label}: expected 1 patched block to rewind, found {content.count(patched_blk)}")
                return content.replace(patched_blk, orig_blk, 1), True
        for orig_blk, _ in pairs:
            if orig_blk in content:
                return content, False
        raise RuntimeError(f"{label}: neither patched nor original block found during rewind")

    for _, patched_blk in pairs:
        if patched_blk in content:
            return content, False

    for orig_blk, patched_blk in pairs:
        count = content.count(orig_blk)
        if count == 1:
            if verify:
                raise RuntimeError(f"{label}: unpatched target block still present")
            return content.replace(orig_blk, patched_blk, 1), True
        if count > 1:
            raise RuntimeError(f"{label}: expected 1 occurrence of target block, found {count}")

    raise RuntimeError(f"{label}: expected 1 occurrence of target block, found 0")


def _apply_pairs(
    path: Path,
    replacements: tuple[tuple[str, str, str], ...],
    *,
    verify: bool = False,
    rewind: bool = False,
) -> bool:
    txt = _read_raw_text(path)
    did_change = False
    ordered = reversed(replacements) if rewind else replacements
    for tag, old, new in ordered:
        txt, changed = _transform_once(txt, old, new, f"{path}:{tag}", verify=verify, rewind=rewind)
        did_change = did_change or changed
    if did_change:
        _write_raw_text(path, txt)
    return did_change


def patch_mesa_tree(mesa_root: Path, *, verify: bool = False, rewind: bool = False) -> list[Path]:
    changed: list[Path] = []
    priv_h = mesa_root / "src/gallium/drivers/llvmpipe/lp_rast_priv.h"
    rast_c = mesa_root / "src/gallium/drivers/llvmpipe/lp_rast.c"
    lin_fb_c = mesa_root / "src/gallium/drivers/llvmpipe/lp_rast_linear_fallback.c"
    kms_c = mesa_root / "src/gallium/winsys/sw/kms-dri/kms_dri_sw_winsys.c"

    for req in (priv_h, rast_c, lin_fb_c, kms_c):
        if not req.is_file():
            raise FileNotFoundError(f"missing Mesa source file: {req}")

    if _apply_pairs(
        priv_h,
        (
            ("helper", LP_RAST_PRIV_OLD, LP_RAST_PRIV_NEW),
            ("shade_quads_all", LP_RAST_PRIV_CALL_OLD, LP_RAST_PRIV_CALL_NEW),
        ),
        verify=verify,
        rewind=rewind,
    ):
        changed.append(priv_h)

    if _apply_pairs(
        rast_c,
        (
            ("shade_tile", LP_RAST_TILE_OLD, LP_RAST_TILE_NEW),
            ("shade_quads_mask_sample", LP_RAST_MASK_OLD, LP_RAST_MASK_NEW),
            ("lp_rast_create", LP_RAST_CREATE_OLD, LP_RAST_CREATE_NEW),
        ),
        verify=verify,
        rewind=rewind,
    ):
        changed.append(rast_c)

    if _apply_pairs(
        lin_fb_c,
        (
            ("shade_quads_all", LP_LINEAR_FB_WHOLE_OLD, LP_LINEAR_FB_WHOLE_NEW),
            ("shade_quads_mask", LP_LINEAR_FB_MASK_OLD, LP_LINEAR_FB_MASK_NEW),
        ),
        verify=verify,
        rewind=rewind,
    ):
        changed.append(lin_fb_c)

    if _apply_pairs(
        kms_c,
        (
            ("struct", KMS_DT_STRUCT_OLD, KMS_DT_STRUCT_NEW),
            ("destroy", KMS_DESTROY_OLD, KMS_DESTROY_NEW),
            ("map", KMS_MAP_OLD, KMS_MAP_NEW),
            ("unmap", KMS_UNMAP_OLD, KMS_UNMAP_NEW),
        ),
        verify=verify,
        rewind=rewind,
    ):
        changed.append(kms_c)

    return changed


def patch_display_gralloc(gralloc_dir: Path, *, verify: bool = False, rewind: bool = False) -> list[Path]:
    """Patch ONLY hi_gbm_internal.h so hi_gbm.cpp and display_gralloc_gbm.cpp stay untouched."""
    changed: list[Path] = []
    hdr = gralloc_dir / "hi_gbm_internal.h"
    if not hdr.is_file():
        raise FileNotFoundError(f"missing display gralloc header: {hdr}")

    if _apply_pairs(
        hdr,
        (("HEIGHT_ALIGN", HI_GBM_OLD, HI_GBM_NEW),),
        verify=verify,
        rewind=rewind,
    ):
        changed.append(hdr)
    return changed


def patch_window_manager_decor(wm_dir: Path, *, verify: bool = False, rewind: bool = False) -> list[Path]:
    changed: list[Path] = []
    session_cpp = wm_dir / "src/window_session_impl.cpp"
    scene_cpp = wm_dir / "src/window_scene_session_impl.cpp"
    for req in (session_cpp, scene_cpp):
        if not req.is_file():
            raise FileNotFoundError(f"missing window_manager source file: {req}")

    if _apply_pairs(
        session_cpp,
        (
            ("SetWindowTitleMoveEnabled", WM_TITLE_MOVE_OLD, WM_TITLE_MOVE_NEW),
            ("SetTitleButtonVisible", WM_TITLE_BTN_OLD, WM_TITLE_BTN_NEW),
        ),
        verify=verify,
        rewind=rewind,
    ):
        changed.append(session_cpp)

    if _apply_pairs(
        scene_cpp,
        (
            ("SetWindowTitle", WM_SET_TITLE_OLD, WM_SET_TITLE_NEW),
            ("Recover", WM_RECOVER_OLD, WM_RECOVER_NEW),
        ),
        verify=verify,
        rewind=rewind,
    ):
        changed.append(scene_cpp)

    return changed


def install_mesa_builder_hook(ohos_root: Path, *, verify: bool = False) -> list[Path]:
    changed: list[Path] = []
    builder = ohos_root / MESA_BUILDER_REL
    hook_record = ohos_root / MESA_HOOK_RECORD_REL
    helper_dst = ohos_root / MESA_BOUNDS_HELPER_REL

    if not builder.is_file():
        if verify:
            raise FileNotFoundError(f"missing Mesa LLVM builder: {builder}")
        return changed

    if "apply_mesa_bounds_and_guard.py" in _read_raw_text(builder):
        return changed

    self_bytes = Path(__file__).resolve().read_bytes()
    if verify:
        if not helper_dst.is_file() or helper_dst.read_bytes() != self_bytes:
            raise RuntimeError(f"missing or stale Mesa bounds helper: {helper_dst}")
        _apply_pairs(
            builder,
            (
                ("cache_identity", MESA_BUILDER_CACHE_OLD, MESA_BUILDER_CACHE_NEW),
                ("apply_call", MESA_BUILDER_CALL_OLD, MESA_BUILDER_CALL_NEW),
            ),
            verify=True,
        )
        if hook_record.is_file():
            rec = json.loads(hook_record.read_text(encoding="utf-8"))
            recorded_sha = rec.get("payloads", {}).get(MESA_BUILDER_REL)
            if recorded_sha != _sha256_bytes(builder.read_bytes()):
                raise RuntimeError(f"{hook_record} payload digest mismatch for {MESA_BUILDER_REL}")
        return changed

    helper_dst.parent.mkdir(parents=True, exist_ok=True)
    if not helper_dst.is_file() or helper_dst.read_bytes() != self_bytes:
        helper_dst.write_bytes(self_bytes)
        os.chmod(helper_dst, 0o755)
        changed.append(helper_dst)

    orig_builder_bytes = builder.read_bytes()
    builder_txt = _read_raw_text(builder)
    was_unpatched = MESA_BUILDER_CALL_NEW not in builder_txt
    if _apply_pairs(
        builder,
        (
            ("cache_identity", MESA_BUILDER_CACHE_OLD, MESA_BUILDER_CACHE_NEW),
            ("apply_call", MESA_BUILDER_CALL_OLD, MESA_BUILDER_CALL_NEW),
        ),
    ):
        os.chmod(builder, 0o755)
        changed.append(builder)

    if hook_record.is_file():
        rec = json.loads(hook_record.read_text(encoding="utf-8"))
        rec_changed = False
        if was_unpatched and "bounds_fix_base_builder" not in rec:
            rec["bounds_fix_base_builder"] = base64.b64encode(orig_builder_bytes).decode("ascii")
            rec_changed = True
        new_sha = _sha256_bytes(builder.read_bytes())
        payloads = rec.setdefault("payloads", {})
        if payloads.get(MESA_BUILDER_REL) != new_sha:
            payloads[MESA_BUILDER_REL] = new_sha
            rec_changed = True
        if rec_changed:
            _write_raw_text(hook_record, json.dumps(rec, indent=2) + "\n")
            changed.append(hook_record)

    return changed


def restore_mesa_builder_hook(ohos_root: Path) -> list[Path]:
    changed: list[Path] = []
    builder = ohos_root / MESA_BUILDER_REL
    hook_record = ohos_root / MESA_HOOK_RECORD_REL
    helper_dir = (ohos_root / MESA_BOUNDS_HELPER_REL).parent

    restored_from_record = False
    if hook_record.is_file():
        rec = json.loads(hook_record.read_text(encoding="utf-8"))
        b64 = rec.pop("bounds_fix_base_builder", None)
        if b64 is not None:
            orig_bytes = base64.b64decode(b64, validate=True)
            if not builder.is_file() or builder.read_bytes() != orig_bytes:
                builder.write_bytes(orig_bytes)
                os.chmod(builder, 0o755)
                changed.append(builder)
            rec.setdefault("payloads", {})[MESA_BUILDER_REL] = _sha256_bytes(orig_bytes)
            _write_raw_text(hook_record, json.dumps(rec, indent=2) + "\n")
            changed.append(hook_record)
            restored_from_record = True

    if not restored_from_record and builder.is_file():
        txt = _read_raw_text(builder)
        if MESA_BUILDER_CALL_NEW in txt or MESA_BUILDER_CACHE_NEW in txt:
            if _apply_pairs(
                builder,
                (
                    ("cache_identity", MESA_BUILDER_CACHE_OLD, MESA_BUILDER_CACHE_NEW),
                    ("apply_call", MESA_BUILDER_CALL_OLD, MESA_BUILDER_CALL_NEW),
                ),
                rewind=True,
            ):
                os.chmod(builder, 0o755)
                changed.append(builder)
            if hook_record.is_file():
                rec = json.loads(hook_record.read_text(encoding="utf-8"))
                new_sha = _sha256_bytes(builder.read_bytes())
                if rec.setdefault("payloads", {}).get(MESA_BUILDER_REL) != new_sha:
                    rec["payloads"][MESA_BUILDER_REL] = new_sha
                    _write_raw_text(hook_record, json.dumps(rec, indent=2) + "\n")
                    changed.append(hook_record)

    if helper_dir.exists():
        shutil.rmtree(helper_dir)
        changed.append(helper_dir)

    return changed


def discover_mesa_trees(source_root: Path) -> list[Path]:
    """Discover extracted Mesa build worktrees only (keep base third_party/mesa3d git repo clean)."""
    trees: list[Path] = []
    llvm_builds = source_root / "third_party/mesa3d/qemu_llvm_build"
    if llvm_builds.is_dir():
        for cand in sorted(llvm_builds.glob("*/*/source")):
            if (cand / "src/gallium/drivers/llvmpipe/lp_rast_priv.h").is_file():
                trees.append(cand)
    return trees


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, help="OpenHarmony source checkout root")
    parser.add_argument("--mesa-source", type=Path, action="append", default=[], help="Extracted Mesa source root to patch")
    parser.add_argument("--display-gralloc-dir", type=Path, help="Path to display_gralloc directory")
    parser.add_argument("--window-manager-dir", type=Path, help="Path to foundation/window/window_manager/wm directory")
    parser.add_argument("--install-mesa-builder-hook", type=Path, help="OHOS root in which to hook build_qemu_mesa_llvm.py")
    parser.add_argument("--restore-mesa-builder-hook", type=Path, help="OHOS root in which to restore unhooked build_qemu_mesa_llvm.py")
    parser.add_argument("--rewind", action="store_true", help="Rewind applied source fixes back to clean upstream bytes")
    parser.add_argument("--verify", action="store_true", help="Verify fixes are applied without modifying files")
    args = parser.parse_args(argv)

    if args.rewind and args.verify:
        parser.error("--rewind and --verify are mutually exclusive")

    mesa_roots: list[Path] = list(args.mesa_source)
    gralloc_dir: Path | None = args.display_gralloc_dir
    wm_dir: Path | None = args.window_manager_dir

    if args.source_root is not None:
        if not mesa_roots:
            mesa_roots.extend(discover_mesa_trees(args.source_root))
        if gralloc_dir is None:
            cand = (args.source_root / DISPLAY_GRALLOC_HEADER_REL).parent
            if cand.is_dir():
                gralloc_dir = cand
        if wm_dir is None:
            cand_wm = (args.source_root / WM_SESSION_IMPL_REL).parents[1]
            if cand_wm.is_dir():
                wm_dir = cand_wm

    has_action = bool(
        mesa_roots
        or gralloc_dir is not None
        or wm_dir is not None
        or args.install_mesa_builder_hook is not None
        or args.restore_mesa_builder_hook is not None
    )
    if not has_action:
        parser.error("provide --source-root, --mesa-source, --display-gralloc-dir, --window-manager-dir, or hook flags")

    modified: list[Path] = []
    if args.restore_mesa_builder_hook is not None:
        modified.extend(restore_mesa_builder_hook(args.restore_mesa_builder_hook))
    for root in mesa_roots:
        modified.extend(patch_mesa_tree(root, verify=args.verify, rewind=args.rewind))
    if gralloc_dir is not None:
        modified.extend(patch_display_gralloc(gralloc_dir, verify=args.verify, rewind=args.rewind))
    if wm_dir is not None:
        modified.extend(patch_window_manager_decor(wm_dir, verify=args.verify, rewind=args.rewind))
    if args.install_mesa_builder_hook is not None:
        modified.extend(install_mesa_builder_hook(args.install_mesa_builder_hook, verify=args.verify))

    if args.verify:
        mode = "verified"
    elif args.rewind:
        mode = f"rewound {len(modified)} path(s)"
    else:
        mode = f"updated {len(modified)} path(s)"
    print(f"apply_qemu_mesa_bounds_fix: {mode}")
    for p in modified:
        print(f"  {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
