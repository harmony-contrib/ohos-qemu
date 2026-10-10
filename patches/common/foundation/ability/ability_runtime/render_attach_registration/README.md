# Renderer publication / attachment ordering (candidate)

Pinned `ability_runtime`: `6c18fdc9bdef6cfcf5888517cd8ed9448584f6e8`.

`StartRenderProcess` runs on a Binder thread, while the authenticated
`AttachRenderProcess` request is dispatched to the AppMgr task queue. A child
can attach before `StartProcess` returns and before `AddRenderRecord` publishes
its PID. That lookup then fails without registering a death recipient.

The shared registration mutex covers spawn through publication and timeout
registration, and the attachment lookup through obtaining its shared record.
It is released before observer / renderer callbacks and on spawn failure.
Timeout registration precedes cancellation, avoiding a late timeout after a
successful attachment. UID allocation retains its existing independent lock.

No SDK, Binder encoding, caller identity, sandbox, permission, UID allocation,
or diagnostic event contract changes. This does not repair failed
`AddDeathRecipient`, nor prove the cause of the historical intermittent Web
exit-callback failure. That failure remains open pending packaged guest tests.

Candidate only: not yet wired into packaging. Require actual service compile,
registration race / early-return regression, and newly packaged Web lifecycle
validation before enabling or claiming closure.
