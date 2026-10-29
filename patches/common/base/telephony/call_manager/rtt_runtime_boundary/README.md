RTT messages previously lost their callId at the service boundary, then lost the
listener's failure return in CallControlManager. Missing media initialization
also marked PrevRtt true, and an unopened media manager accepted queued text.

This component is ordered after the existing api26_enums and api26_rtt_lifecycle
components. Its six complete preimages are the parent's read-only build578-02
container exports, not a host mirror. It preserves all existing system-app and
permission checks. The original callId must resolve to a real active IMS call
with RTT negotiated; the listener also binds its initialized manager to that
callId. Listener/media failure results propagate unchanged. Failed real InitRtt
releases the manager and never marks PrevRtt true. Queue submission requires the
actual media fd and both active threads. A queued submission remains a local
acceptance, not proof of peer delivery.

Apply with `bash apply.sh --source-root OPENHARMONY_ROOT`. The complete six-file
before/final vector guard rejects mixed and unknown states. The parent still
must compile all changed service/control/listener/media TUs and actual callers,
package one representative artifact and verify no-session/invalid-call/error
behavior on that new QEMU image before the remaining matrix. No IMS provider,
SIM, call state, peer, public callback or guest pass is manufactured here.

Authoring only: no host tests, parser validation, SDK build, container mutation,
QEMU, HDC, signing or runtime acceptance was performed by this child.
