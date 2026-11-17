# QEMU ALSA vendor path for OpenHarmony 7.0

The pinned OpenHarmony 7.0 Release `vendor_ohemu` configuration selects its
QEMU ALSA implementation through `drivers_peripheral_audio_vendor_alsa_path`,
but the matching 7.0 `drivers_peripheral` revision neither declares nor uses
that argument. Removing it makes arm64 and armv7a fall back to the nonexistent
`device/board/ohemu/<device>/audio_alsa` directory.

This component backports only the configurable vendor-path handling from the
upstream `drivers_peripheral` implementation. It keeps the 7.0 source baseline
and directs QEMU builds to the existing implementation under
`device/qemu/common/virt_full/audio_alsa`.
The component metadata declaration is included so OpenHarmony's product
feature loader accepts the existing vendor setting before GN generation.

OpenHarmony 7.0 also changed the ALSA adapter `SelectScene` and `Start`
callbacks to receive `AudioHwCaptureParam`/`AudioHwRenderParam`. The QEMU
vendor files still implemented the older pin/path arguments. The ABI patch in
this component updates both capture and render callbacks and obtains the
selected device pin from the 7.0 hardware parameter structure.

The 7.0 ALSA adapter also calls vendor-provided `CaptureGetSceneDev` and
`RenderGetSceneDev` hooks. QEMU exposes only its default ALSA PCM device, so
the component supplies both hooks and returns ALSA's `-1` default-device
selector for every scene.

The in-tree emulator ALSA implementation selected by x86_64 contains a second
7.0 regression: its capture scene callback assigns an undeclared `descPins`
identifier instead of reading the new hardware parameter. The final patch
repairs that callback and adds the matching render-parameter null check. This
path is not selected by the arm64 product, so the issue must be covered by the
x86_64 build and the component fixture. The x86_64 implementation also lacks
the capture/render scene-device hooks required by the 7.0 ALSA core; the next
patch supplies the same default-device behavior as the QEMU vendor path.

The first patch also repairs source trees that had the obsolete workaround
applied. On a clean pinned checkout it is recognized as already present, so the
same component entry point works for both clean and previously prepared trees.

```sh
bash patches/common/drivers/peripheral/audio/apply.sh \
  --source-root /path/to/openharmony
```
