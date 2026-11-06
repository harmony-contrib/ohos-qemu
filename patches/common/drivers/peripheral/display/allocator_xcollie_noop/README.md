# allocator_xcollie_noop

Makes `DisplayBufferDfx::SetTimer()` and `DisplayBufferDfx::CancelTimer()` true no-ops in `allocator_host` while keeping `StartTimeStamp()` / `StopTimeStamp()` `HDF_LOGW` slow-call diagnostics intact. This avoids both the 10-second `XCOLLIE_FLAG_RECOVERY` suicidal `_exit(0)` and `XCOLLIE_FLAG_LOG`'s in-process `SIGLOCAL_DUMP` `GetProcessStacktrace()` unwinding across active `OS_IPC_*` threads during software TCG emulation stalls.
