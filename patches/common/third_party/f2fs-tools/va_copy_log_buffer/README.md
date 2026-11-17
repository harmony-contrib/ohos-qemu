# `f2fs-tools` `va_list` Copy & Initial Log Buffer Fix

Uses `va_copy` before calling `vsnprintf_s` inside `SlogInitBuffer` and raises `LOG_BUF_INITIAL_SIZE` from `64` to `2048` in `third_party/f2fs-tools/lib/libf2fs_log.c` to prevent `x86_64_virt` `fsck.f2fs`/`resize.f2fs` `SIGSEGV` (Issue #27, PR #28).
