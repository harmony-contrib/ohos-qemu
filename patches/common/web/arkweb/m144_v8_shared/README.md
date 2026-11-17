# ArkWeb M144 `v8_shared`

This source component owns every patch required to build the OpenHarmony-TPC
ArkWeb/Chromium M144 `v8:v8_shared` target. Run `apply.sh` with the
root of the assembled Chromium, V8, ArkWeb, and CEF checkout.

The unified 7.0 release source already removed the obsolete presubmit-only gate
and includes the OHOS Dawn/SwiftShader target declarations. Their master-only
patches are no longer applied. The remaining patches
define disabled ArkWeb tests for component-only GN graphs, and make ArkWeb's
preparation helper resolve paths from its source location. They also repair
M144 component boundary checks, retain the release's OHOS third-party targets,
and separate Chromium's pinned compiler from the API 26 sysroot and runtime.
The target-side custom libc++ uses OpenHarmony's `std::__h` namespace and ABI
version 1, because V8 exposes standard-library types in symbols consumed by
JSVM. Host toolchains retain Chromium's defaults.

The arm build disables V8 pointer compression/shared-cage support and installs
the i386 multilib host toolchain needed by V8's arm snapshot generator. Set
`M144_SKIP_APT=1` only when that host toolchain is already present in the build
image.

This component produces the engine artifact consumed by the independent
`patches/common/arkcompiler/jsvm` component.

The release builder retains V8 Intl and embeds the locked ICU data into the
standalone JSVM dependency (`v8_enable_i18n_support=true`,
`icu_use_data_file=false`). It must not silently disable Intl or depend on the
separate ArkWeb HAP's data files. Actual per-ABI GN arguments and current patch
content are recorded and verified; Intl behavior still needs new-guest tests.
