# HiCollie Watchdog / XCollie / FFRT Timeout Scaling for QEMU TCG

Scales native `HiviewDFX::Watchdog` thread checker intervals (`SERVICE_WARNING` / `SERVICE_BLOCK`),
`XCollie::SetTimer` one-shot timeouts (`SERVICE_TIMEOUT`), and `InitFfrtWatchdog` thresholds by
`persist.sys.abilityms.timeout_unit_time_ratio` (clamped to `[1, 20]`), preventing false-positive
5-second `SERVICE_WARNING` `processdump` freezes and 10-second `SERVICE_BLOCK` `_exit(0)` kills of
`render_service`, `foundation`, and `multimodalinput` under software-emulated QEMU TCG.
