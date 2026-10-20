This is an implementation candidate for actual new-package QEMU validation.
No host test, parser check, SDK/compiler/signing command, container operation,
QEMU/HDC run or capability closure was performed by this child.

Exact original IDs (15)

- arkts_export:@ohos.bluetooth.connection:startPairOutOfBand
- behavior:bluetooth-state-transition-false-success
- arkts_export:@ohos.telephony.call:offReceiveRttMessage
- arkts_export:@ohos.telephony.call:offRttErrCause
- arkts_export:@ohos.telephony.call:offRttModifyInd
- arkts_export:@ohos.telephony.call:onReceiveRttMessage
- arkts_export:@ohos.telephony.call:onRttErrCause
- arkts_export:@ohos.telephony.call:onRttModifyInd
- arkts_export:@ohos.telephony.call:sendRttMessage
- arkts_export:@ohos.telephony.call:setRttCapability
- arkts_export:@ohos.telephony.call:startRtt
- arkts_export:@ohos.telephony.call:stopRtt
- arkts_export:@ohos.telephony.observer:offCommunicationStateChange
- arkts_export:@ohos.telephony.observer:onCommunicationStateChange
- behavior:telephony-no-modem-or-sim

Boundary

The fixed default product has no complete IMS/RTT peer/media provider or Bluetooth
controller/vendor/security peer. Only those full positive sessions are bounded
unsupported by provider-support578/PER-ID.json and its primary-source evidence.
API bodies, permissions, parameters, real registration/removal, no-session
failure, no-modem state, and failed-enable OFF rollback remain mandatory real
new-image behavior. No entire original ID is excluded here. Valid classic
P192/P256 OOB calls while OFF must return the actual OFF error, not a blanket
801. LE P192, omitted R, virtual alias and local generation retain their exact
existing limitations; reaching an earlier OFF gate does not test their ON path.

The JS core imports actual public modules. It has no framework implementation,
SDK declaration stub, private registry publisher, callback injection, filtered
listener wrapper or supplied expected result. JS is deliberate: wrong types,
undefined, omitted and excess arguments must reach the actual N-API parser.
EntryAbility is a real singleton Stage caller and persists complete JSONL in its
actual module filesDir. Compile it using the parent's existing real caller
project/build/signing flow; replace exactly one __COMMUNICATIONS578_RUN__ with
the original Owner's 32 lowercase hex run ID. Copy EntryAbility.ets and
CommunicationsAudit.js to the same entryability directory; Index.ets goes to
pages/Index. Use a finite module manifest with no extensions and the exact
singleton EntryAbility. Each role uses a separate actual bundle under
org.harmonycontrib.communications578; lifecycle has three distinct bundles.
Declare only the permissions actually used for that role, from contract.py.
System and denied roles both have real system-app signatures; denied omits the
relevant permission. Ordinary has a real ordinary signature and sufficient
ordinary permissions. Parent must verify actual BMS/APL/token/UDID grants using
its existing signer/profile checks, never just trust a role string.

Callback stage interface

communications578_runtime.run(guest, callbacks, profile=..., run_id=...,
boot_id=..., output=FRESH_PATH, executables=EXACT_PARENT_EXECUTABLE_PATHS).
Nine finite profiles are in communications578_contract.PROFILES. Execute the
observer profile before any other 5A producer on that boot, or first reset the
real state-registry service through the parent's held lifecycle and retain that
source/boot/process evidence. No false callback before a real modem update may
be accepted. The lifecycle stage intentionally tests cached state after a real
independent zero URC and preserves that distinction.

The exact callback keys and positional arguments are:

- prepare_callers(guest, 'communications578', run_id, roles): existing build and
  signing flow on fixed source files. Must verify signed payload/UDID/APL,
  declared grants and caller bytes. Requests never choose source/import paths.
- install(guest, role): original install/ownership callback, intent recorded
  before construction so cleanup attempts even partially installed callers.
- start(guest, role, 'EntryAbility', request): original launch callback;
  aa request is a JSON string, safely quoted by the existing root machinery.
- input(guest, 'communications-permission-consent', selector): actual existing
  permission dialog interaction for ACCESS_BLUETOOTH; retain its UI evidence.
- collect(guest, role, operation_id): complete unmodified caller journal in
  `raw`; first capture also returns exact `bms_raw` JSON, `process_identity_raw`
  and `module_files_raw`. Root must reuse complete BMS/process mapping/file
  inode helpers to bind UID/PID/start_ticks/argv/token/module-files inode and
  signed image mappings. `bms_raw.applicationInfo.uid/bundleName/isSystemApp`
  are checked again here. Complete raw captures must grow by byte prefix.
- network(guest, fixed_action, parameters): the finite actions below, using the
  root's original held-resource/process machinery.
- cleanup(guest): attempts all original held resources even on early failures;
  returns complete existing cleanup transcript in `raw` and command receipts.

Every callback returns a dictionary with nonempty `receipts`. Every receipt is
actual argv, exit_code, stdout, stderr and boot_id. Executable argv[0] must be
one of the root's exact provided executable paths. Neither receipts nor raw
may be replaced by expected booleans. Parent remains responsible for original
Owner.finish, mapped-native/caller generation proof, dependency cleanup and
capability ledger decisions. This stage never defines an Owner or resource
policy, creates a host process, invokes an SDK/tool/HDC directly, or imports a
caller-selected module. Command labels in the adapter must be literal safe
[A-Za-z0-9_-]+; original IDs belong only in metadata.

AT channel and fixed network actions

Actual fixed vendor_adapter.c opens const.telephony.ril.attty.path, or defaults
to /dev/ttyUSB0; EventListeners then calls ATStartReadLoop -> ModemInit. Actual
vendor_report.c accepts +OHOS5A: 0/1 only when radio is not UNAVAILABLE. The
packaged chain is AT read loop -> vendor report -> HRil1412 -> inherited RIL
V1_5 callback162 -> core -> registry IPC14 -> observer callback13 -> public
boolean. No NR/network/SIM state is inferred to mean 5A.

- communications-at-open: the root compiles communications578_at_peer.c with
  the actual platform C toolchain, installs it in an owned fresh guest path and
  starts it using its existing held-process machinery. Pass RUN32 BOOT36;
  stdin is an owned pipe/FIFO kept open by the root and stdout is a raw journal.
  Read the actual configured AT property/path first. Only bind an absent,
  exclusively owned configured path to this fresh /dev/pts/N. Never overwrite
  an existing device/link. Give that ephemeral slave only the actual RIL
  reader's required ownership/mode/SELinux access; no broad chmod fallback.
  The C peer makes the slave raw before publishing ready. Wait for actual
  ATE0Q0V1 and AT+CFUN=1,0 traffic and preserve the actual RIL reader fd target.
  If DAC/MAC/read-loop/provider wiring fails, preserve the failure. No new QEMU
  flags are required for the PTY design; it still requires real guest devpts
  and an actual enabled packaged reference AT vendor, not merely its source.
- communications-at-write: parameters contain fresh operation_id and kind
  one/zero/invalid. Write exactly OP32<TAB>KIND<LF> to the held C process stdin.
  It emits exact URC bytes over its real PTY master and logs each raw rx/tx.
  Its finite AT configuration responses only allow ModemInit to initialize;
  CPIN explicitly reports missing SIM, registration queries remain unregistered,
  and unknown commands return ERROR. It is an explicitly controlled virtual AT
  stimulus, never a full modem/IMS provider.
- communications-at-evidence: return unmodified C stdout as `peer_raw`, plus
  `binding_raw`, exactly two lines from actual readlink -f of the configured
  AT path and the actual RIL reader's fd. Both must equal the ready PTY path.
  Root must bind the native RIL process UID/PID/start ticks and mapped packaged
  HRil/HDI/core/registry files with its original helpers and retain native logs.
  The oracle requires actual ModemInit rx traffic and exact pulse nonce/bytes,
  not just a successful PTY write.
- communications-bluetooth-native-restart: before the second failed-enable
  attempt, use the actual root-held Bluetooth service lifecycle. Return its
  raw transcript plus before/after {pid,start_ticks,boot_id}; generations must
  differ on the same boot. Preserve actual packaged HCI/vendor identity and
  failure logs. No controller or Bluetooth ON state may be invented.

AT cleanup sends/observes explicit zero before shutdown, preserves C raw bytes,
then sends a fresh OP<TAB>stop<LF>, waits the exact held generation, closes all
owned fds and removes only the original absent-path binding whose ownership is
still proved. Restore original configuration/modes where applicable. No killall
or guessed service PID. Caller cleanup uses real public off calls, original
force-stop/uninstall and two complete UID/bundle absence scans. The existing
root Owner remains the final cleanup gate; an API return alone does not prove
process/environment cleanup.

Lifecycle extension

communications578_lifecycle.run_lifecycle uses the same callback dictionary and
three genuine system bundles: system, system_peer, system_replacement. It drives
independent AT bool changes, listener/env isolation, a 5-second real JS event
loop block with actual native receipt followed by public off before queue drain,
the real SYSTEM_FIXED live-revoke rejection boundary, caller exit with surviving env,
and a distinct replacement env followed by all-off/reset. It never masks late
callbacks in user code. Additional fixed callbacks are:

- network communications-queue-native-begin/end: root's existing bounded native
  log window, filtered to actual primary caller PID and current generation.
  End returns pid and raw; exactly one real
  `OnCommunicationStateUpdated slotId = 0, activeStateResult = 1` receive is
  required in the queue challenge. Without that native receive window, queue
  silence cannot establish removal of an actually queued generation.
- input communications-revoke-network-info: PermissionController executes the
  actual AccessTokenKit::RevokePermission(token, GET_NETWORK_INFO, USER_FIXED,
  USER_GRANTED_PERM, false). This system-grant permission has SYSTEM_FIXED flag
  4; actual PermissionDataBrief rejects changing that flag. Require the real
  rejection, granted status and all flags unchanged, and the same live PID/start
  ticks before/after. The actual image then categorizes live revoke unsupported.
  No permission policy is modified. The separately signed observer-denied HAP
  genuinely omits this permission and must receive public 201. It cannot stand
  in for live revocation. The lifecycle continues actual granted on/off, wire
  delivery, env isolation, queued generation, exit and replacement checks.
- network communications-caller-exit: original force-stop/uninstall held caller
  and two complete original UID/bundle absence scans, returning actual `raw`.

Raw oracles deliberately do not assert the unavailable IMS/OOB peer positives.
Each profile lists what its raw result does not establish. The separate real
lifecycle stage is required for observer env/fixed-revoke/queue/exit/recovery. Actual
first artifact package identity/checksum/commands/runtime/cleanup belong to the
parent build evidence. Only after that full representative gate succeeds may
remaining architecture/device packages be built and validated.

Concrete root binding

communications578_bindings.bind(root_io) implements these seven closures with
the original root IO API. It creates no Owner, subprocess, resource lease, SDK
state or container. It reads actual package service configs, BMS identity,
complete process UID/start ticks, actual module/root journal inode, helper argv,
native executable/domain/maps, owned PTY inode/DAC/labels, AT reader fd and raw
wire bytes. It uses real service_control stop/start and original GuestUi. Every
command label is a fixed safe name plus a decimal counter. dmesg is retained
before/after AT and during cleanup; actual global Enforcing is required.

Root IO prepare_callers consumes native helpers already compiled with the
parent's original product helper-builder after new-package installed-profile
export and before VM start. The held-VM stage must not start another native
builder. HAP compilation/signing remains the original same-boot UDID flow.
Return this finite shape:

    {applications: {ROLE: {project: ABS_PROJECT_DIR,
                          unsigned: {path: ABS, sha256: SHA},
                          signed: {path: ABS, sha256: SHA}}},
     native_helpers: {at_peer: {path: ABS, sha256: SHA},
                      permission_controller: {path: ABS, sha256: SHA}},
     receipts: [ACTUAL_SAME_BOOT_ROOT_IO_RECEIPTS]}

Keep the actual pre-VM helper build/link/image receipts in this prepared result
as additional metadata. Do not alter their execution time or pretend they ran
inside the live boot. The same-boot private directory, sends and hashes produce
the live callback receipts. native_sources() is fixed code recipe metadata; no
request JSON may choose a source/import/target path.

environment.communications578_services has exactly the keys ril and bluetooth.
Each value has exactly name, init_path, process_name, libraries. init_path is
the actual observed packaged /system/etc/init/NAME.cfg or /vendor/etc/init/NAME.cfg,
never a guessed filename. process_name is its actual pidof name and must identify
one process, whose exe and SELinux domain must match the parsed service config.
ril.name is riladapter_host; its actual config must use /vendor/bin/hdf_devhost,
radio UID, -n riladapter_host, and u:r:riladapter_host:s0. Its library list must
include libril_driver.z.so, libril_service_1.5.z.so, libhril_hdf.z.so, libhril.z.so
and libril_vendor.z.so. bluetooth.name is bluetooth_service; actual cfg path is
/system/etc/init/bluetooth_service.cfg from the parent's build02 source export,
with /system/bin/sa_main /system/profile/bluetooth_service.json, bluetooth UID
and u:r:bluetooth_service:s0. Its libraries list comes from actual package/native
source identity, and every item must be mapped by the real service process.
environment.permission_allow_text is the exact real dialog selector text used
by the original GuestUi and retained with its hierarchy/click evidence.

Root IO wait returns an actual ordinary receipt, including argv, exit_code,
stdout/stderr strings, stdout_ref/stderr_ref, boot_id and timed_out=false. It
must wait the original held process; this stage neither replaces that process
nor constructs another wait owner. Final cleanup verifies its zero URC, final
closed journal and process absence before removing the owned AT path/files.

communications578_native.helper_recipes() returns the original helper-builder
recipe shape with fixed source_file paths inside these owned QA tools. The C
recipe uses the actual exported ril_vendor.ninja/vendor_adapter.o/source C edge;
the C++ recipe uses the existing actual libaccesstoken_sdk token anchor. Preserve
actual GN flags, runtime-profile relinks, source/dependency/link traces, CFI/LTO,
and ELF/interpreter/DT_NEEDED proofs. The C helper must use the builder's C ELF
contract and has no std::__h symbol requirement; the permission helper retains
the real __h C++ ABI requirement. Both are diagnostics; no fresh GN selection is
claimed merely because this directory includes BUILD.gn declarations.

Root cleanup first attempts a fresh genuine public cleanup command for every
started caller, recording its complete journal and checking late callbacks.
This restores touched RTT local capability OFF and the actual observed data
policy baseline even after an earlier profile failure. Force-stop/uninstall and
original UID scans are still attempted if that public cleanup fails. Callers
that have already exited are never recreated to fake live cleanup.
