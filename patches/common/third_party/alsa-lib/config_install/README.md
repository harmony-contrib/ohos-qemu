# QEMU ALSA global configuration

The fixed 7.0 ALSA library defaults to an empty global configuration unless
`alsa_lib_feature_config_enable=true`. QEMU's HDI calls `snd_ctl_open("hw:0")`
and `snd_pcm_open("hw:...")`, which need real `ctl.hw` / `pcm.hw` definitions.
An empty configuration fails adapter enumeration, despite working ES1370
kernel nodes and a successfully published Audio service.

Both phone and 2in1 narrow profile overlays enable the existing feature.
Its complete upstream configuration dependency tree is installed in the chipset
image, matching the library's unchanged `/vendor/etc/audio/alsa/share` path.
This patch changes only configuration packaging, not ALSA ABI, permissions,
control-device ownership, or its global-config opt-in semantics.

The newly packaged representative guest must pass normal-app real Renderer
callbacks/frame progression, pause/flush/resume, invalid parameters/states and
release/recreation. Config/compile checks are not audio behavior acceptance.
Capturer input and actual host playback require separate data-path tests.

```sh
bash patches/common/third_party/alsa-lib/config_install/apply.sh --source-root /path/to/openharmony
```
