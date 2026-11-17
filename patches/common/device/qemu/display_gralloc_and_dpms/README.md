# QEMU GBM gralloc, DRM master retry, and virtual connector DPMS/backlight

Fixes QEMU `virt_full` display VDI defects:

1. `display_gralloc_gbm.cpp`: fixes the inverted `DMA_BUF_IOCTL_SYNC` retry condition (which previously issued 7 redundant ioctls on every sync), avoids caching `MAP_FAILED` in `buffer->virAddr`, checks `malloc` before `memset_s`, and fixes `referCount`/`drmFd` teardown boundaries.
2. `drm_connector.h` / `drm_connector.cpp`: initializes connected virtual connectors to `DRM_MODE_DPMS_ON`, tracks virtual DPMS/brightness when `/sys/class/backlight` or connector DPMS property writes are unsupported by `virtio_gpu`, and demotes missing virtual brightness property logs to `DISPLAY_LOGD`.
3. `drm_device.cpp`: retries `drmSetMaster` on transient `EBUSY` (`50 × 10 ms`) so `composer_host` reliably acquires DRM master if a software-EGL opener briefly opens `/dev/dri/card0` before calling `drmDropMaster`.
