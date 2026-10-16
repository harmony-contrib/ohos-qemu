# Native side of the QEMU OpenVPN broker

Apply after `qemu_openvpn_control`, together with netmanager_ext/openvpn_broker
and all final qemu_openvpn sources. The three exact files are the existing
SystemVpnWrapper implementation and MultiVpnManager header/implementation.
The existing QEMU product/sysvpn define gates this path; no new public IPC or
broad permission is added. The existing UID whitelist and NETSYS_INTERNAL
permission check still protect ProcessVpnStage.

Start ensures init START without restarting an existing broker. Authenticated
private frames bind each generation to an owner, unique interface and real
broker/worker PID+starttime. Normal STOP affects only the matched worker;
transport ambiguity rolls back only its capability, and an explicit rejected
start never stops an existing session. The dedicated inherited TUN listener
selects a descriptor by generation and exact process identity, verifies the
actual kernel interface and never uses the global latest interface. Existing
legacy tunfd/multivpnfd consumers retain their protocol.

Dead-broker recovery additionally requires exact owner identity, proof that
all original process groups have exited, and a new broker's completed locked
credential cleanup before accepting the old nonce's ENOENT response. See the
paired ext README and the network integration contract for init/SELinux and
native regression commands. Parent owns those shared installation files.
