# SDK105 batch01 profile correction

Root retained actual attempt
`/Volumes/PSSD/qemu/validation/first-20261005/issue-20-20261006/r52-Knowledge-actual-SDK105-01`.
All four dependency commands exited0; all four compile commands exited255 at
the same pre-ArkTS SyscapTransform configuration check. The original report,
projects and logs were read only and are unchanged.

The importer compile log gives the exact cause:

- Line2: device type `phone` is unsupported; use `default`.
- Line14: no systemCapability set for `phone` under the actual SDK's
  `ets/api/device-define`.
- Lines15–17: configuration error00303060, empty multi-device intersection.

The actual SDK105 supplies `default.json`, `tablet.json`, `2in1.json`, etc., but
no `phone.json`. The generator now declares only `deviceTypes:["default"]`,
which is the real SDK's phone-compatible profile. The prepared manifest and
protocol explicitly retain `acceptance_device:"phone"`; this batch makes no
tablet/2in1 runtime claim. No SDK, custom syscap, permission, APL, ACL or API
contract has been changed. Apps was notified of this narrower declaration.

Before preparing a project, `check_device_profile` reads and hashes the actual
SDK `default.json` and requires the declared capabilities for ArkUI, the ability
and window runtimes, BundleManager, AccessToken, language utilities, FileIO,
AppFileService, PhotoAccessHelper, DataShare and Image/ImageSource. Absence fails
before project preparation. A host counterexample removes the real required
PhotoAccessHelper capability; it must fail. It never inserts an SDK capability.

Manual review compared all four pages plus AuditStore/EntryAbility with the
actual SDK105 declarations:

| API/type used | Actual declaration |
| --- | --- |
| process.uid | `@ohos.process.d.ts:258`, number |
| getBundleInfoForSelfSync, BundleFlag | `@ohos.bundle.bundleManager.d.ts:1433/76` |
| BundleInfo.appInfo, ApplicationInfo.accessTokenId | `bundleManager/BundleInfo.d.ts:106`, `ApplicationInfo.d.ts:195` |
| checkAccessTokenSync, requestPermissionsFromUser | `@ohos.abilityAccessCtrl.d.ts:259/340` |
| fs read/write/stat/access/unlink | `@ohos.file.fs.d.ts:2744/3651/3235/336/3506` |
| WRITE_ONLY/CREATE/APPEND/NOFOLLOW | `@ohos.file.fs.d.ts:145/163/182/207` |
| fileUri.getUriFromPath | `@ohos.file.fileuri.d.ts:162` |
| TextEncoder.encodeInto | `@ohos.util.d.ts:496`, Uint8Array |
| ImageSource.getImageProperty/release | `@ohos.multimedia.image.d.ts:12428/12737` |
| PhotoAccessHelper.getAssets/getAlbums/release | `@ohos.file.photoAccessHelper.d.ts:4840/5275/5879` |
| Album.getAssets, MemberType | same file `4290/1523` |
| showAssetsCreationDialog | same file `5561` |
| MediaAssetChangeRequest constructor/setHidden/deleteAssets | same file `9921/10094/10050` |
| applyChanges; MediaAlbumChangeRequest constructor/recover/delete URI | same file `6043/10734/10978/11021` |
| KnowledgeContent getRelatedEntity/getSearchSuggestion | same file `14202/14225` |

No further definite API-name/type mismatch was found in this source review.
The templates use typed Request/Row/Item interfaces, actual PhotoAsset/Album
returns and actual BusinessError logging. Catch handlers do not throw an
arbitrary caught value; every explicit throw constructs Error. That review and
host protocol tests are not an ArkTS compile result: batch01 never reached that
compiler. Root must build all four fresh projects together in SDK02 to discover
remaining actual ArkTS errors, retaining batch01 unchanged.

The22-phase protocol, raw error/EXIF/date/identity checks and mandatory lifecycle
cleanup are unchanged. This batch ran Python host tests only, not SDK/ArkTS/
native compilation, signing, Docker or guest operations. Runtime acceptance and
all requirement closures remain pending.
