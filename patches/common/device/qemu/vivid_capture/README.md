# Built-in actual virtual video capture

Enable the fixed Linux 6.6 Vivid driver and required media core in all three
QEMU kernels; built-in, not a module absent from the package. Limit instances to
one. Existing framebuffer and DMA dependencies must survive real olddefconfig
and actual compilation. This is separate from Camera VDI selection and the
independent kernel Vivid capture-only defaults patch.

This is a kernel candidate, not a device/frame/runtime pass. Kernel fingerprint
and forced rebuild must include it in the next representative package; R6
does not include it. No world-readable video nodes or permission bypass.
