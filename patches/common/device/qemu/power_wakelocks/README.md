# Power HDI 的真实内核 running-lock 后端

固定 7.0 Power HDI 的 `RunningLockImpl::HoldLock` / `UnholdLock` 使用
`/sys/power/wake_lock` / `wake_unlock`；原 ARM64/x86_64 配置关闭
`CONFIG_PM_WAKELOCKS`，真实调用失败。ARM32 还关闭了 `CONFIG_SUSPEND`，
使 wake-lock 的 `PM_SLEEP` 依赖无法成立。

此独立部件在三个内核启用 Linux 原生用户空间 wakeup-source 接口，保留上游
100 个锁的上限和垃圾回收。ARM32 同时启用原生休眠；不启用 opportunistic
autosleep、不改 PowerMgr 超时策略、不添加无限锁/保活、不改变节点授权。
新节点沿用已有 init/SELinux 的 Power HDI 权限配置。

必须验证实际 guest 的锁获取/解除、重复锁及超时、锁持有时阻止休眠、释放后
休眠、RTC/输入唤醒和普通应用 running-lock 权限边界。配置/编译通过不是
运行修复证据。虚拟输入唤醒仍须另行验证，不能据此声称已通过。
