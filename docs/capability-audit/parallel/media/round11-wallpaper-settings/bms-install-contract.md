# BMS feature-only Wallpaper installation: bounded read-only findings

Root owns renderer metadata/signing/BMS and requested these source conditions. No BMS or renderer source was changed by media. The source inspector is `ohos-qemu-parallel-source-20261016-02`. These are real source conditions, not a claim of actual installation.

`foundation/bundlemanager/bundle_framework/services/bundlemgr/src/bundle_install_checker.cpp` SHA `d4431f346bbfa25dc4251ae27218a1c1b05c67a6fd7069cffc81a9d00cc5e7d1`:

- `ParseHapFiles:475-478` derives system/third-party app type from actual verified provision appFeature. Preserve true `hos_system_app` and the real signer; do not fake app identity.
- `ParseHapFiles:496-502` rejects a **second** entry HAP (`if (newInfo.HasEntry()) { if (isContainEntry_) return ...; isContainEntry_=true; }`). It does not require at least one entry HAP in this path.
- `CheckMainElement:1455-1468` returns OK for no modules/shared; otherwise rejects only `GetEntryInstallationFree() && mainAbility.empty()`. Actual Theme module has `installationFree:false`; its lack of a UI ability does not trigger this atomic-service rule. This function does not demand a dummy MainAbility implementation.
- `ModuleProfile` records `module.mainElement` as `innerModuleInfo.mainAbility` at `module_profile.cpp:2844`, and matches it against ability / extension names at 3000 / 3064. These bounded source observations do not substitute for the actual SDK's full manifest validation. Do not invent a MainAbility to satisfy a presumed rule; retain the real wallpaper extension and react to exact SDK/BMS errors if any.
- `CheckSupportAppTypes:1718-1744` adds the default↔phone alias where specified and requires each module's deviceTypes to intersect `const.bms.supportAppTypes`. `CheckDeviceType:1750-1752` immediately returns OK for a nonempty supportAppTypes value that satisfies that check. Therefore the existing QEMU contract `2in1,phone,default,tablet` includes both original Theme phone and pad deviceTypes. The native installer can accept them through its existing compatibility path, without changing module type or disabling checking. Actual packaged parameter and runtime install still require root validation.

`foundation/bundlemanager/bundle_framework/services/bundlemgr/src/base_bundle_installer.cpp` SHA `9e64bd791bc93ecda11f45fa91e5e08d3b76d3f005e823344ae0555d3daf194b`:

- `ParseHapFiles:5613-5646` consumes the checker's result and `IsContainEntry`; no additional minimum-entry rejection was found there.
- `InstallEntryMoudleFirst:8312-8338` returns OK immediately for a new app (`!isAppExist_`); its entry-first loop is not a requirement that a new feature-only application has entry.
- `CheckVersionCompatibilityForApplication:6405-6437` explicitly handles old applications with no entry (`else` of `oldInfo.HasEntry()`), which is further evidence that no-entry application state is represented by the real installer.
- `CheckInstallCondition:6033-6039` consults CheckDeviceType when syscap checking was not OK. Preserve this real policy and validate actual image syscaps/compatibility. Do not infer a runtime failure from original Theme `phone` / `tablet` labels alone.

Conclusion: these concrete core install paths do **not** establish a need to migrate the original extension-only feature HAP to entry, and the existing QEMU compatibility parameter has an explicit matching source path. Whole-HAP parsing, dependency/signature/policy checks, first-boot selection, actual feature-only installation and actual renderer startup are still gates. No blanket statement that a real new package installs successfully is made. Root should retain exact errors and use a legitimate metadata migration only if a concrete check actually requires one.
