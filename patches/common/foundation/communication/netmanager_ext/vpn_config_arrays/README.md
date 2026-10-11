# System VPN configuration arrays

Pinned netmanager_ext: `8c41289750820fb2ddb347b1205cee9a7b527388`.

The existing native-to-ArkTS serializer loses every entry after the first in
addresses, remoteAddresses, dnsAddresses and searchDomains, and replaces every
address prefix with 1. Preserve each native entry, its order, prefix, family and
port. The mandatory addresses member remains an array for an empty config;
optional empty string arrays retain their existing omission behavior.

This does not change the public signature, native data layout, permissions or
VPN IPC. It does **not** fix the separate database conversion that stores only
one entry and loses the prefix. A successful serializer/compile check alone
must not close CRUD, connected-VPN or tunnel/traffic gaps. Actual new-package
round trips, restart, denied callers and a connected tunnel remain required.
