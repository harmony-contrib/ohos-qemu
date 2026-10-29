# QEMU virt 的 GPIO 电源键唤醒

QEMU `virt` 的固定虚拟板提供 `/gpio-keys/poweroff`（KEY_POWER），但生成的
DT 没有 `wakeup-source`。普通 virtio 输入在休眠时被 reset，不能用宿主机
键盘事件替代一条未配置的内核唤醒路径。

本部件只对 `linux,dummy-virt` 根兼容串、OF `poweroff` 节点、EV_KEY/KEY_POWER
四项同时匹配的按钮启用已有 gpio-keys wakeup 路径。现有驱动负责
enable_irq_wake、PL061 父 IRQ、suspend/resume 和按键事件。其他板、其他键、
ACPI/x86 的既有电源键路径不改变；不降低 seccomp/权限、不注入周期事件。

ARM32/ARM64 运行验证须实际休眠后使用一次 QMP `system_powerdown` 电源键
事件，并核对恢复后相同 boot ID/服务实例、真实 wakeup-source/suspend stats。
该命令是电源按钮，不是测试通过证据；未知机型/未休眠时不能盲目使用。
正常键盘/触摸独立唤醒能力尚须验证，不能据本补丁宣称全部输入均可唤醒。
