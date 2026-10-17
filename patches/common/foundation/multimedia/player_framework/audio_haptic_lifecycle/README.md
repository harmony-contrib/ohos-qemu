# AudioHaptic normal playback incarnations

Normal playback now retains the first prepared AVPlayer, then allocates a fresh
AVPlayer/client/listener incarnation for each later real playback attempt after
Stop, nonloop EOS, interrupt or failed Play. A private callback permanently holds
the immutable identity of its actual producer; the normal component, player and
detached EOS/interrupt workers all validate that same identity. First-frame data
received during Play is delivered only after Play succeeds. Stop, Release and
failure retire the identity before waiter cleanup. User callbacks run without
internal locks.

Prepare independently pins the source FD plus offset/length. Restart uses that
FD, including after the caller closes its descriptor or unlinks the source path.
Only final Release/destruction closes the pin. Fresh IDLE players are prepared
directly: the real PlayerServer rejects Reset(IDLE), so the earlier B4 patch's
propagated fresh Reset error must not remain. The first Start retains the first
prepared backend. Loop EOS keeps its backend alive. Native error returns and
existing SetSource/Play error mappings remain explicit; no error produces fake
success. Allocation/registration can genuinely fail. Creating a new backend may
add restart preparation latency and service/resource failure points.

The existing public and inner API headers/vtables are unchanged. Five private
implementation files change (two CPPs, two headers, one new header). A separate
private callback interface avoids changing the existing callback vtable. The
factory's existing NORMAL branch guarantees the concrete static cast; no RTTI
is required. The fast source implementation and its legacy callback path remain
unchanged. All component objects must be rebuilt together because private class
layouts change.

`source_states.json` pins five complete whole-file states: upstream originals,
the complete B4 two-CPP adaptation, the previous frozen incarnation and race candidates,
and this complete incarnation candidate. The
new private header must be absent in both preimages. Component-local `install.py`
accepts each exact preimage directly and is idempotent on the complete new
state. Unknown/mixed source, missing members and symlinks are rejected before
writes. It stages all five payloads, checks for concurrent edits, replaces only
owned members, and rolls back on failure. Rollback removes the newly added header
and refuses to overwrite a foreign edit; failed recovery remains an error. A
process/power loss can still leave a partial state, which is intentionally
rejected for explicit recovery. Shared global patch tools are not changed.
`0001` plus reviewable `0002` describe the source evolution; installation uses
SHA-bound payloads, rather than replaying 0001 against an already adapted B4.

```sh
bash patches/common/foundation/multimedia/player_framework/audio_haptic_lifecycle/apply.sh \
  --source-root /absolute/ohos --product arm64_virt
python3 patches/common/foundation/multimedia/player_framework/audio_haptic_lifecycle/verify_source.py \
  --source-root /absolute/ohos --require-patched
python3 -B ci/capability-audit/test_batch_media_audio_haptic_lifecycle.py
# Only the resource owner may run this separate native gate:
python3 -B ci/capability-audit/batch_media_audio_haptic_generation_native.py \
  --compiler /usr/bin/clang++ --work-root /absolute/owned/evidence
```

The lightweight host suite checks exact install/rollback/source contracts and
real OS FD lifetime prerequisites. The separate native runner compiles the
complete real B4 and candidate CPPs with their actual class and inner API headers
under `-fno-rtti` and ASan/UBSan. External Player, audio_info, parameter, monitor,
fast factory and vibrator dependencies are controlled test surfaces. It does not
simulate IPC event identity by inventing epochs: actual LoadAVPlayer creates and
registers each callback, and delayed relay/worker checks retain that same Session.
Native compilation/execution is a separate gate and was not performed by the
private candidate author. These tests never establish decoder, PCM, vibrator,
SDK, signing or guest success. All capability closure flags remain false until
root's new-package ordinary-caller and independent PCM/VDI acceptance.

The native state callback now computes one state per invocation, retaining only
an immutable initial member for private layout compatibility. Concurrent callback
invocations cannot replace each other's state between mapping and delivery. The
normal instance state was already atomic. Player implementation state and haptics
mode are now atomic enums because existing getter/callback/API precheck paths
read them without the writer's API mutex. No new mutex or public API is added. Exact previous-candidate upgrades are
recognized as `incarnation_v1`; mixed generations still fail. The controlled
audio_info test surface also includes the three ringtone usage enums verified by
root against product audio_stream_info.h; these are not production source edits.

The player sound pointer is published/removed with atomic shared_ptr exchange.
Ordinary sound readers remain under the existing API mutex; the publication
exchange now shares that mutex. GetAudioCurrentTime atomically loads a strong
snapshot, releases the atomic operation and queries it without the API mutex.
Release unpublishes before calling the old sound, and all replaced shared_ptr
destruction happens outside publication/wait synchronization. This also prevents
a native Release reentrant time query from deadlocking. `incarnation_race_v2`
keeps the previous complete race candidate as another precise upgrade preimage.
