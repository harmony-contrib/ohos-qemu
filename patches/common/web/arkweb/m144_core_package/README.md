# Public M144 ArkWebCore HAP packaging

Pinned Chromium: `a8168622b056f25c2e68d5f12fe2759bad2d9a44`.
Pinned ArkWeb: `f3d904432cc1c57468f2b7fe01979d25e0157581`.

Run after the native build passes, before the official `build/build.sh -t w`
entry. Use the same public-core selection (`-without-nweb-ex`) for all three
ABIs. Commercial `com.ohos.nweb` is not a substitute for the release system's
`com.ohos.arkwebcore` loader contract.

The HAP compile SDK and signer use the privately prepared fixed release API26
SDK, retaining the existing compatibility floor. Hvigor runs once with its
original arguments and SDK environment; launch errors and nonzero exits cannot
fall through to a second invocation or reuse a stale HAP. The expired public
profile is renewed through 2030 using the existing OpenHarmony release signer.
Bundle identity, certificate, normal APL, normal-app classification and empty
restricted permissions/ACLs stay unchanged. The signer reads the canonical
public-core profile, not an extension-specific generated copy.

These are build/packaging inputs, not Chromium behavior changes. They cannot be
implemented through `chromium_ext`, and do not edit generated bridges or disable
features. Unit checks, native compilation and signature checks are distinct
from a new packaged guest's Web/API acceptance gate.

Chromium's fixed GCS Node 24.11.1 archive intentionally has no npm. HAP/HAR
therefore use the separate full Node 18.20.1/npm 10.5.0 selected by the fixed
OpenHarmony release build project, exposed as `ohos_sdk/nodejs`. Chromium code
generation continues to use its unchanged Node 24. The host downloads the
checksum-pinned Release command-line archive (Hvigor/plugin
`6.0.0-release-patch-rc.2`, paired SDK manager `2.26.2`), not old npm tools.
All original SDK-manager code and SDK metadata are retained. The project uses
model 6.0 and `compileSdkVersion: "26.0.0"`, with the matching SDK directory;
the SDK's original `apiVersion: "26"` and `platformVersion: "26.0.0"` fields
are interpreted by the unmodified paired tool. Docker mounts the verified
tool cache read-only. The project wrapper delegates to its bundled official
wrapper with all original arguments; no project dependency download is required.
Explicit module/product
selection prevents a successful empty task graph. The private SDK also includes
the previewer tools required by this plugin. Wrapper startup and parser boundary
checks precede native/HAP work. HOME and inherited environment are preserved.
Actual HAP compilation, signature verification and new guest behavior remain
separate gates.

Release Hvigor also performs NativeStrip with the original API26 LLVM15 tool.
Comparing raw native-build hashes directly with HAP members incorrectly rejects
that normal step. The native builder now retains all five original libraries.
`verify_m144_hap_native_transform.py` replays the unchanged, hash-pinned official
kernelpermission action for the engine and the exact SDK NativeStrip command
for all five libraries in owned scratch. The complete resulting bytes must
equal both the unsigned and signed HAP members. Original libraries, replay
outputs, original tool/input hashes and command results remain part of the
artifact provenance; unrelated changes, missing evidence and failed commands
are rejected. No stripping/signing step is disabled, and this remains distinct
from loading and exercising the new OS package in a guest.

The generated project's `hvigor/hvigor-config.json5` is supplied by the real
`dependencies/rk/hvigor` source template patched in `m144_core_build/0009`.
Official prepare deletes and recopies that directory, so this packaging stack
must not patch the derived copy. Wrapper and root project metadata remain
explicit packaging inputs; repeated official prepare must retain the model.

The component script validates the whole ordered stack in owned scratch before
applying it. Overlapping SDK/model diffs are checked as a complete final state,
and earlier contiguous build-cache states can advance safely. Marker files do
not authorize skipped verification. Unknown partial/drifted states fail before
any source mutation.
