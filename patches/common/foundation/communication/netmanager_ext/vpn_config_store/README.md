# Complete system-VPN network storage

The pinned 7.0 source stores only the first address/DNS/domain/remote entry and
discards prefixes and local addresses. An added private `networkConfig` column
stores the full base network configuration and remote/local address vectors.
Database version 3 migrates versions 1 and 2 without deleting existing rows.
New data uses a bounded, versioned encoding of the existing native Parcel data;
decoding checks counts, lengths, UUID binding and complete consumption before
changing any configuration. Invalid nonempty snapshots fail, not silently
fall back to legacy data. Legacy rows retain their original fields; information
already discarded by the old implementation cannot be reconstructed.

Sensitive credential columns retain their existing HKS encryption; the network
snapshot excludes credentials and certificate material. PKCS#12 input
persistence is not claimed by this component. No public SDK signature, permission or VPN
wire protocol changes. The private `VpnDataBean` layout changes, so every image
client/service must rebuild together. Absent/invalid get results reject through
the existing internal-error path instead of resolving an invalid object. List
items now use the same typed serialization as get, including mandatory addresses,
instead of returning only IDs and names; null list items reject before callbacks.

The native-to-ArkTS array serializer is an independent `vpn_config_arrays`
component. Host fixtures and actual TU compilation are not database, VPN tunnel
or new-package acceptance. New package tests must check multiple entries and
prefixes, all VPN config types, replacement, a new caller process, permission
denials and cleanup; connected/tunnel APIs still require a real connected tunnel.
