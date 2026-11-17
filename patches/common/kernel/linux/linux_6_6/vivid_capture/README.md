# QEMU capture-only Vivid defaults

Pinned GPL-2.0-only Linux source `14c77f1541a53e814d89ad6dea5f7f211f9895a6`.
Retain the real Vivid driver, streaming/buffering, test-pattern controls and
timestamps; change only default node_types to Video Capture and input count to
one webcam. No radio, SDR, VBI, output, metadata or touch devices by default.
Explicit module parameters are still honored by Linux. Max instances one comes
from the separate three-kernel QEMU defconfig component.

The fixed module-parameter help strings describe upstream defaults, not these
QEMU defaults; actual source/boot values are acceptance evidence. No source
license removal, API stubs or Camera permission changes. Actual kernel compile,
fresh image boot and challenged normal-app frame tests remain mandatory.
