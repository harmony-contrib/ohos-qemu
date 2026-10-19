# Build and package validation

Batch all known fixes before starting a new representative package build. After
its complete runtime validation, collect all failures and repair them together
before the next build/package/validation cycle. Avoid rebuilding a package for
each individual fix. Finish an already-running representative attempt and
preserve its evidence when changing to this workflow.

When a change requires multiple QEMU artifact packages, build and package one
representative artifact first. Boot and validate that newly packaged artifact
against the behavior the change is intended to fix, including relevant boundary
and regression cases. Confirm the implementation direction from those results
before building and packaging the remaining artifacts.

Do not start an unattended full six-package matrix before this first-artifact
validation gate passes. Compilation, archive creation, static checks, or a test
against an older image alone do not satisfy this gate. If the first artifact
fails validation, fix it and rebuild/revalidate that artifact before proceeding.

Record the first package path, its checksum, test environment, commands, and
results with the build evidence. Validate the remaining packages as appropriate
for their architecture and device profile before delivery.

# Single development branch and agent coordination

All ongoing fixes land on `codex/ohos7-integrated-development` in this checkout.
Do not create agent branches or additional worktrees for this effort. Historical
branch tips and retired worktrees are recorded in
`docs/capability-audit/integration-20261019/README.md`.

The parent agent assigns disjoint file paths before parallel editing. An agent
must request reassignment before touching a path owned by another agent. Shared
build/package scripts, manifests, common verifiers, and this file belong to the
parent agent unless it explicitly delegates an exclusive edit. Do not overwrite
another agent's changes or use an old whole-file version to resolve a conflict.

Only the parent agent stages, commits, merges, switches branches, or removes
worktrees. Agents deliver changes in their assigned paths, with the changed-file
list and validation results; the parent reviews and serializes commits on the
single development branch.

The parent also schedules exclusive access to shared source/out trees, SDK and
signing state, containers, package builds, QEMU instances, HDC, and QMP. Agents
may run isolated host checks in private temporary directories when authorized;
they must not start or terminate shared processes or remove ownership markers.
Source-only candidates and historical evidence must be labeled separately from
active build wiring and newly packaged runtime validation.
