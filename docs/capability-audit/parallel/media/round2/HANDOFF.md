# Media round 2 handoff — 2026-10-16

All 7 requirements remain open. Host regressions and product TU compilation do
not close a requirement. Parent owns the frozen integration, representative
package/runtime gate and subsequent five packages. No heavy build, QEMU, HDC or
container mutation was started by this agent; only bounded read-only source
queries and local single-process host checks were used.

| Requirement | Prepared implementation | Required acceptance / implementation still missing |
| --- | --- | --- |
| KnowledgeContent | Native static API, real account VISITOR bound queries; Photos/AnalysisAlbum/AnalysisPhotoMap/nickname relations, aliases, distinct asset counts and real weighted sampling | Actual 4 TU/NAPI link; populated guest index/update/delete/identity/revocation/account tests; NONE/HOLIDAY producer and canonical default/ranking/display contracts |
| Audio capture and dependent pipelines | Complete blocking reads, real writable offset range, Stop generation fence, cancel rejected queue buffers, Release after active reads; explicit real ALSA capture route plus external PCM producer | New package public Capturer challenged PCM and its permission/lifecycle/interrupt boundaries; MIDI/voice/playback-capture dependencies each still need their own actual behavior |
| Recording input backends | AVC offset/surface fix and audio capture integrity/input route | Actual AVRecorder audio/video input to independently decoded file, PTS, pause/resume/recreate/denial |
| Audio interrupt/haptic renderer | Existing real AudioHaptic/renderer path preserved; no synthetic focus callback | Competing real callers, interruption/resume and synchronized vibration/output |
| Codec base | Real AVC input geometry/stride/offset/UV-tail validation and rejected-surface release | New package actual default codecs, output content, EOS/IDR/bitrate and failure/recreate regression |
| AudioVivid | Missing external dependency identified; no replacement stub | Real licensed algorithm/metadata builder and its runtime integration/semantic output verification |
| Encoder dependent pipelines | Shared AVC repair, input route preparation | New package screen capture/recording/transcoding and dependent producer/output content/PTS/lifecycle |

Commits, in order:

- `11d48c0e8d50bd9213a2b732afff41824bd14e1b`: AVC input integrity (previous round).
- `7e3d63a`: native KnowledgeContent real-data candidate.
- `a68de06e01438e00d8c4494c1c8d04352dbaca1a`: audio capture data/lifecycle integrity.
- `1b71b81d6dbabb6eff6a0d897638abefee0789ff`: real capture-only ALSA route and guest producer.

Integration order: old AVC stack → avc_surface_layout → audio_capture_integrity;
old complete photo/record/ResultSet stack → knowledge_content; old audio driver
0001–0007 → capture_loopback. Parent kernel/adapter JSON/launch changes use card0
AudioPCI render, card1 QemuCapture device0/sub0 capture, device1/sub0 producer.
Precise 20 owned upstream paths are in result.json and each component manifest.
Only device/qemu/common/virt_full/audio_alsa/vendor_capture.c is the delegated
device exception. No other device, kernel, JSON, launch or shared probe was edited.

Host evidence: 8 real SQLite query/weighted-selection tests, 4 exact installation
tests and 21 prior photo regressions; 2 capture integrity tests exercising 40
actual module/filter scenarios with ASan/UBSan; 6 ALSA tests exercising actual
JSON/selector/read/open/vendor/capacity source with ASan/UBSan; 1 whole diagnostic
C/CLI test with controlled ALSA. Successful logs are knowledge-host-01,
knowledge-install-01, knowledge-prior-guards-01, audio-integrity-host-02,
alsa-capture-host-04 and alsa-inject-host-02. Initial host portability/patch-context
failures remain in earlier logs. Controlled dependencies are function regressions,
not an emulated input backend or runtime capability evidence. Parent reports the
two full capture C++ product TUs compiled successfully; parent keeps that evidence.

Actual SDK contract confirmed in fixed interface/sdk-js/api/@ohos.file.photoAccessHelper.d.ts:
KnowledgeContent static getRelatedEntity(topic:string, context:{topicField:FieldType[]},
option?:{rankingMethod?:RankingMethod,recommendationCount?:int,suggestionFields?:FieldType[]})
returns Promise<Entity[]>; Entity is {id:string,name:string,field:FieldType,alias:string[]}.
getSearchSuggestion accepts 1–7 SearchSuggestionType values. Both methods are
system-only and require READ_IMAGEVIDEO; declarations specify errors 201/202,
13900020 for related-entity parameters, 23800151 for suggestion scenarios and
23800301 for internal failure. FieldType spans NONE0, PEOPLE1, LABEL2, CITY3,
YEAR4, MONTH5, DAY6, HOLIDAY7, MEDIA_TYPE8. RANDOM_VOTE is the sole ranking value0.
The fixed declarations provide no default count, weighting formula, NONE wildcard
meaning or suggestion display concatenation rules. Current default10, weighted
without-replacement and space-joined display are unverified choices, not canonical
compatibility findings. Returning internal error for NONE/HOLIDAY is an incomplete
candidate behavior and **does not implement or complete those declared fields**.
Primary-domain exact-term searches yielded no matching external implementation or
detailed contract; an empty search is not proof that an implementation cannot exist.

Real persisted-data producer/maintenance paths found in fixed media_library:
services/media_analysis_data_manager/src/controller/media_analysis_data_controller_service.cpp
(PAH_CREATE_ANALYSIS_ALBUM), its media_analysis_data_policy.cpp system+write policy,
frameworks/innerkitsimpl/medialibrary_data_extension/src/photo_map_operations.cpp
(real AnalysisPhotoMap insert), and attribute/nickname/portrait_nickname_repository.cpp
(real alias insert/delete). vision_db_sqls*.h defines AnalysisAlbum/PhotoMap indexes;
vision_portrait_nickname_column.h defines the unique (album_id,nick_name) index and
album-delete trigger. The candidate reads these real tables, never a shadow catalog.
Automatic semantic analysis generation remains unproven on QEMU and must be exercised
through the actual producer, beyond privileged fixture writes.

A further real holiday component was found: base/global/i18n/frameworks/intl/
include/holiday_manager.h and src/holiday_manager.cpp expose HolidayManager(path),
read actual ICS VEVENT DTSTART/DTEND/SUMMARY/RESOURCES data, and query real holiday
items by date/year. This is an existing parser, **not** a media HOLIDAY index
producer or a packaged calendar data source. Bounded checks found no .ics files
under base/global/i18n, applications/standard/photos or vendor/ohemu/virt. Next
round can assess a real authorized calendar/ICS producer and region/date/index
mapping; it must define stable identities and deletion/update behavior rather
than hardcode dates or return empty arrays as capability success.

AudioVivid loader: foundation/multimedia/media_foundation/src/capi/native_audio_vivid.cpp
requires libAudioVividMetaBuilder.z.so with CreateAudioVividMetaBuilder and
DestroyAudioVividMetaBuilder. No actual builder implementation/library/algorithm
producer was found in the scoped multimedia/vendor/third_party source or primary
exact-term searches. FFmpeg HDR Vivid is video metadata and does not implement this
audio builder. A real compatible implementation and legitimate dependency are
still required; no mock metadata or synthesized callback was introduced.

ALSA producer is ci/capability-audit/batch_media_alsa_inject.c. Parent must compile
it with real guest headers/libasound, verify enumerated card/PCM and exact negotiated
S16LE channels/rate, inject fresh external nonce/channel PCM into actual kernel
aloop, persist ordinary public Capturer output and independently compare content.
The tool fails on data loss/xrun, partial/error/timeout and never replaces an API
backend. Mixer not-supported behavior still needs AudioService startup validation.
Task::Start is void; IsTaskRunning confirms scheduled state only, not thread readiness.
