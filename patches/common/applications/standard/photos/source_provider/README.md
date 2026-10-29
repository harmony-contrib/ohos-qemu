# Fixed-release Photos source provider

Use `apply.sh --source-root <checkout>`, then `prepare_dependencies.py` with
the same source root, an owned cache root and an evidence output. Both steps
run in the normal local Docker recipe before source traversal/preload/GN.

The pinned Photos project contains real Recent/PhotoInfo/DefaultAlbumName and
FA-card extensions absent from the old prebuilt HAP. The numbered patch wires
its Stage module into the `photos` part, selects paired Release Hvigor 6.0.0,
removes accidental production Hypium dependencies, and builds ImageEditor with
real native libraries for all three ABIs. JsonCpp 1.9.5 is compiled from its
pinned source using the original renamed-namespace headers, not an ARM64-only
archive. The actual LP32 duration mismatch is fixed with the existing 64-bit
JSON duration type.
The real FA-card service also initializes its store before the first event,
rather than returning while its `initialized` flag is false.

Dependencies are HTTPS-only and SHA-256 pinned: official Lottie 2.0.19 HAR and
JsonCpp commit `5defb4ed1a4293b8e2bf641e16b156fb9de498cc`. Unknown cache/source
assets, redirects through filesystem symlinks, unsafe archives, partial source
patches and edited vendored headers are rejected. Retry is idempotent.

The source profile expired in 2023 and did not match the release OS signer.
Dependency preparation preserves every bundle/APL/ACL/permission/property,
aligns only the distribution certificate and finite expiry, signs with the
same pinned public OpenHarmony OS release materials, and verifies the result.
A separate exact vendor-policy patch aligns only the Photos certificate pin;
no wildcard or new privilege is granted. The old prebuilt target is removed
separately, and both QEMU profiles select the real owning source part.

This does not implement `userPropertySettings` cloud storage, fix every
hardcoded commercial Photos target, or claim complete Photos capability.
Those must have independent protocol repairs and behavior tests. Source/HAP
compilation and signing are not package or guest acceptance; real provider
discovery, caller permissions, UI results and regression tests are required in
the newly packaged representative artifact before the remaining five builds.

The normal packager reads the actual Photos HAP back from `system.img` and
checks the 15 source extension types, real compiled code/resources, all three
native ABIs, the fixed application signer, code digest/permissions, and an
embedded profile identical to the prepared source profile. Its evidence
explicitly remains offline; it cannot close the guest acceptance gate.

Local Docker validation on 2026-10-09 built a clean clone of the pinned project
using this component, the real Release SDK/Hvigor and all three ImageEditor
ABIs, then rebuilt after the FA-card initialization repair. The real release
signer and `verify_photos_provider_image.py --hap` passed on that newly built
HAP. Evidence is retained under
`/tmp/ohos-photos-candidate-20261009-mbMM70/repository-integration`, with producer
logs `repository-integration-build-02.log`/`-03.log` and signing/verification
logs `repository-integration-sign-04.log`/`-verify-05.log` in its parent.
This private compile is neither a delivered package nor a running guest test.

```sh
python3 -m unittest discover -s ci/capability-audit -p test_photos_source_provider.py
```
