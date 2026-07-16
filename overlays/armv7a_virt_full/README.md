# armv7a_virt Full Overlay

This overlay adds an experimental OpenHarmony standard-system full QEMU product
named `armv7a_virt`.

It is intentionally kept outside the normal packaging scripts because upstream
OpenHarmony currently ships full QEMU products for `arm64_virt` and
`x86_64_virt`, but not for 32-bit ARM. The overlay creates the missing product
and board glue from the upstream `arm64_virt` templates.

Current scope:

- full/rich standard-system product, not min/headless;
- Linux/QEMU execution through `qemu-system-arm`;
- HDC forwarding on host TCP port `5555`;
- windowless headless mode with a PCI virtio GPU still attached. RenderService
  initializes Mesa through `/dev/dri/card0` even when QEMU uses
  `-display none`; omitting the device makes RenderService crash and causes a
  critical-service reboot. GUI modes attach the same GPU plus input devices;
- keeps the standard-system service set and GPU RenderService enabled. Because
  the upstream virtio GPU userspace prebuilts only provide arm64 and x86_64
  payloads, the overlay builds the last OpenHarmony Mesa 21.3.3 revision before
  the 22.2.4 upgrade for 32-bit ARM. Its driver composition matches the arm64
  QEMU prebuilt: `swrast`, `kms_swrast`, and `virtio_gpu`. Account, bundle,
  ability, SELinux, and graphics features remain enabled.

The Mesa baseline is OpenHarmony GitHub commit
[`995d2506d189`](https://github.com/openharmony/third_party_mesa3d/commit/995d2506d18924b48db0cf40e6ad7de04fc4e558).
The build carries forward OpenHarmony's later `vsnprintf` logger correction
from commit
[`c285df95c30d`](https://github.com/openharmony/third_party_mesa3d/commit/c285df95c30d1d7af26d8203c736ecf3f23dc67c).

Apply it to an OpenHarmony checkout before building. The actual OpenHarmony
build must run inside Docker with an Ubuntu 22.04 userspace:

```sh
bash overlays/armv7a_virt_full/apply.sh --source-root /path/to/openharmony
./build.sh --product-name armv7a_virt --ccache --jobs 8
```
