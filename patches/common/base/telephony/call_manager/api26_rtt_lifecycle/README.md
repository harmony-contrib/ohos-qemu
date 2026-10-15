# RTT listener removal and queued-event ownership

The fixed API 26 SDK declares `offRttModifyInd`, `offRttErrCause`, and
`offReceiveRttMessage` as synchronous `void` operations with an optional listener.
The original NAPI implementation required a listener, removed whichever listener
was stored, and invoked the supplied event listener as an async completion.

This component retains the real IMS event route and fixes its listener registry:

- Omitted or explicitly `undefined` listeners remove this environment's registrations. A supplied listener
  removes only matching registrations; it is never invoked as a completion.
- Each event family supports independent listeners and environments. Duplicate
  registration releases its redundant references.
- Pending work retains a registration token rather than a raw callback copy.
  Removal invalidates the token before releasing its two N-API references.
  The environment hook owns the registration and its mutex independently of
  the singleton. Environment cleanup invalidates pending work before exit,
  including when the singleton has already been destroyed.

Apply this component to the fixed source after the existing `api26_enums`
component. It uses the existing `SUPPORT_RTT_CALL` feature gate. Shared patch
registration belongs to the integrating agent.

`LC_ALL=C LC_CTYPE=C LANG=C python3
ci/capability-audit/test_batch_location_rtt_lifecycle.py` applies every production
hunk to fixed-source slices and compiles/runs the actual changed methods with
AddressSanitizer and UndefinedBehaviorSanitizer. The harness exercises N-API and
UV lifecycle boundaries; it supplies no modem or IMS network and proves no
package-runtime closure. A newly packaged phone artifact must still validate
permissions, exported functions, event payloads, sessions and listener silence.
