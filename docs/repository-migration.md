# QEMU source repository migration

This is a source migration in progress. Package builds and runtime validation
are deferred by user instruction. Existing build scripts and patch application
remain the active build input until component source migration is complete.

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
OpenVPN and tool sources. The catalog also includes 16 source dependencies found in component recipes;
progress is recorded with the manifest.

The GitHub OpenHarmony-TPC organization was checked against the required M144
revisions. Its available repositories do not supply all required sources and
commits. TPC entries therefore use independent mirrors of the official GitCode
sources. The new manifest preserves checkout paths and linkfiles across separate
system, ArkWeb and external tool trees.

## Central synchronization

Synchronization scripts, upstream configuration and conflict issues belong to
`openharmony-qemu/mirror-sync`. Its registry is generated from the source catalog;
entries awaiting repository creation and authorization are disabled. GitHub forks
that lack a required locked commit are also synchronized from official GitCode.

The scheduled job runs daily at 19:23 UTC / 03:23 Asia/Shanghai. It fetches every
upstream branch, preserves full ancestry, updates the same branch names with
normal fast-forward pushes, and never deletes destination refs. Non-fast-forward
updates or concurrent changes create a deduplicated issue in `mirror-sync`, while
preserving the conflicting destination ref. QEMU development branches are excluded.

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
- `inventory_sources.py`, `export_source_changes.py`, `publish_source_changes.py`:
  inventory, review and publish component changes separately from build artifacts.
- `generate_manifest.py`: reproduce manifest selection and the six-product contract.
- `verify_remote_state.py`: audit repository defaults and QEMU branch SHAs through
  read-only API queries without altering source history.

Operation journals and source candidates remain under the ignored
`.tmp/organization-migration/` directory. Candidates are not published source
changes. The manifest's `migration-status.json` remains `in_progress` until all
repositories, baselines and source changes have been verified remotely.

Outstanding prerequisites include remaining repository creation and branch
publication, production synchronization of remaining mirrors, additional vendored
source dependencies, component patch review/publication. The system and ArkWeb locks require different
`web_webview` and bounds-checking revisions. Separate ArkWeb mirror repositories
preserve both locked source identities under the same QEMU branch convention.
No package/runtime acceptance is claimed.
