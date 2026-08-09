# Full 2in1 profile for QEMU

This overlay makes the standard QEMU products source-built 2in1 products. It
keeps `rich.json` for the applications, SDK, code-signing, and other capabilities
already required by the runnable QEMU packages, then adds an effective profile
derived from OpenHarmony's `productdefine/common/inherit/2in1.json`. Because
later inherited parts win, shared components use the 2in1 feature selection.

Two current-master compatibility adaptations are intentional:

- stale `thirdparty:eudev`, `thirdparty:libsnd`, and `wukong:wukong` entries are
  omitted when their projects are absent from the checkout; current
  `ostest:wukong` is used when available;
- QEMU retains the community/default display VDI flags from `rich.json`, which
  are board requirements rather than a device-form choice.
- current Launcher/SystemUI prebuilt HAPs declare `default`/`tablet`, so the
  overlay sets `const.bms.supportAppTypes=2in1,phone,default,tablet` and keeps
  `applications:prebuilt_hap`. Without this compatibility declaration BMS
  rejects the desktop, and AccountMgr cannot finish activating user 100.

The generated `vendor/ohemu/virt/virt_2in1_full.meta.json` records the upstream
profile SHA-256, adaptations, and required parts. Packaging copies this evidence
and the resolved preloader parts into `device-profile.json`.

```bash
overlays/qemu_2in1_full/apply.sh \
  --source-root /path/to/openharmony \
  --product arm64_virt
```
