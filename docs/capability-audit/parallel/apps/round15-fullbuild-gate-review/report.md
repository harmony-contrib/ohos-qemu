# Read-only first-package chain review

Reviewed root commit `43a4c43991d3a5a9fe60c50c302d10daae592f99` via
`git show`. Only this new report directory changes. No active source/out,
Docker, SDK, compiler, GN/Ninja, QEMU or HDC was accessed or executed. This
review does not establish successful GN, image construction, packaging, boot
or runtime acceptance. The root GN-only preflight was still in progress.

Two independent offline-gate defects are reproducible. They affect specific
required checks; the counterexamples do **not** demonstrate that the whole
first-artifact gate, its other required checks, or the actual running suite
have passed.

## 1. Aggregate closure accepts absent or older-guest nested proof

`scripts/verify_first_artifact_gate.py:466–490` checks the exact ledger IDs,
counts, baseline hash and exclusions for `cxx-arkts11-gaps`, but never reads
or independently verifies any row in `payload['closed']`. In particular,
neither its `evidence`, `sha256` nor verifier is consumed. The enclosing
`verify()` loop at lines 548–559 hashes only the aggregate file.

The actual retained `verified_payload()` function accepts a synthetic
aggregate containing all 281 expected phone IDs with every closed row pointing
to the same nonexistent nested file and an all-zero SHA. The result is recorded
in `counterexample-result.json`; construction and actual function extraction
are in `reproduce_aggregate_gap.py`. The release policy and immutable ledger
bytes are checked against the reviewed commit before the reproduction.

Practical failure mode: once a real aggregate and its outer hash exist,
deleting/changing its closure-only nested evidence leaves the offline gate
checks unchanged. A claim about an original broad finding, including MSDP,
cannot be independently reconstructed from that aggregate. The new registry
correctly returns no broad MSDP closure from `external-inputs`; the aggregate
consumer must preserve that distinction rather than trusting a closed ID.

Recommended root fix: expose a pure independent verification of the same
runtime-root/boot/archive closure, recompute the registered results and exact
closed records, and compare them with the aggregate. Verify the actual raw
records with their fixed validators; checking only row hash syntax or existence
would not establish a same-boot behavior proof. Add missing, changed,
wrong-boot and mismatched-verifier nested-evidence counterexamples.

## 2. Library-exit special case bypasses archive/boot matching

`scripts/verify_first_artifact_gate.py:98–108` accepts
`issue20-library-exit` by target, architecture, device, case/repeat coverage and
zero guest exit codes. This branch bypasses the generic archive/boot checks at
lines 110–113. A same-target result from an older boot/archive therefore passes
this check even when it explicitly carries conflicting archive and boot IDs.

This is consistent with the real producer:
`ci/capability-audit/run_library_exit_probes.py:67–72` identifies its archive
binding as `not_attested_by_this_diagnostic_runner` and supplies no archive or
boot attestation. `run_packaged_qemu_suite.py:340–344` passes only target,
architecture and device to this producer and checks the parent's same guest
afterward. That confirms the parent guest's health, but does not make the
producer's result independently archive/boot-bound for a later offline gate.

The second reproduction invokes the same actual gate function with the full
8×3 successful case matrix, the expected target/architecture/device, a wrong
archive SHA and a different boot UUID. The function accepts it.

Recommended root fix: make the producer consume the actual archive and
enclosing boot evidence, verify live kernel boot identity before and after its
work and retain the raw binding/commands; independently validate that binding
in the gate. Merely adding the parent's UUID to the old diagnostic JSON is
insufficient. Preserve the no-private-candidate requirement and the actual
eight link-order cases.

## Chain properties confirmed by source inspection

The normal builder has `set -euo pipefail` and invokes `images` with explicit
`--fast-rebuild=false`, `--build-only-gn=false` and
`--build-only-load=false` (`build_standard_qemu_in_docker.sh:1569–1664`). Its
three witness begin calls precede the actual image build; finish calls follow
a zero-exit build pipeline. Load-only returns before witness begin and is not
packaged (`1626–1630`, `3460–3474`). PREPARE_ONLY returns before traversal
(`3453–3457`). A successful GN-only/preparation command is not sufficient for
this normal builder's packaging path.

Contacts witness validates the exact full image argv, real es2abc execution,
three forced actions, native compile/link lines and final hb product success
(`qemu_contacts_build_witness.py:327–367`), as well as all 18 fresh owned
outputs (`397–444`). Its scope explicitly excludes ABC module/literal semantics
and runtime. MSDP and Wallpaper begin move only their owned outputs and old
completion witness aside; their package/image checks bind the retained native
graphs, compile/link log, linked/staged payload and actual image extraction.
These source checks were reviewed without creating a witness or touching out.

The packager checks all three native components against its copied system.img
(`package_standard_qemu.sh:3144–3152`), leaves runtime flags false
(`3244–3249`), and publishes the final tar via a same-directory temporary archive
and atomic rename (`3322–3338`). `verify_device_type_package.sh:226–241` rechecks
the packaged native evidence. No additional definite output-path/argv mapping
defect was found in this pass.

The real suite creates a fresh private extraction, validates all package file
checksums, selects a free HDC port and verifies its owned QEMU process against
the extraction/image and QMP paths (`boot_package.py:200–219`, `293–370`).
`parallel_runtime_suite.py:64–109` freezes a boot copy beside the real qemu.log,
compares its entire core environment and calls the fixed family verifier.
Contacts complete boundaries and Wallpaper native fallback/renderer checks
are required. Its closure registry (`112–121`) closes only the phone Contacts
entry and Wallpaper provider ID; `external-inputs` closes no original broad
MSDP finding. These narrower checks do not repair the two special-case offline
gate omissions above.

## Narrow host reproduction

```sh
LC_ALL=C LC_CTYPE=C LANG=C PYTHONDONTWRITEBYTECODE=1 python3 \
  docs/capability-audit/parallel/apps/round15-fullbuild-gate-review/reproduce_aggregate_gap.py
```

Exit 0. Both counterexamples were accepted by the actual retained function.
No verification function was mocked. Only synthetic JSON was constructed;
no result here is a guest observation or a completed first-artifact gate.
