# Calendar editor native callback dispatch

Apply after `source_provider` and `event_editor` from ee2748c, before compiling
`//applications/standard/calendardata/calendarmanager:calendarmanager`.
Only calendar_manager_napi.cpp and calendar_manager_napi.h change. Existing
CalendarData ArkTS/HAP bytecode is unaffected.

Pinned framework code posts ModalUIExtension results to UI, and callbacks do
not establish a JS handle scope or guarantee env lifetime. This delta sends
native result data with napi_send_event, opens a handle scope on JS, and uses
an env cleanup hook to invalidate pending work. The hook weakly references the
request and is removed on normal settlement; queued lambdas own no JS values.
Environment cleanup cancels native tokens and releases its hook. Failed event
delivery cancels the request and closes only that session when a live matching
host is available; it cannot settle a Promise after JS delivery has failed.
An unexpected handle-scope failure similarly closes without reporting success.
These shutdown/failure boundaries require fresh-image native runtime validation.

onDestroy immediately invalidates the native generation and UIContent identity
on UI before sending cancellation. Previously queued results become stale.
Closing reacquires the host AbilityContext, checks its current UIContent, and
uses only this request's session id. The pinned CloseModalUIExtension copies an
asynchronous UI task before returning, so holding the native lifetime mutex
through that call cannot reenter onDestroy. Destruction/host replacement never
closes a replacement UIContent. Per-request locks use environment before request
when both are needed; UI invalidation releases the request lock before enqueue.

Exact predecessor and final hashes are in verify_source.py. The earlier
`event_editor` checker deliberately does not accept these new final native
hashes. The parent must update shared final-state/replay recognition for the
composed chain, without widening acceptance to unknown source. This component
itself is idempotent and rejects partial/drifted states.

Host checks execute the actual extracted functions with different UI/JS threads
and enforce that value APIs run on JS within a scope. They exercise cancellation,
errors, synchronous creation callbacks, queued result versus destroy, env exit,
failed delivery, host replacement/expiry, duplicate callbacks and two sessions.
They do not replace complete product-TU compilation, system signing or new
ARM64 phone package UI acceptance. The 82-item ledger remains unchanged.
