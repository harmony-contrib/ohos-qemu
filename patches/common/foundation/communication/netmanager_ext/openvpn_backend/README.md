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
