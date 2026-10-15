# Native child-process arguments

Fixes OpenHarmony 7.0 issues reproduced using the SDK C API independently
of Rust bindings:

1. `OH_Ability_GetCurrentChildProcessArgs()` returned null inside a successfully
   started FD child. The header-defined singleton was duplicated across
   `libchild_process_manager.z.so` and the symbol-localized `libchild_process.so`.
   One exported, out-of-line `GetInstance()` now owns the state in the manager
   library. Both libraries must be rebuilt together.
2. A 150 KiB ASCII argument became 300 KiB when serialized as UTF-16, exceeding
   Parcel's default 200 KiB capacity. Both `ChildProcessArgs` and
   `ChildProcessInfo` now provision a bounded 512 KiB capacity, covering the
   startup request and subsequent child-info reply without changing the wire
   format or the global Parcel default. A larger existing capacity is preserved.
   The C API rejects entry parameters above 150 KiB with `NCP_ERR_INVALID_PARAM`;
   both serializers enforce the same byte limit.
3. API26 permits destroying a null configs pointer as a successful no-op, but
   the release implementation returned 401. Null destruction now succeeds;
   non-null destruction still releases the object. The isolation-mode setter
   rejects values outside its two declared enum values before changing config.
   Newly packaged runtime validation is required for these config boundaries.
4. Native startup callbacks were retained only after dispatch, so a notification
   arriving during dispatch could finish before retention and leave a permanent
   reference. Both Create entrypoints now retain before dispatch and release on
   immediate failure. A terminal notification atomically takes the one-time
   callback, releases manager retention and keeps the object alive while calling
   user code without holding a mutex. Null child objects and proxy-allocation
   failure report `NCP_ERR_INTERNAL` exactly once and release retention. Repeated,
   concurrent and reentrant notifications cannot deliver another callback or
   allocate another proxy.

Apply with `./apply.sh --source-root /path/to/openharmony`. Both complete device
profiles and the Docker source-build runner apply this component automatically.
The component does not change device eligibility or child-process count limits.
Patch 0004 accepts only the fixed revision and the exact post-0003 sources;
unknown source bytes, symlinks and a partially applied lifecycle patch are refused.

The supplemental host regression compiles the actual fixed callback and manager
translation units and the two extracted Create functions with ABI shims:

```sh
LC_ALL=C LC_CTYPE=C LANG=C python3 ci/capability-audit/batch_system_child_lifecycle.py \
  --output /tmp/ohos-child-lifecycle-evidence
```

It reproduces seven baseline failures, checks 17 repaired scenarios under
ASan/UBSan and repeats 32-thread terminal-notification contention 20 times.
Apple clang does not provide LeakSanitizer on this host; actual manager retention
is checked using intrusive strong-reference and object-lifetime counters. The
host shim does not exercise AppMgr, AppSpawn, kernel identity or a real guest.

Run the [C API regression](../../../../../../ci/native-child-process/README.md)
against the first newly packaged artifact before building the rest of a release
matrix, as required by the project's `AGENTS.md`.
