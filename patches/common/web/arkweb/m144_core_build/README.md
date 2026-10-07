# Full M144 ArkWebCore build inputs

Chromium source revision: `a8168622b056f25c2e68d5f12fe2759bad2d9a44`.

The full engine is not the V8-only target. Keep the official ArkWeb feature
selection, prepare step and CEF translator. GN's default ArkWeb test setting
allows existing renderer test dependencies; forcing it off exposes a visibility
failure before any engine compilation.

With the official feature selection, the pinned root graph references three
ANGLE test targets that are not declared for target_os=ohos. Limit those test
aggregation edges to their existing non-OHOS platforms. This does not disable
ANGLE, WebGL, Vulkan, test definitions on supported platforms, production
features, render backends, public headers or bridge APIs. The GN-only edge fix
cannot be implemented by a Chromium C++ extension.

Apply before official full-engine GN generation. Reapplication and unknown
source drift are checked; successful GN alone is not an engine/HAP/runtime
acceptance result.

The optional prepared-SDK path is for `prepare_m144_core_sdk.py`: it copies the
fixed API26 SDK into a private writable build dependency tree before the official
stub copier runs. The OHOS source SDK stays read-only, the previous V8 SDK alias
is retained, and the default upstream installer behavior is unchanged. This
avoids substituting missing GitHub LFS SDK pointers or reinstalling bundled
API23 files over the release SDK. A post-prepare build-patch hook makes the GN
edge fix survive official prepare/CEF generation. No generated bridge is edited.

The actual full-engine build also exposes a missing generated-header dependency
in OHOS base's Blankless extension. It includes URL headers, which require the
existing `//build:robolectric_buildflags` output. Declare that header target on
the OHOS ArkWeb base target; do not manufacture a header, disable Blankless,
add a base-to-URL dependency cycle, or depend on an earlier build having left
the generated file behind. This small GN dependency is not implementable in
a C++ extension.

The official glue preparation cache originally compared only the WebView
Git HEAD, so patches to input headers at the same commit left copied headers
stale. Record the exact source include-tree content checksum as a second cache
key, including the exact formatter binary; an older one-line cache is regenerated
by the official copy/translator. Use the formatter's actual fixed-DEPS directory
`buildtools/linux64-format`, rather than an older cached tool in `linux64`.
Compute the stored checksum after official input processing so an unchanged
patched tree stays incremental. No generated bridge/header is hand-edited.

The full graph also included an OHOS target build of `generate_colors_info`,
although `compiled_action` runs its Linux host version to produce the real
color table. R9 failed linking that extraneous target executable with `_start`
missing. On OHOS, redirect all five raw dependency labels to `$host_toolchain`
and declare the executable only in that host toolchain. The existing action,
its generated header and all color/theme code remain enabled; other platforms
retain their previous target selection. This is a GN dependency fix that cannot
be supplied through a C++ extension, not a stub generator or relaxed link check.

R10's fresh GN generation exposed the fifth label in `//chrome/test:unit_tests`.
Patch 0006 keeps that unit-test dependency enabled and selects the same real host
generator. The root graph must resolve in a fresh official GN run; a working
generator binary or an older generated Ninja graph alone is not that proof.

R11 reached the engine link before the NDK stub shared library existed. The
wrapper listed `adapter_ndk_stub` only in `libs`, not as a GN target dependency;
requesting both top-level Ninja targets does not establish their order. Patch
0007 adds the existing real stub target to the wrapper's dependencies. All
generated wrappers/stubs, their fallback semantics, library names, SDK inputs,
CFI/BTI and fatal linker checks stay unchanged. This build-graph edge cannot be
implemented in a C++ extension. Fresh official GN and actual linking remain
required; a prior stub library must not hide the missing edge.

Patch 0008 retains the explicitly prepared public host configuration when
`ARKWEB_PREPARED_SDK=1`, instead of overwriting it with internal Huawei npm
registries. The original unprepared installer path is unchanged. This only
guards host configuration; no engine features, generator outputs, guest
permissions or linking checks are disabled.

Patch 0009 selects the paired Release Hvigor in the public project's source
template under `dependencies/rk/hvigor`. The official build removes and recopies
the derived top-level `hvigor` directory before its post-prepare hook. Patching
that derived copy therefore rolls back the configuration and leaves a partial
packaging patch state. Fix the authoritative template before preparation; keep
the official copy/generation sequence and patch checks. Both repeated prepare
and a fresh build must retain modelVersion 6.0.0 and the original paired tools.
