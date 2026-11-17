# Real software AVC runtime dependency

Add the exact backend required by the fixed AVCodec software encoder to its
component's service build group. Both QEMU profiles use the same implementation;
armv7a installs lib, arm64/x86_64 install lib64. Other products get an empty
QEMU-specific group and are not forced to load this backend.

Before touching source, verify each requested artifact's fixed revisions,
actual copied ABI header, current adapter inputs, complete notices, checksum,
ELF class/machine, SONAME, three exact exports and sole libc dependency. Refuse
stale/mixed-ABI artifacts, not silently reuse a prior local library. Package
the OpenH264 and statically linked LLVM runtime notices with the library.

This is packaging/provenance only. New-image normal-HAP encode/decode, real
challenged pixels/timestamps, dynamic bitrate/IDR, EOS, release/recreate and
malformed input remain required. It does not provide HEVC, a hardware encoder,
Audio Vivid or AudioSuite algorithms. Keep the first-package behavior gate.
