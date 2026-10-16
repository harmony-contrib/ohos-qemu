# Wallpaper runtime candidate

This batch adds test tools only. The eight round11 Settings/native targets and apps' phone/pad renderer remain frozen. No guest, QEMU, HDC, Docker, SDK/HAP build or native compilation was run by this child. No requirement or package gate is closed. The original seven media requirements remain unchanged and open. Root reports its complete Settings SDK06 and Theme phone/pad SDK04 builds passed; those are root evidence, not this tool's runtime evidence.

## Commands and ownership

Use the existing Python/Pillow runtime. Root owns compilation/signing/installation, the enclosing **fresh acceptance boot**, actual UI coordination and final suite/package closure.

```sh
PYTHON=.../host-regression-venv/bin/python
"$PYTHON" ci/capability-audit/batch_media_wallpaper_runtime.py prepare \
  --output /ABS/challenge --width ACTUAL_DISPLAY_WIDTH --height ACTUAL_DISPLAY_HEIGHT

# Root builds generated /ABS/challenge/Index.ets into an ordinary normal HAP:
# org.harmonycontrib.wallpaperchallenge, requestPermissions=[], no extra ACL.
# Keep the generated page and actual compiled module.json, unsigned/signed HAP,
# actual build/sign verification receipts and installed BMS identity.

mkdir -m 700 /ABS/actions
"$PYTHON" ci/capability-audit/batch_media_wallpaper_runtime.py run \
  --challenge /ABS/challenge/challenge.json --boot /ABS/fresh-boot/evidence.json \
  --archive /ABS/new-package.tar.zst --plan /ABS/plan.json --hdc /ABS/hdc \
  --actions /ABS/actions --output /ABS/runtime --action-timeout 90

"$PYTHON" ci/capability-audit/batch_media_verify_wallpaper_runtime.py \
  --runtime /ABS/runtime/runtime.json --output /ABS/independent-verification.json
```

The runner never boots/kills a VM, builds a helper/HAP, grants permissions, writes a media database or calls a wallpaper mutation API as root. It reuses `EnclosingAcceptanceGuest`, `GuestUi`, `account_state` and the actual Photos close-control ancestor parser. Account **100 must be observed foreground** on the same boot; it is not silently inferred from a directory. Every guest shell operation uses a new checked exit marker, even when HDC returns host status zero for a guest failure. The archive/boot/process/target/UDID contract comes from the enclosing framework.

`plan.json` contains actual observed main-Settings navigation selectors (not coordinates). The runner itself clicks the uniquely observed `settings_wallpaper_entry`, choose, Apply, Restore and Cancel controls. It matches the new random image against actual Photos Image/GridItem screenshot bounds before clicking their actual centers. It collects Photos AMS provider evidence **before** a single-select click can close that provider. Photos extension UITest nodes may belong to their host Settings bundle; that does not remove the independent `com.ohos.photos` UIExtension/host check.

```json
{
  "settings_navigation": [{"bundle":"com.ohos.settings","text":"ACTUAL_THEME_ENTRY_TEXT"}],
  "picker_ui_bundle": "com.ohos.settings",
  "screens": {
    "desktop": {"bundle":"com.ohos.sceneboard","identifier":"SCBDesktop_Flex_Desktop"},
    "lock": {"bundle":"com.ohos.sceneboard","identifier":"ScreenLockRootComponent"}
  }
}
```

Use actual per-profile system lock identity, not the example blindly. Legacy phone may use `com.ohos.systemui`/`com.ohos.systemui.screenlock`; visible lock service processes need not claim AMS FOREGROUND. The verifier requires actual current-user AMS process identity plus a visible full-screen UITest node in that system bundle, a valid compositor PNG and new challenge pixels. Desktop and lock cannot use the same viewport. SceneBoard identifiers are constrained to known desktop versus lock roots. No preview, arbitrary app window, API resolve or UI status text substitutes for these checks. Screen capture occurs immediately after the real UI transition, before slower file transfers; no keepalive, forced wake or power override is added.

## Action coordinator protocol

The runner writes an owned 0600 file:

`/ABS/actions/<run>-<sequence:03>-<fresh_nonce>.request.json`

The root coordinator executes the real authorized action and atomically publishes a complete owned, regular, single-link 0600 `...ack.json`. ACK JSON is **exactly** the six identity fields below; omit request `details`. It is synchronization, never a pass claim. Maximum per-action wait is 180 seconds; default 90. Existing request names, wrong owner/mode/link, partial/malformed ACK, stale nonce/run/boot/action and timeout all fail. Root retains these files as evidence; they are not periodically rewritten.

```json
{"schema_version":1,"run_id":"32lowercasehex","boot_id":"actual-boot-uuid",
 "sequence":1,"nonce":"32lowercasehex","action":"verify-package-identities-and-permissions"}
```

There are 21 ordered requests:

1. `verify-package-identities-and-permissions`: actual Settings/Photos/renderer and normal caller installation; actual token queries must later appear in denied observation.
2. `resolve-service-default-resources`: write `/ABS/runtime/default-resolution.json` as below.
3. `import-five-PNGs-via-real-Photos-consent`: stage exactly `desktop-1.png`, `desktop-2.png`, `lock-1.png`, `lock-2.png`, `cancel.png` into the seed HAP private files directory, actual UID and 0600; use its five `wallpaper_import_<case>` buttons and the real Photos creation consent dialog, once each, in that order. Wait for all ten complete actual JSONL records; write `import-observation.json`.
4. For each of desktop-1, desktop-2, lock-1, lock-2: `show-settings-main`, then `show-real-desktop` or `show-real-lock`. Root gets case in details; no fake foreground or privileged unlock. Between these requests the runner performs actual picker selection and explicit Apply.
5. `show-settings-main`, `cancel-real-Photos-picker`: collect actual Photos close Button ancestor/layout/screenshot/AMS before clicking it; write `picker-cancel-observation.json`. Runner then selects the cancel challenge and presses Settings Cancel.
6. `show-settings-main`: runner selects the cancel challenge again and dispatches actual Back; real wallpaper entry must return.
7. `ordinary-denied-set-and-restore`: foreground the same normal seed HAP and press `wallpaper_denied`; wait for all eight errors in the existing log, preserving its first ten records. Write `denied-observation.json` with independent token queries. No grants or APL change.
8. `show-settings-main`, `show-real-desktop`, `show-settings-main`, `show-real-lock`: runner explicitly restores each type between the respective transitions.
9. `delete-only-created-Photos-assets-via-real-UI`: remove exactly the five actual returned Photo URIs using real Photos user controls and collect an actual MediaLibrary API query showing they are no longer active. Write `cleanup-observation.json`. No direct SQL, root unlink of media resources or fabricated empty array.
10. `remove-owned-seed-private-inputs`: remove only those five private input files after all proof is retained. Runner independently queries their absence on the guest. Preserve its JSONL and root artifacts.

The coordinator must actually navigate the existing Settings instance to its main view before acknowledging `show-settings-main`; simply starting an already-running ability does not promise that its navigation stack returned. For system-screen actions, wait for the actual requested system viewport and stable painting before ACK. Failure to reach a real lock/desktop is a failure, not permission to substitute another view. Root coordinator can use the existing boot/home setup and UI framework; no manual UI action is required by this tool.

## Root receipt schemas

All nested file references below use exactly `{"path":"/ABS/file","sha256":"64hex"}`. Every external observation has `run_id` and `boot_id`. Missing evidence fails closed. These root-produced records must be backed by the actual root operation logs; host oracle fixture data is explicitly synthetic and cannot be registered as guest evidence.

`import-observation.json`:

```text
run_id, boot_id, seed_uid,
uris: [five actual MediaLibrary-created URIs in case order],
compiled_module: file(actual unsigned HAP module.json),
compiled_page: file(exact generated Index.ets),
unsigned_hap, signed_hap, build_receipt, signing_receipt: files,
consent_actions: [{case, ui_bundle, layout:file, node:actual selected node,
                  screenshot:file, provider_dump:file}, ... five]
```

Actual build receipt includes `status:pass`, `generated_page_sha256`, `unsigned_sha256`. Actual signer receipt includes `status:pass`, `unsigned_sha256`, `signed_sha256`, `verified_profile.bundle-info` with correct bundle, `apl:normal`, `app-feature:hos_normal_app`. Root must retain original build/sign commands/logs and its real signature validation; receipt adapters may add these fields without replacing evidence. The verifier compares actual signed/unsigned module/ABC bytes, rejects duplicates and permission insertion. Seed log is read independently from `/data/app/el2/100/base/org.harmonycontrib.wallpaperchallenge/files/wallpaper-<run>.jsonl`; private PNGs are independently transferred with stat/hash before and after, exact original SHA, actual UID and restrictive mode. Each creation request and completion must report the original byte count and real source/returned URI. The caller generates no image data.

`picker-cancel-observation.json`: `run_id, boot_id, ui_bundle, layout:file, node, screenshot:file, provider_dump:file`. Node is the actual owned enabled Button ancestor of `Third_Select_PickerClose`, not a guessed point.

`denied-observation.json`: `run_id, boot_id, token_query:file, settings_token_query:file`. Each raw independent AccessToken query JSON contains `bundle, uid, token_id, permission:"ohos.permission.SET_WALLPAPER", grant`. Ordinary grant is **-1**, Settings grant is **0**; identity/UID/token must match actual installed applications. Fixture calls legacy ordinary `setWallpaper/reset` for both types and requires **201**, then system `setImage/restore` and requires **201 or 202**. No other error or success is converted to pass. Exact BusinessError message/code remain in JSONL. Native token-query helper and actual installed-source identity binding remain root-owned.

`cleanup-observation.json`: `run_id, boot_id, deleted_uris:[exact original five], actual_asset_query:file, ui_actions:[{layout:file, selector:{identifier|text}, node, screenshot:file}]`. The raw query JSON is `{queried_uris:[exact original five],active_uris:[]}` **only if a real MediaLibrary/PhotoAccessHelper query proves this after actual deletion**. A privileged/system test caller with legitimate existing permissions or root's actual service query adapter is required; the zero-permission seed does not pretend it can read/delete the whole library. Trash movement is not claimed to be secure permanent erase. Do not manufacture an empty result, mutate DB tables or substitute a receipt boolean.

## Default resolver build request

Fixture `default_resolver.cpp` is a read-only native candidate, **not compiled here**. Build it for the actual guest architecture against actual product headers/libraries with unchanged product protections. Exact real dependencies are those already on both WallpaperService GN targets:

- `config_policy:configpolicy_util`, header `config_policy_utils.h` (actual fixed config-policy public export).
- `cJSON:cjson`, header `cJSON.h`.
- Product libc/libc++ and normal filesystem/syscall headers.

Invoke real guest binary `default_resolver <run_nonce>`. It reads its actual `/proc/sys/kernel/random/boot_id`, calls actual `GetCfgFiles("resource/themes/theme/")`, preserves order and mirrors service first-nonnull path + `default/`, `home|lock/manifest.json`, `image.src`, existing resource and fallback paths. It does not use a guessed policy directory. It reads bounded regular manifests (64 KiB) and regular nonempty assets; nonregular/default-resolution errors must be surfaced, not bypassed. Root should retain actual complete command/log/link inputs and compare linked config-policy/cJSON to this artifact, as with its other guest tools.

The raw output contains `run_id, boot_id, resource_path, paths, resolved:{desktop,lock}, descriptions:{kind:{manifest_remote,manifest_state}}`. Root receives the actual selected manifests, helper binary/source/build receipt and writes:

```text
default-resolution.json:
  run_id, boot_id,
  actual_GetCfgFiles_query:file(raw complete output),
  query_binary:file, query_source:file(exact candidate source),
  query_build_receipt:file({status:pass,source_sha256,binary_sha256,arch}),
  desktop:{remote:actual resolved image path,manifest:file(actual JSON) or null},
  lock:{remote:actual resolved image path,manifest:file(actual JSON) or null}
```

The verifier binds exact source, guest ELF machine, build hash/ABI and actual run/boot resolver output. For a resolved manifest it independently reconstructs the selected `base/resources/image.src` path; for fallback it requires the actual resolver's fallback state and canonical `/system/etc/wallpaperdefault.jpeg` or `/system/etc/wallpaperlockdefault.jpeg`. Root's query adapter must preserve actual absence/invalid-manifest logs. The runner independently transfers the real resolved image from a trusted system/vendor/product path. Restore requires removed user resource, `DEFAULT` config and actual compositor pixels matching that image; successful restore text alone is irrelevant. Runtime supports this fresh product's trusted readonly default paths, not arbitrary writable theme roots.

## Independent checks and limits

Each source image is a new random 12x12 spatial color grid at the actual display size. All five are distinct and nonflat. Service image comparison requires at least 95% tile medians within 26/channel; compositor comparison requires at least 68% and at least half the tiles in **each** quadrant. It uses fixed center-cover geometry, not arbitrary image search/alignment or an embedded preview crop. This tolerates real JPEG, icons and clock overlays while rejecting flat colors, stale images, wrong type and a small selected-image preview. Unhandled rotation/geometry or more occlusion fails; root must record actual profile geometry, not loosen thresholds to obtain success.

Actual persisted paths are `/data/service/el1/public/wallpaper/100/system/wallpaper_home` and `/.../100/lockscreen/wallpaper_lock`; config is `/.../100/wallpapercfg`. Both directories are completely inventoried. Regular files must be bounded, non-symlink and stable across stat/hash/receive/stat/hash. The verifier checks source bytes, second update freshness, other-target isolation, all cancel/back/ordinary-denial content/metadata unchanged, actual PICTURE versus DEFAULT config, both restored resources absent, actual default pixels, user/screen identity, raw UI/provider selections, final private input absence and real created-asset cleanup. It preserves failed observations and always leaves `first_artifact_behavior_gate_passed:false` / no closed IDs.

This is **static image selection/set/restore acceptance only**. It does not implement or close every Wallpaper UI-extension API, live wallpaper, dynamic ThemeService, user switching, camera, AudioVivid or the original seven media capability gates. Root still must bind the exact newly packaged Settings/renderer/native build/provider image/signatures, install selection and run this entire flow on that same fresh boot before final package closure or the remaining five artifacts.
