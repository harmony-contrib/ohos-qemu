# ArkWeb M144 `v8_shared`

This source component owns every patch required to build the OpenHarmony-TPC
ArkWeb/Chromium M144 `v8:v8_shared` target. Run `apply.sh` with the
root of the assembled Chromium, V8, ArkWeb, and CEF checkout.

The patches remove a presubmit-only inner-version gate from the normal target,
define disabled ArkWeb tests for component-only GN graphs, and make ArkWeb's
preparation helper resolve paths from its source location. They also repair
M144 component boundary checks, enable OpenHarmony Dawn and SwiftShader targets,
and separate Chromium's pinned compiler from the API 26 sysroot and runtime.

The arm build disables V8 pointer compression/shared-cage support and installs
the i386 multilib host toolchain needed by V8's arm snapshot generator. Set
`M144_SKIP_APT=1` only when that host toolchain is already present in the build
image.

This component produces the engine artifact consumed by the independent
`patches/common/arkcompiler/jsvm` component.
