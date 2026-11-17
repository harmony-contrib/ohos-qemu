# QEMU JPEG photo capture

The fixed USB VDI advertises YUV/MJPEG, but the ordinary ArkTS JPEG photo
contract is a separate format. With the existing QEMU Vivid opt-in only,
advertise JPEG capture profiles backed by actually enumerated YUYV sizes and
the real CodecNode software encoder. Do not add JPEG preview/video profiles.

BLOB describes the encoded output, not a device MJPEG input. Prefer MJPEG only
when the device advertises it; otherwise feed real YUYV frames through the
existing encoder. Outside this opt-in, the upstream capture behavior remains
unchanged. Camera permission, actual node filtering and stream ownership are
unchanged. This is not a physical-host camera or advanced Camera backend.

Ordinary `PhotoOutput.capture()` supplies rotation and mirror but may omit
`OHOS_JPEG_QUALITY`, although the device advertises an ability default. The
virtual JPEG encoder now uses its existing high-quality default only for that
missing optional field. Explicit quality values retain their mapping, malformed
values fail, and the non-QEMU USB behavior is unchanged.

Apply after `usb_backend` (its product-output configuration generation is part
of the exact preimage) and `vivid_capture` (the feature declaration). Five
independent numbered files form one fail-closed component. Unknown or partial
edits are preserved, and a complete repeat is checked by full source hashes.
Compilation alone does not prove preview pixels, JPEG capture or package
acceptance: rebuild, package and run the ordinary Camera persona.
