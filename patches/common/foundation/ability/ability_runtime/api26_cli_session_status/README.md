# Public CLI session status

Fixed ability source: `6c18fdc9bdef6cfcf5888517cd8ed9448584f6e8`.
Expose the missing API26 `SessionStatus` enum, matching the existing
`SessionRecord::BuildSessionInfo` strings exactly: running/completed/failed.
Every new NAPI operation is checked and no partial object is published.
The existing session provider, process/result/timeout state machine, cleanup,
permissions, callbacks, IPC and other public functions are unchanged.

Registration/error fixtures and actual TU compilation are not guest session
execution or package acceptance. A new packaged ordinary-HAP enum collector
must verify the actual public object; CLI execution and session transitions
still require separate provider, authorization and failure-boundary proof.
