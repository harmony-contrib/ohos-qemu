# RenderService asynchronous commit identity

Pinned graphic project: `81cc9ca9509bccd86c435064136fe45591d29eeb`.
Apply with `bash apply.sh --source-root OPENHARMONY_ROOT`.

Only `COMMIT_TRANSACTION` with `TF_ASYNC` and the existing wire PID zero may
read `IPCSkeleton::GetCallingRealPid()`. This identity originates in the kernel
sender-info ioctl, not in command data. Missing/nonpositive kernel identity
fails closed with the existing `ERR_INVALID_STATE`.

Nonzero wire PID, synchronous calls and other interface codes are unchanged.
The validated asynchronous identity is carried through an internal request
scope into direct-submit statistics. Nested/unrelated requests cannot inherit
it, and scope exit restores the previous thread-local value. No additional
sender-info ioctl is made downstream.
Token-type/access checks, Parcel validation, command PID and node ownership
checks remain intact. There is no protocol, public ABI, token, seccomp or
application permission change. The companion Binder patch must be applied
before building; an old kernel with zero sender info still fails closed.

Separate patch files also harden the directly used transaction path: check
offset-table injection completeness before FD copying, keep ParseFrom's single
memory owner, propagate existing direct-submit error codes, validate ashmem
offset counts before multiplication and all offsets before injection, and
reject undefined scene/follow-type values. Binder's existing 4-byte object
alignment is retained; no arbitrary new object-count cap is imposed. Invalid
or partial ordinary-copy tables are flushed before duplication. Ashmem payloads
are copied into a receiver-private malloc buffer, never retained in shared
memory. Every FD/FDR is sanitized before table publication; restored duplicates
become receiver-owned FDs. The Parcel releases them on early rejection or partial
restoration, and the existing asynchronous FlushBuffer/manual-worker path
explicitly transfers closing responsibility. Legal FD 0 is included.

Objects are read and written as bytes into aligned locals, including legal
four-byte Binder64 offsets. The paired IPC object-safety component fixes the
direct reader and cleanup paths too. Single-frame composition and DVSync/node
access are posted to the main thread without blocking the Binder caller; the
move-only transaction is owned on queue cancellation. Single-frame commands
retain the ordinary path's calling-PID-valid guard.

The executing unmarshal task owns an `AshmemFdContainerScope`: it restores the
previous FD map, use flag and unmarshal flag on that same thread, including
nested/ordinary tasks and parse/drop exits. A shared worker's final owner no
longer mutates another thread's TLS. Non-wait task permits are registered before
publication and completed exactly once on execution, early exit or cancellation;
wait tasks never consume another task's permit.

Delegate composition does not reset a rejected command's authorization flag:
both extraction and execution check it. Listener registration remains available
to ordinary applications, but its existing pid routing field must match the
kernel caller; the encoded 16-bit listener-id prefix and positive signed tid
are checked as routing metadata, never as permission grants. No new system-only
restriction is added. FreezeScreen uses the existing type-checked render-node
cast for the display parent instead of an unchecked screen downcast.

The new main-thread commit queue has global/per-kernel-PID count limits
(512/128) and receiver-observed serialized-byte limits (256/64 MiB). A native
internal submission without a Parcel scope is charged 4 MiB, not exempted.
These are overload admission limits for this new queue, not a bound on all RS
heap allocations or its existing caches. Admission precedes delegate extraction;
delegate extraction and node operations run on the main thread. A task takes
the input out of its scheduled closure before execution and releases its permit
once at completion or final cancellation. Pending permits retain budget storage
through shutdown. Real EventHandler post failure is returned through the existing
ErrCode path; no new synchronous wait, fallback execution or wire change is added.

Apply is whole-state idempotent. Final exact hashes skip the complete stack;
unknown or mixed files fail before mutation, rather than reverse-checking an
early hunk that a later numbered patch has legitimately changed.

Patch 0009 is the explicitly authorized paired private object-code repair.
The two command `sptr` arguments now use presence plus standard Binder objects;
native `sptr` cannot fall through the OHOS POD template. Both ordinary deferred
copy paths rebuild their owning Parcel with standard object/FD readers and
writers before the kernel request returns. They do not call `Append`, copy
borrowed cookies, or acquire objects described by raw shared bytes.

The ashmem sidecar is versioned and transports each FD/strong remote object in
the outer Binder transaction. A receiver-private snapshot supplies only the
validated ordered object layout and ordinary payload bytes. FD/FDR duplicates
and remote references are re-encoded into an owning MessageParcel; DBinder's
PTR/strong-object pair is one logical object, with checked flags, length and
adjacent offsets. Its buffer pointer is never dereferenced in the snapshot.
Standard decoding of the translated outer object occurs while the request is
alive, and standard writing retains its real reference/backing metadata.
Re-encoding may change object spans; subsequent fields and offsets are rebuilt,
not patched with raw pointer-sized bytes. Partial failure/cancellation releases
the owning Parcel and temporary FDs; FD 0 is valid. New ashmem transactions use
the Parcel lifetime directly, not a second worker that could double-close FDs.

This changes only the erroneous private object encoding, rebuilt at both ends
in all six new packages. There is no old-private-wire compatibility, new public
API, synchronous fallback, client-reported caller identity, or permission/node
ownership bypass. The earlier numbered hardening transitions remain part of
the unified exact stack; the new normal/ashmem copy paths supersede their raw
offset-injection logic. Historical fragment tests alone do not validate this
new path: the object-code boundaries and fresh guest tests are also required.

The kernel, IPC and RS components are in one shared patch plan before profile configuration
and build-input traversal. Validation requires real ordinary-app UI and Vulkan
compositor pixels plus forged/missing-identity boundaries on a newly packaged
image. Standalone compilation or an old-image diagnosis is not acceptance.
