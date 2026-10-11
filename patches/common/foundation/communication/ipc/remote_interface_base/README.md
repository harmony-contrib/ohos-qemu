# Native RPC abstract base candidate

The pinned API26 SDK accepts `instanceof rpc.IRemoteObject` and subclasses of
`rpc.IRemoteObject`; direct construction is rejected by the actual compiler.
The pinned NAPI module exports neither the base nor its inheritance relation.

This component defines a distinct native base, not an alias of RemoteObject or
RemoteProxy. Its derived objects own a real existing Binder/JS callback holder
with an empty descriptor (the abstract base declares no descriptor constructor).
The pinned engine exposes its type tag as JS data, so the tag is only a lookup
hint. A native registration and weak reference to the exact same object/environment
authorize unwrapping that holder, not a copied tag, pointer or prototype shape.
Existing concrete constructors and their own methods remain unchanged.

The base captures the original concrete C++ callbacks at module initialization,
dispatches by the actual native object kind, and keeps the existing transport,
argument checks, BusinessErrors and callbacks. An immutable DLL-lifetime method
table holds only environment-independent C++ callbacks, with no per-realm method
data allocation or JS references. Extracted methods may outlive their class. Plain native
functions avoid concrete-class receiver branding on V8 without accepting a
fake/unwrapped receiver. The weak-identity registry uses allocation-free intrusive
buckets and supports the product's existing no-exceptions compilation policy.
Both concrete prototypes and constructor parents are linked and read back.

No public C/C++ header, SDK signature, token, permission or Binder protocol is
changed. All product consumers must be rebuilt together. Compiler results,
isolated objects and host fixtures are not guest or six-package validation.
