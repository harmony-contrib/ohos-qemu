# GNSS rejected GN assignment and exact predecessor migration

Root reported the first representative full build ending after 840.7 seconds
with exit 1: `external_gnss/BUILD.gn` assigned the unused `output_prefix` variable.
This batch removes only `output_prefix = ""`, retaining the existing supported
`output_prefix_override = true`. Root preserves the original failure evidence
and owns the next combined prepare/GN preflight and full package attempt.

Base: `f82275e`; branch: `codex/apps-gnss-prefix-20261017`. The earlier apps
branch is preserved separately; this branch starts from the root baseline to
avoid replaying components already integrated there.

Actual upstream target changed:
`device/qemu/common/virt_full/external_gnss/BUILD.gn`.

| Version | BUILD.gn SHA-256 |
| --- | --- |
| Exact installed predecessor | `436e42030c3e582156b8f9e11a265b4e153890c2c72a4f5d7ed2907245175330` |
| New final | `a33e9ad3ab6652be5e57eb1b310f31652f1b1491b1221dad79d6684a68ad4f16` |

The manifest changes only this final hash and the exact predecessor declaration.
The three original source before/after hashes, four other overlay hashes, HDI
patch hash, actual ABI-header hash, and both fixed upstream project revisions
remain unchanged. The installer also verifies that the new BUILD is exactly
the predecessor with the rejected assignment removed.

The installer recognizes three complete states: pristine sources with no
overlay, the exact predecessor with all three patched original files and all
four other final overlays, or the complete new final state. It rejects every
unknown or mixed state. Both Git projects must exist, resolve to their own
toplevel, contain a real commit object, and match the pinned revision. Normal
repo `.git` metadata symlinks remain supported; source and parent symlinks are
rejected. The root task independently confirmed those two actual project
toplevels in the source inspector; this agent did not query the active source.

For pristine sources only, the original HDI patch is applied in a temporary
candidate and all final bytes are checked before writing. For a predecessor,
the installer does not replay that patch and writes only BUILD. A complete
final installation is a no-op. The full source state is rechecked before and
after writes. Writes retain original modes and use atomic rename. Failures
restore touched files. If rollback fails, a reported `qemu-gnss-recovery-*`
directory retains original bytes and an `original.json` mode/hash manifest.

Host verification command, exit 0:

```sh
LC_ALL=C LC_CTYPE=C LANG=C PYTHONDONTWRITEBYTECODE=1 \
PYTHONPATH=ci/capability-audit python3 -m unittest \
  test_batch_system_gnss_installers \
  test_batch_apps_external_gnss_migration -v
```

Result: 27 tests passed in 23.165 seconds: the existing 10 installer cases and
17 migration cases. The fixture uses real local Git repositories and private
synthetic commit pins only in a copied component manifest; production upstream
revision pins are unchanged. Tests cover fresh installation, two final replays,
exact legacy migration without `git apply`, untouched-file inode/time/mode,
each original and other overlay mismatch/missing state, ABI mismatch/missing,
both missing/wrong/invalid project identities, source/parent symlinks, normal
repo metadata symlinks, a different predecessor declaration, write failures
before/after rename, failed postvalidation, and retained rollback-failure
recovery bytes.

This batch runs no Docker, source/out mutation, GN, SDK, compiler, QEMU or HDC.
It does not establish GN success, new-image inclusion or guest GNSS behavior.
The first-artifact gate and all capability closure statuses remain unchanged.
