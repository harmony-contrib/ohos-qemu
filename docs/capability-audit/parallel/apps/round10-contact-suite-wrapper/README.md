Contacts fresh-package suite wrapper is ready for root integration. This batch
adds no upstream source targets and does not change the four frozen caller ETS
files, seed/observer fixtures, shared suite, signing tool, or package gate.
All 34 apps IDs remain pending their required real runtime evidence.

The callable interface is:

```text
python3 ci/capability-audit/batch_apps_contact_picker_coordinator.py \
  --boot STABLE_SUITE_BOOT_SNAPSHOT \
  --archive CURRENT_REPRESENTATIVE_ARM64_PHONE_ARCHIVE \
  --hdc ACTUAL_HDC \
  --inputs INPUTS_JSON \
  --signer-dist FIXED_PUBLIC_SIGNER_DIST \
  --observer-local ACTUAL_PRODUCT_OBSERVER_ELF \
  --observer-receipt ACTUAL_PRODUCT_HELPER_BUILD_OR_RECHECK_JSON \
  --full-boundaries \
  --output NEW_EVIDENCE_DIRECTORY
```

`--signer-jar` is optional; it defaults to `hap-sign-tool.jar` in signer-dist.
The UI options are `--permission-bundle` (default
`com.ohos.permissionmanager`) and repeatable `--allow-text` (default 允许/Allow).
The parent owns the stable boot snapshot beside its real qemu.log, guest wake,
SDK/native compilation, archive preparation, and the first-artifact gate.

`inputs.example.json` contains the three actual successful SDK project inputs
already checked in this worktree. Each role has `sdk_evidence` and
`unsigned_hap` file descriptors (`path`, `sha256`), `sdk_project`, and
`source_project`. Caller and seed also have a `source_manifest` descriptor.
The provider uses the real Contacts project from the mixed Contacts/Theme SDK02
report. Seed uses contacts-seed from the mixed seed/query/live SDK02 report.
Their batch exit codes remain 1. The adapter verifies every source file, all
commands belonging to the selected project, real command log hashes and Hvigor
success, and the unique project HAP. It never changes the failed batch into a
successful batch or borrows another project's success.

The optional `helper_path_map` supports exactly two old receipt prefixes:
`/evidence/helpers` to the retained helpers directory and `/work` to the
retained frozen repository. It preserves original records and original report
hashes, then hashes the actual mapped private source, ELF, original logs and
fixture. A verify-existing report must preserve the original compile/link
commands, bind its original report, and contain successful new actual readelf
ABI/CFI checks. The host does not claim it has reread inaccessible `/ohos`
headers, compiler or product DSOs; those remain bound to the real Linux
builder's read-only recheck and unchanged-input receipt. A plan or a bare ELF
is rejected.

At runtime the wrapper:

1. Attaches to the suite's actual ARM64 phone boot and current UDID. It extracts
   the unique Contacts inode from that boot's immutable system.img, checks the
   archive's provider guard and system-image inventory, matches the actual
   compiled module/ABC/resources to the real SDK HAP and source module, and
   verifies the physical extracted HAP's code-sign/digest/permission signature
   and exact profile hash. A diagnostic HAP cannot substitute for this image
   extraction.
2. Signs the zero-permission normal caller and the normal READ/WRITE_CONTACTS
   seed with the existing public-key sign_web_probe implementation. It pins
   the signer tool/certificates/template, compares every compiled ZIP member,
   independently runs verify-app and verify-profile, and verifies CMS using the
   fixed ProfileDebug leaf. Exact normal identity, empty ACL/restricted sets,
   and the current UDID are required. It installs only absent audit bundles,
   checks actual BMS normal/non-system UID/token and actual installed HAP bytes,
   and runs the existing public-CRUD/UI driver.
3. Reconsumes the raw complete 15-case/16-invocation result matrix through the
   strict verifier, including six public overloads, actual 205 selection,
   changed selection then default cancel, dual sessions, permission denial,
   force-stop and reopen. It independently checks both normal BMS identities,
   seed denied-to-granted token transition and actual permission-dialog input.
4. Preserves public delete/query read-back cleanup, uninstalls only its two
   audit apps, observes both processes absent with the actual AppMgr API,
   checks BMS absence and no Contacts modal sessions, and deletes its nonce
   helper. Cleanup captures are tied to real HDC command logs with the exact
   guest target, script, successful guest exit marker and output bytes.

`evidence.json` has `status`, `scope`, `archive_sha256`, `boot_id`, raw artifact
references, `cleanup_complete` and `cleanup_errors`. A failure with incomplete
cleanup must stop reuse of the guest. Successful component evidence always
keeps `first_artifact_behavior_gate_passed=false` and `ledger_closed=false`.
`--full-boundaries` is required by the representative first-package gate. It
adds the actual native 600000ms deadline and navigation dismissal, making 17
cases / 18 public invocations. The independent verifier requires both raw
records, actual provider/session closure, the proper BusinessError and a real
600000..659999ms recorded deadline. The product timeout is unchanged. Omitting
the flag leaves the 15-case diagnostic mode with
`full_boundaries_requested=false` and `full_boundaries_verified=false`; the
parent must not use that mode to release the remaining package matrix.

The parent must call
`verify_evidence(evidence_path, archive_path, boot_path)`. This function rehashes
all relevant files, SDK source/project evidence and observer receipt, checks
the stable boot/archive identity, re-extracts the current provider, and
reexecutes actual Java/OpenSSL signature/profile/CMS verification in a new
temporary directory. It reconsumes raw runtime/BMS/token/permission UI/AMS/
cleanup evidence through the strict verifier. A child process's pass field or
a stored verification summary is insufficient. Preserve the extracted package,
SDK snapshots, public signing inputs, and native helper receipts alongside the
runtime evidence so independent verification can run after guest shutdown.
The parent gate also requires the returned, independently recomputed
`full_boundaries_verified=true` (not only the outer JSON field).

`host-checks.json` and `host-tests.log` record 66 passing host checks and the
three real SDK source/HAP input checks. The signing-command parser and ELF
receipt tests use explicitly synthetic data; they are not actual cryptographic,
native compilation or guest behavior results. This batch performed no SDK or
native build, signing, HDC installation, Docker/source/out query or QEMU run.
The first fresh-package attempt must supply the actual provider layout and AMS
records; host-owned UI support remains conditional on independently bound
provider/host sessions and remote picker node identities.

Shared helpers available to the other root-approved wrappers are
`sign_normal_hap(unsigned,bundle,permissions,udid,signer_dist,signer_jar,output,command)`
and `verify_signed_hap_artifacts` with the same arguments except `signed` in
place of `unsigned` and optional `apl='normal',system_app=False`.
`command(argv,label)` must actually execute, throw on nonzero exit, and return
stdout plus stderr. Outputs are new directories. The latter also supports an
explicit `system_basic/hos_system_app` query with exact caller-supplied module
permissions and empty ACL/restricted sets; it does not grant those permissions.
`verify_sdk_project(spec,fixture=None,source_manifest=None)` accepts the real
flat/nested SDK inventory formats. Frozen fixture ETS files are cross-checked
with actual compiled project inputs; wrappers with native fixture code must
also bind their native build receipts and ELF inputs explicitly.
