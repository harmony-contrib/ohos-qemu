# Fixed GN host execution

OpenHarmony 7.0's pinned x86_64 GN can intermittently terminate with SIGILL
inside an amd64 Docker container on an ARM host. A new first-package attempt
failed while formatting its generated `rust_atty/BUILD.gn`. Isolated native and
QEMU-user repetitions both passed, so those repetitions alone do not establish
a deterministic instruction-level cause or OS build success.

This component gives HB's generated-file formatter and command executor an
explicit software-CPU mode, `QEMU_HOST_GN_QEMU_USER=1`. It executes the same
original GN with `qemu-x86_64-static -cpu max`; no GN binary, command argument,
project source revision, success/error result, or guest permission is replaced.
Non-GN commands and the default mode 0 retain their original execution path.
The full launcher automatically selects mode 1 for ARM hosts running amd64
Docker; Intel/native builds retain mode 0. The runtime dependency is checked
before the build and installed through normal Docker dependency setup.

The full image launcher also passes HB's `--gn-flags=--threads=1` in mode 1.
A representative attempt stalled during multi-worker GN generation: the parent
and its forked child remained in futex waits while CPU counters and logs stopped,
with no OOM events. The one-worker limit is a host execution mitigation, pending
a new representative build; it does not prove a specific emulator lock bug was
fixed. Persisted HB GN flags are cleared between invocations so this worker
limit cannot leak into native mode. Target compiler, LTO and CFI settings remain
unchanged.

The two numbered patches modify only the fixed build project's two Python
callers. `apply.sh` checks their complete original/repaired hashes and rejects
unknown or partial edits. Real loader, GN graph, system compilation, packaging
and newly packaged guest validation remain required.
