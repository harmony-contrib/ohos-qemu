# OHOS 7 QEMU 2in1 Serial candidate repair

Scope: official dynamic C++ InnerAPI / ArkTS 1.1 `@ohos.busManager.serial`,
`SystemCapability.BusManager.Serial`, SA 4202. Taihe/static is not a capability
target. This is a candidate implementation, **not a completed runtime repair**.
No QEMU package was produced by this work. No old image, host fixture, SDK HAP,
GN result, or partial compilation passes the first-artifact behavior gate.

## Fixed inputs and corrected source findings

The release manifest remains `OpenHarmony-7.0-Release` at
`f079c4ad9848f9cc4a9a4b3a3613ad8fbb142549`. Actual inspected/build inputs are
the read-only Linux volume mounted at `/Volumes/PSSD/qemu/openharmony`, not a
host seed checkout. The upstream Serial source is absent from that manifest.

| Input | Fixed revision |
| --- | --- |
| Serial SIG manager | `c05fbbf156230982aa576373da6ee04378b09ca0` |
| Serial SIG tree | `c05fa6985730cbbce358cf513dccbb40b9be5054` |
| drivers/interface | `42289d3f8e46f5a112bd7ea6d36e4baaeac0718d` |
| drivers/peripheral | `69094b77aa2200160207b1b06b3c0b586ae2157c` |
| base/usb/usb_manager | `4b5f23603e43628bc70449f0a043f072dcf19814` |
| base/startup/init | `475fcc1e48db623ea4a9ee03b5408a21a19b99c4` |
| kernel/linux/linux-6.6 | `14c77f1541a53e814d89ad6dea5f7f211f9895a6` |
| base/security/selinux_adapter | `cfc1d5b31a7438dbc87763f9222f00337221cf21` |

Serial origin: `https://gitcode.com/openharmony-sig/busmanager_serial_manager.git`.
The supplied read-only git cache is
`/Volumes/PSSD/qemu/validation/first-20261005/serial-upstream.JyGcfQ`.
The suggested GitHub mirror
`https://github.com/openharmony-sig/busmanager_serial_manager.git` could not be
verified (`git ls-remote` requested unavailable credentials). The importer
therefore accepts a supplied fixed git cache and never fetches `master` or a
moving branch. A distributable mirror/fetch policy remains a builder wiring
dependency; this work does not claim that mirror is available.

The SIG `AGENTS.md`/README describe an old success-returning service stub.
Those statements are stale for the pinned commit: its production service calls
real HDI. No stub/test service is installed by this candidate.

`SerialService::InitHdiProxy()` uses `ISerials::Get(true)` (passthrough).
`drivers/peripheral/serial/BUILD.gn` builds `libserials_service_1.0`, tagged
`passthrough`, exporting `SerialsImplGetInstance`. Its selected sources do not
include the unrelated `serial_driver.cpp`. Do not add a fake HDF devhost to
make SA startup look successful. HDI discovers actual `/dev/ttyUSB*` and
`/dev/ttyACM*` via sysfs; onboard serial requires HCB `serial_config_match`
`OnboardSerialList`. Console ttyAMA0/ttyS is not a data endpoint for this work.

Correction to an early inspection report: “no Serial authorization UI anywhere
in source” was incorrect. The existing trusted UI lives at
`base/usb/usb_manager/frameworks/dialog/dialog_ui/usb_right_dialog`, not under
`applications/standard`. The actual release product selects `dialog_hap`.
Its existing system-signed `com.usb.right` bundle has nonexported
`UsbServiceExtAbility` (`sysDialog/common`), routes by `portName` to
`pages/SerialDialog.ets`, and calls the real `addPortAuthorization` API.
No Settings/permission-manager substitute, signer bypass, or new trusted ACL is
needed. Its original Allow handler closed the dialog before the asynchronous
grant completed; this candidate fixes that race.

The installed **public** SDK omits `addPortAuthorization`: attempting to call it
from a normal-HAP public source fails TS2339. That is a declaration boundary,
not a runtime authorization test. The ordinary probe does not fabricate a
system declaration or sign itself as a system app. It uses `port.open()` and
the genuine `com.usb.right` UI. The SDK's `libusb_serial_ndk.z.so` belongs to the
separate USB manager path and is not evidence for BusManager Serial InnerAPI.

Native dialog transport still prefers `com.ohos.sceneboard.systemdialog`, then
falls back to `com.ohos.systemui.dialog`. The fixed fallback source
`applications/standard/systemui/product/default/dialog/src/main/ets/ServiceExtAbility/ExtAbility.ts`
implements start1 and remote-object2, not Serial's close3; its controller keys
windows by calling pid/token. SceneBoard's corresponding implementation is only
present as a precompiled HAP in this checkout. A close IPC log is therefore not
proof that a window disappeared. Nonce and captured-session isolation prevent
an old UI from authorizing/closing the next Serial session, but late native show
IPC/window creation, cancellation and fallback availability remain actual
new-guest tests. This candidate does not modify shared SystemUI transport.
The actual fallback's `pages/ExtIndex.ets` handles UIExtension onRelease by
`Controller.destroyWindow(connectId)`; Controller terminates its service only
when its complete window map becomes empty. Thus its exclusive-window source
path can lead to disconnect, but a different SA's concurrent window can keep
the shared service alive. Frozen r21 writes the authorized cache but waits for
parent disconnect; positive completion in that concurrent case is not established.
The separate `0002` candidate completes only the captured pending connection
after its real cache write succeeds. It does not change SystemUI, public IPC,
trusted/normal-app identities, permissions or signing.

## Component-owned changes

Each independent 2in1 component owns `apply.sh` and its numbered patch.
There is no phone/2in1 compatibility entrypoint. Shared builder, profiles,
evidence ledger, and main audit documents were not edited here.

| Numbered component patch | SHA-256 |
| --- | --- |
| `base/busmanager/serial_manager/0001-integrate-dynamic-serial-and-bound-authorizations.patch` | `ee286cdc1e91f0a6108fac74562eb9a5d218ba10919545c6112d1b9cb81bb01d` |
| `base/busmanager/serial_manager/0002-complete-only-the-verified-captured-grant.patch` | `570d0869f7fca6c98545035a285fde50f2a219dbc507c417a0dfa33d636d2de1` |
| `base/usb/usb_manager/serial_dialog/0001-wait-for-serial-grant-before-closing.patch` | `7e4974ee74860d9af340493da30ffcdb6fac404d1197c751e0c3a46c1e50f443` |
| `base/startup/init/serial_devices/0001-restrict-usb-serial-device-nodes.patch` | `08d698717fffc3ef4f29cf6cbf8fad2fa1717441029993a80a49ffd2c1afaf61` |
| `device/qemu/serial_usb_endpoint/0001-build-in-qemu-ftdi-serial-endpoint.patch` | `d96a84a1dd3ee58b4f29fbefeee30cc4b112ecd058cb98c554966047407a6b7a` |
| `base/security/selinux_adapter/serial_metadata/0001-allow-serial-domain-attachment-metadata.patch` | `f805f847579da6fe85090a2983eb4a04584e1310d631abc1f4442cf46528491b` |

Paths in the table are relative to `patches/2in1`.

- `patches/2in1/base/busmanager/serial_manager`: import pinned source with
  manifest/revision/archive/tree provenance; refuse foreign trees; dynamic
  client/NAPI/SA groups only; select the real peripheral dependency. Parse the
  complete unsigned token range without truncation or C casts. Restrict grants
  to a currently pending token, user, device, and fresh 128-bit request nonce.
  The UI's opaque `deviceId` carries the nonce; the authorization cache retains
  the original physical-device key. Old UI approval cannot approve the same
  app/device's next request. `getrandom` short reads/EINTR are handled; entropy
  unavailable/zero read fails, with no tuple fallback or fake success. Each
  connection owns immutable dialog parameters and its own timed condition
  variable. Connection/send failures wake the waiter. A late close cannot close
  a newer pending request. Dialog IPC uses a named 5-second wait and the dialog
  condition wait is 60 seconds; this is not a hard end-to-end scheduling bound.
  Existing numeric NAPI `BusinessError.code` construction is unchanged.
  The additional `0002` checks the captured connection's immutable nonce,
  token, user and physical attachment before a real `AddDeviceRight` write,
  and performs that write plus successful completion while holding the same
  mutex as timeout/disconnect/cancellation. Its monotonic deadline begins at
  connection creation and cannot be extended by a later wait. Already finished,
  expired, cancelled or disconnected connections cannot write a late grant.
  A successful grant wakes only its own waiter even while a shared parent stays
  alive; a later parent callback cannot overwrite that result. Actual service
  identity and post-open attachment checks from `0001` remain unchanged.
  The component-owned `apply_stack.py` constructs every canonical patch prefix
  from the fixed upstream archive and checks all affected file bytes before any
  payload write. It accepts fresh/complete/valid-prefix trees, rejects mixed or
  drifted states, and never trusts an old `.applied` marker. This permits strict
  idempotence when `0002` overlaps `0001` without changing the shared applicator.
- `patches/2in1/base/usb/usb_manager/serial_dialog`: await the actual grant before
  closing; ignore duplicate Allow clicks while the grant is pending. Use a
  dedicated `LocalStorage` per `UIExtensionContentSession` and immutable
  `SerialDialogRequest` parameters, including a closure capturing that native
  session. An old page cannot read a newer nonce from `globalThis.want`, and its
  late `finally`/cancel cannot terminate a newer `AppStorage['session']`.
  Serial uses `@Entry({ useSharedStorage: true })`; the fixed SDK/compiler
  supports passing storage to `loadContent(path, storage)`. The existing USB
  route and its globals are unchanged. Keep the original bundle, ability,
  signing profile, and system-API identity checks.
- `patches/2in1/base/startup/init/serial_devices`: `/dev/ttyUSB*` and
  `/dev/ttyACM*` become `0660 serial serial`, not world-writable. Existing serial
  uid/gid is 1025. No broader console permissions change.
- `patches/2in1/device/qemu/serial_usb_endpoint`: build in FTDI USB-serial and
  USB-serial core for ARM64, ARMv7, x86_64; enable ARMv7 xHCI/PCI prerequisites.
- `patches/2in1/base/security/selinux_adapter/serial_metadata`: only add
  `serial_service tty_device:chr_file getattr` for the real devnode stat.
  Guard fixed revision and complete original source SHA; no change to HAP/root,
  read/write/open/ioctl ranges, signing, labels or user grant policy. Root and
  sepolicy AGENTS were read fully. Sysfs link/search and fs_attr directory getattr
  already have generic domain rules. Actual new guest USB/ACM labels, enforcing
  stat behavior and AVC results are still unverified.

Serial init drops the unnecessary shell group and vendor ttyHW8/proc chmod
operations. The original UI has **no “remember this device” option**. Its cache
nevertheless uses maximum validity, OnStop appends records to the DB, and OnStart
loads them; only the original boot job clears the DB. That boot-time clearing
remains, but physical offline now revokes the matching attachment.

For USB/ACM, the internal key includes the real character devnode and resolved
sysfs device directory's dev/inode/rdev/ctime metadata. Both must exist. This
discriminates attachment lifetimes, **not hardware authenticity or a trusted
hardware serial number**. Old unbound DB keys cannot match the new keys.
The immutable request checks the attachment every 100ms while awaiting UI,
at approval, and before/after actual HDI open; missing/replaced input yields
the existing numeric disconnected error, not successful authorization.

Offline revokes all old-user grants for that **one attachment**, exactly matching
cache record deviceId and a bound Rdb predicate; other devices/users' records
are preserved. An absent DB is not created by revocation. DB failures are
reported, not hidden; attachment-key matching also prevents stale rows from
authorizing reattachment. Only that pending connection is cancelled.
Revoke happens before waiting for serviceMutex, which OpenSerial can hold while
awaiting UI. HDI callbacks carry immutable attachment IDs; a late old offline
callback cannot erase the newer same-tty context. The fixed passthrough HDI
holds its shared mutex across offline callback, so post-open mismatch cleanup
releases serviceMutex before taking the HDI close lock.

Read-only review while r20 builds also confirms a remaining upstream lifecycle
lock inversion: ordinary `CloseSerial` and `OnClientDied` hold serviceMutex while
calling HDI `Close`, which takes its exclusive mutex; concurrent
`NotifyDeviceOffline` holds the same HDI shared mutex while waiting for
serviceMutex. This can deadlock a close/client death concurrent with unplug.
The r20 inputs remain frozen and do **not** fix those two older paths. The r21
candidate keeps that context marked closing in the map (same-tty reopen stays
busy; ordinary operations reject it), performs HDI cleanup outside serviceMutex,
and erases only the same shared context afterward. A closing context's offline
callback cannot remove that reservation. The real HDI callback still revokes
that attachment before entering the service. The death recipient holds weak SA
and per-open context references, so late/expired death cannot clear a reopened
context even on the same attachment. HDI close failure maps to the existing
numeric error instead of successful close. Three cleanup-only unit fixtures
cover the bounded offline interleaving, old/expired death, and HDI error; they
do not fake device open/data or establish guest acceptance. r21 still requires
its own full GN/component evidence and actual guest boundary tests.

The fixed HDI has no global observation interface for unopened ports: the
devnode/sysfs checks cover UI-pending or SA-unloaded detach/replacement.
HDI still opens a pathname, not a supplied verified fd. Pre/post identity
checks reduce this race but do not establish an atomic kernel attachment/fd
binding. The existing TOKEN_NATIVE/system-HAP authorization policy is unchanged.

Upstream `SerialRightTest` gains real manager/helper boundaries: unsigned
tokens, no/out-of-context grant, wrong user/token/device, cleared request,
repeated same-port stale grant, immutable connection parameters, connection
failure, late disconnect, exact all-user attachment revocation, other-device
pending preservation, missing attachment refusal, no DB creation and exact DB
row deletion across reload. Service tests also assert late old offline cannot
erase a replacement context. These are unit tests, not a hardware acceptance
substitute. Test variants in upstream `test/develop` stay uninstalled.
The additional grant tests create the actual captured connection and exercise
the actual manager/cache methods: positive completion while a local Binder
endpoint remains alive, duplicate grant, missing captured connection,
cancel/timeout/disconnect, deadline expiry before the waiter starts, and altered
pending nonce/token/user versus immutable connection parameters. The synthetic
non-USB port is explicitly cache/state-machine-only, not fabricated USB hardware
or a trusted UI/permission substitute. Writing or compiling these tests does
not establish their execution or actual guest authorization correctness.

## Verified so far (2026-10-06)

`check_serial_candidate.py` on actual fixed source copies passes all five
components' application/idempotence/reverse checks, foreign-tree preservation,
mismatched provenance rejection, actual release GN-format validation, and compilation/execution of the **actual**
token, request-ID, and attachment helpers on Linux. Request tests use real host entropy plus
explicit host syscall-controlled EINTR/short/EAGAIN/zero boundaries; they are
not OHOS runtime evidence. Evidence:
`ohos-qemu-capability-inspect:/tmp/serial-candidate-checks-20261006-r12.json`.
Attachment helper tests use controlled stat boundaries for missing devnode/sysfs,
permissions/I/O failures, wrong node type, inode/ctime replacement, invalid path
and unbound keys; no hardware/HDI success is simulated.
The actual new UI helper and actual ability routing are transpiled with the
fixed SDK TypeScript compiler and checked with controlled frontend-only
session/IPC fixtures: concurrent storage, stale same-port nonce, changed target
token, duplicate Allow, grant-before-close, late reject/success `finally`, own
close failure preserving a numeric grant error, malformed parameters, original
USB route preservation, and failed content load closing only its own session.
These fixtures do not render UI, make a real permission decision, or install a
fake SA/HDI implementation. Fixed CRLF ability input uses the shared applicator's
explicit line-ending-tolerant reverse check where necessary.

`check_serial_kernel_config.py` resolves the candidate configurations through
the actual Linux 6.6 Kconfig, staging its real common-module Kconfig directories.
ARM64/ARMv7/x86_64 all resolve `USB_SERIAL`, `USB_SERIAL_FTDI_SIO`, `USB_XHCI_HCD`,
`USB_XHCI_PCI` to built-in `y`. This is not a full board kernel build.
Evidence: `/tmp/serial-kconfig-20261006-r3/serial-kconfig-evidence.json` in the
inspector; per-architecture olddefconfig logs and commands are included.

Full ARM64 **2in1** preload/load/GN runs, not SDK-only or `--fast-rebuild`:

| Attempt | Actual result |
| --- | --- |
| r6 | GN failed: upstream camera GN touches RO config placeholders. |
| r7 | LOAD failed: a partial drivers symlink skeleton hid `drivers_devhost`. |
| r8 | GN passed; first direct Ninja omitted hb's normal `dupbuild=warn` policy and rejected a duplicate Contacts edge. |
| r9 | GN passed; Ninja failed because the fixed NOTICE collector opened an RO input COPYRIGHT with `O_RDWR`. |
| r10 | GN passed after applying the independent common NOTICE input fix; old candidate lacks nonce. Only its own confirmed Ninja PID 57056 was stopped; actual return was 130, not 143. No containers or production build were stopped. |
| r11 | Nonce candidate full preload/load/GN passed; actual Ninja failed at 2509/16595 generating Hiview IDL: the fixed reader requires writable original inputs, rejecting a resolved read-only source path. Actual return 255. |
| r12 | Final GN-formatted source-list candidate full preload/load/GN passed; no Ninja compile was requested. C++ source is identical to r11. |
| r13 | Pre-GN partial IDL directory materialization hid `ability_base` from LOAD; actual return 255. No reader check was bypassed. |
| r14 | Full preload/load/GN passed; after GN, 1492 original IDL files were byte-identically materialized in owned scratch. Old globally bound UI candidate was interrupted after the per-session race was found: own Ninja PID 162614, cwd and parent PID155890 checked, actual return 130. |
| r15 | Per-session UI full GN0; actual Ninja1 at jsoncpp generated source after its RO installer failure. No link pass. |
| r16 | Attachment candidate LOAD255: premature third_party link promotion hid mindspore. |
| r17 | Attachment candidate full GN0; owned Ninja TERM130 at550 while freezing final K&R/test source bytes. |
| r18 | C++/UI attachment source frozen, full GN0; own Ninja TERM130 at1180 to include minimal metadata policy. No link pass. |
| r19 | Five components, including fixed-guard metadata policy, full preload/load/GN0; actual Ninja1 at TypeScript npm-pack action2902: `npm` absent from PATH. |
| r20 | Adapted old service-unit assertions; fixed release Node18 PATH/owned offline npm cache; parent jsoncpp generation repair in owned copy; full preload/load/GN0, Ninja1 at flatc CMake cache's old scratch path. |
| r21 | Removed actual product `-Werror` unused constant; close/death/offline context and lock-order repair; preserve moved path-bound CMake binary directories in owned quarantine; full preload/load/GN0, Ninja1 at libjpeg-turbo generation action7131. |
| r22 ARM64 | Separate `0002` grant candidate; full preload/load/GN0 and all three complete changed product/unit translation-unit objects compile0. No link, package or unit-runtime pass. |
| ARMv7 / x86_64 grant-r1 | Pre-GN profile refusal: disabling only the selected copied ABI leaves another phone inherit controlling the shared HandsetSmartWindow parameter. No compiler pass. |
| ARMv7 / x86_64 grant-r2 | Disable all copied existing phone inherits in the Serial-only isolated helper before applying the selected PC profile; both fresh full preload/load/GN0. Object diagnostics in progress. |

r11 GN log SHA-256:
`fea1f50fbd58f7f3a1c671af0c1e60eb7632f9d562cb4156b82a473d509e8817`.
r11 failed compile log SHA-256:
`483136d1560c52252179c63cd2c39f379f2dce404c5515670a4d6e2c3a975f30`.
r12 final-format GN log SHA-256:
`c27c210333a224df137fddb2ef7baf3617a20d32ed1d0c2f4b1c89ee05b7dd75`.
r13 failed LOAD/GN log SHA-256:
`3b41f9641b74a12770c952e57265e3af5c4c44c2116b9c671e136493fb22859e`.
r14 full GN log SHA-256:
`d533553c5b5d4b0733418617b2f369973f6e6bd7cb687c19626840b28c1a3514`.
r14 interrupted old-UI compile log SHA-256:
`5da7ff1647a72448cdfe240636f115a97c975cca1defcea6d08a7f8b98c9d5b3`.
r15 per-session candidate full GN log SHA-256:
`c588365a535adaa358c582e4b272bc7e1194afe204b0b10efebb1164aee20b37`.
r15 actual Ninja failed at 1049/14400, exit1, log SHA
`efe5bc592e823c44860bbdadbc5b1cf121980db390165aff7b7e5c1df6d14a4c`.
The fixed jsoncpp installer extracts next to its own file. Its RO-linked
source directory caused tar failure, which it swallowed, followed by copy
failure and a success stamp. Real clang then could not find generated
json_reader.cpp. The actual archive exists with SHA
`f93b6dd7ce796b13d02c108bc9f79812245a82e577581c4c9aabe57075c90ea2`.
New scratch builds copy only that installer workspace's exact original bytes
after GN, excluding git metadata, and record hashes. No production permission
or installer implementation is changed.

r16 attachment candidate LOAD failed255: promoting third_party before LOAD
hid mindspore behind child symlinks; log SHA
`5117efa9025ee16e46c49218d2479560560cb0559327b326aebc10f5b33cf724`.
This isolation failure is preserved, not called a Serial compiler failure.
r17 copies jsoncpp workspace after GN: full GN0, SHA
`e45c6c24bf54b25c1213f367002066b2295ac8a5492af15c5388c947c1e51edb`.
Its source manifest SHA:
`f442c6d2e5f812c1e4caee277b98fbcbd7d94038ded47a9b47be7dae0ca442ab`.
Own Ninja213553/parent207601/cwd were verified before TERM to rebuild the
final K&R candidate plus late-context test; actual exit130, log SHA
`d21d42db225620f95566ae9a1363bf912a1007e6cb6fb5daf67e0986ef582cb1`.
r18 reruns complete preload/load/GN and actual Ninja for the current patch.
Full GN0 log SHA
`44a6229c54485ff94d1e0a281f488a6f750b573db26c1e07a4f2f8e50976ef21`;
actual candidate source manifest SHA
`15427c93846d7331c48141b93dfb9f6919d4e433e0b9225d929c334ea6fe543d`.
Read its precise final outcome from its own build evidence; r17 is not
validation of those final source bytes.
r18 was stopped only after verifying own Ninja228152/parent216528/cwd.
Actual exit130, log SHA
`5c6ad017d752a2197d19b6021e6034c0a5700f28eae137114ffa6cb0f4a505c5`.
It did not include the new policy. r19 copies the complete actual 125MiB
base/security subtree into its owned scratch to preserve LOAD topology,
applies the guarded metadata patch before fresh GN, and selects
`selinux_adapter` for actual policy/component compilation. No active candidate
source was patched in place.
r19 full GN0 log SHA
`d6bdf102e5b30cda9d577558146dae58af22c7034240bae3fd62b096e714e682`;
actual candidate source manifest SHA
`dd78dd94b4c4fdd266eebbbfa641dda2d87a5da6e0c3173cde34fab682f10eef`.
The generated release args still select `selinux_adapter_enforce=false`.
Building this policy cannot establish enforcing-runtime permission correctness;
retain actual guest `getenforce`, devnode labels, Serial-domain stat and AVC
evidence separately. r19 did not complete the component link.
Actual r19 Ninja exited1, compile log SHA
`1a412d4843c9ff41607c11e4a38d66efe35bb2a217f3f2c7df5f91b99aa09c11`;
its finished evidence SHA
`9144ee948af23c56770e527da45d37249d73b6a699ae1c3e86f993cefee4a8ae`.
Failing action2902 was `/usr/bin/env ../../third_party/typescript/compile_typescript.py SRC DEST`,
calling `npm pack` in its real owned output. Fixed Node/npm exist; the prior
isolated PATH omitted them. The Node18 path in r20 matches the parent's real
production builder selection, not a substituted SDK/compiler. Its actual
Node/npm hashes and scratch-only offline npm cache are recorded in evidence.
No global npm bootstrap/install or moving registry dependency is added.
The r19 original service test's BuildDeviceId assertions assumed an absent
USB/ACM node yields a nonempty key, and expect decimal substrings despite the
original `%04x` implementation. Those old assertions must be adapted in a next
frozen candidate before claiming an actual C++ unit-suite pass; r19 only builds
the test targets and has not run them. No absent-hardware success should be
introduced to satisfy the old tests.
r20 adapts those three format assertions to an explicitly synthetic, never-opened
format-only port and correct hex IDs; USB/ACM missing devnode/sysfs yields an
empty key, while a genuinely present node must have matching attachment metadata.
The negative HDI-error mapper is tested directly; a nonenumerated reported
port must be rejected before HDI open. These unit-only checks do not replace
the real ordinary-HAP/HDI tests or claim a complete C++ unit-suite runtime pass.
r19 retains the older `ac33a8c6811c7d0e698629b8f5b82ba40d397680b0ec1461120d7f5f2ba045dc`
Serial patch; r20 changes only upstream test bytes, not production C++/UI/TE.
After full GN, r20 consumes the parent's guarded
`patches/common/third_party/jsoncpp/generated_source` repair in the byte-identical
owned jsoncpp copy; its git metadata remains a read-only fixed-source link.
This retains r15/r19 failures and propagates real generation errors.
r20 full GN0 log SHA
`5fe33654692263e3d03d4b461fb2b2e5fb0b296c35b069cbae0b9ade02b7edd7`;
actual candidate source manifest SHA
`a16f0464e8971e68ce2c1ba7a4fbeabb3cb31918c9187f8535dadd9ca82fafd7`.
Only stopped owned r19 output was moved as ordinary incremental state;
the finished r19 evidence and its hashes remain intact. No production source,
output, package evidence or runtime state was modified.
r20's Serial patch was
`c20beba7af113574badfb104ca0709e783e7f8bcc84a9383423ed1d81325e260`.
Its actual TypeScript npm-pack action1784 succeeded. Ninja then failed at
action1787 `es2panda_build_flatc`: `build-flatc.sh SRC BINARY CMAKE` detected
the old r19 CMakeCache binary path; CMake also retained the old source path.
Compile log SHA
`4cdf932afeecac1f5f9ad8c4cef11364aa522b3d4ed85cb8c3ec92aa8d4aa2ea`;
finished evidence SHA
`32386806ab3272d49284b4b49368f16a65cbeac100a13c723c66926c65075bed`.
This isolated incremental-cache failure is not a Serial C++ source failure.
After Ninja naturally stopped, separate actual-GN-command diagnostics found
the obsolete `DECIMAL_BASE` constant rejected by `-Werror`, while service.cpp
still lacked the not-yet-built real Serial IDL header. The new authorization
boundary test object compiled0. These are object-only results, not component
link/unit-suite passes; evidence SHA
`d46ec3b5d81327df307e779e5400febec7ca9325e2a6b62e77286dfbdded9127`.
r21 removes that unused constant and applies the close/death repair above.
The isolated build helper validates and moves only path-bound CMake binary
directories under the stopped owned output into a recoverable scratch
`serial-moved-cmake-cache` quarantine, retaining original cache SHA and contents.
It never rewrites cache bytes or removes production/user directories. Fresh
full preload/load/GN is still mandatory; no stale-generated-header substitutes
or compiler warning suppression are added.
r21 full GN0 log SHA
`932dfda46fbdd8e92acfa5c2a727f07e1f3c5137ba7f2b3e865b97b3106bc6e6`;
actual source manifest SHA
`fea0006cb41ad4034eb027c32a2e5e8fed06bc405051cbe1c4e6bd38f6a1542f`.
The r20 finished failure remains untouched; only its stopped owned output is
used as incremental state. r21 naturally ended with Ninja1 at action7131:
the fixed libjpeg-turbo installer encountered rejected upstream patch hunks,
then attempted to copy `jmorecfg.h` into its read-only linked source directory.
Compile log SHA
`a422979ee2e0cb89dd0f53c7d57e43c26222fd184e297f4b363df72c42827dd2`.
This is retained as an actual dependency/isolation failure, not a Serial source
failure or component-link pass. No component link or test execution pass yet.

The `0002` candidate's identical source/UI manifest is
`445b59182d4256aca5572a546cdc033c7d88144a604e31e838b926a0c23e4394`.
All three new full-GN records select actual `device_type="2in1"`, materialize
1492 byte-identical original IDL inputs in private scratch, and keep production
source/output read-only:

| ABI and owned scratch | Full GN log SHA-256 |
| --- | --- |
| ARM64 `/tmp/serial-full-gn-arm64-r22` | `688ff27adbf0eeda85827cd49a26bb4774da86cf5c1b2eacea68fafe1d5a6695` |
| ARMv7 `/tmp/serial-full-gn-armv7a-grant-r2` | `0f5fa2e8b271e1d6a78d26aac9dcd097e6f0c5b43afd1db6814d9329b6c87b6c` |
| x86_64 `/tmp/serial-full-gn-x86_64-grant-r2` | `d71964554e7a135ea91c28363759019e3a0b1f4b5ba023fab4c8a2252b3be286` |

Host copies of the reports are under
`/Volumes/PSSD/qemu/validation/first-20261005/serial-grant-completion-20261006`.
The canonical fixed-source check `fixed-source-checks-r15.json` covers all five
components, overlapping-stack idempotence/reverse application, real token/nonce/
attachment host helpers and actual TypeScript frontend fixture checks.
The Serial-only host regression suite currently passes **76 tests**. These are
not an OHOS authorization/HDI/UI unit-runtime or fresh-package acceptance pass.
Report SHA:
`d43077039e8f93af7f871c8551a885e050276e1f1160f4950c5be2f2c8eb1430`.
Host regression log SHA:
`1b1fc7302330cda3cc863534a9c059138fd594e8a7648fe389fece1bddbd79e8`
(`host-serial-regression-stack-evidence.log`; earlier reports are retained).

All three ABIs now compile all three complete changed translation units with
their genuine product compiler commands: the production
`serial_right_manager.cpp`, that same production source in `SerialRightTest`,
and `serial_authorization_boundary_test.cpp`. All nine exits are zero. Original
warning/security/CFI flags are retained; only diagnostic object and depfile
paths change. Reports and the actual objects/depfiles/logs are copied into the
host evidence directory above:

| ABI report | Report SHA-256 |
| --- | --- |
| `objects-arm64-r1.json` | `1ef5db01965c5f3ca99725ae21ffdc64a3b12e9bc4209f1c9639519ac4856656` |
| `objects-armv7a-r3.json` | `07a85df2c2bad804dc9d1e211e3f066089804f86074bb320b0433a591421ca74` |
| `objects-x86_64-r3.json` | `cb6be221d88904a55a20dad4f0b744fd8b5ee18a1a593bba0f287b1dea56a8ae` |

This does not link or execute `SerialRightTest`, validate the public service
permissions on OHOS, or pass the first-package gate.
The three touched candidate C++ files additionally pass the genuine release
clang-format15 `--dry-run --Werror`, using the component's full style with the
SIG-mandated K&R `BreakBeforeBraces: Attach` override. No source files are
written by this check. Log `actual-format-grant-final.log` SHA
`b880e647d997b7487a28bb03ed879c1e2caffbad199916fb0d5119b1c38bc259`.

The dedicated real-object checker is reproducible for each matching completed
full-GN scratch, using a new output path for every attempt:

```sh
docker exec ohos-qemu-capability-inspect python3 \
  /work/ci/capability-audit/check_serial_grant_objects.py \
  --source-root /Volumes/PSSD/qemu/openharmony \
  --scratch-source /tmp/serial-full-gn-armv7a-grant-r2 \
  --output /tmp/serial-grant-objects-armv7a-next --product armv7a_virt
```

The two other ABIs retain their first two actual failed object checks:
fresh GN had no generated product musl `features.h`, then no generated BMS
`ibundle_mgr_ext.h`. The selected genuine `musl_headers` Ninja group completes
307 edges in each owned product. The next input build uses the two real BMS IDL
header outputs and fixed jsoncpp generator output in the same fresh graph;
the required real host IDL tool is built as an ordinary dependency. No old
generated headers, replacement SDK sysroot, simplified service header, fake
interface, fabricated hardware or permission decision is used. These remain
input-generation/object diagnostics, not component or runtime acceptance.

The actual next Ninja actions exposed a common JSONCPP installer defect:
GN/Ninja create the declared-output parent directories before running the
generator, but the first installer repair treated this entirely empty skeleton
as an incomplete extracted source tree. Both ABIs failed before archive
extraction. The exactly observed directories were `.`, `src`, `src/lib_json`,
with no files or links; directory-list SHA
`0f385739dc09d4fec36411805841114a4bd678f9cd0a815e55387613730345fc`.
An explicitly authorized recoverable move of only those owned empty directories
also failed: actual Ninja immediately recreated them. Both attempts and their
quarantine paths remain recorded; no generated bytes were changed or borrowed.
The parent-owned common `0002` repair accepts only these known empty output
parent directories and rejects partial files, unexpected directories and links.
Its final installer SHA is
`31d602cb122bf1b2a0635b1b63319c4ada731bdeda5e9cbbfe612147c8af22d4`.
Normal Ninja regeneration passes0 in both ARMv7/x86_64 r2 scratch trees,
including genuine BMS IDL actions. Reports `input-json-bms-armv7a-04.json` and
`input-json-bms-x86_64-04.json` have SHA
`c05b1d2275025ec88fc0db31c039b916d6c3133312c8ff8524a8f50a8604e97c`
and `6153dfb8fdc4575ce504c76c6065af8e616218a21ac99b3d3bd69f62523f0c71`.

An independently created `/tmp/serial-full-gn-x86_64-grant-r3` uses **no output
seed** and passes fresh preload/load/GN0 with the identical Serial source
manifest. Its real JSONCPP Ninja action then passes0, without manual directory
isolation or generated-input substitution. Full-GN report
`full-gn-x86_64-r3.json` SHA
`994e63a9533f20ce52c3b6711c3515cf3572fb3b99133c795a105e3df96fdf70`;
generation report `input-jsoncpp-fresh-x86_64-r3.json` SHA
`6e56f851ccc99283a132f14c73e73ea1c794d7e53dd12e178a5fa01cdd7f8d24`.
The separate `fresh-common-stack-x86_64-r3.json` records the actual final
installer, both numbered common patches and applicator SHA (report SHA
`8483696c4464cc21a1e91437f53e654da0d67a972851742939d039a9819be430`).
The Serial-only compile helper now records the entire overlapping common stack
in subsequent full-GN reports; the historical r3 report, created before that
evidence-only change, remains untouched and is supplemented by this record.
Reproduction using a new independently generated scratch and evidence path:

```sh
docker exec ohos-qemu-capability-inspect python3 \
  /work/ci/capability-audit/compile_serial_component.py \
  --source-root /Volumes/PSSD/qemu/openharmony \
  --source-repo /tmp/serial-upstream-pinned.git --repo-root /work \
  --product x86_64_virt --work-dir /tmp/serial-fresh-generator-x86_64-next

docker exec ohos-qemu-capability-inspect python3 \
  /work/ci/capability-audit/prepare_serial_grant_inputs.py \
  --source-root /Volumes/PSSD/qemu/openharmony \
  --scratch-source /tmp/serial-fresh-generator-x86_64-next \
  --output /tmp/serial-fresh-generator-x86_64-next/grant-jsoncpp-inputs \
  --target gen/third_party/jsoncpp/jsoncpp-1.9.6/src/lib_json/json_reader.cpp
```

These are genuine fresh generator and source-object checks, not a whole
component link, executed GTest suite, OHOS guest, or packaged-image acceptance.
r10 interrupted compile log SHA-256:
`03a68a42010b02b2efdbe8aa87db41d23167e664441f6bf8c2f87bac3a159562`.
r11 moves only the stopped, evidenced, **owned scratch** r10 output as ordinary
Ninja incremental state. It does not read writable production out, bypass GN,
or symlink the out directory back to old relative source paths. Live source/out
are required `ST_RDONLY`. Scratch build applies the parent's independent
`patches/common/build/notice/readonly_input` repair.
Subsequent owned stopped output moves retain and validate the original evidence
hash ancestry, including r13's failed LOAD; no failed GN is relabeled a pass.
The actual IDL check is
`foundation/ability/idl_tool/idl_tool_2/util/file.cpp:392`, `F_OK|R_OK|W_OK`.
Only original `.idl` bytes are copied, with per-input SHA records; no generated
header, template, compiler, or production mount is substituted or modified.

Reproduction (the cache was copied read-only to the inspector's private `/tmp`):

```sh
docker exec ohos-qemu-capability-inspect python3 \
  /work/ci/capability-audit/compile_serial_component.py \
  --source-root /Volumes/PSSD/qemu/openharmony \
  --source-repo /tmp/serial-upstream-pinned.git --repo-root /work \
  --product arm64_virt --work-dir /tmp/serial-full-gn-arm64-new \
  --compile --jobs 2
```

This invokes normal `build/hb/main.py build --no-indep --prebuilt-sdk=true`
with `--build-target serial_manager serial_manager_tests drivers_peripheral_serial selinux_adapter --build-only-gn`
and `--gn-args 'device_type="2in1"'`, followed by actual release Ninja with
`-w dupbuild=warn`. The generated part variant is called `phone` by the generic
platform; the GN `device_type` is explicitly `2in1`. Each finished attempt
writes its own `serial-build-evidence.json`; only a completed actual Ninja can
set `product_component_compile_passed`. No value sets the first-package gate.
Ninja additionally names the actual path-qualified trusted UI target
`base/usb/usb_manager/frameworks/dialog/dialog_ui/usb_right_dialog:dialog_hap`
(the unqualified `dialog_hap` is ambiguous in the generated graph).

The permission-free ordinary HAP's public ArkTS 1.1 page and native ACL
diagnostic compile through the installed SDK for all three ABIs. No HAP is
signed or installed by this work; these are **SDK probe-build checks only**.
Artifacts under `/Volumes/PSSD/qemu/validation/first-20261005`:

| Architecture/project | Unsigned HAP SHA-256 |
| --- | --- |
| `serial-normal-hap-arm64-20261006-r4` | `3e82be27a3df39377ba80dd79a02651d4411bcfa6174a66807de5faebc0bf41f` |
| `serial-normal-hap-armv7a-20261006` | `9590a46e54b5d9c2a709fa4377df5734c65a97b95e11b550d76453028e60b302` |
| `serial-normal-hap-x86_64-20261006` | `6bfda1ffe2769da33e12041647c20cfa273eadde4d2e9c8e8286505bb65adf03` |

Each project has `serial-probe-inputs.json`, actual commands, and SDK build-log
hashes. The verifier, private Unix transport/attachment, IDL/jsoncpp/CMake-isolation,
fixed-policy and parent-owned builder wiring fixture tests pass:
`python3 -W error::ResourceWarning -m unittest discover -s ci/capability-audit -p 'test_*serial*.py'`.
Fixtures, including the synthetically consistent transcript, never establish
guest or package acceptance. The verifier always leaves the package gate false.
The host helper records completed echo only after actual `sendall` succeeds,
rejects partial/error sends and late unexpected bytes, and keeps the endpoint
attached while guest control/close tests finish.

The attachment scenario also builds a permission-free normal HAP through the
real ARM64 SDK. Project `serial-attachment-hap-arm64.2qsmCu`, unsigned HAP SHA
`918a1589db29fcdc64af9a8a21424991f9bf202883f1a6ae41708f2947e8d229`.
Its fresh run ID and source hashes are recorded in its own inputs. This SDK
build is not real authorization, rendered UI, device or guest acceptance.

`check_serial_product_objects.py` queried the actual r14 GN/Ninja compiler
commands for changed production manager/service and new boundary-test objects,
then redirected only object/depfile outputs to a separate diagnostic directory.
The initial attempt failed because genuine generated prerequisites were not
ready (`ibundle_mgr_ext.h` for all three objects). No substitute header was made.
This is an object diagnostic failure,
not an SDK check or a component link result. Evidence:
`ohos-qemu-capability-inspect:/tmp/serial-product-objects-arm64-r14/serial-product-object-evidence.json`.

## Required builder/packaging wiring

Before a fresh **2in1** preload, import the pinned SIG and invoke the five
component `apply.sh` files on a safely writable new candidate checkout. Add to
that product config only:

The r19 application order and complete arguments are:

```sh
bash patches/2in1/base/security/selinux_adapter/serial_metadata/apply.sh --source-root NEW_SOURCE
bash patches/2in1/base/busmanager/serial_manager/apply.sh --source-root NEW_SOURCE --source-repo PINNED_CACHE
bash patches/2in1/base/usb/usb_manager/serial_dialog/apply.sh --source-root NEW_SOURCE
bash patches/2in1/base/startup/init/serial_devices/apply.sh --source-root NEW_SOURCE
bash patches/2in1/device/qemu/serial_usb_endpoint/apply.sh --source-root NEW_SOURCE
```

Only the importer requires the extra `--source-repo`. None of these entrypoints
accept `--product`. Import must precede generic part traversal; do not repeat
it through a generic invocation missing the cache or adding unsupported flags.
The persistent original host cache is the fixed path listed above; mount it
read-only into a new builder and pass its container path. The inspector's
`/tmp/serial-upstream-pinned.git` is not a persistent production input. Parent
subsequently made a separate bare local mirror at
`/Volumes/PSSD/qemu/git-mirrors/busmanager_serial_manager.c05fbbf.git` with
`clone --bare --no-hardlinks`; the same commit/tree guards still apply. No
network fetch or change to the release manifest is required for this cache.

Required product parts:

```json
{
  "busmanager": ["serial_manager"],
  "hdf": ["drivers_interface_serial", "drivers_peripheral_serial"]
}
```

Keep the release manifest fixed. Do not select Serial/Taihe for phone, delete
the official 2in1 syscap, or advertise phone's unrelated USB Serial NDK as this
module. Verify actual product selection/packing of `dialog_hap`; an existing UI
source is not proof that the signed HAP reached the image.

Before guest testing, verify actual image files/ELF architecture/DT_NEEDED:
`libserialsrv_client.z.so`, `libserialservice.z.so`,
`module/busmanager/libserial.z.so`, `serial_service.cfg`, profile
`/system/profile/serial_service.json`, SA4202's correct libpath, the Serial
interface proxy, vendor/chipset passthrough `libserials_service_1.0`, and the
trusted `com.usb.right` HAP with unchanged signing identity. Full product packing
must include the selected peripheral group, not only link the client service.
The SA is on-demand (`run-on-create=false`), despite the older AGENTS note.

Check namespace passthrough loading and the existing
`base/security/selinux_adapter/sepolicy/ohos_policy/busmanager/serial_manager/system/serial_service.te`
on the guest. Source SELinux policy existing is not an enforced-runtime pass.
Do not globally widen system ACLs, relabel arbitrary ttys, install develop-test
services, or treat driver/proxy absence as a successful empty implementation.

## Dedicated real endpoint and new-package acceptance procedure

Use a separate QEMU USB FTDI endpoint, not the monitor, HDC, ttyAMA0 console,
or an ordinary app-shared world-writable PTY. QEMU 11.0.3 locally exposes
`usb-serial`/`chardev` and default `always-plugged=off`. Example additions to a
**new Serial-validation VM**, reusing its existing xHCI bus (do not add a
conflicting second host controller):

```sh
umask 077
serial_runtime_dir=$(mktemp -d /tmp/ohos-serial-runtime.XXXXXX)
# Insert the following into the scoped new QEMU launch, not an existing VM:
# -chardev socket,id=serialdata,path=$serial_runtime_dir/data.sock,server=on,wait=off
# -device usb-serial,id=serialdata,chardev=serialdata,serial=ohos-qemu-serial
```

Keep the private directory mode 0700 and Unix socket owner-only; no TCP listener
or broadly reachable host data channel. Verify the actual guest's FTDI binding,
sysfs VID/PID/manufacturer, `/dev/ttyUSB0` (or explicit other port), uid/gid1025,
mode0660, and ordinary raw-open `EACCES`. Without connected hardware, there must
be no successful fabricated transfer or authorization. Empty enumeration can
describe actual absence; it is not positive Serial acceptance.

Build a fresh ordinary HAP (new random run ID per actual run), then sign with
the existing test-only development signer as `normal` / `hos_normal_app`, empty
ACLs/restricted permissions. Do not use `com.usb.right` as the probe bundle or
change signing identity to bypass approval.

```sh
python3 ci/capability-audit/build_serial_hap_probe.py \
  --arch arm64 --output /absolute/new-serial-project
# serial-probe-inputs.json freezes run_id and selected port.
python3 ci/capability-audit/serial_host_echo.py \
  --socket "$serial_runtime_dir/data.sock" --run-id FRESH_RUN_ID \
  --output /absolute/new-host-transcript.jsonl
```

Host connection makes the real FTDI hardware visible. The HAP buttons enumerate
the device, record genuine ordinary-HAP raw syscall denial, ask the operator to
choose **Deny**, then ask for **Allow** in the actual system dialog. It performs
fresh challenge-correlated binary transfers, two callbacks, 4096-byte write,
individual/last callback removal and restart, flush/drain/break, RTS/CTS/DTR/DSR,
close, and numeric invalid parameter/not-opened/denied errors. Control APIs must
report real results; a socket endpoint does not establish electrical modem
signal behavior on a physical cable.

```sh
# Capture serial-results.log from the ordinary HAP's own sandbox via the scoped
# guest test channel; retain operator/UI evidence, not only application logs.
python3 ci/capability-audit/verify_serial_results.py \
  --guest /absolute/guest-serial-results.log \
  --host /absolute/new-host-transcript.jsonl \
  --inputs /absolute/new-serial-project/serial-probe-inputs.json
```

The verifier rejects wrong run/bundle/port, missing or reordered lifecycle cases,
non-number errors, root/raw-node/world-writable “permission” proofs, changed or
partial bytes, duplicate/stale host frames, and a missing positive grant/data
path. It never changes the repository's first-package gate.

For a separate fresh ordinary attachment HAP use
`build_serial_hap_probe.py --scenario attachment`. Retain actual trusted UI
video/logs and read-only guest `stat -L` snapshots of both `/dev/ttyUSB0` and
`/sys/class/tty/ttyUSB0/device` before/after every detach/replacement. Use only
the new validation VM's owner-only socket or scoped QMP device; do not alter
the live R6 VM/HDC/console. The stage button exercises:

Use the dedicated host controller for this **separate** no-byte-transfer
attachment scenario, rather than the four-frame echo helper:

```sh
python3 ci/capability-audit/serial_host_attachment_control.py \
  --socket "$serial_runtime_dir/data.sock" --run-id FRESH_ATTACHMENT_RUN_ID \
  --output /absolute/new-attachment-host-transcript.jsonl
# Commands on stdin: attach, detach, attach, detach, attach, detach, quit.
# Issue each command only at the matching actual HAP/UI/sysfs stage below.
```

Keep the connection open during each Allow/Deny step. First attach, start the
pending-open stage, detach during the actual trusted UI. Reattach for replacement
Deny and Allow, then detach with the opened port's disconnect observers armed.
Reattach for replug Deny/Allow/close; detach and explicitly quit afterward.
The controller checks private socket ownership/permissions, rejects duplicate
connects or a replaced backend, and journals only completed real host socket
operations. EOF, failed operations and unknown commands fail rather than imply
acceptance. Host disconnect is not itself proof that the guest's real devnode
disappeared; correlate guest sysfs/stat snapshots and UI evidence independently.

Attachment HAP stages:

1. Original enumeration, open waiting in actual UI, physical detach:
   numeric35700003, no silent successful open.
2. Reattach identical public VID/PID/maker/tty, choose Deny in a **new** UI:
   numeric35700007; silent inherited approval fails the probe.
3. Choose Allow, retain raw EACCES, register two disconnect callbacks and remove
   one, unplug: retained callback once, removed callback zero; absent enumeration
   then stale-object write numeric35700003.
4. Reattach identical tuple, new Deny35700007 then actual Allow and close.

Capture `serial-attachment-results.log` and run
`verify_serial_attachment_results.py --guest LOG --inputs INPUTS`. It strictly
checks stage order, numbers, tuple, callback counts and ordinary ACL record,
but explicitly does **not** establish hardware/UI/package acceptance. Actual
late trusted-UI approval after detach, old-session late finally, two ordinary
apps/users and preservation of another attached device's grant remain required
guest cases. A public HAP cannot impersonate the trusted grant caller to “test”
the system-API cases.

Still required before calling this repaired:

1. Complete latest-candidate real component/test and peripheral library builds;
   test the actual trusted dialog HAP build/signature, not only the public probe.
2. Boot a **new packaged 2in1 artifact** containing this candidate; retain path,
   checksum, host/guest versions, launch command, input/HAP/profile identities,
   commands, real UI decisions, guest/host data and namespace/SELinux results.
   A phone first artifact cannot positively test a 2in1-only Serial repair.
3. Deny/allow race and timeout with late grant to the same token/port; UI
   connection failure/cancel, duplicate Allow, wrong user/bundle/token/device;
   genuine system-API calls using the real system SDK/identity are separate
   tests. Public-SDK TS rejection must not be counted as this runtime test.
4. Two ordinary apps/users: no inherited grant, busy-device behavior, client
   death/GC cleanup, last listener removal, SA death/reconnect, idle save/reload,
   boot-scoped authorization clearing. Actual C++ InnerAPI client runtime
   results remain separate from the public NDK and root-only diagnostics.
5. Physically disconnect the dedicated backend, exercise on/offDisconnect,
   reattach/re-enumerate and stale port object errors. Test changed device info,
   unavailable host input, read/write timeout and 0/max boundaries. The public
   device key lacks a hardware serial-number field. Verify the new attachment
   metadata boundary on the new guest with reused tty names; it is not
   cryptographic hardware authentication or an atomic verified-fd binding.
6. After representative behavior is genuinely accepted, validate other
   architecture/device artifacts. Do not start an unattended six-package matrix
   from any compile, archive, static, fixture, or older-image result above.
