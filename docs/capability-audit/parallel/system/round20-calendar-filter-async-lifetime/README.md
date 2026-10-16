# Calendar filter async lifetime handoff

The new independent `filter_async_lifetime` component repairs the raw wrapper
ownership defect identified in round19 and its necessary queue failure paths.
Only two upstream C++ files change. The frozen eight-file export was provided
by root, and every exported source's host SHA matches its recorded before/after
SHA. The installed editor dispatch pair is additionally pinned as an unchanged
dependency. No active source/out, Docker, SDK, native compiler, VM or HDC was
accessed by this agent. The running representative fullbuild02 is untouched.

The original GetEvents parser unwraps an EventFilterNapi pointer, creates a JS
reference, then deletes that reference immediately after queueing. The worker
later dereferences that raw wrapper. A temporary filter that is finalized in
between can therefore leave a dangling wrapper. The new parser validates the
Calendar receiver through its existing ToJson/instance check, obtains both
native shared owners on the JS thread, and stores them in GetEventsContext.
The worker never unwraps or dereferences a JS wrapper. It needs no filter NAPI
reference, and ordinary callers need no extra retention workaround.

The queue previously ignored promise/resource/work creation status and replaced
a promise with `undefined` when enqueueing failed. Its cancellation path changed
the status but could retain error code zero. The new queue preserves/rejects
the original promise or calls the callback once; failure to retain a callback
or create a promise propagates synchronously. Numeric BusinessError codes are
attached using `set_named_property`; existing pending JS exceptions are kept.
All thirteen fixed queue callers return the queue's result directly. Callback
setup failure can call a retained callback synchronously; the source inspection
shows no native caller ownership that relies on deferred callback dispatch.
Actual JS callback reentry remains a native/runtime validation gate.

Environment teardown is handled with a separate cleanup token, shared atomic
alive state and a weak request context. No hook holds a raw AsyncContext. A
failed hook removal can leave only the environment-owned token until teardown,
not a pointer to freed request storage. A live completion removes the hook and
releases self/callback refs and work on the JS path. After a cleanup hook or a
null completion env, the code suppresses NAPI access; the native snapshots stay
owned until the complete callback releases the request. It does not free a
running worker's data or call delete_async_work before completion.

`host-tests-07.log` contains the final thirteen passing light tests. They run
actual patch application/whole-file hash verification, transaction rollback,
unknown/mixed/dependency checks, and executable ownership/scheduling models
constrained to the retained original and changed C++ source. The models are
explicitly **not C++ execution or engine emulation**. Their original-source UAF
counterexample is a model exception after wrapper finalization, not an ASan
crash from the original binary. Their queue counterexample exposes the lost
promise state. Worker/complete/env/cancel/ref-release behavior still needs real
native execution; passing a model is not an API capability closure.

All intermediate logs are retained. The first patch replay failed because the
original napi_queue.cpp has no final newline and the generated patch lacked its
explicit marker. After fixing that serialization, host-tests-02/03/04 passed.
host-tests-05 preserves a failed experiment that removed whitespace-only patch
context; that did not exactly match an original whitespace-only source line.
The final zero-context review patch is replayed with its explicit supported
Git option and the output SHA must match both complete postimages. The actual
installer still requires exact full-file predecessor bytes. An encoded exact
postimage preserves that untouched original whitespace; no whitespace gate or
unknown-source guard is disabled. host-tests-06/07 pass, with 07 covering the
final encoded-payload installer too.

Root's next batch should apply the component to the isolated next tree only,
compile both full actual product TUs and CFI/LTO link the real
`//applications/standard/calendardata/calendarmanager:calendarmanager` target,
and run actual native sanitizer / OHOS engine tests for temporary-filter GC,
malformed/null receiver/filter, queue construction/enqueue failure, callback
and Promise completion, cancellation, simultaneous requests, callback throw
and reentry, environment exit during work, and hook-removal failure. In
particular, verify the real Ark NativeEngine complete-callback delivery and
work/reference cleanup order on env teardown; the public API says complete is
called for finished/cancelled work, while the model assumes that contract.

Then exercise the ordinary CalendarManager API in the next representative new
package, along with the Calendar Main/Editor boundary cases. The current
fullbuild02 image does not contain this private source candidate. SDK/native
compilation, runtime safety, signing/BMS and the first-package gate remain
unpassed here. The original audit ID stays open; no ledger was changed.

Reminder delivery is separately owned by root, which has now identified the
real notification-service CalendarAlerts consumer. This batch adds no new
reminder producer and does not replace that real chain with a local timer.
