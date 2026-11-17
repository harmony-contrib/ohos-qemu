# QEMU OpenVPN owner broker and recovery candidate

Apply after `openvpn_session` and `vpn_callback_dispatch`, together with the
netmanager_base `qemu_openvpn_broker` component and the final dynamic backend
files. Exact predecessor guards accept only this complete successor; a partial
or unrelated edit still fails. Public IPC signatures, the single system VPN
exclusion, account/permission checks and other VPN type selection stay intact.

The fixed ARM64 args enable both sysvpn features. Its real net_vpn_manager
Ninja entry defines SUPPORT_SYSVPN and consumes MultiVpnHelper. The service
already supports extension VPNs keyed by vpnId, validates callingUid on destroy
and allocates at most 20 interfaces. Rejecting every second OpenVPN owner was
therefore a backend gap. Pending QEMU owners now reserve distinct
`multitun-vpn1` through `multitun-vpn20` interfaces and enter the real service
map before asynchronous negotiation can complete.

A start request carries one checked, length-delimited owner/userId/uid/vpnId,
interface, kernel-random generation, decoded profile and password snapshot
through the existing permission-protected netsys call. The global "latest
connecting owner" credential read is disabled for the reserved private request.
Each broker worker authenticates its generation through actual IPC process
identity before starting OpenVPN. Final negotiated config and TUN setup still
come from that worker's authenticated actual OpenVPN bridge. CONNECTED needs
both actual TLS management state and a live real TUN bridge.

The one init broker keeps at most 20 workers, one process group and private
session directory per worker, and at most 1024 used capabilities per broker
lifetime. Replayed capabilities, duplicate owner keys/interfaces and malformed
or oversized frames fail. It forks before touching IPC/FFRT. Start replies pin
the actual worker PID/starttime; native TUN delivery checks that exact worker,
its exact broker starttime, bridge/client lineage, capability and actual TUN
name. An authenticated negative readiness byte promptly reports bridge failure.

STOP signals only its matched owner/generation group, allows 500ms grace, then
kills and reaps that whole group before removing its private files and replying.
It never waits for a worker's synchronous VPN callback. Queued CONNECTED events
are revoked before stop; genuine disconnect events can still be delivered.
Netsys start, stop and mode failures, supplier/link/UID/up-rule errors and
best-effort cleanup failures return to callers. The QEMU OpenVPN TUN skips only
the IPSec UP step that RouteManager already skips for real TUNs; UID rules and
NetLinkInfo errors remain mandatory. IPv4 interface /0 and signed-mask shift
boundaries are repaired in the actual native implementation.

An independent FFRT health queue schedules one 500ms check, with an epoch for
stop/restart and weak service ownership. It detects worker/broker starttime
changes, startup claim timeout (10 seconds), and failed stop/cleanup requests.
It marks disconnected, retries real cleanup and releases only the matching
service-map object. OnStop and destruction force owned-session teardown. Queue
failure is recorded in the existing failure counter and rejects a new setup
before the backend start. A dead broker cannot leave getter state CONNECTED.

Recovery never equates a missing PID with completed teardown. Native bindings
hold the original authenticated owner, broker and worker starttimes. A lost
broker is recoverable only when its actual worker process group is empty;
starting a cleanup broker additionally requires every old broker group to be
empty. The new broker must finish its exclusive no-follow SessionStore cleanup
and reply ENOENT for the old capability before native STOP acknowledges loss
and drops its binding. A still-live old group keeps recovery in explicit error
and retry. Live owners under an existing broker are preserved.

Central installation/compilation and newly packaged peer validation remain
required. This is a source candidate, not closure of the three VPN audit items.
`persist-tun`, DNS policies not representable by OHOS and nonzero route metrics
remain explicit unsupported cases, with genuine multi-owner TLS/data/routing,
account/permission, reconnect and abrupt-death acceptance still pending.
