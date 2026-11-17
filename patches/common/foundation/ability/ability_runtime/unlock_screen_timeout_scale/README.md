# unlock_screen_timeout_scale

Scales `AbilityRuntime::UnlockScreenManager::UnlockScreen()`'s `future.wait_for(...)` budget by `persist.sys.abilityms.timeout_unit_time_ratio` (preserving `500 ms` when `ratio == 1` on hardware while giving `10000 ms` when `ratio == 10` on QEMU), preventing spurious `10106102` (`ERR_UNLOCK_SCREEN_FAILED_IN_DEVELOPER_MODE`) failures when `aa start` runs while `SceneBoard` is unlocking under TCG emulation.
