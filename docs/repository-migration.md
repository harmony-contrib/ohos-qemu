# QEMU source repository migration

Component source changes and adaptation inputs have been published and verified.
Final upstream mirror verification is still in progress; the manifest lock remains
incomplete until it passes. Package builds and runtime validation are deferred by
user instruction. The historical patch tree and 77 source helpers in this checkout
now link to generated component inputs, with the original files preserved locally.

## Ownership and branches

- Organization: <https://github.com/openharmony-qemu>
- Manifest: <https://github.com/openharmony-qemu/manifest/tree/OpenHarmony-7.0-Release-qemu>
- Central synchronization: <https://github.com/openharmony-qemu/mirror-sync>
- Every maintained component uses `OpenHarmony-7.0-Release-qemu`, including
  unpatched components. Future major baselines use the corresponding release name.
- Component repositories own their source changes. The eventual build repository
  consumes these branches and must not maintain a second patch application stack.

The catalog in `migration/repositories.json` tracks distinct
repositories across the OHOS 7.0 source lock, ArkWeb M144 source lock, Serial SIG,
OpenVPN and tool sources. The catalog also includes source dependencies found in component recipes,
including the separate historical Mesa 21.3 and SDK LLVM 15 inputs;
progress is recorded with the manifest.

The GitHub OpenHarmony-TPC organization was checked against the required M144
revisions. Its available repositories do not supply all required sources and
commits. TPC entries therefore use independent mirrors of the official GitCode
sources. The new manifest preserves checkout paths and linkfiles across separate
system, ArkWeb and external tool trees.

## Central synchronization

Synchronization scripts, upstream configuration and conflict issues belong to
`openharmony-qemu/mirror-sync`. Its registry is generated from the source catalog;
all 186 required daily mirrors are enabled. GitHub forks that lack a required
locked commit are also synchronized from official GitCode.

Component repositories have GitHub Actions disabled. Imported upstream workflow
files remain part of the source history, but do not launch upstream build matrices
when mirrored branches are published. Central synchronization remains enabled in
`mirror-sync`; future package CI belongs to the separate build repository.

The scheduled job runs daily at 19:23 UTC / 03:23 Asia/Shanghai. It fetches every
upstream branch, preserves full ancestry, updates the same branch names with
normal fast-forward pushes, and never deletes destination refs. Non-fast-forward
updates or concurrent changes create a deduplicated issue in `mirror-sync`, while
preserving the conflicting destination ref. QEMU development branches are excluded.

An upstream branch rewrite is recorded separately from the fixed QEMU baseline.
Migration evidence verifies the preserved destination SHA and the matching open
issue in `mirror-sync`. Such a reported upstream conflict can coexist with a
complete QEMU source migration; conflicts on the fixed baseline or QEMU branch
still prevent completion. Outstanding upstream conflicts remain explicit in
`migration-status.json`.

The former sync installations in `global_i18n`, `developtools_smartperf_host` and
`device_soc_rockchip` are retired through signed deletion commits affecting only
the four migration-owned sync/configuration files. Source tree contents are
preserved. The removal commits and original-to-hosted baseline mappings are
recorded in the manifest repository's `migration-evidence/mirror-sync/` directory.

GitHub rejected deploy-key creation because deploy keys are disabled for these
repositories. Central CI therefore supports a GitHub App (recommended) or a
fine-grained PAT restricted to target repositories. Configure `MIRROR_APP_ID`
and `MIRROR_APP_PRIVATE_KEY`, or `MIRROR_TOKEN`, in the central repository as
documented there. App authorization is now configured, and the first production
sync of all 326 `global_i18n` upstream branches was verified against remote SHAs.
Production verification records are archived with the manifest. A `prepare_only`
diagnostic run never publishes branches.

Long uploads use repository-scoped App tokens renewed before expiry. Git LFS
credential caching is disabled so a long-running transfer can obtain a fresh
token. The current token is revoked when the job finishes.

GitHub's large-blob limit requires LFS history conversion in some independent
mirrors. Original upstream SHA and hosted SHA are distinct identities and must
be retained in source provenance; do not silently substitute one for the other.

## Local migration utilities

These scripts are administrative tools, not build-time dependencies:

- `create_repositories.py`: create reviewed forks or independent mirrors,
  recording an append-only journal and preserving existing repositories.
- `publish_baselines.py`: establish missing QEMU branches from source locks.
- `setup_mirror_ci.py`: generate the **central** mirror registry; it never adds
  workflows to component repositories.
- `import_mirror_baseline.py`: create a missing QEMU branch from a centrally
  synchronized baseline, without adding automation to the source tree.
- `retire_component_sync.py`: remove the three reviewed legacy installations.
- `configure_source_automation.py`: disable component Actions and cancel automatic
  CI triggered by this migration, preserving unrelated manual workflow runs.
- `inventory_sources.py`, `export_source_changes.py`, `publish_source_changes.py`:
  inventory, review and publish component changes separately from build artifacts.
- `generate_manifest.py`: reproduce manifest selection and the six-product contract.
- `verify_remote_state.py`: audit repository defaults and QEMU branch SHAs through
  read-only API queries without altering source history.
- `stage_component_recipes.py`, `stage_source_helpers.py`: assign tracked patches
  and source preparation helpers to their owning repositories. Cross-component
  patches are split at file boundaries and retain exact reconstruction hashes.
- `verify_component_payloads.py`: verify published component bytes and modes
  against the manifest ownership index and publication lineage.
- `harvest_completed_mirrors.py`, `publish_ready_components.py`: collect completed
  synchronization evidence and resume explicitly reviewed source publications.
- `snapshot_publication.py`: archive full journals and derive the manifest lock.
  Its completion checks require matching remote refs/defaults, current export
  fingerprints, component payloads, production mirror evidence and input cutover.
  When later local edits exist, `--verified-inputs` checks an independent exact
  reconstruction and the preserved original files. It also verifies the active
  compatibility links, backs up changed local inputs, and records them as
  unpublished work. It never replaces those edits or includes them in the lock.
- `scripts/prepare_component_inputs.py`: retrieve locked component inputs and
  invoke the component-owned materializer. It performs no patch application,
  compilation, packaging or guest validation.

The manifest's `adaptations.json` contains ownership and checksums only. Editable
recipes live under `.qemu/adaptations/` in their component repositories; the
generic materializer belongs to `openharmony-qemu/build`. A generated compatibility
tree preserves existing relative imports. It is not another editable patch stack.
Historical recipes retain their original source checks; transferring them does
not establish that the deferred build entry point accepts the new branch graph.

Operation journals and source candidates remain under the ignored
`.tmp/organization-migration/` directory. Candidates are not published source
changes. The manifest's `migration-status.json` remains `in_progress` until all
repositories, baselines and source changes have been verified remotely.

All 695 catalog repositories have been created. All 105 reviewed component source
changes are published, and all 2,160 original adaptation inputs have been verified
against 104 owning repositories. Remaining prerequisites are the last baseline
branches, complete production synchronization, and the final manifest lock. The system and ArkWeb
locks require different
`web_webview` and bounds-checking revisions. Separate ArkWeb mirror repositories
preserve both locked source identities under the same QEMU branch convention.
No package/runtime acceptance is claimed.

## Retrieve historical component inputs

After `components.lock.json` is complete, a fresh checkout can retrieve the
component-owned compatibility inputs with:

```sh
git clone --single-branch --branch OpenHarmony-7.0-Release-qemu \
  https://github.com/openharmony-qemu/manifest.git .qemu/manifest
python3 scripts/prepare_component_inputs.py --manifest .qemu/manifest
```

The retriever requires committed manifest documents and the exact locked component
SHAs. It verifies the component-owned materializer and all reconstructed hashes
and file modes. Generated files live under ignored `.qemu/component-inputs/`;
`patches` and the transferred helper paths are compatibility links. Keep changes
in the owning component repositories instead of editing this generated tree.
If that directory already contains local work, select a fresh `--output` directory
for verification and preserve the active directory until those changes are moved
to their owning components. Migration status lists any preserved unpublished inputs.
The manifest records the six-product contract in `products.json`. The independent
build entry point and package/runtime acceptance remain deferred.
