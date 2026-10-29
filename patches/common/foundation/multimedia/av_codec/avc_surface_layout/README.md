# AVC input byte ranges and supported surface layouts

This independent component follows `avc_eos` and `software_avc` at the fixed
OpenHarmony 7.0 AVCodec revision. It changes only `avc_encoder.cpp` and
`avc_encoder_util.cpp`. It requires the complete prior EOS/input patch stack;
the old applicator recognizes this exact later wrapper overlay and does not
reverse old overlapping patches over it on subsequent preparations.

The actual `AVMemory::GetAddr()` returns the base address while `GetOffset()`
is stored separately. The software encoder previously encoded the prefix when
an application supplied a nonzero input offset. Apply the offset only after
checking the complete offset/size/capacity range.

For surface input, strides and plane offsets are bytes. Validate dimensions
against the configured encoder, RGBA's four bytes per pixel, even/aligned YUV
geometry and the complete chroma end against the allocation. Use 64-bit
arithmetic before converting to the fixed 32-bit ABI. Accept NV12/NV21's two
physical planes and explicitly validated three Y/U/V component views. Planar
I420 uses the contiguous U/V layout that the existing encoder actually reads;
different chroma strides or V gaps require a converter and are rejected.

The fixed QEMU gralloc returns NOT_SUPPORT for GetImageLayout. Keep its existing
contiguous fallback, with complete byte-range checks; this does not add support
for tiled or hidden padded YUV allocations without layout metadata. P010 has
no 10-bit converter in this encoder, so preserve UNKNOWN/error propagation
rather than routing its bytes into an 8-bit NV12/NV21 converter. This neither
removes a public SDK capability nor implements P010/HEVC.

When a surface frame fails conversion validation, return the acquired surface
buffer and clear its held buffer/fence before the existing asynchronous error.
The encoder keeps ERROR and emits no header/frame for that input. Other error
and lifecycle paths still need packaged runtime tests.

`test_batch_media_avc_surface_layout.py` runs the actual fixed wrapper functions,
the original scalar RGB/NV12/NV21 converters and the actual SendFrame control
flow under host ASan/UBSan. It checks challenged pixels, offset prefix, padded
UV starts, exact last-byte boundaries, unsupported/malformed layout rejection,
overflow and acquired-surface cleanup. Its small Surface/Memory/callback/backend
harness supplies contracts and call counters; it is not an OHOS HDI, a real
encoder backend, a HAP run or a package acceptance result. The two copied source
fixtures include their original license and pinned Git/hash manifest.

Before any gap can close, compile the actual full product TU(s), build the
central representative package, boot that new package and run the ordinary
application encode/decode/PTS/EOS/recreate gates plus the new public offset and
surface-layout cases. Complete recording, screen capture and transcoding need
their own real input/output/lifecycle validation. No package or ledger item is
closed by these host checks.
