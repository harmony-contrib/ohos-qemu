# OpenHarmony QEMU component patches

The patch tree follows OpenHarmony component ownership. Every leaf component
has its own `apply.sh`; stable source edits are stored as independent unified
diff files, while generated product profiles and architecture products keep
their deterministic generators beside the component entry point.

- `common/`: patches shared by phone and 2in1.
- `phone/`: phone-only product profile and standalone aggregate entry point.
- `2in1/`: 2in1-only product profile and standalone aggregate entry point.
- `lib/`: strict idempotent patch application and shared orchestration only.

The old `overlays/` entry points are intentionally removed. Apply either
`phone/apply.sh` or `2in1/apply.sh`, or invoke an individual component leaf.

The shared accessibility leaf also extends the system `ohos-a11yManager` so
QEMU tests can enable an arbitrary installed accessibility extension without a
separately compiled guest helper.

The shared audio leaf carries the minimal upstream vendor-ALSA-path support
needed by the pinned 7.0 Release sources. This keeps the QEMU product's existing
`device/qemu/common/virt_full/audio_alsa` selection instead of falling back to a
nonexistent board-local directory.

The shared `build/github_lfs_assets` leaf restores the exact binary objects
whose GitHub mirror entries are former-LFS text stubs. Its pinned map and
component entry point run before any build traversal.

The `common/standard_vpn/components/qemu_mesa` leaf also imports its pinned
historical Mesa revision from a host-verified GitHub cache during patching, so
the later Ninja source build does not depend on missing checkout history.
