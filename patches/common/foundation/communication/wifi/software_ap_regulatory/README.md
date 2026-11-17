# Software AP regulatory backend

Pinned OHOS 7.0 `WifiApHalInterface::SetWifiCountryCode` unconditionally fails
without chip HDI. R31 actual Settings hotspot startup reached that branch and
aborted on country `HK`; successful `startSharing` submission did not mean an
active AP. Evidence: `r31-hotspot-ui-runtime-03/immediate-after-request` under
`/Volumes/PSSD/qemu/validation/first-20261005/issue-20-20261006`.

Only non-chip, WPA-backed standard builds use this candidate fallback. It sends
a real cfg80211 regulatory request through libnl, requires the kernel ACK and
matching kernel readback, and fails on invalid inputs, unavailable interface,
transport errors, malformed replies, wrong reply source or timeout. No shell
command, fixed-success stub, permission grant, unsigned regulatory database or
regulatory-check bypass is introduced. Chip HDI behavior is unchanged. Existing
Wi-Fi service CAP_NET_ADMIN remains the authority for the operation.

The same algorithm compiled for all three SDK ABIs. A package-external root
diagnostic on an unmodified R31 guest applied/read back HK, repeated the operation,
and rejected lowercase/oversized country and missing interface. Evidence:
`regulatory-candidate-compile-r32-01` and `r31-hotspot-ui-runtime-04`.
These are **not** production Wi-Fi service identity, AP startup, association,
DHCP, data-path, P2P, six-package or first-artifact acceptance. R32's already
frozen build does not contain this component. Require a subsequent rebuilt
representative archive and ordinary Settings regression before closure.

The component pins complete source states (including the bundle's original
missing EOF newline) and rejects partial edits. New libnl dependency is applied
before dependency traversal through the shared local Docker build entry.
`libnl` must be in `component.deps.components`: the real OHOS external-dependency
checker does not consult `third_party` for `libnl:libnl_share`. R33 caught the
initial incorrect classification before packaging. The corrected declaration is
tested with the actual checker, including rejection of the previous metadata;
no dependency whitelist or checking bypass is added.
