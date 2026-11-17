# Retire and wake normal Capturer reads

Pinned audio_framework 6932fa64335b8272ca4a59de7808ab0d6c9eae7a. Both complete
CPP/header before bytes come from the root-owned F09 source export02. The
installer accepts only the complete before or complete after vector. It checks
all payload hashes before publication, rejects mixed/unknown/symlink states,
serializes publication, and restores exact original bytes/modes on a failed write.

Normal blocking Read currently waits up to 100 seconds in OHAudioBuffer::WaitFor.
Successful Pause, accepted Stop (including terminal acknowledgement failure),
and Release now retire an immutable private read generation and call the existing
WakeFutex. Release wakes before its remote IPC. A successful Start creates a new
generation; failed Start/Pause and synchronously rejected Stop retain their real
existing public state/error semantics. The 100-second data timeout is unchanged.

Each normal Read captures its generation at the initial state check, rechecks
after readMutex, and validates it under statusMutex before each bounded cache or
shared-buffer mutation. Its wait predicate permanently observes retirement even
if a newer Start is already RUNNING. A short/partial old Read retired before its
successful commit returns an error and cannot contribute bytes or position counts.
A real positive result commits stream-wide counts with period->status lock order.
Mark preparation happens separately with no status/period lock; event dispatch is
outside all position/status locks. This preserves reentrant Stop from the existing
mark/period callbacks, which hold their own locks. No control path waits for
readMutex while holding status or the av_codec captureMutex. No user callback is
invoked from a new status critical section. A read that committed before Stop may
still dispatch its already-earned asynchronous stream-wide position event.

Only CAPTURE_MODE_NORMAL uses the new read implementation. Callback-mode queue,
ReadCallbackFunc, HandleCapturerRead and its existing wake path remain unchanged.
No public API/virtual signature changes. The private class layout grows and must
be rebuilt together with its native clients; source-only checks do not prove ABI.

Known boundary: RestoreAudioStream/InitSharedBuffer can replace clientBuffer and
reconfigure ringCache without this new state discipline. Concurrent service death,
Restore or stream reconfiguration with Read is not claimed fixed. Existing user
position callbacks re-entering another blocking Read are also not made safe by
this patch; the preserved readMutex/position callback ordering needs separate
scope if that use is supported. Do not relabel these cases closed.

The owned Python test runs exact production method bodies plus the unchanged F09
FutexTool.cpp/.h and complete AudioRingCache.cpp/.h. IPC/shared-buffer carriers are controlled dependencies,
not a full product class/DSO or an audio provider. Real Linux futex syscall tests
require Linux and /proc/self/task/<ownedTid>/syscall; other hosts explicitly skip
that test and must not be reported as native passage. Baseline failure is observed
before an explicit host-only WakeFutex recovery. All runtime/SDK/native and host
test execution is reserved to root; none was executed while preparing this batch.
