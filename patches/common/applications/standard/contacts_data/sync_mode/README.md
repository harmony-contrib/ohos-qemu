# API26 ContactSyncMode

The pinned OpenHarmony 7.0 ContactsData source defines the real sync modes but
does not register their enum. Its unused declaration also exports an incorrect
class name and an unrelated member name. The existing JavaScript wrapper and
API26 SDK both require `ContactSyncMode.MODE_INCREMENTAL = 1` and
`ContactSyncMode.MODE_CLOUD_BASED = 2`.

This component registers that declaration and corrects those names. It retains
the native module's existing enum implementation, actual sync operations,
permissions, storage, and constructor behavior. No legacy misspelled exports or
placeholder DTO constructors are added. The common build plan applies this
patch before compilation for both profiles and all three ABIs.

Fresh/repeat patch checks and isolated compilation are not guest acceptance.
The newly packaged image must expose both actual numeric enum members through
the public `@ohos.contact` wrapper; this alone does not attest cloud-sync or
contacts provider behavior.
