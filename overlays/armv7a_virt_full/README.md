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
- keeps the standard-system service set enabled. The upstream virtio GPU
  userspace prebuilts currently only provide arm64 and x86_64 payloads, so the
  overlay excludes that missing prebuilt dependency for 32-bit ARM instead of
  disabling account, bundle, ability, SELinux, or other system features.

Apply it to an OpenHarmony checkout before building. The actual OpenHarmony
build must run inside Docker with an Ubuntu 22.04 userspace:

```sh
bash overlays/armv7a_virt_full/apply.sh --source-root /path/to/openharmony
./build.sh --product-name armv7a_virt --ccache --jobs 8
```
