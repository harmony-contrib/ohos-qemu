# Exact audio capture data and lifecycle

Fixed av_codec e5c525670d1f6622d441c9e5bf975ea0579ea177, after existing QEMU
adaptations. `apply.sh --source-root ROOT` preflights all four complete SHA256
states and installs their paired payloads; partial/unknown states fail unchanged.
The numbered diff is for review, the manifest guards the actual install bytes.

A frame succeeds only after positive bounded blocking Capturer reads fill every
requested byte. Zero, negative, overreported, stopped and previous-generation
reads fail and cannot publish a queue buffer. AVMemory offset, capacity, writable
flag and SetSize are checked. Cached buffer copies obey the same writable range.
Stop does not take the reader lock. Deinit stops/revokes the capturer, releases
the capture lock, waits for the in-flight reader, then releases the actual object.
Control operations are serialized; the worker does not acquire the lifecycle
mutex. Pause/Stop/Release stop blocking capture before synchronously waiting on
the task, and failed Stop/Start are propagated.

Task::Start is void and IsTaskRunning confirms only its scheduled state. Actual
thread readiness, hardware Stop/read wake-up, interrupts and ordinary Capturer /
Recorder PCM/output must be verified against the newly packaged representative
image. This component does not provide or emulate a capture backend.

`test_batch_media_audio_integrity.py` compiles unchanged actual method bodies
with ASan/UBSan in a controlled dependency harness. Forty scenarios include
segmented/full/zero/error/overreported reads, offset tail, overflow, cancellation,
SetSize failure, failed startup/stop, old generation after Resume, first resumed
frame, concurrent control and release waiting for an active read. These are
function regressions, not permission/HDI/product runtime evidence.
