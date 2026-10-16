# Public `still` source batch

The source candidate connects API26 `stationary.on('still', ...)` to the real
existing absolute-still threshold algorithm, with independent logical type state,
shared physical accelerometer ownership and real worker retirement. It also fixes
per-type listener/event/death cleanup and failed-enable rollback. No event is
created without acceleration input. `relativeStill` remains unsupported.

The two native batches were frozen separately and used only private mounts,
2 CPUs, 5 GiB, no network and a 60-second outer timeout plus a 3-second kill grace.
No OHOS source/out, SDK, product compiler, GN, Ninja, QEMU or guest was used.
Both containers were removed and the unique heavy lease returned immediately.

- `host-01/` preserves both failed compile commands and logs. No case ran. GNU
  found incomplete `SensorUser` initialization, treating a real void callback as
  bool, a missing owner-check macro and an unused parameter. Its original driver
  printed failure but returned shell status 0; the delivered driver returns 1.
- `host-02/` preserves both successful GNU `-Werror` ASan/UBSan commands and all
  12 passing cases. The batch also contains the actual death-recipient declaration
  and the corrected ordinary-mutex call chain found in light review before it.
- `source-guard-tests.log` records six Python-only exact installer tests.
- `platform-compilation-contract.json` gives real fixed GN labels and Ninja object
  targets, configurations and CFI/LTO link boundaries for root integration.
- `result.json` reviews all ten assigned system requirements once, identifies
  these fourteen source targets and retains the cumulative 37-target set.

The native cases cover public type dispatch without aliasing other types, physical
subscription sharing, duplicate-reference cancellation, callback reentrant stop,
actual `dlopen`/`dlclose` and three reload generations, SetBatch rollback, failed
Deactivate retention/retry, unsupported relativeStill, missing shared ownership,
per-type first/last listener, failed enable/death registration, client death,
callback reentry and per-listener ENTER/EXIT selection. The Linux map check proves
actual host unload; a successful cleanup return alone is not accepted.

Actual SensorAgent API and DTO headers, IMsdp and unchanged algorithm support
sources are frozen with hashes. Only host logging/thread-name adapters and
explicit SensorAgent/Binder fault injection are used. This does not establish
actual OHOS ABI/CFI behavior, Binder death, a genuine external Sensor HDI input,
physical immobility accuracy, normal HAP permissions or newly packaged behavior.

Root must compose the component after `sensor_input`, compile/link the affected
real product objects in the listed configurations with product CFI/LTO intact,
then build/sign the normal caller and validate a fresh external challenge through
VDI → Sensor HDI → SensorAgent → actual algorithm → public callback. The normal
caller/controller work is a separate next delivery. Package archive, signature,
UID, same-boot, nonce/generation, stop/quiet and negative input proof remain open.
The ledger remains unchanged: zero requirements closed and no first-artifact gate
passed by this batch.

## Bounded-wait follow-up after host-02

Light review found that the external callback drain was safe but unbounded. The
follow-up keeps the same 14 source targets and adds a one-second wait deadline.
Failure retains the inactive callback slot/owner and logical stopping state and
propagates RET_ERR without physical stop or dlclose. A later retry may complete
after the real callback returns. Self-unsubscribe remains nonwaiting.

The harness adds `external_callback_quiesce`: block the real algorithm callback,
require bounded truthful failure with the DSO still mapped and no Deactivate,
release the callback, retry and require actual worker join/unload. It is prepared
but **not executed** in this follow-up. `bounded-wait-prepare.json` and
`bounded-wait-source-guard-tests.log` are light checks only. Root's already frozen
platform01 attempt is allowed to finish; all new native failures and this delta
are to be batched in the next diagnostic cycle. No new host or product native
compile was started for this follow-up.

## Actual platform01 compile feedback

Root completed and retained its frozen `a9189eb` attempt. Twelve actual MSDP
objects passed; the three manager variants failed the same unused private-field
warning. `platform-01/` preserves those exact logs and hashes. The current source
removes the obsolete `type_`, `event_`, `arrs_` fields and array-only `argSize_`
after checking all actual member uses. It preserves warning settings. The real
stationary-server label has manager/client objects, no service object; the
platform contract now lists exactly 15 real objects. Current-source native
recompilation and all 13 host cases remain pending a root-scheduled batch.
