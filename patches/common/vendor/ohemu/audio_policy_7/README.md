# QEMU AudioPolicy 7.0 pipe schema

R6 actually reaches the audio services/ALSA config, but a fresh normal HAP fails
both Renderer Starts with result2 and zero PCM callbacks. The policy dump has
supportFlags=0 and no supported devices for every pipe. The fixed 7.0 parser
builds its device-route map from each streamProp.supportDevices and the pipe's
flag attribute; the old QEMU XML only declares device.supportPipes.

This numbered vendor patch supplies the reciprocal mappings and NORMAL flags
for the five existing pipes, uses schema2.0, fixes ignored buffer_size spelling,
and supplies real stereo buffer sizes for existing distributed routes. It adds
no device, permission, hardware capability, low-latency/offload route or fake
backend. The existing Speaker default and streams remain selected. Selection
of Bluetooth/distributed config is not proof that those devices are available.

The apply script checks the fixed vendor/audio_framework revisions, exact XML
preimage/candidate, and parser/map inputs before touching only this owned XML.
It refuses unknown edits or symlink inputs. Apply before traversal/preloader:

```sh
bash patches/common/vendor/ohemu/audio_policy_7/apply.sh --source-root /path/to/openharmony
```

The image check requires the exact repaired XML at AudioPolicy's preferred
chip_prod path. XML/map checks and compilation are not runtime acceptance: a
new first package must pass the normal-app Renderer create/start/PCM/pause/flush/
resume/stop/recreate challenge. Capturer needs separate permission/data tests.


The E repair changes only primary_input sampleRates from 44100 to 48000. Exact
F09 current XML/source and preferred chip_prod staging have SHA5adbfe3e7366d3cd20cfe2091cda8b295ecf1a889e3b4db4aef3a8c19afbf038.
The new final XML is SHAde3498e4246c439d27eb435237dda795ad73c1ff79eb942401e7219af5e35d04.
The original XML and the previous complete reciprocal-route XML are distinct
accepted upgrade inputs; neither qualifies as final image verification. New
component-local apply.py publishes exact payload bytes transactionally and rolls
back failed replacement. It retains the existing fixed vendor/framework revisions,
Git-original XML hash and all three parser/map source hashes from check.py.
Unknown source, mixed edits and symlink inputs remain errors. check.py also rejects
input44100/render48000 semantically even when a unit test disables the full hash.

The rate choice is backed by root's unchanged-F09 diagnostic and independent
replay: 75 same-boot snapshots, 18 with both playback pcm1p and capture pcm0c RUNNING,
each 48000/S16_LE/2ch; capture period4800/buffer24000, producer period1200/buffer4800.
That old image still failed positive microphone acceptance. These observations do
not prove the repaired image or its installed config: root must verify the new
image's preferred chip_prod XML and actual declared/applied rates, PCM challenge,
clock and independent Recorder decode after a representative build.
