# Full phone profile for QEMU

This overlay adds a current-tree-compatible profile derived from OpenHarmony's
`productdefine/common/inherit/phone.json` after the QEMU rich base profile.
It removes unavailable legacy entries, maps the current Wukong part, preserves
the QEMU community display VDI, and keeps the prebuilt Launcher/SystemUI part.

Because those system HAPs currently advertise `default`/`tablet`, the shared
QEMU product parameter accepts `2in1,phone,default,tablet`. This lets a genuine
`deviceType=phone` boot finish its first-user activation.

The generated `vendor/ohemu/virt/virt_phone_full.meta.json` is consumed by the
packager to produce auditable `device-profile.json` evidence.
