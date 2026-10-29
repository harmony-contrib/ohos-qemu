# NumberIdentity native-provider preload

Add only the exact `com.ohos.numberidentity` bundle to MainThread's existing native-provider load list, alongside Contacts and TelephonyDataAbility. The complete original/final `main_thread.cpp` fixtures come from immutable official ability_ability_runtime commit 6c18fdc9bdef6cfcf5888517cd8ed9448584f6e8, not the different 4d07 hostseed checkout.

The existing launch path loads the bundle's BMS-reported native libraries before Stage and extension creation. Its actual failures, native paths and `dlopen` semantics are unchanged. The NumberIdentity DSO constructor registers the real DataShare creator; no new JS stub or Stage import is introduced. Source-level ordering is conditional on actual packaging, nativeLibraryFileNames/path, dependency and loader identity.

The one-file exact component rejects unknown source bytes or a wrong project HEAD when project Git metadata exists, using the unchanged shared helper. This is not a cross-component transaction and does not strengthen that helper's existing concurrency/alias guarantees. Root must wire and verify all three components, package actual native DSO bytes, and demonstrate actual BMS/DSO/creator/caller/permission behavior. No runtime pass is asserted.
