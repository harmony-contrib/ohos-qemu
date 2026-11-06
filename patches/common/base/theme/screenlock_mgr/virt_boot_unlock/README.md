# virt_boot_unlock

On `ohos.boot.hardware=virt` without a configured user PIN:
- Keeps `PowerManagerService` awake across slow TCG cold-boot `SCBScreenLock` startup (which otherwise arms a 10-second `overrideScreenOffTime(10000)` before `SendScreenLockEvent(LOCK_SCREEN_RESULT)` completes after ~10.9s under `x86_64` TCG) and ensures the restored `9000000ms` screen-off timeout is armed on an `AWAKE` display once initial unlock completes.
- Automatically dismisses unrequested no-PIN sleep locks upon subsequent `OnWakeUp(END)` / `OnScreenOn(END)` while canceling pending auto-unlocks on `OnSleep(BEGIN)` / `OnScreenOff(BEGIN)` so `power-shell suspend` remains asleep and `power-shell wakeup` returns to an unlocked, non-overridden desktop.
- Explicit `Lock()` calls cancel auto-unlock and preserve native lock behavior.
