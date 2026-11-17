# M144 custom media document binding

Request a fresh document-scoped media factory through the current browser
interface broker for each custom-player creation. The RenderFrame's cached
factory can outlive the old document until its asynchronous Mojo disconnect
handler runs; immediate media initialization after navigation can then target
the closed old-document endpoint.

Keep the posted main-thread request, renderer/client endpoints, existing
browser document/origin checks, cookie checks and player ownership unchanged.
Do not reset the factory shared by decoders/CDMs. A failed current-document
binding must fail normally rather than retrying on a stale document. The
explicit injected-factory constructor (no broker) retains its original path.

This is a repair candidate. Source/host/native checks are not proof of runtime
closure: package the rebuilt full core, then validate repeated navigation,
actual distinct surface IDs, bridge creation and release on a fresh archive.
