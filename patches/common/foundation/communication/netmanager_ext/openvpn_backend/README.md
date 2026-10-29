# Native QEMU OpenVPN backend candidate

The dynamic sources now implement one init broker with per-owner workers,
private credentials and management/ready sockets, and a real negotiated TUN
bridge. Apply the paired `netmanager_base/qemu_openvpn_broker` and
`netmanager_ext/openvpn_broker` components after the reviewed session/callback
layers. Central installation, narrow policy and final product compilation are
owned by the parent agent.

Start is acceptance of an actual owned worker; CONNECTED requires both real
OpenVPN TLS management state and an authenticated live bridge using the exact
native TUN descriptor. Owner/uid/user/vpnId and kernel-random generation stay
atomic. Per-owner STOP proves actual process-group exit and never restarts
another owner. An independent FFRT health queue handles broker/worker death,
cleanup failures and service teardown; getters check actual starttimes.

See [broker source contract](../openvpn_broker/README.md) and the detailed
[integration and acceptance contract](../../../../../../docs/capability-audit/parallel/network/vpn-broker-integration-20261016.md).
The existing profile policy, real negotiated DNS/address/route parser, ancillary
FD bounds and parent-death guards remain enforced. No profile hook or public
fake-connection entry point is introduced.

Earlier complete ARM64 helper compile/link evidence belongs to the prior
sources. This broker revision needs fresh real product compilation/linking,
Linux death/recovery checks and a newly packaged TLS peer challenge before any
VPN audit requirement can be closed. persist-tun, unsupported OHOS DNS policies
and nonzero route metrics remain explicit open support cases.

Cleanup retains separate process-kill and reap stages. A directory removal
failure keeps its owner/interface reservation and retries removal without
signalling the retired process group. Shutdown preserves failed jobs for retry
and reports failure to the supervisor until cleanup completes. See the
[round 21 handoff](../../../../../../docs/capability-audit/parallel/network/round21-coordinated/HANDOFF.md)
for the real filesystem counterexample and remaining Linux/package gates.

The client and helpers retain init's `netsysnative` domain, matching the
existing `netsysnative sysvpn_exec` execution model. The component-local
`whitelist/perm_group_whitelist.json` records only
`netsysnative qemu_openvpn_exec` for the standard `execute and execute_no_trans`
check in user policy (also inherited by developer policy). It does not grant
permissions; the dedicated executable label, allow rules and execute
neverallow remain in force. The unmodified full SELinux checker must pass
before another representative package attempt.

Private VPN files carry `data_service_file_attr`; their management socket and
the init-created control sockets carry `system_sock_domain`. The control
parameter is system internal. These classifications retain the dedicated
labels and do not add an access rule. Regular config/lock files have no ioctl
grant; the existing TUN-device ioctl remains narrowly specified separately.
