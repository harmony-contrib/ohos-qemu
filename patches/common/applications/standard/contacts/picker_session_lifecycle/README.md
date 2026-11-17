# Contacts picker session ownership

Pinned source: `applications/standard/contacts` at
`65de33df8d6d7aaa5797a5625ed0e5938e5cb050`. This component changes six
business files only; the separate source_provider metadata, all manifests,
bundle identity, request permissions and signing profile remain untouched.

Each UIExtensionContentSession now owns its LocalStorage, presenter, callbacks,
metrics interval and display/window listeners. Account-query completion checks
that same lifetime before opening content and uses the request's userId, so a
later request cannot change an earlier request's account check. Window creation,
resize, content loading and show completion cannot resume setup after destroy;
owned listeners are detached before the owned subwindow is destroyed. Repeated
destroy is safe and an older destroy cannot remove a newer global fallback.

WorkerWrapper's fourth scope argument is optional. Its original three-argument
path is unchanged. Cancelling one scope clears only its callback, including while
audit logging awaits, without terminating the shared worker. Callbacks settle
once; taskpool queries and searches have generation checks and attempt cancellation
only on their own tasks. Query rejection now reaches the resultCode failure path
instead of leaving an async Promise executor pending forever.

The real picker still queries contacts, uses the original selected-contact DTOs,
Want URI/IDs, 100-item pickerData/index/total batches, resultCode 0 success,
resultCode 1 cancel and existing 401 parameter error. Backend/transport failures
return nonzero -1 instead of manufacturing success. Cancellation preserves the
original default-selection result and invalidates the previous selection query;
empty defaults need no database request. Result delivery captures the original
session; retrying a rejected terminal delivery never sends the chunks twice.

Page callbacks and subscription creation are fenced across disappear/reappear.
Selection emitter IDs and click handlers belong to individual presenters/pages;
only their own event callback is removed. Avatar completion checks item reuse.
The ordinary Contacts import UI publishes an unaddressed VCARD_SHARE event; an
independent public picker does not subscribe to that authority-free close signal.

Apply `source_provider` then `picker_session_lifecycle` on a private checkout;
the two components have disjoint exact target sets and can both be replayed.
`test_batch_apps_provider_lifecycle.py` runs 38 scenarios against extracted actual
classes/page methods with deferred host adapters, plus full-stack replay and
drift rejection. These tests do not execute ArkUI, a database provider, a HAP or
a product NAPI caller. The root must compile with the full official product SDK,
verify the actual ABC imports, install with the existing OS policy and validate
all public picker overloads/permission boundaries/chunk error mapping in a newly
packaged image. Save/edit-contact and MeeTime screens retain their other existing
presenters; this component does not claim to repair all Contacts application flows.
