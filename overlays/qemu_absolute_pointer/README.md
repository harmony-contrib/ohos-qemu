# QEMU absolute pointer synchronization

QEMU scales graphical frontends independently from the guest framebuffer.
A relative `virtio-mouse` therefore cannot preserve host click coordinates
when the window, HiDPI scale, or guest GPU resolution changes.

This overlay teaches OpenHarmony MMI to handle
`LIBINPUT_EVENT_POINTER_MOTION_ABSOLUTE` with libinput's transformed absolute
coordinate API and the current display's valid dimensions. Packages built from
the patched source use `virtio-tablet-pci`; relative mouse and touchpad paths
remain unchanged.

Apply it with:

```bash
overlays/qemu_absolute_pointer/apply.sh --source-root /path/to/openharmony
```
