# Fixed Wallpaper renderer source packaging candidate

`applications/standard/theme` is pinned to
`a436a43f1c0948fa12df6d520ec695ae4388a057`. This component adds `BUILD.gn`
and model6 OHPM/Hvigor metadata and updates only the project's build profile.
It compiles with SDK 26 while retaining the original compatible/target SDK 9,
both module definitions, business source, legacy task files, original package
files, bundle identity, manifests and signing profile. New model6 dependencies
are empty because the real renderer has no production npm/OHPM dependencies;
obsolete Hvigor1/Hypium tooling in the retained historical package.json is not
part of the model6 dependency manifest.

- `//applications/standard/theme:wallpaper_phone_hap` selects `phone-wallpaper`.
- `//applications/standard/theme:wallpaper_pad_hap` selects `pad-wallpaper`.

Both produce `Wallpaper.hap` under separate GN target output directories and
use `app/com.ohos.wallpaper`. A product must select exactly one. Device types
remain respectively `phone` and `tablet`; compatibility with an actual 2in1
image is unproved and must not be inferred from the target name. The existing
`prebuilt_hap` part is used, so no invented bundle component is introduced.

These are **rendering extensions**, not wallpaper selection/settings UI. Both
original modules are type `feature` and contain only a type `wallpaper`
`WallpaperExtAbility`, importing `@ohos.WallpaperExtension`, reading
`getPixelMap(0)` and displaying it in a full-screen Image. No selection, set,
restore or cancel UI is added. Feature-only bundle installation and legacy
extension APIs require actual SDK/BMS verification. The original failure path
references undefined Log/TAG variables and onDestroy does not close its window;
those business files remain outside this metadata-only batch.

The original `wallpaper.p7b` is expired, with APL `system_basic` and restricted
`GET_WALLPAPER` / `READ_USER_STORAGE` permissions. Its bytes and policy are
retained. Exact OS profile renewal/signing and preinstall integration belong to
the parent. Native `wallpaper_service.cpp` also targets
`com.ohos.launcher/WallpaperExtAbility` without ThemeService; installing this
separate bundle does not repair that route.

Run `apply.sh --source-root ROOT` on a private checkout. Exact metadata hashes
make it replayable and reject unknown/partial input. Host fixture/schema checks
are not official SDK compilation, installation or runtime evidence. The wallpaper
UI requirement and native fallback route remain unresolved.
