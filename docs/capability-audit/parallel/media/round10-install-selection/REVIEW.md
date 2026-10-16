# Round 10 — provider install selection review

Read-only review of Settings, Photos and AdminProvisioning image guards against the actual BMS preinstall consumer. Defects below are reproduced from main commit `afa564ae0f4a603d933f63e9cff78674ed8e3cbf`; root began repairs while this review was running. Its new Admin `selected_entry` correctly rejected the numeric-zero counterexample during an initial live-tree test. The final reproduction therefore loads the original main commit's git blobs, with exact digests in `review-inputs.json`. Mixed-time working-tree hashes are retained separately and must not be mistaken for the reproduced baseline. This is a historical defect/repair handoff, **not a claim that root's ongoing fix still has every baseline defect**.

Only this documentation directory changed. Existing inspector `ohos-qemu-parallel-source-20261016-02` was queried with bounded read-only `docker exec -i`; no container was started, modified, compiled or restarted. `/ohos/out`, package images, SDK/HAP builds, HDC and QEMU were not used. No permission, APL, signing, or capability change is proposed. Closed requirements: **0**. Actual image/guest acceptance: **not performed**.

## Real source and installation contract

The inspector's `vendor/ohemu/virt/preinstall-config/install_list.json` has exactly one row for each of these targets, all with the genuine JSON boolean `removable:false`. Its full SHA is `b3c23ff2133586df1dfbd6865b9e7e848c1d10ea3ae9de9aec1d76e5bfee097d`. `uninstall_list.json` contains `uninstall_list:[]` and `recover_list:[]`, SHA `1d2c69e6abeeaa1e9648bed76fba1cad730f440319f7f5cd818db164b3f06238`.

| Provider | Actual source project | GN install directory | Required BMS runtime `app_dir` | Image HAP checked |
| --- | --- | --- | --- | --- |
| Settings | `applications/standard/settings` | `app/com.ohos.settings` | `/system/app/com.ohos.settings` | `/app/com.ohos.settings/Settings.hap` or the checker's unique `/system/app/...` alternative |
| Photos | `applications/standard/photos` | `app/com.ohos.photos` | `/system/app/com.ohos.photos` | `/app/com.ohos.photos/Photos.hap` or unique `/system/app/...` alternative |
| AdminProvisioning | `applications/standard/admin_provisioning` | `app/com.ohos.adminprovisioning` | `/system/app/com.ohos.adminprovisioning` | `/app/com.ohos.adminprovisioning/adminprovisioning.hap` or unique `/system/app/...` alternative |

The image's `/app/...` entry maps to the mounted runtime `/system/app/...`; it is not a reason to put `/app/...` into the BMS selection list. Source `vendor/ohemu/virt/preinstall-config/BUILD.gn` installs the four configuration files under `etc/app`. Settings/Photos `ohos_app` GN hashes match their fixed source guards. Inspector Admin GN is still the older `ohos_hap` form, although its install directory is the same; root's candidate guard requires its newer `ohos_app` source build. This directory review does not claim that this inspector Admin checkout alone passes root's final build guard. Full observed GN bytes and per-project revisions are retained in `source-observations.json`.

**No actual missing source selection row was found for these three providers.** The confirmed problem is incomplete acceptance checking when the packaged configuration differs from valid source.

## Actual BMS selection semantics

These references are from the inspector's real `foundation/bundlemanager/bundle_framework` source, with full TU hashes and line-numbered excerpts in `source-observations.json`:

- `appexecfwk.gni:53` defaults `use_pre_bundle_profile=true`; service `BUILD.gn:217-219,508-510` defines `USE_PRE_BUNDLE_PROFILE` accordingly. This is source configuration evidence, not an inspection of a newly built BMS binary's final flags.
- `bundle_mgr_service_event_handler.cpp:734-756,774-822` obtains configuration roots, includes `/system`, and parses `/etc/app/install_list.json` plus the module-update configuration. Capability and permission files have different roles; a certificate/grant row does not select an app directory.
- `GetPreInstallDir:843-853` uses a nonempty loaded profile and returns without the directory-scan fallback. `GetPreInstallDirFromLoadProFile:855-864` iterates the loaded `bundleDir`s and skips any exact directory in `uninstallList_`. A removed target row in an otherwise nonempty profile is therefore not repaired by the existence of its HAP on disk.
- `pre_bundle_profile.cpp:59-126` parses `app_dir` and a bool `removable`; duplicate directories replace the earlier effective set entry. An offline guard should reject ambiguous duplicates rather than depend on their order. `bms_json_util.cpp:45-66` explicitly requires `is_boolean()`, otherwise reports a property type error; the transform then skips that row.
- `pre_bundle_profile.cpp:241-281` reads string arrays, inserts `uninstall_list` items, then erases `recover_list` items. The consumer compares these resulting strings against exact runtime directory paths. `IsPreInstallRemovable:4336-4363` returns the selected row's removable bool for a matched path.

Other configuration-policy roots/module-update profiles can affect the merged runtime selection. This bounded review did not prove their complete absence in a new image or inspect a live BMS cache. These are explicit limits of source-level selection checking, not invented failures.

## Confirmed baseline guard gaps

### R10-1 — all three image guards omit the packaged directory-selection file

- `scripts/verify_settings_provider_image.py:221-242` extracts only `install_list_capability.json` and `install_list_permissions.json`. `verify_source:199-218` checks fixed source component hashes and the capability signer; it does not validate the source `install_list.json` row either.
- `scripts/verify_photos_provider_image.py:122-143` extracts only the same two files. `verify_source:108-119` similarly does not validate the source install-directory row.
- `scripts/verify_admin_provider_image.py:56-77` invokes the source guard, but the image loop uses `provider.POLICIES`, which contains only those same two files (`patches/lib/admin_provider.py:20`). The actual Admin source guard validates its source install row, not the image's install row.

Counterexample: retain the exact signed HAP and both policy siblings, but delete `/system/app/com.ohos.photos` from the image's otherwise nonempty `install_list`. Alternatively, change its directory or set `removable:true`. None of these three baseline image scripts requests that image file. Their offline checks can therefore accept the other validated inputs without detecting the missing selection / changed nonremovability contract. The bad row is not asserted to be present in any actual newly packaged image.

MMS already has the relevant narrow comparison pattern: `scripts/verify_mms_provider_image.py:86-91` extracts the image selection file and calls `provider.install_entry`; the baseline MMS guard uses a JSON-type-strict comparison. Reuse the selection principle for these three actual identities, rather than adding any permission.

### R10-2 — Admin source comparison accepts numeric false

Baseline `patches/lib/admin_provider.py:115-118` compares a Python list/dict to `{'app_dir': '/system/app/com.ohos.adminprovisioning', 'removable': False}` using normal `==`. JSON numeric `0` and `0.0` compare equal to `False`. Both are accepted by its real selection branch under controlled unrelated metadata/crypto dependencies; BMS rejects their non-boolean type and skips the directory row.

Root's new `selected_entry` already rejected `0` during this review. Keep the strict type check in source and image paths, including `type(removable) is bool` and `removable is False`, or equivalently a JSON-type-strict recursive comparator. Missing/wrong/duplicate directories and extra changed row fields must not be normalized into success.

### R10-3 — an uninstall veto remains invisible to these baseline image checks

Counterexample: keep the correct nonremovable install row and all other validated artifacts, but place its exact `/system/app/<bundle>` string in the image's `uninstall_list`, with no matching recovery. The actual BMS consumer skips it at lines 858-860. None of the three baseline image guards reads `uninstall_list.json`. The fixed source veto set is empty, so there is no established reason to permit such a packaged discrepancy for these required providers.

This is an additional selection boundary; the existing MMS install-row comparison alone does not close it either. Check target absence from the effective packaged veto set, honoring the actual recovery semantics. Do not describe a matching install row alone as proof that BMS installed the app.

## Minimal combined repair and regression request

1. Add one read-only exact-entry helper for the approved bundle paths, with duplicate-key/type/list validation, exactly one target directory, canonical runtime path and real boolean `false`. Apply it to source **and** actual extracted image configurations for Settings, Photos and Admin. Leave unrelated app entries and all existing capability/signature/permission constraints unchanged.
2. Read actual packaged `install_list.json` through `dump_unique_file`, preserving the existing unique `/etc/app/...` versus `/system/etc/app/...` protection. Save its actual image path, inode/hash and selected row in offline evidence. `--hap` mode can validate source selection only and must not report actual image selection checked.
3. Check effective targeted uninstall veto using the actual arrays/recovery contract and packaged file, retaining provenance. Do not broaden APL, signer privileges, ACLs, granted permissions, or uninstall policy to compensate for a wrong selection path.
4. Negative cases per target: missing row; wrong bundle directory; `/app/...` instead of runtime `/system/app/...`; trailing-slash alias; duplicate/conflicting directory; `removable:true`; numeric `0`/`0.0`; string `"false"`; missing removable field; malformed/duplicate-key JSON; correct source with bad image; correct image row with uninstall veto; ambiguous image aliases. Positive controls retain exactly the valid source row, other app rows, and original signer/grants. Preserve evidence from the already-running representative build; batch these known fixes before its next cycle.
5. Re-run new offline guards against the actual first packaged system image, then use that same new guest to verify BMS identity, source path, nonremovability and the intended provider behavior. Host fixtures, HAP build/signature success and static image checks do not satisfy that behavioral gate or authorize the remaining five-package matrix.

## Host reproduction

```sh
PYTHONDONTWRITEBYTECODE=1 LC_ALL=C LC_CTYPE=C LANG=C python3 docs/capability-audit/parallel/media/round10-install-selection/reproduce_selection_gaps.py --root /Volumes/PSSD/code/ohos-rs/ohos-qemu --output docs/capability-audit/parallel/media/round10-install-selection/host-observations.json
```

Final result on the pinned baseline: Settings/Photos policy helpers omit install/uninstall files in 8 isolated bad-selection cases; the real Admin source selection branch accepts numeric `0` and `0.0`, while positive boolean `false` passes and boolean `true` fails. The image extractor and unrelated Admin crypto/manifest dependencies are expressly controlled. These checks prove missing guard coverage and the comparison bug, **not** a valid real HAP, ext4 filesystem, package or guest. Temporary files were created only beneath this documentation directory and removed. An initial live-tree run failed its old-bug assertion because root had already introduced the stricter Admin helper; the final reproducible evidence is explicitly pinned to the original commit. Root owns final repairs and acceptance.
