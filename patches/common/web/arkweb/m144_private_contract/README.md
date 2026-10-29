# M144 private adapter contract

Sync the private NDK mirror with the fixed OpenHarmony 7.0 / TPC adapter
contract; do not edit the public headers or generated C++/C bridges.

* Request configuration has no timestamp slot. Use the existing flush
  timestamp immediately before flushing; leave formats and rendering unchanged.
  Chromium's concrete request helper remains nonvirtual too; it cannot declare
  an override of a removed release slot. The concrete getter/setter and the
  authoritative flush timestamp are retained.
* Frame listeners expose context and function getters. Keep the shared,
  locked callback registry: retain an old registration on replacement/unset
  failure, release a new failed registration, and clear only after SDK destroy.
  The Chromium GL listener implements the same getters with a null-safe
  trampoline and retains immediate callback-thread signaling. The registry
  holds a shared reference during dispatch; the context does not outlive it.
* Preserve the local HiTrace `StartTraceEx` forwarding feature as a nonvirtual
  method. The release vtable must not gain a slot before `FinishTrace`.

These changes do not grant permissions, change the public API, disable tracing,
or constitute a successful full-engine build or booted-package acceptance.
