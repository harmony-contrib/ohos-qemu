# `2in1` Pad-Mode Window Decor Compatibility (`libwm.z.so`)

Allows `SetTitleButtonVisible`, `SetWindowTitleMoveEnabled`, `SetWindowTitle`, and `Recover` to cache state and return `WMError::WM_OK` when `persist.sceneboard.ispcmode=false` (`!IsDecorEnable()`) on `2in1` while preserving `WM_ERROR_DEVICE_NOT_SUPPORT` (`801`) on `phone` (`OHOS_QEMU_WM_PAD_DECOR_COMPAT_V1`, Issue #35).
