# Bounded QEMU software-capture wait

Pinned window_manager: `c9e0c375301ef3fc5cb08d4e5ab69bc7fe04bf73`.

The unchanged R25 ARM64 phone archive demonstrably produces valid asynchronous
1920×1080 capture callbacks after the fixed 2-second DMS wait. In
`r25-direct-capture-latency-runtime-04`, three public DMS captures timed out;
late RS/PixelMap events were preserved. A fresh boot in runtime-06 measured a
real RS callback at 4,489,856 microseconds with one valid pixel map. Both runs
used the actual packaged libraries, not replacement libraries. These are
diagnostics, not evidence that this candidate works.

Only `arm64_virt`, `armv7a_virt` and `x86_64_virt` select a 10,000 ms budget.
Other products retain 2,000 ms. Both SDR and HDR existing waits use the same
bounded budget. Requests, callbacks, permission checks, null-result rejection,
error codes, mutex release while waiting, and asynchronous IPC are unchanged.
There are no retries and no manufactured image. This accommodates measured
software-render startup latency; it does not fix or conceal a missing callback.

`check_qemu_capture_budget.py` tests exact application, idempotence, unknown and
partial-source rejection, the actual GN predicate for three QEMU and three
non-QEMU products, and the actual pinned Future/DropLock code under ASan/UBSan.
Only logging, PixelMap and callback dependencies are host stand-ins. Checks
cover immediate/delayed/null/error/HDR results, releasing the global lock for
the callback, and finite no-callback expiry in both timeout branches. This is
not real IPC, GN generation for the full product, or guest acceptance.

`compile_qemu_capture_budget.py` additionally compiles the actual full DMS
translation unit with each product's real Ninja flags and the explicit candidate
define. Its report deliberately does not claim that full-product GN selected
the flag or that a linked/newly packaged image passed runtime tests.

The candidate is wired into the common pre-build patch sequence for both device
profiles. It is not in the already frozen R26 build. Before delivery it must be
selected by real product GN, rebuilt into a fresh representative package, and
validated for cold public capture, real pixel contents, ordinary-app denial,
missing/error callback behavior and regression. Remaining five packages cannot
start before that representative gate passes.
