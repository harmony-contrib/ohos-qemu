# Fixed OpenVPN OHOS build candidate

This is a source-backed dependency for the missing system VPN backend. The
upstream archive is fixed in `scripts/openvpn_source_lock.json`. The port
recognizes OHOS and preserves its libc `sockaddr_storage` while isolating the
incompatible duplicate Linux UAPI declaration. No transport state is synthesized.

After preparing the corresponding fixed OHOS musl/OpenSSL outputs, build one
architecture with `scripts/build_openvpn_ohos_in_docker.sh arm64_virt` (or
`armv7a_virt` / `x86_64_virt`). `OPENVPN_SOURCE_ARCHIVE` selects the exact
checksum-verified archive and `OPENVPN_ARTIFACT_OUTPUT` must be a new path.
The wrapper freezes its recipe and mounts OHOS source/output read-only.

The candidate has compiled and linked for ARM64 with the pinned OpenHarmony
compiler, generated musl sysroot and generated OpenSSL headers/libraries. Its
interpreter matches existing OHOS programs. Neither that compilation nor the
legacy TUN packet diagnostic establishes a working system VPN backend.

This dependency is not yet installed by the QEMU package recipe. Integration
must supply a real native service bridge, process ownership, negotiated
configuration and connection state, actual peer traffic, teardown and failure
handling. Do not claim getter or aggregate VPN closure until a new packaged
guest proves those behaviors, including roles, accounts and multiple callers.
