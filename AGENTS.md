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
