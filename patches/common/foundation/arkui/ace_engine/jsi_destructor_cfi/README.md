# JSI native callback CFI types

Build23's representative QEMU image reaches SceneBoard after the PixelMap
repair, then aborts inside `JsiJSNativePointerDestructorInterceptor` when an
asynchronous native finalizer invokes the registered destructor. The three
complete native fault records have the same CFI failure and callback stack.

All three JSI binding registration paths reinterpret-cast a destructor taking
`C*` into a callback taking `void*`. The adjacent GC mark callback has the same
parameter erasure. Calling either through the erased function pointer violates
the original function type.

This component stores typed adapters in the existing JSI constructor binding.
Each adapter captures only the registered function address, converts the native
object pointer back to `C*`, and calls the original function through its true
type. GC mark information is forwarded unchanged. Null callbacks remain empty.
The adapters do not own or delete native objects; the original callbacks retain
that responsibility. The existing thread-local binding, reset behavior,
constructor flow, outer three-parameter finalizer, and CFI checks are unchanged.
The global callback aliases and NAPI/Ark callback contracts are untouched.

Both source preimages are from the actual read-only Native capture
`r67-build23-destructor-source02/native`, ACE revision
`e55e178228b9f6388b15d3024e8caf125fa293d7`. The component uses the unchanged
exact apply helper via `apply.sh --source-root ROOT`; packaging can verify the
final state without mutation using `apply.sh --source-root ROOT --require-final`.

The two whole-file changes and complete literal inverses were checked as data.
No source, patch, guard, compiler, host test or shared resource was executed.
The parent must build and boot the new representative QEMU package to validate
native object finalization and the relevant regressions.
