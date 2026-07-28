# Standard QEMU VPN Overlay

This overlay makes OpenHarmony's standard VpnExtension capability a required
part of the `armv7a_virt`, `arm64_virt`, and `x86_64_virt` QEMU products.

It does not grant VPN authorization to any application. A clean image must
show the system `VpnDialog` on first use and persist the user's decision
through SettingsData.

The overlay:

- enables namespaces, Unix fd passing, built-in TUN support, and policy
  routing for IPv4 and IPv6;
- enables fs-verity and built-in signature verification for installed HAPs;
- explicitly enables `netmanager_ext` VPN and VpnExtension features;
- requires SettingsData, the VPN authorization dialog build target, its
  preinstall entry, and its privileged-extension capability entry.
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

The package script independently checks the final kernel `.config` and
`system.img`. Packaging fails if any required VPN capability was optimized out
or omitted from the image.
