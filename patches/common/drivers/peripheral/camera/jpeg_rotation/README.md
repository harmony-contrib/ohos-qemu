# Deterministic USB Camera JPEG rotation

Pinned peripheral revision: `69094b77aa2200160207b1b06b3c0b586ae2157c`.
Apply `apply.sh --source-root ROOT` before the Camera source is compiled. The
guard accepts only the original or repaired whole file at that revision,
rejects source symlinks and unknown edits, and verifies the result after patching.
When the later `jpeg_capture` component has also repaired optional JPEG quality
in this same TU, the guard accepts only that exact combined SHA-256 state on
repeat application; it still rejects unknown or partial edits.

`RotJpegImg` passed an uninitialized marker-copy enum and partially initialized
`jpeg_transform_info` to libjpeg-turbo. Initialize the complete transform and
copy all optional markers, preserving EXIF, ICC and comments through the real
upstream transform, including its existing EXIF dimension adjustment. Keep the
existing orientation mapping, `perfect=TRUE`, `trim=FALSE`, and JPEG quality.

When a lossless rotation is not perfect for the input MCU dimensions, destroy
both JPEG objects. Create the memory destination only after the workspace check
succeeds: its allocation otherwise leaks when the caller sees output size zero.
The existing caller keeps its original encoded JPEG on this rejection. Public
interfaces, metadata parsing, rendering backends and permissions are unchanged.
No GN or dependency changes are required.

`ci/capability-audit/check_camera_jpeg_rotation.py` applies the component twice in
an owned `/tmp/camera-jpeg-*` copy, extracts the exact repaired rotation function
for a real libjpeg-turbo 3.1 regression, and compiles the complete candidate CPP
for arm64, armv7a and x86_64 using each completed Camera scratch graph's actual
`ninja -t commands -s` command. It changes only the candidate source, object and
depfile arguments; matching generated headers, flags and dependencies remain
the real GN outputs. All original scratch graphs and evidence remain intact.

The runtime regression checks four orientations, decoded pixels/dimensions,
EXIF/ICC/comment preservation, non-MCU-aligned rejection and 400 rejection
replays. Linker wrappers count real JPEG object creation/destruction and memory
destination calls; AddressSanitizer also checks the host regression for leaks.
An original-source rejection run must fail before the candidate is accepted.
These are component/host checks. A newly packaged first QEMU artifact must still
boot and pass ordinary-app photo/preview and relevant boundary/regression tests
before any remaining package matrix is built.
