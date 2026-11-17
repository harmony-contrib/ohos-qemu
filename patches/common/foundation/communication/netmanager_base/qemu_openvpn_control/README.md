# QEMU native OpenVPN service control candidate

Pinned `netmanager_base`: `9831989d54f490d046a632ab13d309580d2fa710`.
Use `apply.sh --source-root OPENHARMONY_ROOT` after enabling system VPN.
Whole-file hashes reject partial/unknown source changes before mutation.

Only `netmanager_base_enable_feature_sysvpn` together with product
`armv7a_virt`, `arm64_virt` or `x86_64_virt` defines `OHOS_QEMU_OPENVPN`.
Those products send OpenVPN restart/stop to init's real `ServiceControl` API,
instead of depending on the absent `/system/bin/ipsec` wrapper. Restart fails
if the supervisor is not installed/executable, and init rejection propagates
as `NETMANAGER_ERROR`. Other products keep their existing IPsec route.

Success means init accepted a request; it never publishes a connection.
The staged supervisor still requires actual TLS and authenticated TUN readiness.
No new queue, connection lock or wait-for-child-exit is introduced here.
The fixed init implementation's restart helper can wait for its own service
status, which is published immediately after signalling the old supervisor;
that status does not prove process-group cleanup or TLS readiness.

The aggregate recipe does not apply this component yet. It must install the
complete backend and narrow service-control DAC/SELinux policy together.
The host regression compiles the real Update body in QEMU and non-QEMU modes
with explicit init/access doubles, checking rejected starts/stops and preserved
legacy routing. Real identity, status permissions, restart, network traffic and
new-package validation remain required.
