# QEMU AdminProvisioning HAP graph

Pinned HAP project f2e956a5dd26102f85c86e91d2bfd7c0998534f8, after the existing
calendar_provider -> photos_provider -> settings_provider HAP components.
Expected pre-hash: 3c9db915d35742864f493c1c3f502314d43ebc85d6e79321e3647db25eb88df4.
Expected final hash: f53e1d7c537ec63ef5c7ebb37b16bcd4a95e1d4a8a17fe68a034b0d65955b9d2.

This adds the actual source target
//applications/standard/admin_provisioning:adminprovisioning_hap for only the
three QEMU products arm64_virt/armv7a_virt/x86_64_virt. Existing rk3568 and
ohos-arm64 branches remain unchanged. Standard prebuilt_hap ownership and
provider signing apply; there is no alias/prebuilt download.

Apply after all three predecessors. A regression starts with real git HEAD
BUILD.gn, applies the complete four-component chain, then replays the entire
chain twice. All states have exact hashes. Unknown future HAP graph changes
must be explicitly reviewed and added to the composition; never skip the guard
based on marker files or reapply this patch only to pristine HEAD.
