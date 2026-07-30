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
- forces QEMU's RenderService composer onto its CPU raster path while
  retaining the existing OpenGL ABI and build cache compatibility, so the
  authorization dialog works on hosts whose QEMU build has no guest 3D
  acceleration.

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
