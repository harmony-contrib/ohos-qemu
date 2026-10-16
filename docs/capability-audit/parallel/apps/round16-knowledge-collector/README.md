# Same-guest Knowledge collector candidate

New files only: `batch_media_knowledge_suite.py`,
`batch_media_knowledge_artifacts.py`, their dedicated host test, and this report
directory. No application/product source, shared runner, signer, ledger or
existing file changes. Actual upstream targets: none. No requirement is closed.

The executable interface is fixed:

```sh
python ci/capability-audit/batch_media_knowledge_suite.py \
  --boot /absolute/parent-boot/knowledge-holiday-boot.json \
  --archive /absolute/new-package.tar.gz \
  --artifacts /absolute/knowledge-artifacts.json \
  --hdc /absolute/actual/hdc \
  --output /absolute/new-exclusive-output
```

It borrows `EnclosingAcceptanceGuest`; it never creates or stops a VM, starts a
second HDC server, changes power policy, grants permissions through a shell API,
or accesses media SQL. Root retains the fresh stable boot snapshot, archive,
actual SDK105 compilation, current-product observer rebuild, signing inputs,
suite/first-artifact integration and final guest validation.

## Precompiled input schema

`--artifacts` contains exactly these keys:

```json
{
  "schema_version": 1,
  "challenge": {"path": "/absolute/challenge.json", "sha256": "actual SHA256"},
  "projects": {
    "importer": {"sdk_evidence": {"path": "/absolute/sdk/evidence.json", "sha256": "actual SHA256"}, "sdk_project": "knowledge-importer", "source_project": "/absolute/knowledge-importer", "source_manifest": {"path": "/absolute/knowledge-importer/knowledge-source-manifest.json", "sha256": "actual SHA256"}, "unsigned_hap": {"path": "/absolute/importer-unsigned.hap", "sha256": "actual SHA256"}},
    "denied": {"same five SDK fields": "for the actual denied project"},
    "query": {"same five SDK fields": "for the actual query project"},
    "curator": {"same five SDK fields": "for the actual curator project"}
  },
  "signer": {"dist": "/absolute/public-QEMU-signer-dist", "jar": {"path": "/absolute/hap-sign-tool.jar", "sha256": "actual SHA256"}},
  "helpers": {"build": {"path": "/absolute/helpers/build.json", "sha256": "actual SHA256"}, "output_directory": "/absolute/helpers", "path_map": {"/evidence/helpers": "/absolute/helpers", "/work": "/absolute/frozen"}},
  "ui_plan": {"path": "/absolute/source-reviewed-ui-plan.json", "sha256": "actual SHA256"}
}
```

The example abbreviates three repeated project objects and uses explanatory
hash placeholders; it is not runnable evidence. Root's real SDK adapter report
already contains the exact `projects` and `challenge` objects. `path_map` is
optional; when supplied only the explicitly retained private `/evidence/helpers`
and frozen `/work` prefixes are accepted. Original receipts are never rewritten.
The actual helper selector and fixture are `knowledge_token_query` and
`batch_media/knowledge_runtime/knowledge_token_query.cpp`.

Both normal roles request zero permissions. Query uses the legitimate
`system_basic`/`hos_system_app` profile with READ_IMAGEVIDEO; curator uses that
same explicit test profile with READ+WRITE_IMAGEVIDEO. All profiles have empty
ACL/restricted arrays and the actual fresh boot UDID. SDK source/member bytes,
fixed signer leaves, real codesign/Java/CMS checks, exact installed HAP bytes,
four ordinary user100 UIDs/tokens and initial/final native permission readbacks
are independently verified. SDK module device type is the real SDK105
`['default']`; the acceptance guest remains strictly ARM64 phone.

## UI plan and real actions

The plan has `schema_version`, nonempty `source_evidence` descriptors,
`permissions` for query/curator and `photo_consent`. Each dialog contains only
`bundle`, `title` (one exact text selector), and `allow` (one exact text selector).
Permission titles/Allow texts are limited to the real source zh_CN/base
templates and actual SDK role label. The Photos consent currently uses the
root's fixed zh_CN `photos_dialog_contract.select_dialog`; other locales fail.
The exact title is `允许“Knowledge audit importer”保存 N 张图片？`, with N from
the real challenge count. No fixed `advanced_dialog_button_1` assumption is
made. Root's parser requires the actual title and both Allow/Deny Buttons in the
same dialog, including Text-child to Button-ancestor resolution, arbitrary
generated IDs, actual bounds, visibility, enabled and clickable state.

Root/System source evidence is in
`docs/capability-audit/parallel/system/round18-knowledge-UI-contract/`; it is a
source contract, not a guest observation. UITest may attribute Photos nodes to
the importer host or Photos provider. Either choice requires a separately
captured genuine Photos UIExtension AMS record for the importer host. Every
click retains original nonce-scoped guest dump/read commands, the normalized
tree, source-selected Button, PNG capture/transfer plus actual guest SHA, exact
clicked node center and AMS. The independent verifier replays those selections
from the original command bytes rather than accepting a normalized receipt.

The collector invokes the exact 22 `runtime.STEPS`: ordinary/system denial,
real grouped READ/WRITE grants, baseline, public creation consent and writes,
present/parameter bounds, retained public PhotoAssets, hide/unhide,
trash/recover/permanent delete, owned-asset cleanup/TRASH absence, and private
JPEG removal. Each fresh operation request is staged atomically in that role's
filesDir with its actual UID, and the real `knowledge_run` UI button is clicked.
The URI map comes only from actual public creation results. Curator's singleton
PID is checked from prepare through completion; restarting loses held objects
and fails. Journal-before emptiness, all four original JSONL streams, initial/
final token readbacks and before/after live kernel boot UUIDs are retained.

## Independent verification and cleanup

Public API:

```python
verify_evidence(evidence_path, archive_path, boot_path)
```

It rechecks all current tool hashes, artifact/source/SDK/member bytes, actual
Java/CMS signatures, ordinary BMS role UID/token and installed HAP transfers,
actual helper compile/link/header/ELF/defined-CFI receipt and unchanged source,
the exact staged helper, actual guest product DSO hashes, HDC target/remote exit
nonces, raw input transfers, all 22 requests/operations, actual UI selections,
singleton PID and final resource cleanup. It calls both media's `verify_raw`
and `verify_role_bindings`; their unverified transport/observer fields are not
used as pass claims. Only after the additional independent bindings pass does
it return all four required parent flags:
`all_phases_verified`, `role_identity_and_signatures_verified`,
`observer_product_ABI_verified`, `transport_guest_binding_verified`.

Finally cleanup always attempts real public curator operations and active/TRASH
absence queries before removing only the four owned callers. A failed partial
run uses a separately recorded public emergency cleanup attempt; ambiguity,
partial consent, lost curator ownership or failed query remains a cleanup error.
It never converts that attempt to a successful 22-phase acceptance. BMS, actual
process absence, live AMS host/provider-session absence and exact owned helper/
UITest-file removal are checked. Preexisting helper directories are not removed.
Every cleanup error is retained and forces `cleanup_complete=false`; the parent
must stop reusing that VM. No system Photos/PermissionManager process is killed.

Successful evidence is `<output>/evidence.json`, with `status='pass'`, actual
`archive_sha256`, `boot_id`, `scope`, `cleanup_complete=true`, `cleanup_errors=[]`
and all raw references. It explicitly leaves the overall first-artifact gate,
account isolation, nonempty analysis producers and original broad Knowledge
finding unverified; no ledger ID is returned for closure.

## Checks performed here

Final host suite: **49 tests passed**, exit 0. This is 24 dedicated collector
checks plus media's 25 raw/project checks. See `host-checks-final02.log` and
`host-checks.json`. The tests use explicitly synthetic layouts/metadata and
mocked transport where needed; they do not demonstrate any guest behavior.
They cover source/UI-plan changes, privilege/UID boundaries, missing receipts,
remote exit/target/failure checks, forbidden grants/SQL/power, whole raw bytes,
actual UI dump/screenshot/click linkage, dynamic Button/Text ancestry, retained
PID, public active/TRASH cleanup and failed-cleanup VM-reuse refusal.

`adapter-readonly-03.json` additionally records actual read-only revalidation of
all four successful SDK10502 project inventories/HAP members and root's genuine
helper01 ELF/log/CFI/source/DSO receipt. Earlier 01/02 snapshots remain retained.
`recheck_existing.py` reproduces this narrow check; its explicit dependency
context is the main repository as it will be after cherry-pick. It hashes real
root dependencies, does not mock a verification function, and does not rewrite
the original receipt or pretend to reread `/ohos` headers/compiler on the host.

The actual SDK report SHA is
`8d80201702abf12418060f452e6eff6ca3e5bce605e5ae24d695ce36adef461f`.
The actual helper01 report SHA is
`dc47c6d2094bdf98ed5bb6eee2c9ad032b2106cb097047b8428ce696bc99c7d1`;
its ELF SHA is `0d6a1ba2cba790f47af4359940f710dad2dad2e07057cacd8feb8f686a6c682f`.
Helper01 used the old product DSOs and is only a diagnostic candidate; root
must rebuild against the full product and pass that current receipt for the
new-package run. No compilation, signing, Java execution, Docker, source/out
query/write, QEMU or HDC execution occurred in this delivery.
