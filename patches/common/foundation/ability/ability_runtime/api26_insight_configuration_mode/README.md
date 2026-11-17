# Configured InsightIntent execution mode export

Fixed ability source: `6c18fdc9bdef6cfcf5888517cd8ed9448584f6e8`.
Register the missing API26 public `ExecuteModeForConfiguration` object through
the existing checked NAPI enum helper and native foreground/background values.
The existing native enum, intent dispatch, callback ownership, permission
checks, errors, IPC and all previously exported objects are unchanged.

This is additive public registration, not a change to an existing API or a
synthetic implementation of intent execution. Exact registration/error tests
and real three-ABI TU compilation do not establish guest query/dispatch or
permission behavior. New packaged ordinary-HAP regular-enum collection and
separate real intent-provider behavior proof remain necessary.
