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
IPv4 `/31`/`/32`, IPv6 `/128`, or wider native port values.

Get and list also omitted stored routes, MTU, IPv4/IPv6 acceptance, legacy and
blocking flags, trusted/blocked applications and service-selected user ID.
Serialize those actual native fields for every variant. Parse and return the
existing `Route::isExcludedRoute_` member as the SDK's optional
`isExcludedRoute`, without changing Route layout or its existing Parcel codec.
Optional empty routes/application arrays remain omitted. No certificate or
credential fields are added by this network-field serializer.

This does not change the public signature, native data layout, permissions or
VPN IPC. It does **not** fix the separate database conversion that stores only
one entry and loses the prefix. A successful serializer/compile check alone
must not close CRUD, connected-VPN or tunnel/traffic gaps. Actual new-package
round trips, restart, denied callers and a connected tunnel remain required.
