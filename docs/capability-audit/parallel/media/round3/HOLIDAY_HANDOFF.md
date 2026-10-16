# Batch 3 handoff

All 7 requirements remain open. This batch is based on bb34c6f7f1534be701e64337f0708e49f6b50bc9.
The existing public native Capturer and real grant-dialog ETS caller are already
separate commits. Parent reports actual API26 native compile/link for three ABIs
and HAP02 compilation passed; no representative-image runtime acceptance yet.

KnowledgeContent now has a real service producer for the optional trusted
all-day ICS resource, same-MediaLibrary-DB transactions/upgrade/open/refresh,
real field-7 asset/date relationships and replacement/removal, parameter error
for NONE, omitted-count streaming/budget semantics and specified weighted
ranking/display. Input/parser/limits, absence/error policy and ownership/lifetime
are in the component README. No holiday dates or AudioVivid metadata are invented.
The observer uses cancellable five-second fixed-path polling, managed join and
weak RDB ownership. Concurrent Stop and worker-reentrant Stop cannot self-join;
external Stop waits for in-flight import before releasing the service DB.

The four new approved actual upstream targets are:

- foundation/multimedia/media_library/services/media_rdbstore/include/rdbstore/knowledge_holiday_index.h
- foundation/multimedia/media_library/services/media_rdbstore/src/rdbstore/knowledge_holiday_index.cpp
- foundation/multimedia/media_library/services/media_rdbstore/src/rdbstore/medialibrary_rdbstore.cpp
- foundation/multimedia/media_library/frameworks/innerkitsimpl/medialibrary_data_extension/BUILD.gn

The overlay also updates the previously owned knowledge_content_napi.cpp,
knowledge_content_query.cpp/.h and media_asset_rdbstore.cpp. Its exact manifest
covers the full 13-source Knowledge stack; cumulative media ownership is 24
upstream targets. It adds the real producer to the actual GN target with the
existing OpenSSL shared dependency. No non-existent media_rdbstore BUILD is used.

Parent integration order: old complete photo stack -> knowledge_content ->
knowledge_holiday_index; include this component in frozen source/input hashes.
Compile full new producer TU plus changed NAPI/query/helper/service TUs, actual
headers and link into the real media service and photo module. Wire optional
real trusted asset at the fixed path with external hash/provenance; no resource
is valid no-data, unsupported/invalid resource retains the preceding good version.
On a new package test populated assets/analysis/nicknames, actual trusted calendar
versions, ordinary/system/READ-role identities, current account, counts/aliases/
relationships, asset delete/hide/trash, resource replace/remove, cursor snapshot
and active permission revocation through the public API and real service Visitor.

Host evidence: holiday-host-07.log has 10 passing tests. Actual producer TU and
actual query/cursor functions execute under ASan/UBSan. Underlying NativeRdb/NAPI/
permission interfaces are controlled adapters; SQLite persistence/transactions
and OpenSSL hash are real. Tests cover invalid calendar/I/O/permissions/rollback,
legacy DB, Unicode/folding/duplicate UID/limits, leap/cross-year/exclusive end,
real photo joins/deletion, one-read-snapshot resource switch, directory absence,
weak lifetime, cancel/join/reopen/in-flight/reentrant Stop, and exact installer
repeat/forward/partial/symlink guards. Earlier failed logs are preserved. The 33 original Knowledge/photo guards pass
in holiday-prior-guards-01.log. git diff whitespace diagnostics are confined to
six intentional single-space unified-diff context lines in the review patch;
the parent owns its precise .gitattributes exception.

Remaining per ID:

- KnowledgeContent: actual product compile/link, public populated data and service ACL/account/revocation/runtime acceptance.
- Audio input: real root D1p random challenge -> ordinary granted MIC public Capturer D0c PCM correlation/rate/timestamps/lifecycle; denial, revocation, interruption and other input modes remain.
- Recording: public AVRecorder actual audio/video file, independent decode/challenge/PTS/pause/stop/release/recreate and permissions; next media batch.
- Interrupt/haptic: real competing focus callers, interruption/resume and synchronized playback/vibration; next candidate batch.
- Codec: parent reports actual two AVC TUs passed; representative-image encode/decode/surface/offset/EOS/PTS/bitrate/IDR matrix still required.
- AudioVivid: actual libAudioVividMetaBuilder.z.so algorithm/metadata implementation with provenance/license and matching factory/destructor ABI not supplied; parent asked user. No legitimate implementation identified in bounded fixed source; keep actual unsupported behavior and continue other items.
- Video-dependent pipelines: ordinary real recording/screen capture/transcoding, independent pixels/audio/timestamps and cancellation/recreate/permissions still required.

No new SDK build, Docker build, package, QEMU or HDC was started by media. Parent
retains heavy-resource lease and one representative package runtime gate before
building remaining artifacts.
