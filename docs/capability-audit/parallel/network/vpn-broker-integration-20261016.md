# Native broker integration and acceptance contract

This batch starts at 87e106fce6145751c52930991a8206ab07367abe. All 9 assigned
requirements remain open. No build, QEMU, HDC or shared-source mutation was
started by the network agent. Parent owns product installation and acceptance.

## Fixed contract and order

The fixed `/ohos/out/arm64_virt/args.gn:28,30` enables base/ext sysvpn; actual
net_vpn_manager Ninja flags define SUPPORT_SYSVPN and consume multi_vpn_helper.
The existing service has a 20-interface extension map, vpnId destroy, owner UID
checks and multi events. System-settings single VPN remains mutually exclusive.

Apply base `qemu_openvpn_control`, then `qemu_openvpn_broker`; ext
`always_on_vpn`, `connected_vpn_nullable`, `openvpn_lifecycle`, `openvpn_session`,
`vpn_callback_dispatch`, `netvpn_callback_unused`, then `openvpn_broker`.
Install the full dynamic `openvpn_backend/files` set, including both new broker
headers. Preserve parent recipe/source lock, GN product/sysvpn/fpga selection,
policy and license binding. Add `init:libbegetutil` to helper external deps for
GetControlSocket; do not reuse old helper object/link/package receipts.

## Init and policy

| Init service | Socket name/path | Type and DAC | Caller/process contract |
| --- | --- | --- | --- |
| qemu_openvpn | qemu_openvpn; /dev/unix/socket/qemu_openvpn | AF_UNIX, SOCK_STREAM, default protocol, 0600, netsysnative:netsysnative | UID 1098; exact /system/bin/sa_main with the complete NUL-delimited argv `/system/bin/sa_main`, `/system/profile/netsysnative.json` |
| netsysnative | qemu_openvpn_tunfd; /dev/unix/socket/qemu_openvpn_tunfd | AF_UNIX, SOCK_STREAM, default protocol, 0600, netsysnative:netsysnative | Actual qemu_openvpn_tun, qemu_openvpn client and the bound service worker/broker ancestry and starttimes |

The actual existing second cfg is
`foundation/communication/netmanager_base/services/etc/init/netsysnative.cfg`.
Both listeners call fixed init GetControlSocket (OHOS_SOCKET_name environment
ABI), then independently validate Unix stream type, exact bound pathname,
filesystem socket type/owner/mode. UID 1098 never binds in the root-owned 0755
socket directory. Parent creates the descriptors. New service control is START
only; normal per-owner STOP does not stop or restart the init broker.

Keep the existing netsysnative domains for broker/worker/client/bridge, with
private sock_file labels for these two paths (suggested exact type names:
qemu_openvpn_control_socket and qemu_openvpn_tunfd_socket). Only init creates the
filesystem endpoints; netsysnative connects/listens/accepts on the passed FDs.
Keep the current private qemu_openvpn data-root label for its 0700 directory,
0600 profiles/passwords and per-session management/ready sockets. NetworkVpn
service needs its already-used readlink/status plus read-only /proc/PID/stat
for starttime checks; add only actual demonstrated narrow policy if needed.
No net_manager connection or file access to the 0600 control/TUN sockets or
0700 credential root is required. No extra caller permission or SDK test hook.

## Private protocol and bounds

All streams use a 32-bit network-order length and bounded payload. Commands
start with `qemu-openvpn-broker-v2\n`, then start/stop and 8 length-delimited
fields: UID, userId, bundle owner, vpnId, interface, 32-hex generation, profile,
password. Stop has empty profile/password. Start reply is `0\nPID\nstarttime`;
stop reply is `0`; errors are decimal errno. A new cleanup broker replies
ENOENT for an old stopped capability only after its exclusive SessionStore
cleanup completes. Netsys accepts that as recovery only with its independently
stored matching owner and proven dead old process groups.

TUN requests are framed `qemu-openvpn-tun-v2\n` plus generation; owner/interface
selection comes entirely from the native binding. The FD must name that exact
TUN with IFF_TUN|IFF_NO_PI. Ready uses authenticated R/F bytes; only R plus real
TLS and a live bridge can publish CONNECTED. Failure never synthesizes a TUN.

Limits: 20 concurrent workers; 1024 non-reusable capabilities per broker
lifetime; 1MiB profile, 4096-byte password, 1024-byte bundle/vpnId; stream maximum
1MiB+8192. Length-delimited text has no framing ambiguity; field-specific validation rejects NUL and invalid numeric/password encodings.
Native startup waits at most 3s for init; individual frame transfers have 2s
bounds, STOP response waits 7s. Worker stop has 500ms grace followed by a 2s
reap bound. Health delay is 500ms and unclaimed session timeout 10s. Runtime
uses an independent health queue with at most one pending tick; callback,
account and worker generations are checked before stale work can act.

## Exact tests to run centrally

Host complete regression:

```sh
LC_ALL=C LC_CTYPE=C LANG=C PYTHONPATH=ci/capability-audit python3 -m unittest discover -s ci/capability-audit -p 'test_batch_network*.py' -v
```

Run the same suite in private Linux scratch using a frozen commit snapshot.
These two new cases require real Linux prctl/subreaper and must not skip:

```sh
PYTHONPATH=ci/capability-audit python3 -m unittest \
  test_batch_network_vpn_broker.VpnBrokerTests.test_linux_stop_reaps_worker_and_descendant_blocked_on_callback \
  test_batch_network_vpn_broker.VpnBrokerTests.test_linux_sigkill_broker_kills_all_descendants_and_reclaims_credentials -v
```

Keep the earlier `test_batch_network_openvpn_lifecycle` real fork/exec
parent-death case. The new blocked-descendant case verifies that no Notify RPC
is needed to complete a stop; the SIGKILL case verifies worker/client/bridge
parent-death cascade and actual locked stale-password cleanup.

Emit two current actual-function probes with real FFRT APIs:

```sh
python3 ci/capability-audit/batch_network_emit_vpn_broker_native.py --output-dir PRIVATE_DIR
```

Compile vpn-broker-callback-native.cpp and vpn-broker-health-native.cpp against
the fixed target ABI, FFRT interfaces/kits and actual libffrt, then run with a
bounded timeout. Callback probe covers stop revocation while a publication is
blocked on netVpnMutex; health covers delayed scheduling, failure/retry,
stop/restart epochs and weak teardown on real FFRT. Account/IPC/backend doubles
remain explicit; these probes do not constitute a running guest VPN proof.

Compile/link the real complete supervisor, bridge, service/controller and
native MultiVpnManager/SystemVpnWrapper TUs with their final changed headers;
verify all generated IPC and linked consumers for each architecture. Then the
first newly packaged artifact must prove simultaneous owners with different
accepted-app rules and TLS peers, correct interfaces/routes/DNS/IPv4/IPv6,
legitimate getters/events, normal and failed stop, owner/account/permission
rejection, stale generation, reconnect/new configuration, broker SIGKILL,
all-descendant exit, private file removal and restart. Record artifact path,
checksum/environment/commands/results. Only after that complete runtime gate
may the other five packages be built and validated.
