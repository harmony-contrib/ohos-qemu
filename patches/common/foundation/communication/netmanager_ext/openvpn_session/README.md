# Atomic native sessions and negotiated QEMU network configuration

Apply after `connected_vpn_nullable` and `openvpn_lifecycle` at pinned
netmanager_ext `8c41289750820fb2ddb347b1205cee9a7b527388`. The preceding
validators accept this complete exact follow-up, including every unchanged
file in their own manifests; unknown or partial edits still fail closed.

The existing private `GetSysVpnCertUri` ABI carries a reserved native request
that returns configuration, password and a kernel-random generation in one
locked snapshot. It binds the real supervisor executable's IPC PID. Subsequent
native events identify that generation, and the service resolves its exact
controller rather than borrowing `connectingObj_`. The controller accepts only
the bound supervisor or a real bridge/OpenVPN child lineage. Config and TUN
setup belong to the bridge, connection/reconnection state to the supervisor.
Legacy IPSec APIs and permission/account checks remain in place. Controller
errors now reach the private IPC caller instead of being discarded.

The bridge consumes the fixed OpenVPN AF_UNIX environment: subnet or point-to-
point IPv4, IPv6, sparse IPv4/IPv6 route indices, explicit redirect flags, final
structured DNS and legacy foreign options. Structured final DNS takes priority.
The paired OpenVPN port patch exports its actual final DNS state before the
bridge is forked. Unsupported encrypted/nonstandard-port DNS, split-DNS policies,
block-local redirects and nonzero route metrics fail explicitly. The bridge
never substitutes default DNS or invents a connection. The controller validates
and replaces all addresses/routes/DNS/domains atomically before the real TUN
setup. The generic VPN base now uses each DNS literal's real address family
and handles IPv4 /0 without a shift by 32.

A reconnect removes the old network configuration and requires fresh bridge
readiness plus real management CONNECTED before publishing success again.
`persist-tun` is explicitly rejected because that upstream mode does not fork
another AF_UNIX bridge or deliver updated environment to it; a configuration
update channel for that mode remains open. The one native init service also
cannot serve two simultaneous OpenVPN owners yet: a second owner is rejected
before restarting/killing the first. This is not multiple-owner completion.

An exclusive, owned 0700 session root and 0600 lock serialize supervisors.
After an abrupt previous exit, only exact `session-XXXXXX` directories and
known private files are pruned using no-follow directory-relative operations.
Symlinks, unexpected names and unknown directory contents are not traversed.
The Linux parent-death binding remains required for the actual exec children.

Host tests execute the real prepared controller/service/base method bodies
with the fixed cJSON implementation and explicit backend/process-role doubles.
They cover atomic reads, stale generation routing, failed controllers, DNS and
prefix boundaries, full snapshot replacement, reconnect gating and session
cleanup. They are not native identity, routing, packet-transfer or package
acceptance. Final full-TU compilation/linking, Linux lineage and process tests,
external-callback lifecycle repair and first-new-package TLS/permission/account/
network validation remain mandatory before delivery or ledger closure.
