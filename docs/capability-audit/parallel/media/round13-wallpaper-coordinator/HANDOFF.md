# Wallpaper action coordinator

This batch adds an executable coordinator for the frozen round12 runtime's 21 requests. It uses the same `EnclosingAcceptanceGuest`, archive, boot ID, account100 and `GuestUi`; it creates no VM. ACK means the requested operation completed, never that wallpaper acceptance passed. The frozen independent validator still decides persisted files, default resources, cancellation/denial isolation and desktop/lock pixels. No requirement, runtime gate or package gate is closed.

Only the two new Python files, `fixtures/batch_media/wallpaper_receipts/` and this report directory change. Round12's three Python files, eight product sources, shared suite/build/sign/closure tools and cumulative requirement ledger remain unchanged.

## Root execution

Use the same challenge for the importer and query caller. Five PNGs must match the actual display; root's SDK02 challenge is 1280x800 and cannot be used on another geometry. First prepare the separate read-only query source:

```sh
"$PYTHON" ci/capability-audit/batch_media_wallpaper_coordinator.py prepare-query \
  --challenge /ABS/challenge/challenge.json --output /ABS/query-source
```

Root builds/signs the generated page into `org.harmonycontrib.wallpaperquery`, `EntryAbility`, a legitimate `system_basic` / `hos_system_app` role requesting **only READ_IMAGEVIDEO**. The fixed permission definition places READ_IMAGEVIDEO at `system_basic`, user_grant, NORMAL, provisionEnable=true. Do not promote the zero-permission ordinary importer, edit ACLs to force a grant or call root grant APIs. The query HAP itself calls `requestPermissionsFromUser`; the coordinator observes the caller-named PermissionManager dialog, clicks its real Allow control and independently queries the resulting token. It accepts standard reason/usedScene/resource metadata in the compiled permission declaration, but no other permission. Root owns the legitimate actual signer/profile and install decisions; unavailable permissions fail the run.

Run this coordinator beside the unchanged runtime, with owned0700 action directory and separate output directories. Start the runtime first so its receipt directory exists. Both must use the same boot/archive/challenge/plan/actions. Use runtime `--action-timeout 180` and coordinator `--action-seconds 175` to bound the five actual imports/deletions within the existing maximum. The coordinator default is80 seconds; idle waiting defaults180 seconds. Do not run concurrent unrelated HDC/UI actions.

```sh
"$PYTHON" ci/capability-audit/batch_media_wallpaper_coordinator.py run \
  --boot /ABS/fresh-acceptance/evidence.json --archive /ABS/new-package.tar.zst \
  --challenge /ABS/challenge/challenge.json --plan /ABS/plan.json \
  --inputs /ABS/coordinator-inputs.json --hdc /ABS/hdc \
  --actions /ABS/actions --runtime-output /ABS/runtime \
  --output /ABS/coordinator --action-seconds 175
```

If root explicitly delegates caller installation, add `--install-callers`. It installs the exact verified signed HAPs and records actual commands. Otherwise both callers must already be installed and BMS must expose one retained `hapPath`; that real HAP is transferred and its SHA compared. In either mode actual BMS identities must match signer roles and account100. Settings must remain actual system_basic/system app with SET_WALLPAPER granted; the ordinary seed must be normal/non-system with it denied.

Each file reference is exactly `{"path":"/ABS/file","sha256":"64hex"}`. `coordinator-inputs.json` has:

```text
seed:
  compiled_page, unsigned_hap, signed_hap, signing_receipt, sdk_evidence: file references
  source_key: wallpaper/entry/src/main/ets/pages/Index.ets
  ability: EntryAbility
query:
  same file references, source_key: actual query project prefix + entry/.../Index.ets
  ability: EntryAbility
tools:
  token: {binary:file, source:file(token_query.cpp), build_receipt:file}
  default: {binary:file, source:file(round12 default_resolver.cpp), build_receipt:file}
```

`sdk_evidence` consumes root's real schema with integer exit_code0, source_commit, archive_sha256, runner_sha256, source_files, successful commands and exact produced HAP bytes/SHA. There is no invented source-report `status` field. Every command log hash is checked; exactly one applicable `assembleHap` compile must report BUILD SUCCESSFUL. Multi-project reports select `haps[].project` and its `<project>-compile.log`. Generated page and original AppScope app_name resource must be hashed in source_files. The actual compiled app label binds the READ consent title. Signed and unsigned module.json / modules.abc must remain equal. Signature receipt must use root's existing `actual_signature_profile_and_codesign_NOT_guest` scope, status pass, exact signed/unsigned SHA and verified_profile with the actual boot UDID. These adapters validate evidence; they do not build/sign anything.

Actual SDK02 importer adaptation was executed against root's original source/log/evidence without another build. `sdk39-importer-adapter-actual.json` binds unsigned HAP SHA `15a9debb3eae1c4ea5e8bf64c9742c68081280784fe2f55b823bcf134b22ee94` (70855B), page SHA `4656f5d43e11d7b5415d22c322fa098e1cfd38f84f20f08545df6907acc69c14`, and original wallpaper compile log. This proves receipt compatibility, not signing/BMS/guest behavior. Root's SDK02 source key starts with `wallpaper/`.

## Actual UI plan

Keep all round12 fields and add these actual profile-specific selectors; selectors are identifiers or text from real source/UI, not arbitrary coordinates. No manual receipt/pass flag is accepted.

```text
settings_ability: actual Settings ability
settings_main: {bundle:com.ohos.settings, identifier|text:unique main-page marker}
settings_navigation: [existing round12 Settings entry selectors]
photos_ability: actual Photos ability
photos_main: {bundle:com.ohos.photos, identifier|text:unique gallery main marker}
photos_navigation: [optional actual Photos page controls]
photo_browser_navigation: [optional actual image-browser toolbar controls]
save_ui_bundle: org.harmonycontrib.wallpaperchallenge or com.ohos.photos
picker_ui_bundle: existing round12 actual host bundle
screens: existing round12 actual full-viewport desktop and lock selectors
lock_navigation: [optional actual SCB/SystemUI lock controls with bundle]
```

Starting an existing ability does not reset its navigation stack: Settings returns by at most8 Back actions, only while its real window and account100 AMS foreground identity own the view. Photos similarly returns to its observed main marker before locating each new challenged thumbnail. Photos creation/selection UIExtension may inherit its host bundle; AMS independently binds the real Photos provider to that host before clicking. Creation uses the actual `advanced_dialog_button_1`; deletion uses actual `ToolBarButtonDelete` then its actual confirmation. Each deleted image is selected by frozen independent thumbnail correlation, not list order or name alone.

Desktop uses the actual full-viewport system root. Lock uses the real profile's SceneBoard or legacy SystemUI root. Home may perform exactly one ordinary upward swipe on an already observed lock root; credentials or an unknown screen fail. Optional lock_navigation must refer to actual system controls. Without such a control, the coordinator waits up to65 seconds for real idle lock; after a serial-confirmed kernel sleep it may send one normal QMP power-key event and observe real resume. It never toggles power while awake, suppresses sleep, enters PIN, uses force unlock or substitutes desktop for lock. Startup also handles an already sleeping enclosing guest this way. Serial/QMP/raw UI evidence is retained; the framework's fatal/process/boot checks stay active. A product with no reachable actual type1 consumer will fail.

## Real query and token contracts

The query HAP only reads five original returned Photo URIs. It closes every FetchResult and reports actual per-URI cursor count and returned URI. A fresh root-owned, then caller-owned0600 private `query-request.json` carries run, nonce, before/after and exact five URIs. The caller produces a fresh nonce filename under its own sandbox with actual query interval and entries. Partial files are not consumed; a fresh EOF sentinel preserves the final newline even though GuestUi strips transport newlines. Before deletion all five must have count1 and exact returned URI; after deletion all must have count0. A permission, cursor or JSON error never becomes an empty result. Raw full records remain alongside the two-key receipt required by the frozen oracle. This proves absence from active queries after UI trash deletion, not secure erase.

`token_query.cpp` is a read-only native candidate, **not compiled here**. Root may reuse its actual audio token tool build recipe and product headers without weakening flags:

- Header: `base/security/access_token/interfaces/innerkits/accesstoken/include/accesstoken_kit.h` and its actual c_utils exported include tree.
- Library: actual product `out/<product>/security/access_token/libaccesstoken_sdk.z.so` (access_token `libaccesstoken_sdk`), libc/libc++.
- Same real architecture/triple, sysroot, `-std=c++17 -Wall -Wextra -Werror -fno-exceptions -fno-rtti` as root's existing `build_audio_capture_tools.py` token target; do not use a stub library.
- Invocation: `token_query <32hex_run> <actual_BMS_UID> <bundle> <permission>` as root. Only seed/Settings SET_WALLPAPER and query READ_IMAGEVIDEO are whitelisted. It checks GetHapTokenID/GetHapTokenInfo against BMS UID/user100, two stable VerifyAccessToken reads, actual boot ID and monotonic interval. No grant/revoke API exists.
- Build receipt: actual `{status:pass,source_sha256,binary_sha256,arch}` with original compile/link logs retained. `arch` is enclosing `arm64`, `armv7a` or `x86_64`; ELF machine and both hashes are independently checked before staging.

The round12 default resolver remains unchanged and requires actual `config_policy:configpolicy_util` / `config_policy_utils.h`, `cJSON:cjson` / `cJSON.h`, libc/libc++. Root already owns its build. Both tools are staged into a fresh root-owned0700 directory, binaries0500, with independent guest SHA checks. No media SQL or service mutation is performed as root.

## Evidence, completion and remaining gates

Request reading enforces owned0600 regular single-link bounded files, exact boot/run/sequence/action/nonce/name, and rejects replay. Partial JSON retries only within the original deadline. ACK uses fsync and atomic rename behind a persistent0700 `.once` publication guard; the reader can never see a transient two-link ACK. It includes exactly the frozen six identity fields. A handler failure or deadline leaves no ACK. All original raw command, timeout, BMS, token, UI tree, compositor image, AMS provider, query and operation logs remain under coordinator output. The final coordinator status is `completed_actions_NOT_runtime_acceptance`, never an acceptance pass.

Root must still build/sign/install the query role and compile/link both real native observers, provide actual plan selectors and coordinate the unchanged runtime/validator on the newly packaged acceptance boot. After ACK21, root should wait for runtime/validator completion before removing query caller/helper/private observation artifacts; the coordinator deliberately makes no concurrent HDC call after the final ACK. Existing private seed challenges and only the five created active assets are removed by actions20/21, while raw journals/proofs remain. Root owns eventual observer uninstall and artifact cleanup.

Host tests are synthetic orchestration/adversarial receipts, plus real API26 SDK declaration checking and real SDK02 evidence adaptation. They are not HAP, native or guest tests. The initial declaration check caught nonexistent `EXCL`/`chmodSync`; the candidate now uses actual API26 CREATE|WRITE_ONLY|NOFOLLOW, a serialized sandbox writer and fresh nonce/preexistence checks. No invented numeric flag or fake chmod is used. Official ArkTS/HAP semantics and native linking remain root's final build checks. See `evidence.json` for exact commands, hashes, retained failures and final light-test result.
