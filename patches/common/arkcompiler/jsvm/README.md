# QEMU JSVM / ArkWeb M144 V8 component

This component adds `arkcompiler:jsvm` to a generated phone or 2in1 profile and
stages a pinned ArkWeb M144 V8 artifact under the location consumed by the
upstream JSVM build.

The artifact contract is deliberately strict:

```text
manifest.json
v8-include/v8-include/v8.h
v8/<arch>/libv8_shared.so
v8/<arch>/lib.unstripped_v8/lib.unstripped/libv8_shared.so
```

`manifest.json` records the 40-character Chromium, V8, ArkWeb, CEF, and
OpenHarmony WebView interface revisions.
The component rejects SDK link stubs, wrong-architecture ELF files, and V8
libraries whose exported C++ API does not use OpenHarmony's `std::__h` ABI
namespace and libc++ ABI version 1. The M144
build uses Chromium's pinned Clang 22 compiler with the OpenHarmony API 26
sysroot and target runtime libraries. The JSVM wrapper keeps the engine artifact
root independent from that toolchain, accepts every long option passed by GN,
removes target-incompatible Arm compiler flags, and adapts JSVM's legacy V8
calls to the M144 public API. M144 does not expose the old OpenHarmony-only raw
heap dump extension, so that API streams the supported V8 heap snapshot format.
The component also links the OpenHarmony toolchain's `libc++` instead of the
obsolete `c++_static` library name. Pointer compression and the shared cage are
enabled for arm64 and x86_64, while the armv7a build and its JSVM wrapper both
disable those 64-bit-only ABI definitions. The armv7a wrapper also preserves
Clang's system-header order so the compiler resource `stddef.h` is not shadowed
by Musl's architecture-specific UAPI headers.
The JIT diagnostics path uses a width-safe integer conversion so its remote
address handling compiles on both 32-bit and 64-bit targets, and defines the
declared `JsSymbolExtractor` destructor so `libjsvm.so` has no unresolved
internal DFX symbol at load time.

The ArkWeb/Chromium source-build patches and their entry point live separately
under `patches/common/web/arkweb/m144_v8_shared`. Artifact provenance remains
enforced here by the pinned revision and SHA-256 validator.
