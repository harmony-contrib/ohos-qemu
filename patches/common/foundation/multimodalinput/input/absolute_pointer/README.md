# QEMU absolute pointer component

This component maps `virtio-tablet` absolute events to the active guest
framebuffer. It is a single idempotent unified diff owned by the
`foundation/multimodalinput/input` component.

```sh
bash patches/common/foundation/multimodalinput/input/absolute_pointer/apply.sh \
  --source-root /path/to/openharmony
```
