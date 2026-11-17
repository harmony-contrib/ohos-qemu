# QEMU virtio-gpu s2idle state

Linux 6.6's virtio-gpu has no freeze/restore callbacks, but the PCI
transport resets the device on resume. QEMU then loses the host-side ring
addresses while the guest keeps using the old queues. A display DPMS commit
blocks indefinitely and the service watchdog restarts the compositor.

For QEMU `linux,dummy-virt` machines and QEMU DMI systems only, retain the
virtual GPU during **s2idle** when the driver lacks both PM callbacks.
QEMU remains running, so GPU queues/resources and IRQ routing do not need
reset/recreation. Other virtio devices and physical machines are unchanged;
S3 and all hibernation callbacks retain the original reset path. A GPU
driver gaining real PM callbacks automatically uses the original path.

This neither disables suspend nor keeps the VM awake, and adds no private
host protocol. Validate repeated real power-key wakeups, compositor/RS
identity, and display readback before treating it as a runtime fix.

Sources: Linux 6.6 `drivers/virtio/virtio.c`, `virtio_pci_common.c`, and
`drivers/gpu/drm/virtio/virtgpu_drv.c`; the upstream failure is also described
in <https://lkml.iu.edu/2306.1/00095.html>. That proposed protocol extension
is not used because the packages must run with ordinary host QEMU.
