# Shared Ethernet candidate, round 16

`behavior:peer-device-user-nat-isolation` remains **open**. This batch supplies
an explicit real two-QEMU Ethernet connection and independent-instance staging;
it does not supply evidence of a guest boot, discovery, trust, or a session.
The base is `2c6a5c2`, branch `codex/network-peer-lan-20261017`. Nothing changes
OpenHarmony source/out, the shared runners/verifiers, or the other five packages.

## Backend and launch contract

The installed Darwin binary is QEMU 11.0.3. Its actual `-M virt -netdev help`
contains `stream` and `user`. `host-backend-contract.json` retains the binary
hash, exact commands/results, and hashes/line anchors for official v11.0.3
`net/stream.c`, `net/stream_data.c`, and `qapi/net.json`. The stream receiver
forwards Ethernet packets to QEMU's network client, rather than routing them
through libslirp. The official [manual](https://www.qemu.org/docs/master/system/qemu-manpage.html)
describes the two-guest stream endpoints and filter-dump capture. This is
source/help evidence only; Linux and Darwin guest execution is still pending.

For `arm64_virt`, `armv7a_virt`, and `x86_64_virt`, the POSIX package launcher
retains the original management user NIC and can append:

```text
listener:  -netdev stream,id=peer_lan,server=on,addr.type=inet,addr.host=127.0.0.1,addr.port=PORT
connector: -netdev stream,id=peer_lan,server=off,reconnect-ms=250,addr.type=inet,addr.host=127.0.0.1,addr.port=PORT
both:      -device virtio-net-pci,id=peer_lan_nic,netdev=peer_lan,mac=OWN_UNIQUE_MAC
```

This is a two-endpoint Ethernet wire on the same host. Broadcast/multicast and
ARP travel between the actual guest NICs. Each endpoint's original user network
remains isolated management access; its identical default guest-side address
is not used as a peer address. No root host bridge, TAP, Python packet proxy,
soft-bus callback replacement, or generated device-manager identity is used.

Enable `QEMU_PEER_MODE=listen|connect`, the same `QEMU_PEER_PORT`, and explicit
unique `QEMU_PEER_MAC`, `QEMU_MGMT_MAC`, `QEMU_INSTANCE_UUID`, and
`QEMU_GUEST_SERIAL`. Default `off` adds no data NIC; an original explicit
management MAC and boot serial are preserved. Input validation rejects option
injection, multicast/global MACs, a reused own management MAC, reserved duplicate
peer/UUID extra arguments, and unsupported QEMU backends. Optional
`QEMU_PEER_CAPTURE_FILE` creates a new safe pcap path for the data NIC. Windows
and the minimal non-PCI product are outside this candidate.

The launcher substitutes only an already-present kernel `sn=` parameter;
UUID/serial describe the emulated hardware and do not assert an OpenHarmony
UDID. The fixed source's complete serial-to-UDID behavior is not established
in this host-only batch. Actual duplicate UDIDs must fail before addressing.
In particular, cloned previously initialized userdata may retain identity or
credential state: it cannot be repaired by inventing identity API results or
copying account/HUKS/trust databases. Fresh legitimate guest provisioning may
be required and remains a runtime dependency.

## Root-owned later first-package procedure

Run the following only after root assigns the two-VM resource lease. Preparation
can copy many GiB; no actual images were copied during this development batch.

```sh
python3 ci/capability-audit/batch_network_peer_lan.py prepare \
  --package /ABS/EXTRACTED_REPRESENTATIVE_PACKAGE \
  --archive /ABS/ACTUAL_REPRESENTATIVE_PACKAGE.tar.gz \
  --qemu /ABS/qemu-system-aarch64 --output /ABS/PRIVATE_NEW_PEER_DIRECTORY \
  --hdc-port 5558 --vnc-display 41 --peer-port 24680 --subnet 172.27.77.0/30
```

The actual archive's regular file set/content must exactly match the extracted
package, including the candidate launchers. Symlinks, hardlinks and traversal
members are rejected. A package whose launchers were rewritten after archiving
must be repackaged and get a new checksum. Staging checks available distinct
HDC/VNC/data ports, creates a fresh mode0700 control directory under `/tmp`,
and copies the entire package into `listener/` and `connector/`. Every disk,
including userdata, has a separate actual inode and identical initial bytes.
The original package remains unchanged. Source hashes are rechecked after
copying to reject a mixed snapshot. The plan retains actual source/clone hashes
and disk device/inode values. Neither hardlinked disks nor shared writable
backing files are used.

`start-listener.sh` and `start-connector.sh` export fixed per-instance MACs,
serials/UUIDs, HDC ports, VNC displays, distinct private QMP sockets and pcap
paths. They use the existing packaged launcher, default to TCG, and never auto
start during preparation. Root can supervise these two scripts with its actual
boot ownership mechanism and capture process identities, logs, QMP and archive
binding. Port availability checks are not reservations: a later bind conflict
must fail and be preserved. Do not probe the peer TCP port by connecting an
unrelated client; wait using the actual owned QMP/log/guest observations.

After both actual guests boot and root establishes the two HDC connections:

```sh
python3 ci/capability-audit/batch_network_peer_lan.py observe \
  --plan /ABS/PRIVATE_NEW_PEER_DIRECTORY/peer-lan.json --hdc /ABS/hdc \
  --output /ABS/NEW_PEER_OBSERVATIONS --configure
```

The observation helper executes actual bounded HDC commands and retains raw
stdout/stderr, SHA256, host intervals, target and nonce-based guest exit status.
It first reads both `bm get --udid` outputs, kernel boot UUIDs and actual
`ip -o link` MACs. Both UDIDs and boot UUIDs must differ; both actual NICs must
exist. Only after that check, `--configure` brings up the MAC-matched data NIC
and adds its own RFC1918 `/30` address if absent. It does not flush addresses,
change the management NIC, install a default route, or overwrite another
assigned data address. Existing unexpected addresses fail observation. Omitting
`--configure` performs only observation and ping.

The two actual `ip route get` results must be direct through their own data
NIC, with the correct source address and no gateway. Actual interface-bound
ping must succeed, actual neighbors must resolve to the other configured data
MAC, and UDID/boot/MAC identity is re-read afterward. This is kernel networking
candidate evidence only. It always leaves `first_artifact_behavior_gate_passed`
false and never marks distributed capabilities accepted. The root independent
verifier still must bind real QEMU/QMP process identities, current archive and
pcap bytes before using it as part of an actual service test.

## Remaining service and cleanup work

Root must complete and retain these stages on the same newly packaged pair:

1. Observe the real network service's interface/address/link records; configure
   its actual supported Ethernet API if raw kernel addressing alone is not
   advertised to SoftBus. Kernel ping cannot stand in for service readiness.
2. Install separately signed ordinary API26 probes against each actual UDID;
   observe legitimate discovery of the other real device and record raw
   callback IDs. Record actual permission, account and trust state through the
   supported service APIs/UI. If account authentication or peer pairing is
   unavailable, keep this requirement open without borrowing credentials or
   bypassing permission checks.
3. Establish a real authenticated service session between these identities.
   Exchange a root-generated fresh nonce in both directions, retain actual
   endpoint UID/session/peer IDs, payload hashes and callbacks, and independently
   correlate data NIC pcap/guest service/network evidence. A raw TCP/ICMP echo
   or this host's argument fixtures cannot substitute for that service session.
4. Remove only this peer link through the owned QMP NIC/link operation, observe
   actual peer/session-offline and cleanup callbacks, reject replay/late sends,
   then cancel discovery and release sessions/listeners. Check both services for
   leftover peer/task/permission/session resources. Stopping QEMU by itself is
   not service cleanup proof.
5. Undo only the explicit peer addresses when their actual MAC/boot identity
   still matches; retain final route/interface/service dumps. Root stops only
   its two owned QEMU processes after native/service cleanup, waits for exit,
   then removes only the plan's matching UID/inode private QMP directory.
   Failed attempts retain all logs, plan/pcaps and actual cleanup errors.

Do not build or package the remaining five artifacts until the representative
new archive's complete intended runtime gate passes. This batch cannot close
that gate, and no current host check is recorded as a guest test.

## Host checks

`host-tests.json` binds exact inputs and logs. The peer suite exercises actual
rewritten launchers with argument-capture doubles for all three products,
default preservation, both stream endpoints, rejection boundaries, independent
actual tiny host-file disk copies, archive mismatch/links, distinct identity
parsing, and direct-route isolation. Existing kernel-log and accessibility
pointer launcher regressions are also retained. These tests run no VM, HDC,
SDK/native compiler, Docker, or OpenHarmony source/out query.
