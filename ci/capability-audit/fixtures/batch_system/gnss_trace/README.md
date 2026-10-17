# Existing GNSS callback diagnostic

The client checks its actual UID/EUID, obtains only the already running GNSS SA,
and invokes its existing root-only Dump option. It never acquires an HDI owner
or starts/stops the provider. Build it with
`batch_system_gnss_trace_helper.py` against the actual ARM64 product source/out;
the selected GN graph must already define the trace and GNSS feature.

The small client inlines standard-library operations. Its ABI evidence comes
from the fixed source and builder's compiled `std::__h` assertions, actual system
headers, linker input hashes, AArch64 musl ELF and cross-DSO CFI. It does not force
an unrelated string or IPC operation merely to add a dynamic symbol/dependency.

`batch_system_gnss_trace_window.py` checks bounded raw snapshots and complete
ordinal intervals. Old history overwrites can coexist with a complete current
interval. Local ordinals do not prove a wire nonce, process continuity across
boots, actual source authenticity, ordinary API behavior, or capability closure.
New-package boot identity, genuine root IPC, source/input provenance and normal
location/skiing/fusion regressions remain separate runtime requirements.
