# SceneBoard runtime assets for QEMU 2in1

The 2in1 build enables the SceneBoard window architecture. The OpenHarmony
7.0 prebuilt SceneBoard HAPs carry provisioning profiles that expired in 2023,
and its entry HAP does not contain both native libraries for all three QEMU
guest ABIs. Stage renewed HAPs in `SCENEBOARD_RUNTIME_ASSET_ROOT` (default
`/Volumes/PSSD/qemu/artifacts/sceneboard-runtime`) before building a 2in1
product. Phone builds do not use these assets.

Required files:

| File | SHA-256 |
| --- | --- |
| `SceneBoard.hap` | `8c5a973d79142d42303f2d551dd7573ab63b412891f91d14c9a2285aa97a492e` |
| `NotificationManagement.hap` | `92ea8841aa9b1b52220fd0a9b4ae7de140c802bc95b002abc8202ec5c43f9458` |
| `ThemeService.hap` | `cc90b410e637ba97d8d31760821088b964c1d4702bab9db4a1b515cf4bf1fb08` |
| `ThemeComponent.hap` | `adb16b26d2acc7d1e60ad70b8225dfc420635763fc63e4e27307eb11f0aee399` |

These are based on `applications/standard/hap` revision
`f2e956a5dd26102f85c86e91d2bfd7c0998534f8`. The entry HAP native
libraries were built from the OpenHarmony SceneBoard revision
`27befcf82a71047a585d725bb8c7805031472e86` for `arm64-v8a`,
`armeabi-v7a`, and `x86_64`. Each ELF was signed, and all four HAPs were
re-signed with the OpenHarmony development certificate and a system-app
provisioning profile valid from 2026-01-01 through 2040-01-01. The profile
includes `AllowAppUsePrivilegeExtension`, which BundleManager requires for
three SceneBoard modules; all four renewed HAPs were installed successfully
in an arm64 QEMU guest. They are
development image assets, not release-key signed applications.

The entry HAP also corrects the first-user unlock event. Its original
`ets/modules.abc` SHA-256 is
`4866846a48fa6247ce48edf449fc306c5ce1a2f19f7338f6377621c5130b1549`;
the patched SHA-256 is
`f1ceb224f8ffa56181c5de199db9bcf7e3c25a84d4dd538f8600330019d63759`.
The patch replaces `common.event.UNLOCK_SCREEN` with the AbilityManager 7.0
event `usual.event.SCREEN_UNLOCKED`. Headless 2in1 boots cannot interact with
the black lock surface, so the QEMU product also installs
`qemu_2in1_unlock.cfg`. It runs CEM after boot completion, when AbilityManager
has subscribed and the foreground account is ready. AbilityManager requires
both `usual.event.USER_UNLOCKED` and `usual.event.SCREEN_UNLOCKED` for the same
user before it removes the first-boot interceptor. The config publishes the
first event with user 100 as its common-event code and the second with user
100 in its Want. The accompanying CEM patch makes `cem publish -u` include
`userId` in the event Want while routing the event through the current user.
The init configuration is
part of the 2in1 product profile and is removed when that profile is disabled.

`apply.py` verifies HAP signatures, bundle/module identities, profile
validity, privileged-extension capability, native ELF architecture, and
records the actual HAP hashes in the
product metadata. The package verifier then compares those hashes with the
files installed in `system.img`.
