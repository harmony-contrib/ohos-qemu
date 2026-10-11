# EffectSuggestionStatus data record

Pinned camera_framework: a421fc5b11593deb06a1b3928ebdf81b2655870b.
The API 26 declaration exposes a constructible data class with caller-owned
`type` and `status` fields. Native SetEffectSuggestionStatus already parses those
fields; no module initializer registers the constructor.

Register a real NAPI class and return the actual new instance. No invented field
defaults, shared objects, camera service calls, permission changes or simulated
effect support. Existing native setters and validation remain unchanged.

This patch is separate from depth enum repair and must remain repeatable in the
same source tree. Host/three-ABI compilation and new-package typed constructor
tests are required; class registration alone does not close camera behavior.
