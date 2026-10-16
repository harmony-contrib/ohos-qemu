# Round 8: one fresh MIC observation per focus handshake

Base2b308a73d60c095926bb6dc34612de87947269b2. Only the existing
batch_media_audio_event_probe.cpp and test_batch_media_audio_events.py change,
plus round8-* evidence. No ETS/HAP wrapper, product component, shared runner or
verifier changed. Root reported the previous3 event unsigned HAPs passed and
mode0 actual live-revoke PID/token/PCM gate passed. This changed caller still
needs root's actual rebuild and two-UID focus run; this agent closes0 IDs.

## Request and completion

Only owner mode1 ACTION=focus_begin and contender mode2 MIC-primer
ACTION=contender_start process a request. All other actions keep the original
behavior. Every handshake keeps its original15s total deadline and cancellation.
No stream/permission/focus state is changed by observation itself. Failure uses
the existing failed-handshake cleanup; it is never turned into a successful ACK.

Inside each actual app private directory define:

    P=/data/storage/el2/base/files/audio-event-RUN-ACTION
    N=the32-lowercase-hex nonce from P-ready.json

Root publishes exactly one new request at **P-snapshot-request** containing
exactly N plus newline (33 bytes). Create a unique temporary regular file,
complete write/fsync and set actual app UID/mode0600 before publishing it into
the final previously-absent request path. Do not expose a partially written or
root-owned request; do not reuse or replace prior evidence. The native reader
uses O_NOFOLLOW|O_NONBLOCK, rejects nonregular files/FIFO, wrong UID, any mode
other than0600, wrong size/nonce, short/extra bytes and changed fstat identity,
mode, owner, size or nanosecond modification/change times. Missing is pending;
other failures fail the handshake.

The control thread records request_seen_ns and current byte/chunk boundaries,
then uses actual public GetCurrentState/GetFramesRead/GetTimestamp/
GetCapturerInfo/GetSamplingRate/GetChannelCount/GetSampleFormat. It must already
be RUNNING, MIC,48k,2 channels,S16LE. It waits for at least96000 additional bytes
from new Read callbacks after that boundary, then copies exactly the newest
96000 bytes (24000 frames,0.5 seconds). Counts or elapsed time cannot unlock a
copy of the old buffer. All selected callback ranges must be frame aligned,
contiguous, in bounds, in the same source phase, with monotonic callback times
strictly after request_seen_ns. The latest callback must be within250ms of the
final real query completion. Real frames, timestamp position and timestamp must
advance from the request query. Suspended/stopped streams, invalid callbacks,
failed getters or missing progress cannot publish success.

The only two response files are:

- **P-snapshot-N.pcm**: exactly96000 actual copied bytes.
- **P-snapshot-reply.json**: one newline-terminated JSON object described below.

Both are created O_EXCL|O_NOFOLLOW, must be regular/current-UID/mode0600, have
checked final sizes, and pass write/fsync/close checks. Prior files are preserved;
partial failed-attempt files are not reused. At most one request/reply is consumed
per handshake. Replacing a consumed request does not produce another snapshot.

Wait for **event_fresh_reply** in the actual app's existing
`audio-event-RUN-modeN-results.log` before consuming the response. This exact
JSON line is emitted only after both response files passed completion checks;
it matches the JSON reply file. Existence of the reply path alone is insufficient
because its first create/write is not an atomic publication. event_fresh_request
means only that the request was accepted. event_fresh_error contains the failed
stage; query failures also log the actual getter codes/values/interval. Never
ACK a failed or missing reply. An ACK observed after request acceptance but
before successful reply is rejected. Without a request, the legacy ACK path is
unchanged. The new wait never extends the15s deadline.

## Reply fields and root validation

| Fields | Meaning |
| --- | --- |
| type,run_id,action,ready_nonce,request_nonce,uid,euid | event_fresh_reply, actual run/action, both nonce fields equal N, actual native process identities |
| phase |1 for owner MIC,0 for contender MIC primer |
| request_seen_ns,requested_offset | monotonic request observation and byte boundary before accepting new callbacks |
| request_frames,request_position,request_timestamp_ns,request_query_before_ns,request_query_after_ns | actual public getter baseline and its monotonic call interval |
| state_result,state,frames_result,frames,timestamp_result,position,timestamp_ns | actual final state/frames/timestamp getter results and outputs |
| source_result,source_type,rate_result,rate,channels_result,channels,format_result,format | actual final configuration getters; successful MIC=0,48k,stereo,S16LE=1 with this fixed SDK |
| query_before_ns,query_after_ns,copy_before_ns,copy_after_ns | final native query interval and mutex-protected PCM copy interval |
| first_callback_ns,last_callback_ns,callback_count | actual selected callback monotonic range/count, not a generated timer event |
| offset,bytes,end_offset,pcm_basename,persisted,reply_prepared_ns | original accumulated-buffer byte range,96000 length, actual private PCM filename, checked persistence and preparation time |

Interpret an output value only with its associated successful getter result.
Reply success requires every getter return0 and actual state RUNNING=2; source
MIC/type0 is queried, not inferred from the action. Validate identities using
root's independent BMS/token data. Require request_seen_ns < first_callback_ns
<= last_callback_ns <= copy_before_ns <= copy_after_ns <= query_before_ns
<= query_after_ns, requested_offset <= offset and end_offset-offset=96000.
The first/last callback timestamps mark callback observations; their difference
need not itself equal0.5s because callback buffers have duration.

Root should correlate the complete96000-byte fresh file to its independently
held stereo challenge. It already contains a steady-state window: do not trim
startup samples from this half-second snapshot. The existing media PCM
phase_content accepts24000 frames and two disjoint8192-frame windows. Silence,
counters, duplicate channels or stale/unrelated challenge must fail. Root's
shared verifier still owns acceptance. Later require the snapshot to equal
`audio-event-RUN-mode1.pcm[offset:end_offset]` for the owner or
`audio-event-RUN-mode2-primer-full.pcm[offset:end_offset]` for the contender,
and check all overlapping final event_chunk/event_primer_chunk phase/time/ranges.

Obtain both actual services, ordinary background token grants and real task/
notification evidence first. Request fresh snapshots from both apps after the
second app's permission/background setup, independently validate both while
still waiting for ACK, then ACK contender_start. Its real MIC primer releases
before actual VOICE_COMMUNICATION Start. Do not treat an old baseline checkpoint
as this new observation.

## Live actual interrupt evidence

Every original event_snapshot now also has **last_callback:null** or an object
with actual **kind,code,hint,monotonic_ns** from Context.events.back(). The control
thread copies event/count/byte fields under Context.mutex and releases it before
FILE I/O. Interrupt/Error callbacks still only append in-memory real events;
no callback-thread FILE I/O is added. This is a bounded single-object addition
per existing snapshot; MAX_EVENTS remains128.

Before ACK owner focus_begin, root must observe the actual forced STOP tuple
kind1/code0/hint3 and bind its real callback time to the contender's actual Start
before/after interval and service/session evidence. events>0 or a generic STOP
state does not establish it. The final unchanged event_callback rows emitted by
Persist must contain the identical tuple and timestamp previously observed.
Original snapshot fields, callbacks and final persistence remain available.

## Evidence and limits

round8-host-02.log: all6 tests pass, including original PCM/nonce/permission/focus
oracle fixtures and acceptance of extra event_fresh_reply rows without closure.
The final frame-alignment refinement is verified in round8-final-host-04.log:
actual caller syntax against official API26 headers plus both actual-function
ASan/UBSan tests pass, with UBSan halt_on_error enabled. Snapshot tests cover
both MIC phases,20 refusal/collision/deadline cases,7 failing getters that leave
outputs untouched, no-overwrite behavior, one reply, early ACK, cancellation,
positive request/reply/ACK and unchanged legacy/other-action paths. Actual
Interrupt->Snapshot->Persist fields/timestamps match exactly. Getter callouts
and PCM inputs in these host tests are controlled dependencies, not actual
capture backend or runtime focus evidence.

round8-host-01.log preserves first UBSan diagnostics from an invalid enum test
and sentinel. Valid enum defaults and a genuinely supported alternative-format
negative case fixed this; no sanitizer is disabled. round8-host-03.log records
stronger untouched-output getter-failure checks; final04 repeats these with
frame-alignment checks. round8-evidence.json binds final source/header/test/log
hashes. No Docker, product/HAP/NDK-link build, QEMU or HDC was run here. Root must
rebuild the changed caller and perform the actual two-app protocol on its real
new representative image; the old HAP/library is not this changed candidate.
