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

The repository supplies `ci/capability-audit/build_project_quota_probe.py` and
`run_project_quota_diagnostic.py` for a fresh disposable packaged boot. The test
allocates a new directory and an unused random project ID, writes through UID
65534 with no effective/permitted capabilities, requires real EDQUOT below a
2 MiB hard limit, observes accounting decrease on deletion, restores the limit,
and requires a 4 MiB write to succeed. It removes its file/directory and checks
zero residual usage/limits before reporting success. It never remounts /data,
sets an application quota, changes global quota activation, or attaches to an
existing guest. A missing project format or mount option fails, not skips.

Build with `--sdk <native-sdk> --arch arm64 --output <new-build-directory>`.
Run with `--archive <new-package.tar.gz> --probe <build>/project-quota-runtime
--output <new-evidence-directory> --hdc <hdc>`. Retain `build.json`, the entire
boot evidence and `diagnostic.json`. This narrow kernel test deliberately closes
no Storage API ledger entries; the ordinary/service API tests remain separate.
