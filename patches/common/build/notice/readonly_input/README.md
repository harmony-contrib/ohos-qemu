# Read-only NOTICE inputs

The pinned 7.0 collector reads license inputs but opens them with `O_RDWR | O_CREAT`.
This fails on an immutable source mount, and can create a missing source file
when the helper is called directly. Use `O_RDONLY` for the input only. Keep the
existing complete output merge, deduplication and writable output handling.
Missing inputs raise rather than becoming an invented empty license.

The independent numbered patch checks fixed build HEAD and the exact full known
source transformation; unknown edits are rejected. Apply before source traversal.
This does not certify license completeness for every package or pass a QEMU gate.
