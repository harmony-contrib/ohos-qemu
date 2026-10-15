# RS application agent identity

Apply after the complete `async_caller_identity` component on the pinned
OpenHarmony 7.0 graphics project. Registration is a one-way Binder request;
Linux deliberately keeps its wire PID zero. Use the existing kernel-backed
`IPCSkeleton::GetCallingRealPid()` only for an asynchronous zero wire PID and
reject nonpositive identities before registration. Synchronous positive callers,
interface permissions, the Binder wire format and profiler mapping stay intact.
No Parcel PID is read or accepted as identity.

The old registration stored agents under PID zero while color notifications
looked them up by the real node owner PID. The new registration uses the same
kernel identity already preserved by `binder_async_sender`. This repair does
not fabricate luminance or change the real GL sampling path.

Whole-file hashes require the complete prior transport stack and its exact
successor. Parent replay recognizes only this successor with every other parent
file fully repaired. Host branch tests and real three-ABI TU compilation are
not package acceptance: build and boot a new representative archive, then prove
real dark/light callbacks, off/re-subscribe, caller termination and all full gates.
