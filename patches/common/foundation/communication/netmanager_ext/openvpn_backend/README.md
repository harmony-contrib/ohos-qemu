# Native OpenVPN supervisor and TUN bridge under preparation

The sources in `files/` address the absent system OpenVPN process backend.
They are not yet installed by the full QEMU recipe. The fixed OpenVPN dependency
alone does not provide this service.

The supervisor uses init's actual `netsysnative` UID 1098, obtains the active
configuration through `NetworkVpnClient`, owns the OpenVPN process group and
uses a private management Unix socket. It accepts management events only from
its exact exec child. It publishes CONNECTED only after both a real successful
management state and readiness from that child's TUN bridge. Signals, child
exit, malformed states and disconnects terminate the owned process group and
remove session files. Password files are private to the session.

The profile policy accepts data/TLS/network directives and inline credentials.
It rejects daemonization, identity changes, nested configuration, arbitrary
credential paths, management/TUN endpoint replacement, executable hooks,
plugins and log/PID/replay-file outputs. The private askpass path is appended
only after validation. The supervisor also keeps the authenticated bridge's
readiness connection open, so a bridge exit terminates the owned session.

The bridge consumes OpenVPN's negotiated configuration and AF_UNIX packet
socket, requests the real TUN descriptor from netsys, verifies TUN/NO_PI and
signals readiness to the supervisor. It never fabricates a connection state.
The management parser was checked against the actual fixed upstream formatter,
including its different IPv4/IPv6 field counts.

The descriptor receiver bounds ancillary reads by the actual supplied buffer
and closes all delivered descriptors when extra/truncated data is rejected.
Its real Linux socket regression passed 512 messages with ASan/UBSan and
descriptor-count checks. The complete updated supervisor/bridge also compiled
and linked against the real OHOS ARM64 compiler, headers and client library.

`BUILD.gn`, the init configuration and a service-specific DAC file are staged
drafts. The fixed GN parser accepts the draft. The action waits for real musl
and OpenSSL targets, builds the locked upstream source in a dedicated generated
directory, and preserves previous successful outputs on replacement. None of
these draft files is installed by the aggregate recipe yet. Narrow SELinux
service-control policy, complete checked source installation and netsys start/
stop/error propagation remain required before activation.

The supervisor and bridge have compiled and linked with the actual ARM64 OHOS
compiler, source includes, generated IPC headers and VPN client library. That
is not a running VPN proof. Remaining work includes the QEMU-only GN/init and
netsys start/stop wiring, checking the profile policy against the real upstream
configuration parser, negotiated DNS
and full IPv6/routing behavior, restart/multiple-owner lifecycle, and actual
new-package TLS peer traffic and failure/role/account boundaries. None of the
three outstanding VPN requirements is closed by these sources.
