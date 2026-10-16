# Media round 7: Holiday product no-exceptions compatibility

Base a5fe4322f776c5e35e5839903bae35d0b1aa61aa. The only actual upstream
source changed from the preceding complete component is:

    foundation/multimedia/media_library/services/media_rdbstore/src/rdbstore/knowledge_holiday_index.cpp
    SHA256 0858f5406dc651091a9fa1f4cc264ef32b9f94d8c0cd6106dd138aa267caf6bd

Cumulative ownership remains25 targets,7 requirements open,0 closures. No public
API/header, GN option/dependency, product exception switch, shared builder,
runner/verifier, HAP or other media feature changed. No Docker, product/HAP/SDK
build, QEMU or HDC was started.

The parent actual platform03 compiled5 other Knowledge TUs successfully and
rejected the Holiday TU's3 try/catch blocks under the real -fno-exceptions
contract. no-exceptions.json binds that original full diagnostic and source
hashes. Keep the product flags unchanged; the parent only needs to retry this
full TU and actual final library link. This host result does not replace that
platform compile or representative-package runtime gate.

The observer now uses pthread initialization/create/condition wait/broadcast/
join return codes and a nothrow-allocated observation state. No throwing
std::thread constructor or C++ exception handler is used. Gregorian decimal
conversion uses bounded validated digits instead of std::stoi. Refresh keeps
actual RDB/IO/parser status returns and transaction rollback; it no longer
claims to recover a C++ allocation exception under this product contract.
Bounded standard containers retain the product's ordinary allocation behavior.

The worker independently retains observation state and uses only a weak DB
reference between imports. It takes a temporary strong DB solely during the
actual import. It never captures an owner/service/raw RdbStore pointer. Owner
and state locks are released before every external RDB call and join. Cancel
sets the predicate while holding the wait mutex and wakes the real condition.

Ordinary Stop cancels and joins outside lifecycle locks; concurrent external
Stop callers wait for the retiring generation. A reentrant worker Stop cancels
and returns failure/deferred-join without joining itself, also when another
thread is already joining it. Failed join preserves that same generation and
its owner reference for a real retry. Owner destruction on its own worker
cancels and detaches only for destruction: the independent worker state and
temporary DB remain alive until the callback/import returns. Normal Stop does
not detach. Initialization/thread-create failures release initialized state
resources before returning failure. Poll wait errors are logged and terminate
that worker; actual RDB/IO errors are logged, preserve the previous transaction
and retry on later polls. Stop success asserts shutdown, not prior import health.

Evidence:

- holiday-host-01.log:8 full producer/cursor/SQLite/query tests pass with
  -fno-exceptions -Wall -Wextra -Werror plus ASan/UBSan. This was before the final
  lock/error logging and join-notification propagation refinement.
- holiday-final-host-02.log: final full producer TU compiled with the same
  no-exceptions/sanitizer options; both observer tests and6 exact source tests
  pass. Failure callouts cover mutex init, condition init, thread create, join,
  timed wait, cancellation wake and join notification. Tests also cover retry,
  resource reclamation, two concurrent external stops during an in-flight RDB
  call, self-stop, weak DB expiry, no lock across a callback, worker-owned
  destruction/detach, real SQLite rollback and subsequent successful poll retry.
- knowledge-prior-guards-01.log:33 existing real query/NAPI body and complete
  photo/Knowledge composition/forward guards pass on the final component.

Pthread/NativeRdb/filesystem failure callouts are confined to host fixtures;
the actual product payload has no test flag, injected backend or replacement
query. SQLite and OpenSSL execute for real in the host harness. They do not
prove the actual OHOS RDB pool, Visitor ACL, service scheduler, installed system
calendar provenance, HAP roles or device runtime.

All13 exact file hashes/review diff are updated. The prior complete a5fe432
component is now an explicit whole-state upgrade input in addition to e0d1137
and caeaf60; unknown/mixed/symlink edits remain rejected before writes. A new
fixture proves that exact upgrade and unknown producer-byte preservation.
Keep the5 passed TUs' evidence; their output source hashes are unchanged.
