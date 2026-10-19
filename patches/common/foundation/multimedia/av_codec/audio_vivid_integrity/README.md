# AudioVivid sink metadata integrity

This bounded repair changes only `AudioSink::CopyAudioVividBufferData` in the
actual prepared av_codec e5c525670d1f6622d441c9e5bf975ea0579ea177 source.
The complete source preimage is pinned in `manifest.json`; unknown files and
linked paths fail unchanged. Reapplying the exact payload is idempotent.

The old function dereferenced a null metadata object, accepted missing or wrong
metadata after logging, and committed PCM counters before copying metadata.
It also used the requested copy size as destination capacity and ignored the
AVMemory offset. The repair checks the source memory and destination ranges,
queue counter, metadata object, actual typed metadata and exact metadata size
before publishing lengths, PTS or consumption. Both secure copy failures leave
those counters unchanged. A failed copy may have touched destination memory;
the failed descriptor is never published as valid output.

Compressed pass-through shares this helper and remains valid without AudioVivid
metadata. EOS handling remains in the existing caller before this function.

This does not implement the external `libAudioVividMetaBuilder.z.so` metadata
builder, the separate `libaudio_integration_mcr.z.so` spatial converter, a decoder,
or an onset clock. The metadata/plugin finding remains
open until a newly packaged image has a real compatible plugin and an actual
metadata-bearing decoding/rendering test. The source export and controlled
function harness are not that runtime proof. Root owns active manifest/build
wiring, native/CFI compilation, the fresh representative package, and guest
validation before the other five packages.
