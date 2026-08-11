# Standard QEMU VPN Overlay

This overlay makes OpenHarmony's standard VpnExtension capability a required
part of the `armv7a_virt`, `arm64_virt`, and `x86_64_virt` QEMU products.

It does not grant VPN authorization to any application. A clean image must
show the system `VpnDialog` on first use and persist the user's decision
through SettingsData.

The overlay:

- enables namespaces, Unix fd passing, built-in TUN support, and policy
  routing for IPv4 and IPv6;
- enables fs-verity, the advanced code-sign/HCK vendor hooks, built-in SHA-256
  and ECDSA verification, F2FS quota-inode support, 64-bit XPM
  developer-mode support,
  and F2FS in the kernel,
  including the explicit fs declarations needed by the 32-bit code-sign
  build and 32-bit-safe fs-verity Merkle-tree arithmetic,
  then generates writable F2FS `userdata.img` with the verity/code-sign ioctl
  path required by HAP code-sign enforcement;
- selects `statx` through the target ABI's `SYS_statx` definition so x86_64
  code-sign builds cannot inherit arm64 syscall numbers from a generic
  `asm/unistd.h`;
- selects `add_key` and `keyctl` through the target ABI's `SYS_*` definitions,
  so `key_enable` can populate the fs-verity trust keyring on all three
  architectures;
- fixes the upstream musl sysroot staging rule to copy `asm-x86` for x86_64,
  protecting every guest component that invokes architecture-specific
  `__NR_*` syscalls rather than only the VPN installation path;
- initializes the optional HCK JIT `mprotect` hook result before dispatch, so
  a kernel without the JIT-memory hook cannot reject valid executable-memory
  transitions from an uninitialized x86_64 stack value;
- explicitly enables `netmanager_ext` VPN and VpnExtension features;
- requires SettingsData, the VPN authorization dialog build target, its
  preinstall entry, and its privileged-extension capability entry;
- replaces the expired bundled VpnDialog profile with a currently valid
  OpenHarmony system profile that grants every restricted permission declared
  by VpnDialog;
- packages launchers with `oemmode=rd`, `buildvariant=eng`, and
  `developer_mode=1`, and enables the guest developer-mode parameter so both
  kernel XPM and AccessToken accept normal development HAP profiles;
- keeps QEMU's RenderService on its standard OpenGL context and EGLImage path;
  the portable `virtio-gpu` backend uses Mesa `kms_swrast` when host 3D
  acceleration is unavailable. For arm64 and x86_64 it replaces the old QEMU
  GPU prebuilts with Mesa 21.3.3 built from OHOS source plus upstream fix
  `c285df95c30d1d7af26d8203c736ecf3f23dc67c`, which changes the broken
  `va_list` formatting in `ohos_logger` to `vsnprintf`. armv7a uses the same
  fix in its source-built Mesa path. The image installs both `swrast_dri.so`
  and `virtio_gpu_dri.so` as aliases of the resulting multi-driver
  `kms_swrast_dri.so`, matching every portable DRM selection path without
  relying on QEMU GPU Git LFS binaries. This keeps authorization dialogs,
  surface capture, and UI application switching on one coherent rendering
  lifecycle.

Apply it after the `armv7a_virt_full` overlay, when that product is selected,
and before building:

```sh
bash overlays/standard_qemu_vpn/apply.sh \
  --source-root /path/to/openharmony \
  --product arm64_virt \
  --product x86_64_virt
```

The package script independently checks the final kernel `.config`, x86_64
code-sign syscall ABI, the `userdata.img` F2FS magic and verity feature bit,
and the exact signed VpnDialog HAP extracted from `system.img`. Packaging fails
if a required VPN capability was optimized out, if userdata lacks the F2FS
code-sign path, or if the HAP profile is expired or lacks a required system
ACL.

## Paws IPv6 runtime check

Import `ci/standard-vpn/ipv6-direct.yaml` into Paws, start the VPN, and approve
the system's first-use VPN dialog. Then run:

```bash
ci/standard-vpn/verify-paws-ipv6.sh \
  --target 127.0.0.1:5555 \
  --hilog /path/to/paws-smoke.hilog
```

The verifier requires the expected `fdfe:dcba:9876::1/126` address, the
`::/0` VPN route, a running TUN fd, successful Paws network protection and
startup, plus IPv6 connectivity to QEMU's user-network gateway. Supplying the
smoke-test hilog also verifies the system's address and `::/0` route install
events rather than relying only on the live interface and VPNManager state.
