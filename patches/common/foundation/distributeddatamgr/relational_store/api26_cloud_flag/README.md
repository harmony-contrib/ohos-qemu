# CloudExtension Flag export

The pinned embedded JS module exports FieldType and ErrorCode but omits the
SDK's Flag. Add INSERT=0, UPDATE=1, DELETE=2 in the same enum construction style,
and include that same object in the module's existing default export.
These are record operation flags, NOT the different CloudDb RPC request codes.

Only two additive export hunks: existing stub/proxy code, record marshalling,
authorization, service identities and transport are unchanged. No cloud
provider or successful synchronization is invented. NDK/ETS declarations and
native ABI are unchanged; no external dependency or static linkage is added.

Applied by the common phone/2in1 pre-traversal plan. Real product ABC generation and
a host JS-module enum check do not satisfy new-image runtime or cloud-service
acceptance. The complete original typed/NAPI collector must validate the actual
new package. Cloud backend requirements remain independent and unresolved.
