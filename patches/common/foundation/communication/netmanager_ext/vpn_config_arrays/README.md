# System VPN configuration arrays

Pinned netmanager_ext: `8c41289750820fb2ddb347b1205cee9a7b527388`.

The existing native-to-ArkTS serializer loses every entry after the first in
addresses, remoteAddresses, dnsAddresses and searchDomains, and replaces every
address prefix with 1. Preserve each native entry, its order, prefix, family and
port. The mandatory addresses member remains an array for an empty config;
optional empty string arrays retain their existing omission behavior.

The input parser also incorrectly interpreted an IPv6 **host** address as a
subnet mask instead of reading `prefixLength`, and narrowed IPv4 prefixes before
validation (`257` became `1`). Read the actual requested prefix for both
families; reject non-finite, fractional, out-of-range numbers and NAPI failures
before narrowing. Keep the existing nonzero/less-than-address-width and IPv4
subnet/broadcast restrictions. This patch does not claim support for `/0`,
IPv4 `/31`/`/32`, or IPv6 `/128` in the standard system-config address path.
The paired port repair below supplies the full native port range separately.

Routes have a different contract: destination prefixes include the default
route `/0` and host routes `/32` (IPv4) or `/128` (IPv6). Validate the required
numeric `prefixLength` before narrowing, using the actual destination address
family. Reject negative, fractional, non-finite, missing, wrong-type and
out-of-family-range values rather than silently wrapping or defaulting them.
This does not relax the separate interface-address restrictions above.

Get and list also omitted stored routes, MTU, IPv4/IPv6 acceptance, legacy and
blocking flags, trusted/blocked applications and service-selected user ID.
Serialize those actual native fields for every variant. Parse and return the
existing `Route::isExcludedRoute_` member as the SDK's optional
`isExcludedRoute`, without changing Route layout or its existing Parcel codec.
Optional empty routes/application arrays remain omitted. No certificate or
credential fields are added by this network-field serializer.

Validate the actual optional address-family number in all four standard and
extension setup/system-config sources before narrowing. Only integral finite
1/2 values are valid; 257/258, fractions, wrong types and NAPI failures are not
legitimate families. Absent/undefined family uses the SDK's IPv4 default 1.
Address, route destination and gateway paths share the same validation within
each TU. OpenVPN hostname handling is preserved but cannot bypass family
validation. Do not change the uint8 field, public signature, Parcel or rights.
This family repair does not claim to repair the separate remaining extension
prefix conversions. The subsequent port repair depends on inet_addr_port.

Use the shared strict uint16 helper for all four VPN address, destination,
gateway and hostname paths. Keep 0..65535 intact; missing/undefined is 0 and
invalid original values fail before narrowing or sending IPC. Apply the paired
netmanager_base/inet_addr_port component and uniformly rebuild native storage,
Parcel, NAPI utility and every image-side consumer. This changes the internal
port field type, not public SDK signatures or permissions; do not mix old wide-
port-truncating receivers with newly compiled users.

The final prefix repair covers the other three duplicated address/destination
parsers (ordinary standard setup, ordinary extension setup, extension config).
Validate the original finite integer before uint8 conversion; use the requested
IPv6 prefix, never infer it from the bits of a host address or silently turn
zero into a different prefix. Preserve these callers' existing nonzero address
prefix limit and IPv4 subnet/broadcast checks; ordinary setup's existing host
address /32 exception remains. Routes accept /0..32 and /0..128 based on the
actual destination IP. Missing/wrong-type/NAPI-failed route prefixes cannot
silently default to zero. This does not broaden existing interface-address
policies or claim connected/tunnel/extension-ability guest behavior.

The array/family/prefix repairs do not change public signatures, native layout,
permissions or VPN IPC; the paired port repair widens the internal port field.
This component does **not** fix the separate database conversion that stores only
one entry and loses the prefix. A successful serializer/compile check alone
must not close CRUD, connected-VPN or tunnel/traffic gaps. Actual new-package
round trips, restart, denied callers and a connected tunnel remain required.
