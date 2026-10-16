# Calendar GetEvents async ownership candidate

This separate component changes only `calendarmanager/napi/src/calendar_napi.cpp`
and `calendarmanager/napi/src/napi_queue.cpp`. The current original bytes were
exported by root into the frozen `r52-Calendar-filter-NAPI-source-01` host
directory. It requires the fixed upstream revision and eight unchanged native
dependencies, including the complete installed editor dispatch pair. It does
not modify that component, Calendar Main, HAP metadata, signing or permissions.

```sh
bash patches/common/applications/standard/calendardata/filter_async_lifetime/apply.sh \
  --source-root /path/to/private/full-source
python3 patches/common/applications/standard/calendardata/filter_async_lifetime/verify_source.py \
  --source-root /path/to/private/full-source --require-patched
```

The installer verifies the complete original or complete successor state,
stages both exact postimages, and restores all predecessor bytes/modes if a
replacement or final verification fails. Unknown/mixed inputs and symlinks are
rejected. Its handled-failure rollback is not a power-loss filesystem
transaction. The reviewable original patch uses zero context; the test replays
it with `git apply --unidiff-zero` and verifies both complete output hashes.
Installation uses exact postimages, not relaxed patch context matching.
`calendar_napi.cpp`'s postimage is gzip/base64 encoded to preserve an untouched
whitespace-only original line byte-for-byte; the decoded SHA is mandatory.

GetEvents now validates/unwraps the Calendar and EventFilter on the JS thread
and copies their native `shared_ptr`s into the request. Its worker uses those
native snapshots only. There is no retained raw EventFilterNapi/CalendarNapi
pointer and no filter `napi_ref` to leak, delete early, or access from a worker.
Malformed/null wrappers and a valid wrapper without a native filter fail;
the real zero-argument no-filter overload remains available. The API caller
does not need to retain its filter until the operation finishes.

The queue's existing shared context/execute/complete ownership retains the
native snapshots until completion or synchronous submission failure. The new
environment hook owns a separate token containing shared environment state and
a weak ContextBase; it never owns a raw async-context address. Normal completion
unregisters/deletes that token. If unregistration fails, the environment still
owns the token until teardown, without keeping a finished request alive.
Teardown marks the environment dead and clears the context's NAPI environment;
queued worker/complete callbacks then skip JS/NAPI work. Pending native owners
are retained through the complete callback; work is never prematurely deleted
while a worker can still execute. A null complete-callback environment also
suppresses NAPI access and leaves any uncalled hook token environment-owned.

Checked promise/resource/work/hook creation and queue failures now throw when
no callback/promise handle can be retained, or reject the original promise /
call the retained callback once with an error. An enqueue failure no longer
returns `undefined` while losing an unresolved promise. Cancellation carries
a nonzero internal error. BusinessError's numeric `code` is attached as a
property; it is not passed as the string-only `napi_create_error` code argument.
Pending JS exceptions are preserved, and callback invocation uses a real
undefined receiver. No user callback runs under a new lock. The thirteen
existing queue callers all return its result directly; none relies on the old
lost-promise behavior or post-return reference cleanup.

```sh
LC_ALL=C LC_CTYPE=C LANG=C PYTHONDONTWRITEBYTECODE=1 \
  python3 ci/capability-audit/test_batch_system_calendar_filter_async_lifetime.py -v
```

These checks execute the exact patch/installer and source-constrained ownership
models. They do **not** execute C++, an OHOS NAPI engine or a guest. Model
schedules cover original GC/UAF and lost-promise counterexamples, successful
ownership, concurrent requests, failure/cancel, callback reentry, environment
exit and a failed hook removal. Native sanitizer execution, real product
TU/CFI linking, actual engine teardown ordering and a new-package API/lifecycle
test remain required. No finding is closed by this source candidate.
