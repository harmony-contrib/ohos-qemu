# QEMU RenderService YUV layer fallback

On QEMU, the OHOS Mesa EGL dma-buf import path only accepts RGB formats. The
Camera preview and other media surfaces use NV21/NV12; importing them as an
EGL image fails and leaves an otherwise valid preview black. This component
routes only those YUV layers through RenderService's existing CPU YUV-to-RGBA
conversion. RGB layers and the render backend remain unchanged.

The build script applies this patch to the pinned OpenHarmony 7.0
`foundation/graphic/graphic_2d` source before GN traversal. The component
script is idempotent and verifies the resulting patch state.
