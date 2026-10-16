# Wallpaper suite wrapper

This batch implements one executable command for the first ARM64 phone artifact. It consumes the existing suite-owned fresh acceptance guest, actual SDK02 callers and real product helpers. It builds no SDK/HAP/native target and starts no VM. Root retains ownership of suite/first-gate/closure registration and the frozen runtime/verifier. No requirement or representative-package gate is closed by this delivery.

## Parent interface

```sh
"$PYTHON" ci/capability-audit/batch_media_wallpaper_suite.py \
  --boot /ABS/work/boot/wallpaper-boot.json --archive /ABS/new-package.tar.gz \
  --hdc /ABS/hdc --artifacts /ABS/wallpaper-artifacts.json \
  --suite-evidence /ABS/parent-suite-evidence.json --output /ABS/work/wallpaper
```

`run` is an optional prefix. `--timeout` defaults5400 seconds and is bounded300..7200. Root must save its suite report before invocation and must not operate HDC/UI concurrently with this wrapper. CLI help is retained in `cli-help.txt`. The result is `<output>/evidence.json`, with top-level `status`, `scope`, `archive_sha256`, `boot_id`, `cleanup_complete`, `cleanup_errors`, raw artifact references and `first_artifact_behavior_gate_passed:false`.

Exported independent entry point:

```python
from batch_media_wallpaper_suite import verify_evidence
result = verify_evidence(evidence_path, archive_path, parent_boot_path)
```

It rehashes the original sources/build receipts/logs, recomputes the frozen file/pixel oracle and exact21 action/ACK/query/helper/power proofs, and re-verifies the existing signed HAPs using actual Java/OpenSSL. It issues **no HDC/VM/build command**. Temporary cryptographic extraction files are discarded. The returned result remains the frozen narrow wallpaper runtime scope, with no closed requirements. Parent must separately bind its native/source/image attestation and any extra extension-connection witness before closing the corresponding behavior finding.

Integrate apps commit `a3e0347` first: the wrapper deliberately imports its shared `batch_apps_contact_picker_coordinator` signing mechanism. It does not fork another ordinary signer. Helpers require the root's current actual `batch_system_build_runtime_helpers.py` corresponding to the successful recheck report. These are runtime Python dependencies, not work performed by this child.

## Artifact input

Every `file` below is exactly `{"path":"/ABS/file","sha256":"64hex"}`. Paths are actual retained root artifacts, not hand-written success receipts.

```text
challenge: file(actual SDK02 challenge/challenge.json)
ui_plan: file(actual source-defined profile plan)
seed:
  source_project: /ABS/r52-Contacts-Wallpaper-callers-Linux-SDK-02/wallpaper
  source_key: wallpaper/entry/src/main/ets/pages/Index.ets
  sdk_evidence: file(actual SDK02 evidence.json)
  unsigned_hap: file(actual produced HAP)
  ability: EntryAbility
query:
  source_project: /ABS/r52-runtime-seed-query-live-Linux-SDK-02/wallpaper-query
  source_key: wallpaper-query/entry/src/main/ets/pages/Index.ets
  sdk_evidence: file(actual query batch evidence.json)
  unsigned_hap: file(actual produced query HAP)
  ability: EntryAbility
helpers:
  build: file(/ABS/r52-runtime-product-helpers-recheck-02/helpers/build.json)
  output_directory: /ABS/r52-runtime-product-helpers-01/helpers
  path_map:
    /evidence/helpers: /ABS/r52-runtime-product-helpers-01/helpers
    /work: /ABS/r52-runtime-product-helpers-01/frozen
signer:
  dist: /ABS/actual-public-QEMU-signer-dist
  jar: file(actual SDK hap-sign-tool.jar)
```

All selected project source_files are checked against source_project, including module.json5, page, label, build configuration and any source manifest present. The exact generated seed/query page must match the fresh challenge nonce and frozen original template. SDK target commands, original logs, module/ABC and actual HAP SHA/bytes are checked; signing must leave the complete compiled payload unchanged.

The shared signer pins the original public SDK JAR/template/certificates and fixed application/profile leaf fingerprints, performs real code-sign/digest/permission verification and verifies the profile CMS with the fixed ProfileDebug leaf. Both callers receive the **actual new boot UDID**. Seed is normal/hos_normal_app, zero permissions, empty ACL/restricted lists. Query is system_basic/hos_system_app, only READ_IMAGEVIDEO, empty ACL/restricted lists. No API grant/revoke, APL escalation of the importer or image policy exception exists. Original query signer output is retained; the coordinator schema uses a separately named adapter, never overwrites that receipt. The wrapper journal alone is mutable; raw evidence remains exclusive.

The actual importer HAP is70855B/SHA `15a9debb3eae1c4ea5e8bf64c9742c68081280784fe2f55b823bcf134b22ee94`. The actual query HAP is68710B/SHA `641d2246bafbb5bd570a8a8fac64a881977ab1c5fd2ac443adcc37902bb4663c`. Their run nonce is `33993bd29f85a3c0c1375c3eff25ef61`. Query batch exit1 belongs to another project; every wallpaper-query command actually succeeded. `actual-query-project-adapter.json` retains `actual_batch_exit_code:1`, exact target project and original report/log hashes. It does not change the original batch result or trigger a rebuild. These existing PNGs are1280x800; the wrapper independently captures the real display before install and fails if dimensions differ.

## Real product helpers

The adapter consumes root's successful **read-only recheck02** and unchanged original failed build01. It preserves original_report, original status/error, original compile/link argv and log hashes, reused source/ELF hashes and the explicit two-prefix map. Recheck source/version and successful full ELF inspections must match. A planned/failed recheck, changed input, wrong binary/source, missing original command or naked `{status:pass}` receipt fails. `/ohos` headers/compiler/DSO files are **not mapped or claimed to be reopened on the host**: their original and rechecked Linux read hashes remain the builder's evidence. The adapter independently reads the actual host ELF interpreter/DT_NEEDED and binds each needed product DSO hash to those recorded link inputs. Before either helper runs, the coordinator checks the real guest's corresponding DSO bytes, clears LD_LIBRARY_PATH/LD_PRELOAD, stages a root-owned0700 directory/binaries0500 and verifies guest binary SHA.

Both real adapters were exercised read-only against root's final recheck02:

- `wallpaper_token_query`: SHA `de80a45dd1bb3fc1e0bf48d8e60958611a85cfa2822ee7160357e783cfbf3563`.
- `wallpaper_default_resolver`: SHA `13b9f2abee00eef20b618c8b1f3096494ecbf0876f6719c5739d6afac0aa6011`.

The retained `actual-*-adapter.json` files keep `original_build_status:fail`; they are compile/link receipt adaptations, **not guest execution**. This private branch does not contain root's newly added builder, so that diagnostic used the root's actual read-only Python directory as the expected builder/fixture origin. Source bytes match this candidate; no alternative header/library/ABI substitution or compilation was performed.

## UI and power contract

`fixtures/batch_media/wallpaper_receipts/phone-ui-plan.json` contains source-defined first-phone selectors. `ui-source-contract.json` preserves full source hashes and exact excerpts from the fixed RO Photos source and actual Settings SDK06 source. Settings uses the real `theme_settings` row. Photos uses actual `com.ohos.photos.MainAbility`, whose CommonAbility loads `MainAbility/view/index`; its phone branch declares `TabPhotos`. The wrapper checks the ability against actual BMS declarations. It never substitutes the misleading short mainElement value `MainAbility` for that real ability name.

All coordinates come from uniquely observed enabled UITest controls. TabPhotos, Settings row, Photos creation/delete confirmation and each challenge thumbnail still must appear on the **new guest**. The plan is a candidate, not an offline UI success claim. If a real profile instead exposes legacy SystemUI lockscreen, root must supply that actual profile plan; phone SceneBoard roots are never substituted for another consumer. Credentials, missing consumer, duplicate/hidden controls, source/installed mismatches and stale windows fail with raw tree/screenshot/AMS evidence. No generic arbitrary Tabs node, guessed coordinate or hard-coded completion flag is accepted.

The parent suite owns an86400000ms test override. With `--suite-evidence`, the wrapper proves the same archive/boot and original before(no override)/setup(86400000) states, then requires the live PowerMgr state to equal that setup before suspending it. It saves the parent report's actual bytes into its private journal directory so later parent saves cannot invalidate ownership evidence. Each coordinator action records actual PowerMgr before/after states. The UI flow runs with the original policy and observes any real system lock consumer's own override. At the end an ordinary Home/lock gesture lets that consumer restore its own state; only then is the parent's original86400000ms override restored and independently read back. Unknown overrides are never cleared. This is not a new default-power-policy acceptance claim.

The wrapper takes an exclusive0600 byte-for-byte snapshot of the supplied actual boot JSON in that same boot directory, retaining its real qemu.log/process/socket. Runtime and coordinator use that immutable snapshot. Independent verification compares its complete core test_environment/archive against the parent-supplied boot; future parent interaction-cycle journal updates do not invalidate a completed wallpaper result. No boot data is invented or replaced.

## Scheduling, cleanup and remaining runtime evidence

Both signed callers are actually installed before the frozen runtime reads its initial BMS identities. The coordinator retains its explicit actual reinstall command as binding when BMS does not retain the HAP path. Runtime is started first; the coordinator waits for its real request writer. Runtime action timeout is180 seconds; coordinator remains175. The parent issues no HDC while either runs. A failed or timed-out child cancels only its owned peer process group, saves both raw logs and never fabricates an ACK. The coordinator runs all21 existing requests: actual import consent, Settings entry/return, desktop/lock, cancellation/back/ordinary denial, both default restores, real UI deletion and private PNG removal. Full source records, actual token/BMS identities, exact query cursor counts and independent pixels remain mandatory.

Finally stops/uninstalls only the two disposable callers and removes only known helper binaries after owner/mode/hash checks, including partially staged directories; unknown files are preserved and reported. `cleanup_complete:true` requires actual owned policy/guest restoration and observer cleanup. Once any media mutation started, it additionally requires all21 actions, before-present/after-absent real five-URI queries, both DEFAULT configs with no user wallpaper resource and real private-input absence. A functional pixel failure can therefore remain a failure while safe reuse is certified from complete cleanup. A partial import/delete/restore cannot be certified; cleanup_errors then forces parent to stop reusing that VM. Before import begins, immutable raw action/command evidence may prove no media mutation began. No direct DB mutation, root unlink of Photos assets or synthetic empty query exists.

Root still must run real signing/installation/token/creation consent/UI/correlation on the newly packaged representative artifact, review the exact UI/extension connection witness and collect every failure before the next package cycle. Runtime/source fixes for the precise layout-transition/connection findings are parent-owned. ARMv7/x86_64 and2in1 plans/helpers remain outside this first ARM64-phone candidate and cannot be declared delivered based on its result.

## Light checks only

`host-tests-06.log`:23 tests passed/1.453s. They exercise project-local SDK success inside a failed batch, complete source inventory, exact minimal profile, genuine host child success/cancellation, owned override pause/resume, complete helper/recheck receipt and tampering negatives, exact UITest transition exception versus other errors, journal/raw-receipt separation, ELF/path-map negatives, source-bound phone plan and the existing21-request/nonce/cleanup/query/API26 declaration regressions. A valid JSON request without its completed final newline now waits instead of racing its writer. Constructed ELF/receipt/PowerMgr data is explicitly host oracle input, never actual native/guest evidence. The first run's fixture used one space instead of the real PowerMgr two-space delimiter; that failure is preserved. No native compiler, signing process, HAP build, SDK build, QEMU or HDC was run here. Narrowly authorized RO inspector queries exported source facts only.
