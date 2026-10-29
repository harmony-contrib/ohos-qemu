# Restore the declared ContinueState export

Only registers the existing API 26 enum with checked NAPI calls. Values come
from the native mission_info.h contract; UNKNOWN/MAX remain internal.
No SDK signatures, native enum values, error codes, privilege checks, IPC,
mission state transitions, persistence or peer transport change.

Applied by the common phone/2in1 pre-traversal plan. Host fixtures
and read-only product TU checks do not demonstrate new guest runtime closure.
The unchanged complete typed/independent-NAPI enum collector must validate
this export in the actual new packaged image. No backend behavior is closed.
