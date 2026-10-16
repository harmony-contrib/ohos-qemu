# Wallpaper native/image/connection composition

Base: `d860039d996c6147cec09b706f4b51aa34cf8148`. This batch changes only media-owned Python, tests and this report. No product source, frozen Runtime/oracle, shared suite, root guard, Apps helper, permissions, SDK, native build, signer, VM or HDC server was changed or run. All seven media requirements remain unclosed. These are executable acceptance candidates; there is no new-package or guest pass claim.

## Required root interfaces and input

The existing wrapper CLI and `verify_evidence(evidence_path, archive_path, boot_path)` are unchanged. Root must integrate its native witness guard `14ebd31` and Apps connection helper `0652db2` (root `c7a60b6`), plus the root-owned Theme extension of the shared provider function:

```python
provider_from_image(boot, spec, output, signer_dist, signer_jar, command,
                    provider_name='theme', device=actual_environment['device_type'])
verify_runtime_connections(runtime_path, target=actual_target,
                           user_id=100, module_name='phone_wallpaper')
```

`provider_name` and `device` are keyword-only. Root is responsible for the source HAP input spec and implementing/testing that extension; this child does not fork the provider guard or signer. The existing artifacts JSON now also requires `provider`, with the shared Apps SDK spec shape:

```text
provider:
  source_project: /ABS/actual-Theme-SDK04/theme
  sdk_project: theme
  sdk_evidence: {path: /ABS/actual/evidence.json, sha256: actual SHA}
  unsigned_hap: {path: /ABS/actual phone or pad HAP, sha256: actual SHA}
```

The helper verifies the full SDK source inventory and selected actual product HAP, original compile log/command result, complete image-vs-SDK payload, original module/extension/profile policy, actual image HAP/inode, and Java/OpenSSL signature evidence. Wrapper run and independent replay both call this interface; omission or an older signature fails. It binds the image and `contacts-theme-provider-evidence.json` SHA to the independently reread current archive. Replay compares raw HAP and embedded-profile bytes, plus system image, image identity, archive guard, source SDK proof and signer inputs.

## Current archive/native proof

New `batch_media_wallpaper_native.archive_native` streams the current `.tar.gz` once for metadata/native payloads and image hashing. It writes only bounded native evidence: at most50,000 tar entries,128MiB per native file,512MiB total native evidence and the existing8GiB image limit. It rejects unsafe/duplicate/link entries, missing/extra native payloads and wrong manifest roots. The multi-GB image is not duplicated into the wrapper evidence directory.

The archive must contain all seven `wallpaper-native/` files (inventory, graph, compile commands, selected GN args, library, fresh-build witness and log), `wallpaper-native-image-evidence.json`, `contacts-theme-provider-evidence.json` and their `SHA256SUMS` entries. Each selected SHA must agree with the original boot's `initial_package_file_sha256`. The streamed archive system image must agree with the real boot-extracted regular system image and its exact QEMU drive argument.

Only root's public `check_inventory` and `image` interfaces evaluate native GN, fresh2TU compilation/link/CFI, `theme_service=false`, ELF and actual debugfs image DSO. This child does not reconstruct those source/compiler checks. Their freshly recomputed image result must equal the packaged native image evidence. Independent `verify_evidence` reopens the current archive and reruns both APIs in a fresh temporary evidence directory; stored `status:pass` cannot substitute for this work.

Retained outputs are `<output>/native-archive/`, `native-archive.json`, `native-connections.json`, `native-mappings.json` and `renderer-provider/`. Top-level wrapper evidence references these and the exact native/Apps verifier source hashes. No native pass JSON is supplied by the caller.

## Two actual Apply-to-ACK observations

Inside only the existing `show-real-desktop` requests for `desktop-1` and `desktop-2`, Coordinator performs ordinary Home, then read-only native mapping and BMS-installed HAP observations before the original ACK. The restore request does not collect another pair. No explicit start/connect command for `com.ohos.wallpaper` is introduced.

The native scan emits the original request nonce and actual kernel boot ID, hashes the actual `/system/lib64/libwallpaper_service.z.so` before/after the read, records file device/inode/size, and reads the one process that actually maps that library. `/proc/PID/status`, cmdline, executable maps and process start ticks before/after the scan must agree. All relevant maps must use the same real file device/inode/path and at least one executable mapping; deleted, replaced, foreign, duplicate, absent or multiple-process mappings fail. The process must have an actual system UID below10,000. The hash must equal the current archive/image-linked DSO.

The BMS observation independently reads the current `com.ohos.wallpaper` system app UID and its unique HAP path under that bundle's `/system/app/` or `/data/app/el1/bundle/public/` namespace. It copies that actual regular HAP through the existing stat/hash-before/recv/stat/hash-after transport and compares complete bytes to the source-bound current-image HAP. The copy limit is32MiB. A later installed replacement, another bundle, missing path or wrong UID fails. Both actual HAP copies remain in Coordinator output.

Independent replay ties raw BMS/maps/stat logs to exact successful GuestUi scripts, target, remote exit nonce, transport output and HDC receive source/destination. Each observation is inside its original fresh nonce/sequence/boot Apply-to-ACK interval. It then calls the unmodified Apps `verify_runtime_connections` on the original Runtime report, requiring both actual desktop-stage SERVICE connections, exact module/ability/CONNECTED state, AppRunningRecord/PID/BMS/user100 identity and genuine command/raw-byte bindings. Installed HAP UIDs must match these observed connected renderer UIDs. Existing file/pixel/Photos/default/permission/cancel/cleanup oracles remain mandatory.

Native service-host PID and renderer PID are separate observations. Non-UI AMS does not expose a direct service-token-to-PID mapping or connection caller identity. Both remain explicitly `false`; neither is inferred from a token, counter, process name alone or a self-reported success. Root still decides whether the complete composed finding can close.

## Retained host evidence and limits

`host-tests-01.log` and `host-evidence.json` retain57 passing light host checks:20 new native/archive/HAP/composition tests,23 existing media wrapper/coordinator tests and14 unmodified Apps connection tests. The unittest suite completed in1.873s; the retaining subprocess elapsed2.077s. The log SHA is `072157eecc31d904d69aa039706c3f090e5c1d834b5a86e9f0dcf10683852ba8`.

New tests cover missing witnesses, changed initial checksums/image, a similarly named QEMU image, unsafe native payloads/symlink archive, public checker rejection, different image inode result, wrong nonce/boot/hash/map device/inode/UID/executable mapping, deleted backing file, process generation change, multiple mappings/processes, actual command target/exit/raw mismatch, ACK interval bounds, installed HAP/source/image mismatch, current UID/path, missing second observation and distinct service-host/renderer PIDs. Shell syntax is checked with `/bin/sh -n`; the generated `/proc` scan is never executed against host or guest.

Tiny image/native/HAP bytes and the public native guard are explicit host doubles in these tests. Actual Apps parsers and their original raw/transport counterexamples are exercised. No real large archive, ELF/native checker, debugfs image dump, Java/OpenSSL provider verification, signing, SDK build, new guest, HDC/UI, live maps, BMS-install or actual wallpaper pixel result was run by this child. Root's complete fresh representative package remains required. Current wrapper remains limited to the actual ARM64 product helpers and real source-defined UI profile; no remaining five-package build or capability closure is authorized by these host results.
