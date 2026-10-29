# API 26 photo enum contracts

The pinned media_library source registers PhotoRiskStatus, AppLinkState,
LivePhoto4dStatus and DeepOptimizeState only in UserFileManager, although the
API 26 SDK declares them in PhotoAccessHelper. Register the missing six public
enum objects there, checking every NAPI operation. Use the native enum values
and the existing AppLinkState 0-based wire table, not substitute provider results.

PhotoAccessHelper's LivePhoto4dStatus must expose LIVEPHOTO_4D, not the old
UserFileManager table's FOURD_LIVEPHOTO spelling. The old module is unchanged.
CoverUriSource exposes DEFAULT_COVER=0 and MANUAL_COVER=1; normalize the native
local/cloud/pending manual distinctions only at the existing JS getter.
Native storage, IPC, system-app authorization, Photo operations and unknown
stored values are unchanged. ThumbnailVisibility uses its native definitions.
The public JS wrapper already forwards the other four enums, but also needs
explicit CoverUriSource/ThumbnailVisibility forwarding; 0002 preserves the
real native object identity and does not construct replacement enum values.

Applied by the common phone/2in1 pre-traversal plan, before fresh GN generation.
Host sanitizer fixtures and real product TU checks do not demonstrate new
archive runtime closure or photo provider functionality. The complete original
typed/NAPI regular-enum collector must validate the new packaged module.
