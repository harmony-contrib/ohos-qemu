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
