# Network NAPI caller API version

Read the application's target API from the actual NativeEngine behind napi_env
when constructing BaseContext. The fixed runtime sets this from the application's
target version. A Binder calling token is not the NAPI environment's API version.
Decode release-stage digits with the same 1000 modulus before the existing API24
BusinessError comparison. Default/unversioned engines keep the legacy branch;
null environments retain zero. Explicit context version setters remain supported.

No permission, error value, parser or IPC changes. Apply before GN/traversal for
all profiles and ABIs. Complete TU compilation and host doubles are not guest
proof; new-package invalid-argument and permission callers must still pass.
