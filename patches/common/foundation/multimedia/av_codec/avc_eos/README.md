# AVC wrapper EOS and real input bounds

The pinned software wrapper reuses output buffers. Its EOS branch sets only
the flag, leaving stale memory size/PTS, and ignores the backend's return code.
Reset size/PTS from the actual backend result only after success. Report an
actual backend failure through OnError and retain ERROR rather than claiming
EOS completion. No source outside these exact changes is overwritten.

The second independent patch makes InputFrame strides consistently byte-based
for RGBA in buffer and surface modes; the converter still receives pixels per
row. The original buffer path checked width * height but actually read four
bytes per pixel, accepting truncated RGBA input. Size calculation now uses
positive, aligned strides and even positive heights with int64 arithmetic;
YUV calculation also avoids multiplying the full product by three first.
Existing valid RGBA/YUV conversions, errors, public signatures and permissions
are retained. This is not a replacement codec or a claim of media pipeline
completion.

This shared component is applied before software-backend packaging for both
profiles/all native ABIs. The source guard accepts only pristine fixed HEAD
or the complete earlier EOS repair or this complete two-patch repair. Partial
new input changes, unknown edits and linked inputs are rejected. Compile and
new-package callback/packet/EOS/input-boundary tests remain
required; source inspection or a flag alone is not media API acceptance.
