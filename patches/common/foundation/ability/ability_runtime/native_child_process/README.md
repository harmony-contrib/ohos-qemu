# Native child-process arguments

Fixes two OpenHarmony 7.0 issues reproduced using the SDK C API independently
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

Apply with `./apply.sh --source-root /path/to/openharmony`. Both complete device
profiles and the Docker source-build runner apply this component automatically.
The component does not change device eligibility or child-process count limits.

Run the [C API regression](../../../../../../ci/native-child-process/README.md)
against the first newly packaged artifact before building the rest of a release
matrix, as required by the project's `AGENTS.md`.
