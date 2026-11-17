# Taskpool thread snapshot publication

Pinned OHOS 7.0 ets_utils: `37cafe4c6d96858e976107d41d4f723adfde4a61`.
R32 ordinary-app runtime returned a `ThreadInfo` with `tid=0` during worker
creation. `workerEnv_` becomes non-null before the worker obtains its real TID;
checking that pointer was neither a readiness gate nor synchronized publication.

Publish readiness with release semantics from the existing worker-created
notification, after runtime/TID/handles initialization. The snapshot acquires
that publication before accessing immutable TID data. Uninitialized workers are
not public thread records; no fabricated TID or waiting/retry is introduced.
Snapshot task IDs under their existing writer mutex, while retaining the worker
lifetime mutex. Make the concurrently updated priority atomic. Task scheduling,
priorities, IPC, permissions, and exported ArkTS property names are unchanged.

The header's original CRLF bytes are preserved by the exact-component helper.
Unknown revisions, partial application and drift fail closed. This candidate is
not in frozen R33; it requires a subsequent rebuilt representative and actual
ordinary-app startup/expansion/task completion/idle regression before closure.
