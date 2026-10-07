# Real USB Camera backend selection

Pinned peripheral source: `69094b77aa2200160207b1b06b3c0b586ae2157c`.
When real USB Camera is explicitly enabled, build the existing portable HAL on
x86_64 too. Preserve its existing off condition when USB is disabled, and do not
set `is_emulator`: that would enable the unrelated express-camera protocol.

Phone selects the paired `drivers_peripheral_camera_feature_usb=true` and
`drivers_peripheral_camera_use_commom_usb_camera_host_config=true`; the latter
installs the existing HCB that actually names `libcamera_external_usb_camera.so`.
Product-local masking is repaired by `vendor/ohemu/camera_profile` separately.

The second patch generates pipeline C sources and headers in the current
product's `target_gen_dir`, with explicit generator dependencies. Remove the
old source-tree `touch`/`cp` and source-only prebuilt installation: concurrent
products must not overwrite one another's pipeline data, and read-only source
compiles must not depend on write permission. Keep both real HCS inputs and all
pipeline nodes/implementations unchanged.

The third patch fixes the actual x86_64 full-GN failure with USB enabled:
the common adapter appended to an undefined `defines` list in an emulator
configuration. Initialize only when it was absent (or the original non-emulator
condition applies), retaining an already defined emulator list.

This is backend selection/configuration, not hardware or image acceptance.
A real USB camera or a correctly adapted kernel virtual video producer, capture
buffers, public preview/photo/video calls, permission denial/grant and lifecycle
tests are still required. Excluded from the frozen R6 first package.
