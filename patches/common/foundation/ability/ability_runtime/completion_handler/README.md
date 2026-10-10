# SDK-declared completion handler constructor

Pinned ability_runtime: `6c18fdc9bdef6cfcf5888517cd8ed9448584f6e8`.

The API 26 declaration exports a class with two optional callback fields, but
the pinned NAPI module exports only `AbilityStartFailureCode`. The candidate
adds the missing named constructor. Instances are ordinary JS data objects;
optional callbacks remain undefined until assigned and are not shared between
instances. There is no native allocation, service identity or IPC in this class.
Calling without `new` throws TypeError; failures of NAPI operations return
without continuing. Existing error-code enum registration is unchanged.

The corresponding `JsUIExtensionCallback::SetCompletionHandler` consumes the
ordinary `onRequestSuccess`/`onRequestFailure` function properties; it is not
changed. This does not change startup, permission checks, FA/Stage lifecycle,
IPC, public signatures, or published error-code numbers.

Three real product module translation units compile with the actual pinned
Ninja commands. Host Node N-API runs the exact constructor body, checking
construction, no-new rejection, optional callbacks, mutation, independent
instances, inheritance and 10,000 allocation/GC cycles. Separate ASan/UBSan
injection covers each NAPI failure. Neither test represents Ark, a linked
product library, or real component-start callbacks.

The candidate is selected by the shared pre-build recipe, but not the already
frozen R26 build. The ordinary ArkTS caller compiles against API26 Release.
Both profiles require its raw constructor/field observations in the package
gate, bound to the actual archive, boot, ABI, normal UID and compiled inputs.
Only that exact export can close, not startup delivery or service IPC. A linked
newly packaged module still needs runtime validation; no guest library replacement
or host test can close this audit gap.
