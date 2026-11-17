# M144 OpenH264 software AVC backend

The fixed AVCodec wrapper dynamically loads `libavcenc_ohos.z.so` and requires
`InitEncoder`, `EncodeProcess` and `ReleaseEncoder`. The base image lacks this
backend; a working decoder or RK-specific hardware codec is not a replacement.

Build the adapter with M144's existing, pinned OpenH264 source at
`652bdb7719f30b52b08e506645a7322ff1b2cc6f`. Its source uses the BSD license;
keep the original license alongside generated artifacts and final packages.
Do not use a moving master or an unsigned downloaded binary. The adapter uses
the actual header from AVCodec `e5c525670d1f6622d441c9e5bf975ea0579ea177`,
verified by SHA-256 before copying, so the 32-bit ABI is not guessed.

The backend emits real Annex-B parameter sets and encoded access units,
preserves timestamps, honors dynamic bitrate and explicit IDR requests, and
uses no delayed frames. It supports the wrapper's advertised Baseline/Main
profiles and planar YUV420 (the wrapper converts its NV12/NV21/RGBA inputs).
Unsupported profiles, malformed planes, invalid configuration and insufficient
output buffers fail rather than returning fabricated encoded data. No hardware
encoder, HEVC, Audio Vivid, or AudioSuite algorithm is claimed by this repair.

This is a candidate implementation. Require source/three-ABI compilation,
memory-safety and negative tests, and actual new-image ordinary-HAP AVCodec
encoding plus decoded-frame checks and release/recreate/EOS boundaries before
marking it repaired. Building the dependency is not QEMU package acceptance.
