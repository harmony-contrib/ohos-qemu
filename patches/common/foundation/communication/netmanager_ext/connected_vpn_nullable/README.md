# Connected VPN empty state across private IPC

Pinned netmanager_ext: `8c41289750820fb2ddb347b1205cee9a7b527388`.
Apply after `always_on_vpn` with `apply.sh --source-root OPENHARMONY_ROOT`.

The service already returns success with no configuration while disconnected.
The generated non-null Parcelable proxy rejected that result with internal IPC
error 5 before the existing NAPI undefined conversion. Represent this private
result as a zero-or-one list. The native client keeps its public signature,
returns null for the empty list, and rejects multiple or null entries. Active
configuration values and service errors pass through. Permission/account checks
and locking remain on the service path before reading the connection.

Rebuild the generated proxy, stub, service and client together in every package.
The private wire changes at that existing method; no mixed old/new image is
supported. The ArkTS declarations, permission rules and public native client
signature stay the same. Test mocks match the regenerated service interface.

The candidate compiled all four real translation units on all three ABIs.
Compilation does not establish active VPN, account isolation, packet transport,
permission boundaries, teardown or complete new-package acceptance. A new full
representative gate remains required before building the other five packages.

The connected application list also includes the API10 single-connection slot.
Retain its validated bundle owner in the existing immutable connection field,
which also fixes the previous empty owner reported by Prepare. Read owner,
current user and connected state under the existing connection lock. Merge
connected multi-VPN entries once per nonempty bundle and ignore other users.
The follow-up service TU compiled again for all three ABIs. Real no-ID and
multi-ID callers, permission/account boundaries and packet transport still
require newly packaged runtime validation; no host result closes that gap.

The connected system configuration is also scoped to the calling account,
using the existing OS-account lookup and the connection owner under the same
shared lock. A permitted caller in a different account sees no owned system
configuration. This does not grant access to another account or alter profile
permissions. The real service TU and subsequent guest boundary tests must use
this final source hash, rather than an earlier candidate's compile receipt.

The application-list system API now shares the existing CheckIpcPermission
path with the system-configuration getter. Real ordinary-caller diagnosis
returned 201 where this system API declares 202. The shared check rejects a
non-system caller with 202 before evaluating MANAGE_VPN, then preserves 201
for a system caller without permission. No token or process grant is added.
The fourth patch again compiled the actual service TU for all three ABIs;
new-package permission and lifecycle validation remains required.
