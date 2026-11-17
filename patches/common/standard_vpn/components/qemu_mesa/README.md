# QEMU Mesa

This component replaces the stale QEMU GPU prebuilts with a source build of
OpenHarmony Mesa 21.3.3 at commit
`995d2506d18924b48db0cf40e6ad7de04fc4e558` and applies the OHOS logger fix.

The pinned OpenHarmony 7.0 checkout contains Mesa 25.0.1 and does not retain
that historical object when populated from the GitHub project mirror. Before
the build graph is traversed, `apply.sh` imports the exact, host-verified
revision from `QEMU_MESA_REVISION_CACHE` without changing the Mesa worktree
HEAD. Prepare that cache with:

```sh
bash scripts/prepare_qemu_mesa_revision_cache.sh
```
