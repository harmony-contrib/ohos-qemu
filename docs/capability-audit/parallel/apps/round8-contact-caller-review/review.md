# Contacts public caller and result review

The provider lifecycle work is insufficient by itself: the pinned public caller
wrapper and native bridge contained independently reproducible result bugs.
The source candidate repairs the selection path in five separately authorized
ContactsData files. No ledger item is closed. The ordinary caller HAP and fresh
representative package acceptance remain pending root integration.

## Actual public chain

The inspected API26 declarations are
`@kit.ContactsKit` → `@ohos.contact` (contact declarations SHA256
`61bd74e70d532dde26e51cecc861e575366b37d5708f95397e835e99419ff391`).
They declare four `selectContacts` overloads and two deprecated `selectContact`
overloads. There is no public `getContact` export in this declaration: the keyed
read operation is `queryContact(context, key)` and requires READ_CONTACTS.

Pinned ContactsData project `c73bd27daa3fcd8ed6099b17cbffbd7021e3873e` compiles
`contacts/src/contact.js` through `contacts/BUILD.gn`'s `gen_contact_abc` and
`contact_abc/contact_js` into native module `contact`. Its public selection
aliases both invoke `contactsPickerSelect`, obtain `getContext(this)`, and call
the internal Contact module's `startContactsPicker`, bound to native
`ContactsPickerSelect`. The actual target is `com.ohos.contacts` /
`ContactUiExtentionAbility`, `sys/commonUI`, `BatchSelectContactsPage`.
The provider sends JSON Contact arrays in 100-record `sendData` frames with
integer `index`/`total`, followed by `terminateSelfWithResult`.

## Confirmed caller-side failures and repair

| Original source location | Failure | Candidate behavior |
| --- | --- | --- |
| contact.js:490–502 | JSON parse and total mismatch only log; malformed JSON can succeed with `[]`, incomplete 205-result can succeed with 100 records. | Strict object-array and exact bounded total validation; errors become BusinessError. |
| contact.js:505–547 | Context/native exceptions resolve `undefined`; callback overload can never invoke its callback. Nonzero provider result is rejected/callbacked as a bare number. | One Promise operation; callback returns void and receives exactly one success or BusinessError; no catch swallows failures. |
| contact.js:150–189 | API26 `isAutoDismissOnNavigation` is discarded. | Validated boolean reaches actual modal router/navigation configuration. |
| contacts_napi_utils.cpp:285–290, contacts_api.cpp:1989–2007 | Highest index advances before range checking; missing slots cause `substr(1, ...)` exceptions, indices ≥100 cause out-of-bounds access. | New selection helper checks types/ranges/counts before any array access; parses frames before aggregation. Duplicate, missing, malformed or inconsistent frames fail. |
| contacts_api.cpp:1980–1987, 2097–2131 | Selection polls a worker indefinitely, startup return 0 is unchecked, error does not assign failure, destroy is not bound. | Per-request UV async/timer, explicit failure and 10-minute deadline, immediate native window invalidation on destroy; no worker polling. |
| ModalUICallback raw BaseContext/PickerCallBack ownership | UI callbacks can outlive native async completion and still retain raw pointers. | Selection callbacks own only shared native state; no raw async context, no NAPI on UI callbacks, env cleanup closes its own handles/hook. |

The initial early report described `PickerCallBack::resultCode` as uninitialized.
That was too strong: `make_shared<PickerCallBack>()` value-initializes it to 0.
The real failure is that `OnError` leaves that implicit success code unchanged.
This correction is not counted as another defect.

The existing 205-record provider protocol is valid: indices 0/1/2 contain
100/100/5 records with total 205. Cancellation with default selected contacts
deliberately returns those contacts as result code 0. An empty user cancel is
code 1 and returns `[]`. The candidate preserves both cases. It does not use
user cancellation to mask partial data or provider errors.

Native adapter tests exercise the exact generated header and the exact new
selection implementation extracted from the patched cpp. Production UI/NAPI/UV
contracts are adapted for the host; the test does not prove the real framework
dispatch or caller permissions. 44 protocol challenges and 17 lifecycle adapter
scenarios passed ASan+UBSan. The original unsupported Darwin LeakSanitizer run
is kept in `asan-01.json`; the unchanged binary retry is recorded separately.
There is no LSan claim. 86 actual JS-wrapper scenarios passed; source guard
replay and unknown/partial-state rejection also passed.

Legacy import/save routes still call their old native helper. This selection
component does not certify that independent transport. Allocation failure that
prevents opening a NAPI handle scope cannot be treated as successful completion;
the candidate cleans native resources and logs the unavailable scope. It does
not fabricate a result in an unusable JS environment.

## Install and ordinary caller privilege

The actual BMS install check is
`BundleInstallChecker` in `bundle_install_checker.cpp:1677–1688` at BMS commit
`537bdea9ae5634a847db774fe00ba4d190cbcc65`. Its privileged-extension set is
SERVICE/DATASHARE/UI_SERVICE; its system-extension set is empty.
`SYS_COMMON_UI` is not gated by `allowUsePrivilegeExtension`. This does not waive
checks on any other extension types packaged in the same HAP.

AMS `CheckUIExtensionPermission` at
`ability_manager_service.cpp:12901–12951` classifies SYS_COMMON_UI as a system
UI provider and requires **the target** `abilityRequest.appInfo.isSystemApp`,
plus a valid caller record. The separate `IsSystemCallerNeeded` set does not
contain SYS_COMMON_UI. Foreground and PID/host-window checks still apply.
Therefore preserve Contacts' real system-app profile and signature association;
do not add privilege-extension permission to the ordinary test caller. This is
source evidence, not a BMS install/token result. Exact file hashes and excerpts
are in `policy-and-lifecycle-evidence.json`.

## Integration boundary

Root owns `sync_mode → picker_result_protocol` ordering, precise predecessor
successor guard, product compile/TU/ABC, OS signing/preinstall and fresh ARM64
phone UI acceptance before the other five packages. The existing eight provider
business files and all build metadata remained frozen in this batch. No SDK,
product native compilation, QEMU or image build was run here. Only explicitly
leased small host compilation/execution occurred.
