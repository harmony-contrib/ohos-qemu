# Binder connector initialization

Pinned IPC project: `b8d3e96cfcf382c8fae54502679ac8b3d827b428`.
Apply with `bash apply.sh --source-root OPENHARMONY_ROOT`.

Move the existing singleton mutex before every `instance_` read, eliminating
the unsynchronized outer double-check. Allocation and `OpenDriver` failure
still return null and allow the next call to retry. The destructor, atomically
managed driver FD, public ABI, Binder wire layout and permission policy are
unchanged. `GetSelfTokenID` now uses a function-local ioctl result, matching the
kernel's current-thread token semantics and the existing first-token query.
It keeps the same zero-on-failure behavior and class member layout (the retained
unused field is annotated, rather than removed); it does not
cache another thread's token or change token permissions.

Complete pinned/repaired source hashes reject foreign, partial and symlink
inputs before mutation. Compilation and host concurrency fixtures are not
ordinary-app, target-driver or new-package acceptance.

The host query fixture executes the changed query tail under 256 deterministic
two-thread success/success and success/failure interleavings with ASan/UBSan.
Its ioctl/file seams are explicit: it is not a guest token-driver test or TSAN.
