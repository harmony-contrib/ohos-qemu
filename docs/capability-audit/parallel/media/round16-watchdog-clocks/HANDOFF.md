# Actual dual-clock observation candidate

Base: `571eb8190f02cb9fc3545b12e891a2ac673708bf`. Only the three newly authorized source/test files and this documentation are added. Existing boot, health, suite, build, runtime and media files remain unchanged. This delivery closes no capability or package gate.

`watchdog_clock_probe.c` accepts exactly one32-character lowercase hexadecimal nonce. It calls actual `clock_gettime` in the sequenced order `CLOCK_MONOTONIC` before, `CLOCK_BOOTTIME`, `CLOCK_MONOTONIC` after and emits exactly one JSON line:

```json
{"schema_version":1,"nonce":"<the exact 32 lowerhex argument>","monotonic_before_ns":0,"boottime_ns":0,"monotonic_after_ns":0}
```

The zeros above illustrate field types only; the implementation converts all three actual `timespec` readings to checked `uint64_t` nanoseconds. Invalid arguments, failed real clock calls, negative/out-of-range fields, multiplication/addition overflow, backwards MONOTONIC bracket or failed stdout writing return a nonzero exit. Clock-call failures retain actual `perror` information on stderr. Missing `CLOCK_BOOTTIME` fails compilation; there is no replacement clock, fabricated data, host-time source or fallback. The CLI performs no sleep, input, background work or power/policy operation.

Python interface:

```python
from watchdog_clocks import parse, compare, capture_script
before = parse(actual_first_stdout, expected_first_nonce)
after = parse(actual_second_stdout, expected_second_nonce)
result = compare(before, after)
script = capture_script('/data/local/tmp/owned-clock-run/probe', expected_first_nonce)
```

`parse` accepts text or ASCII bytes with an optional single final LF, at most1024bytes/characters. It requires an exact five-field object, version integer1, exact expected nonce, nonnegative integer timestamps through `2**64-1` and `monotonic_before_ns <= monotonic_after_ns`. It rejects booleans/floats, non-finite numbers, duplicate decoded keys, unknown/missing fields, wrong challenge, partial JSON, multiple lines, prefixes and suffixes. `compare` revalidates both parsed samples, requires the complete later MONOTONIC bracket to follow the earlier one, and rejects backwards BOOTTIME. Different expected phase nonces are preserved in the result; neither function proves freshness or same boot independently.

For snapshots `a` and `b`, define `B = b.boottime - a.boottime`. The simultaneous MONOTONIC elapsed interval is:

```text
M_min = b.monotonic_before - a.monotonic_after
M_max = b.monotonic_after  - a.monotonic_before
sleep_clock_difference_ns = [B - M_max, B - M_min]
uncertainty_ns = M_max - M_min
               = width(a.MONOTONIC bracket) + width(b.MONOTONIC bracket)
```

The output has `schema_version`, `before_nonce`, `after_nonce`, exact `boottime_elapsed_ns`, `monotonic_elapsed_ns:{minimum,maximum}`, `sleep_clock_difference_ns:{minimum,maximum}` and `uncertainty_ns`. Arithmetic remains integer-exact, and negative interval edges are not clipped. BOOTTIME may include accumulated suspend time, so its numeric reading is not required to sit between the MONOTONIC readings. Their call-order bracket bounds the measurement uncertainty. Even an exact zero difference does **not** establish absence of s2idle, and a positive difference alone does **not** identify a particular sleep state. No `pass`, sleep-state decision or health override is emitted.

`capture_script` is only a deterministic foreground shell command generator. It validates a canonical absolute path and nonce, removes `LD_LIBRARY_PATH`/`LD_PRELOAD`, checks the executable is a regular final non-symlink file, then runs it. It does not deploy, connect to a VM, manage exit markers, infer ABI or verify a binary. Root must bind actual SDK3ABI source/compiler/ELF/link receipts, deployed binary SHA and permissions, actual transport exit/stdout/stderr, fresh per-phase nonces, unchanged boot/current account, original phase ordering, deployment cleanup and the independent RS/watchdog health evidence. No intentionally stalled-watchdog positive case was added.

`host-tests-01.log` retains14 passing Python protocol/counterexample tests in0.001s (retaining subprocess0.09752s); SHA `68c405c851079f2e41f985f2bcb512fe141650dd14d217c0ecc1f3c22084247e`. `host-evidence.json` records the exact invocation, source SHA values and limitations. Test timestamps are explicit synthetic host inputs for the interval oracle. The C probe was neither compiled nor executed; no actual clock/syscall, SDK/signing, VM, guest/HDC, s2idle, watchdog-stall or package validation occurred in this batch.
