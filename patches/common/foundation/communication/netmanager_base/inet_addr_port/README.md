# Full SDK network address port

Pinned netmanager_base: `9831989d54f490d046a632ab13d309580d2fa710`.

NetAddress.port is an optional integer in 0..65535, default 0. The innerkit
INetAddr field and both native Parcel writers previously truncated it to uint8.
Use uint16 storage and the existing padded four-byte Uint16 Parcel slot; read
the full Uint32 slot and reject values outside uint16 rather than truncating
malformed IPC. This is not support for an old receiver retaining a wide port;
all image-side consumers must be rebuilt together. No exported OH SDK C ABI,
permissions, routes, family or prefix policy is changed by this component.

Add a strict existing NapiUtils helper and use it for addNetworkRoute and the
add/delete VLAN address paths. Missing/undefined defaults to 0; wrong type,
fractions, non-finite values, negative/out-of-range values and NAPI failures
return the existing parameter error before IPC. VPN standard/extension inputs
use the same helper via vpn_config_arrays/0006 and its existing napi_utils
dependency. Apply this component before those users and before GN generation.

Exact source hashes, double application and compilation are not a connection,
VPN CRUD/restart, tunnel or guest acceptance proof. Validate full-width ports
and default/error behavior in the newly packaged artifact before delivery.
