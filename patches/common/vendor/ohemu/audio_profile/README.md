# ALSA board inheritance

The fixed QEMU product configs declare an empty `alsa-lib` component locally.
hb replaces the inherited whole component with that local entry, silently
discarding feature settings in phone/2in1 profiles. Move only that unchanged
empty entry into the shared QEMU board profile, before generating the final
device contract overlay. Other local parts remain untouched; the generic
product-local shadow rejection remains strict.

Apply after creating the ARM32 product, before enabling either device profile.
ARM64/x86_64 and the optional generated ARM32 config use independent patches.
The original `alsa-lib` selection is preserved even with both full profiles
disabled. Nonempty/drifted local ALSA entries do not apply cleanly.

```sh
bash patches/common/vendor/ohemu/audio_profile/apply.sh --source-root /path/to/openharmony
```
