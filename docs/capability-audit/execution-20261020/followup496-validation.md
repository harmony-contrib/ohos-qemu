# Follow-up batch 496 validation

This batch follows representative attempt 494 at canonical commit
`054d684589538d12f6e6c1981ccff80c5137f8a3`. Source and host checks do not
establish a new package, a successful boot, native callbacks, audio onset, or a
passed first-artifact gate. The active attempt must finish before these changes
are applied to the shared source tree.

| Area | Observed problem | Source change and validation |
| --- | --- | --- |
| ACE CFI dependency | SmartLayout target dependency checking rejects its ACE-specific bounds library because the part manifest omits the third-party dependency. | Add that manifest dependency. Preserve the six CFI source changes, native closure guard, and the four-component preparation order. Accept only the complete known predecessor or final state; do not accept arbitrary partial states. Root isolated checks: 79; independent checks: 56. |
| Audio synchronization | Positive synchronization IDs are not forwarded. Directly switching to `StartWithSyncId` would omit ordinary-start volume and boot-state updates. | Forward positive IDs and retain the same HPAE side effects and ordering. Root recompiled the four actual extracted methods with LLVM sanitizers; independent review: 75 checks. No presentation frame or hardware onset has been demonstrated. |
| ALSA accepted bytes | Exhausted EAGAIN retries can leave an unwritten tail while the primary layer reports the whole request as accepted. | Carry the actual accepted prefix through the private ALSA dispatch. Transport a confirmed prefix as success with its actual length and a confirmed retryable zero as success with zero length. Invalid private counts poison the render instance. Root and independent replays passed 40 extracted C cases and 10 generated proxy/stub branch models; component and mixed-state checks passed. The internal structure additions require a matching rebuild. |
| HPAE output queue | A short or failed write removes a whole queued packet and advances its scheduled duration. | Retain confirmed unwritten tails, perform at most one primary write per tick, and advance software duration only for confirmed accepted frames. Unknown acceptance permanently stops writes from that node, including after reset or pointer replacement. Scratch storage prevents gain or mute from being reapplied to a retained tail. Original 30 groups in each hook variant, 14 component tests and independent sequence boundaries passed. |
| Resampler input counts | The C resampler can consume fewer frames than requested; the converter previously removed the whole input request. | Carry actual consumed/produced counts and explicit leading padding, retain unconsumed frames, and drain queued output before pulling more input. Failed processing requires a successful real reset before reuse. Root replay passed 23 host groups in each hook configuration and 49 component checks; the actual C algorithm and public base vtable retain their bytes. Target behavior and latency remain unvalidated. |
| Client and server audio queues | A later pause or error hides an already-published prefix; converted output and copy failures can also lose or repeat queued data. | Count only successful cursor publications. Own bounded converted output, drain older tails before new input, and retain unknown state until actual native recreation succeeds. Check Ring copy results before clearing data or advancing the read cursor. Client 25 groups, 506 speed/format cases, server 19 groups, original Start and output-node regressions, and 16 component tests passed from the frozen source. Later full-composition findings and converter reset successors are recorded separately below. |
| Sonic arithmetic | Negative shifts and a signed sinc accumulator can mis-handle legal PCM extrema. | Use defined coefficient arithmetic and a wide accumulator; clamp only the final mathematical sum and preserve negative rounding. Root replay and independent source review passed normal audio, positive/negative clipping, and cancellation cases. The latter matters when an intermediate sum exceeds the narrow range but the final sum returns inside it. The table, phase logic and public API retain their bytes. |
| PA lower write errors | The actual PA implementation logs a failed lower write but still counts the full request and returns success. | Return the lower write failure before advancing the software count. The existing server check can then retain its input. Frozen author and independent replays passed 61 actual-method groups and 28 component checks; three parent recipe tests passed. Success means local PA queue acceptance; target output remains unvalidated. |
| Audio converter reset | Draining and discarding Sonic output leaves internal history that changes the next segment. An empty `Finish()` also changes a new stream before its first input. | Recreate Sonic on explicit Flush and mark a successfully created, empty stream as already finished. Configuration or creation failure still returns errors until valid recreation. The final successor passes 741 focused groups and independent component checks, including initial/post-Flush/repeated empty Finish, actual short input, and failed recreation. The unchanged 18 complete queue-composition cases pass, including the previously failed next-segment comparison. Locks, Pulse and service transport are controlled host dependencies; target concurrency and actual output remain unvalidated. |
| Audio source observations | Existing metadata does not identify source generations and cached ingress slices; the rejected first candidate also replayed ordinary setters during a late update. | Observe the actual bounded source FD window, SHA256 digests, generation and real renderer-session query results. A strict single-key private metadata route preserves ordinary relay bodies and setter calls. Root and independent canonical host checks and 10 component tests passed. Partial cached slices retain their original binding. These software records do not establish decoded frame zero or hardware onset. |
| JS framework tests | The original Mocha suite reports 41 passing and 2 failing tests because the Node test bridge lacks the native compiler. A bare shell `wait` hides failed children. | Add the Node test-only compiler bridge and collect child exit statuses. Actual original Mocha inputs on Darwin Node 18.20.1: 41/2 before, 43/0 after. Original assertions, two test globs and timeouts are unchanged. Actual Linux native Mocha execution remains required. |
| Number native observations | Existing public API results do not prove which loaded provider handled a request. | Record actual loader/creator/connect/Query events without logging queried numbers or predicates. Keep original IPC permissions, payloads, returns and errors. Independent source and selector review: 159 checks. Original image checks and three native-library requirements remain mandatory. |

The actual Node replay uses copied runtime/test/dependency inputs from the
owned 494 container, each read twice and compared by content. The baseline
compiler-test failures and the corrected replay are retained under
`/Volumes/PSSD/qemu/validation/first-20261005/issue-20-20261006/r62-js-mocha-host495-01/`.
This is a Darwin replay; it does not replace the Linux build step. Existing
nonfatal ESLint diagnostics have not been presented as passing lint.

The new loader ELF export is an on-disk package check. It separately records
image inode/path aliases, architecture, actual bytes and checksum; loaded
process and callback fields remain false. Runtime association must use the
actual new image and raw guest observations.

All changes use `codex/ohos7-integrated-development`. The parent owns shared
build/package files and serializes Git commits and resource access. New builds
must batch all known fixes. After the new representative package is created,
record its path and checksum, boot it, and validate the original full suite and
required dedicated capability cases before building the other five packages.

Supplement the unchanged original host selection with these new test modules
on the actual committed checkout, using the host regression Python with `-B`
and working directory `ci/capability-audit`:

```sh
python -B -m unittest -v test_audio_haptic_sync_id_component \
  test_audio_haptic_sync_id_recipe test_jsframework_native_test_bridge496 \
  test_jsframework_native_test_bridge_recipe496 \
  test_number_native_observation495 test_number_native_observation_recipe \
  test_number_native_loader_image496 test_number_native_consumer498 \
  test_number_native_source_loader499 test_audio_haptic_source_provenance \
  test_audio_haptic_provenance_recipe test_audio_resampler_counts_recipe \
  test_sonic_defined_arithmetic_recipe test_pa_write_status_recipe
```

The Number consumer successor additionally fixes two independent review
findings: it accepts the original image reader's finite same-inode root/system
alias vectors, and binds the current caller's kernel birth across captures and
to the conservative Query clock bound. The nine new source-model tests and 22
original negative models pass in isolated host replay. These tests never create
an admitted observer or an actual guest callback proof. Independent review closed both findings. Actual new-package execution remains
required.

The integrated Number source delivery includes the actual observer source kit
and seven fixed-before patches. Its Owner patch goes directly from the
original 494 source to the reviewed 499 loader; it contains no intermediate
loader implementation. The loader compiles the verified source bytes, rejects
foreign or changed module objects, ignores cached bytecode, and rolls back only
its own inserted objects. Thirteen portable repository tests cover source,
cache, metadata and ownership boundaries. The original Owner lifecycle and
public API verdicts remain; actual new HEAD, source kit, SDK, observer and
package inputs must be bound before resource admission.

The next build source fixes compilation concurrency at four jobs, with prepare
and kernel jobs remaining two, four virtual CPUs, 10 GiB memory and one linker.
The original resource Owner and complete environment/configuration checks stay
in place; exact new driver and manifest pins accompany the source patch. Root
host replay passed 42 checks, and independent review passed 15 groups including
74 environment rejection cases. This changes the next attempt's configuration;
actual performance and memory peaks have not been measured.

The parent recipe checks the complete historical lifecycle vector, the exact
AudioVivid before/after state, and both provenance components before invoking
the legacy installers. Each of the six historical lifecycle vectors can upgrade
from either whole AudioVivid state. Only the complete provenance final state can
skip both legacy installers. A partial component or drift in any other member is
refused. The accepted-write component follows the existing capture component's
final check. The Sonic repair runs before the audio queue component, whose
external prerequisite requires that exact repaired C file. The independent
resampler and PA components also run before final provenance preparation. The source gates run before package-directory removal
and produce separate receipts. The original ACE native-closure gate and full
runtime requirements remain.

Source installers reject an interrupted or unknown accepted-write vector. That
installer uses sequential writes and does not roll back an I/O failure; such a
failure cannot be retried as an authenticated complete state without restoring
the pinned inputs. Independent write-failure injection confirmed rejection.
Generated IPC host models also show that a transport error can hide an accepted
prefix, which is why the HPAE successor never retries an error tuple. Real loaded
driver selection, target ABI, service concurrency, auxiliary-sink acceptance and
the source-to-PCM-to-hardware association still require actual package evidence.

An earlier combined replay of eleven supplemental modules completed 113 tests
in 28.313 seconds with exit0 and unchanged source bytes. Independent review then
found that those recipe fixtures missed the AudioVivid preimage and final-repeat
interaction. The corrected parent recipe passed 15 component/recipe methods;
independent review reproduced the old failures and verified their repair. The
actual AudioVivid payload retains its bytes. The original failed attempts remain
in the evidence; the earlier 113-test run does not establish acceptance of the
later aggregate. The resampler's five additional actual-shell recipe tests also
passed. A fresh combined replay on the final candidate and actual committed
checkout is still required after the client/server audio queue successor is
ready. That later thirteen-module replay completed 124 checks with three command
exit codes zero, including both shell syntax checks, and unchanged bytes for
213 curated files. After PA error propagation and the converter reset repair,
the fourteen-module replay completed 127 tests in 52.954 seconds with all three
command exits zero and 222 curated paths unchanged. That replay precedes the
newly confirmed empty-finish repair. After that successor, a fresh complete
fourteen-module replay passed 127 tests in 48.965 seconds, again with all three
command exits zero and 222 curated paths unchanged. Only this validation note
changed afterward. The same checks on the actual committed checkout remain
required. None of these host checks establish a new representative artifact or
its runtime acceptance.
