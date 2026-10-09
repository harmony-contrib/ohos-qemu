# Real userdata quota support

Read-only R23 guest queries confirmed user/group accounting works, while project
quota queries fail with ESRCH. The QEMU-specific userdata format omitted the
official image builder's `--prjquota` option. Its launchers also omitted quota
mount options: Linux F2FS then enables usage accounting but not limit enforcement.

This component follows the existing shared F2FS/VPN format patch. It adds real
project quota inodes and extra inode attributes through the existing mkf2fs
builder. The packager separately requires the real quota/extra-attribute/verity
feature bits and launches with usrquota, grpquota and prjquota on every host.
It never changes a running mount, existing image, app permission or quota limit.

New-image accounting, actual owned-file growth/deletion, limit rejection and
recovery, and the Storage service API remain required runtime validation. Static
feature bits and root query success alone cannot close the Storage audit gap.
