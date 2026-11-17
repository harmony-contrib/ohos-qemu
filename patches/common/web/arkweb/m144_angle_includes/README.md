# Release ANGLE extension header paths

Pinned ArkWeb: `f3d904432cc1c57468f2b7fe01979d25e0157581`.

The official full ARM64 build reaches `ohos_util.cpp`, whose hard-coded
ancestor path escapes the actual Release layout and fails to find ANGLE's
`common/platform.h`. The sibling OHOS display extensions have the same defect.

Use the existing ANGLE `src` include directory for ANGLE headers; resolve the
private OHOS adapter headers from each existing extension's actual directory.
Only includes in existing `chromium_ext` files change: no new source/generated
files, public/bridge API, feature flag, backend, permission or error handling.
The adapter and ANGLE headers remain the original fixed Release inputs.

Apply with the full core patch hook, before official prepare/GN/compilation.
Repeated application and unknown context are checked. Source/header checks
are not a complete native build, signed HAP, WebGL or new-guest validation.
