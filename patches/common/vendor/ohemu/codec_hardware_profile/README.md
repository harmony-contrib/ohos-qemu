# Truthful QEMU video codec capabilities

The fixed QEMU board does not include Rockchip OMX/MPP hardware. Its HDI 4.0
manager nevertheless reads media_codec_capabilities from the main hdf.hcs and
registers nonexistent OMX.rk AVC/HEVC encoders and decoders. The standalone
adapter and older alternative configuration repeat the same incorrect hardware
declarations. Selecting SOFTWARE in a test bypasses this defect.

Four independent diffs empty only those hardware video groups in the pinned
QEMU vendor. Existing root/config names, match attributes, transport choice and
all software/audio groups are preserved. Real AVCodec software AVC encoding and
software decoding remain supplied by their existing framework/backends. No SDK,
SysCap, permission, IPC, driver implementation or dayu200 configuration changes.
Do not advertise a software codec as hardware, rename it to OMX.rk, or claim
software HEVC encoding has been implemented by this change.

The common exact-state applicator rejects unknown edits, partial stacks, links
and another vendor revision, and applies before GN/preloader/traversal for both
profiles and all three ABIs. Native default-capability/CreateByMime and selected
name round trips must pass on a newly packaged guest before closure. HCS/HCB
compilation and removal of an incorrect advertisement alone are not that proof;
recording, screen capture, transcoding and HEVC require their own evidence.
