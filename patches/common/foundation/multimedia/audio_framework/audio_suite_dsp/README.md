# QEMU AudioSuite CPU DSP

This component builds `libqemu_audio_suite_dsp.z.so` from source and routes only
EQUALIZER, SOUND_FIELD and ENVIRONMENT_EFFECT to its real implementation. It does
not impersonate the absent vendor `libimedia_sws`, or declare missing AI plugins
supported. It checks fixed audio_framework commit and exact iMedia ABI hash before
changing source. Existing unknown files are preserved and rejected.

The public equalizer's ten bands (31 Hz to 16 kHz, +/-10 dB) use peaking biquads;
coefficients follow the mathematical formulas in the [W3C Audio EQ Cookbook](https://www.w3.org/TR/2021/NOTE-audio-eq-cookbook-20210608/).
Sound-field modes use stereo mid/side widths. Environment modes apply radio,
telephone, underwater or phonograph filtering; the phonograph also has bounded
soft clipping. This is a deterministic QEMU CPU implementation, not a claim of
bit-identical proprietary effects or calibrated acoustic reproduction.

The pinned wrapper passes 48 kHz stereo Q31-container/16-bit PCM, 480 samples,
master gain 15. Other internal ABI formats are rejected instead of reinterpreted.
Parameters, scratch size, kind, channels and frame bounds are validated before
processing. No allocation or locks occur in the audio processing loop.
The three mandatory `iMedia_*_GetSPECS` entrypoints describe exactly the
implemented 48 kHz stereo S16LE pipeline format and 480-sample frames. The
wrapper converts these frames to/from Q31 words. Hard realtime and absent
formats/algorithms are not advertised. The image checker requires all 19
entrypoints; the old 16-symbol implementation cannot create actual effect
nodes even when the library loads. Only the exact known old generated sources
are migrated; foreign changes remain rejected and preserved.
The separate `audio_suite_library_path` component retains canonical-path security
and adapts the XML's lib64 paths to ARM32's lib directory.

Run `bash apply.sh --source-root ROOT` before product metadata traversal. Package
depends on the real `audio_framework_feature_audiosuite_support` flag; phone has
that official capability, not a placeholder feature. Compile/source/host signal
tests do not close guest API acceptance or the representative-package gate.
Noise reduction, audio separation, voice effects, tempo/pitch and spatial/HOA
algorithms remain separate missing dependencies. Download support is not repaired
by this component.
