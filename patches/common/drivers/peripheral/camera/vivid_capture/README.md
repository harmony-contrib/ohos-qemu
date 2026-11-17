# QEMU real V4L2 virtual capture

Opt-in phone feature for the pinned USB Camera VDI. Accept the actual kernel
driver `vivid`, card `vivid`, bus `platform:vivid-000` only, preserving its actual
name/metadata derivation. Use per-node device_caps, not aggregate capabilities:
output/meta/multiplanar-only/non-streaming nodes are not a single-planar capture
device. Bounded driver/card/bus strings cannot over-read ioctl output.

The kernel's independent Vivid component must supply the real streaming node.
Do not fake a camera ID, buffers or success without it. Existing USB device
filtering, camera_host-only /dev/video permissions and public application Camera
authorization are unchanged. Outside the phone feature the virtual node is not
accepted. This does not validate advanced modes, host-camera input, preview,
photo/video or guest lifecycle; excluded from R6 frozen inputs.
