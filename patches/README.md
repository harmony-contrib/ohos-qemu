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
