# virt_userspace_suspend

Uses a synchronized userspace condition-variable wait in `power_host` on `ohos.boot.hardware=virt` instead of writing `mem` to `/sys/power/state`, preserving `PowerManagerService` sleep/wakeup callbacks without freezing the guest kernel, `virtio-net`, or `hdcd`.
