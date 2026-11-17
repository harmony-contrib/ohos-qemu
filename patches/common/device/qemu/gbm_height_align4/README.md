# QEMU Display Gralloc `HEIGHT_ALIGN = 4U`

Raises `HEIGHT_ALIGN` from `2U` to `4U` in `device/qemu/common/virt_full/hardware/display/src/display_gralloc/hi_gbm_internal.h` (`OHOS_QEMU_GBM_HEIGHT_ALIGN_4_V1`) so linear DMA-BUF / GBM buffers align to Mesa `llvmpipe` `4x4` shader blocks (Issue #35).
