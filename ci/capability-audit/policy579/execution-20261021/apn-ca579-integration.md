Source candidate only. No parser, import, host test, SDK, signing, compiler,
component applier, QEMU, HDC, QMP or resource command was executed here.
All runtime/first-artifact/full-matrix gates remain false.

Apply the 17 `canonical/` files by their CHANGES.json paths and modes, plus the
16 caller deltas using CALLER.patch. Parent must compare each explicit before
hash against its current serially edited source; do not overwrite with a stale
whole module if the parent has further changes. Original 28 sources and the
previous frozen NetPolicy/DND batch are not rewritten. The generic helper
`patches/lib/apply_exact_component.py` and `exact_source_states.py` stay original.

The four components contain 26 managed product sources: CallSetting 15, its
native launcher 1, CertManager 9, and its native launcher 1. All ordinary product
source modes are 0644. Each component's apply.sh is 0755; all other canonical
files are 0644. Whole-before/whole-after hashes reject unknown or partial states.
CRLF_FILES names the original CRLF targets for the existing applier. No native
interface, permission definition, public vtable or certificate service policy
was widened.

Parent source integration order:

1. Apply all original application/native components and the four new exact
   components before calling the profile helper. Add the CallSetting single GN
   hunk in HAP-SOURCE.patch to the current composed HAP BUILD.gn; HAP-BLOCK.json
   records its actual original export. The parent updates existing whole-GN
   guards to this exact final composed state. Do not restore an old whole file.
   The selected `CallSetting_hap` now depends on the complete official
   `//applications/standard/call/CallSetting:callsetting_hap`, so the new UI
   enters the real image instead of leaving the selected prebuilt unchanged.
   The already-selected `user_cert_manager` target retains its target/name/
   component/install directory, and now compiles the whole modern CertManager
   feature instead of the legacy asset targets.
2. Resolve the complete original CallSetting dependencies through the parent's
   actual prepare path. Preserve `@ohos/lottie:2.0.23`, common and cust HARs and
   original satellite/other pages. Root obtained the real 193331-byte HAR
   c05579c5378e6ac696a4c36e7ae0a1fde09f611bc47ec198fc91100c8db2cbc5.
   The fixed default dependency is file:libs/lottie-2.0.23.har; helper requires
   --lottie-input root-ref.json containing the actual absolute path/sha256
   (optionally bytes), copies exactly those pinned bytes into the owned cache
   and that fixed source path, and all later source/package admission rechecks
   them. No live registry fallback or stub dependency exists. The HAR is a
   producer-staged immutable input, like the bound profile, rather than a
   component-managed mutable file. Root owns its true download/cleanup receipt.
3. Parent serializes only the exact BMS entries. CallSetting is installed at
   `/system/app/com.ohos.callsetting`, removable=false; its capability row is
   `{bundleName:com.ohos.callsetting,app_signature:[existing OS signer],
   allowAppUsePrivilegeExtension:true}` for its original restricted extensions.
   Preserve the already-existing CertificateManager install entry at
   `/system/app/com.ohos.certificatemanager`, removable=true. Its actual bundle
   is `com.ohos.certmanager`, feature module `CertManager`; add only its exact
   OS-signature capability row, with no new privilege-extension flag. Never
   confuse the install directory with the bundle. Root owns whole install/
   capability/grant JSONs; this candidate does not replace those tables.
4. Through the existing original producer environment, after source and BMS
   preparation, run the fixed helper for each provider:

       python3 patches/lib/dialog_providers579.py --provider callsetting --source-root "$SOURCE" --cache-root "$OWNED_CACHE" --lottie-input "$LOTTIE_REF" --prepare-profile
       python3 patches/lib/dialog_providers579.py --provider certmanager --source-root "$SOURCE" --cache-root "$OWNED_CACHE" --prepare-profile

   This composes the exact original profile with the existing OS leaf and
   expiry only, verifies original and final CMS using the actual signer tools,
   and reports the actual signer/profile. It does not invent signing results.
   CallSetting retains original system_core APL and all original ACL/restricted
   permissions. CertManager retains original normal APL, complete original ACLs
   (including their actual null element) and original privilege capabilities.
   Original profile bytes are pinned from their fixed Git objects, then exact
   final CMS is verified; a mutable signed profile is intentionally not also an
   immutable source prerequisite. No ordinary negative caller gets a privilege
   extension or extra permission to make installation succeed.
5. Use the original ohos_app/Hvigor/image packaging path. Before old package
   removal, call helper `verify(root,provider)` for actual source/profile
   admission, and `payload(hap,root,scratch,provider)` for the real compiled HAP.
   It requires exact source bundle/version/module/device/permission/extension
   lists and actual implementation markers/resources, while allowing unrelated
   Hvigor-generated metadata fields. It invokes the original actual signature
   verifier with this prepared profile. These results admit actual production
   inputs only, never a runtime/first-artifact pass. Parent adds fixed package
   gate/build-input HAP receipts and actual same-boot BMS/hash binding.

The existing held Apps callbacks/bind(root_io) surface is unchanged. Only one
finite business action, `apn-type`, is added to the existing business callback.
It accepts `{field:name|apn,text:<one of the four nonce-derived literals>}`,
requires the actual QMP send-key command, clears the focused real editor with
Ctrl+A/Backspace, and types physical keys (`.` maps to QEMU `dot`). Every record
retains full original greeting/capabilities/request/reply JSONL and same-boot
Refs. The parent must bind each through original_qmp_replay; no synthetic QMP
reply or shell label containing an ID is introduced.

APN original ID: `behavior:telephony-apn-settings-provider-missing`.
The native public launcher now targets the actual OH bundle and sys/commonUI
extension. GeneralCallSettingDialogAbility admits only the actual default
active SIM slot and SYSTEM_APN_SETTINGS local Want, then serves the original
APN List/Details and real DataShare backend. Original ordinary CallSetting
navigation remains; the separate modal supplies the same path stack/context
and an actual content-session close callback. Existing original CRUD writes
now await actual backend completion and reject failure before reporting the
UI operation complete. Real prefer selection requires a true readback before
updating original preferences/radio state. The original empty-name alert
closes its own dialog. Added node IDs attach to existing real controls; they
do not replace business actions.

APN caller a/b has MANAGE_APN_SETTING + GET_TELEPHONY_STATE only. The actual
03 export's `base/telephony/telephony_data/pdp_profile/src/pdp_profile_ability.cpp`
Query:396 checks GET_TELEPHONY_STATE; Insert/Update/Delete still require SET,
which stays exclusively with the real original CallSetting provider. Normal
and system-denied callers use a public-only program without the DataShare
implementation. All writes are real packaged UI actions. The original public
query and an independent readonly DataShare catalog/preference consumer must
agree for a/b. Each original row, default slot/operator and preferred APN is
retained; cleanup only deletes the unique current-nonce new row through UI.
The actual EditableTitleBar Save/Back IDs are derived from the actual hierarchy
using fixed source patterns, and scrolling uses actual List bounds. The plan
`apps_ui578/ui_plans/apn-base.json` pins original default English strings and
the exact source controls; there is no invented Chinese/other locale fallback.

APN positive requires a true active default SIM, valid operator numeric and an
existing restorable preferred APN, then real create/blank-name reject/select/
edit/cancel/death/recreate/delete/finally restoration. Current AT peer has SIM
missing/unregistered and no CRSM/ICCID/CIMI; it cannot meet this precondition.
The no-SIM path records the actual native null rejection (Journal code -1),
then fails the positive case. `verify_no_sim_boundary` may report only that
bounded actual failure after original raw binding, always runtime_pass=false,
formally_closed=[]; it is not unsupported and not a repaired positive. Root
will supply an actual RIL SIM fixture separately, never a JS/DB fake active SIM.
The reused official APN pages serve slots 0/1; eSIM/SkyTone slot2 is not claimed.

CA original ID: `behavior:certificate-dialog-device-result`.
The native uninstall launcher keeps actual certificateType separate from page
type and sends both; page5+UNINSTALL now selects the real new removal page.
The page displays the actual certificate subject/issuer/fingerprint, uses the
original user-auth model, re-reads exactly the displayed URI/DER after auth,
then invokes the original certificate service deletion. Actual permission,
URI ownership, CA syscap/IsEnableCACertDialog policy and service authorization
remain. Completion is delivered only after real delete success; cancel/param/
operation errors retain the original native error mapping. Auth exceptions
invoke failure instead of hanging, and stale/dead UI callbacks cannot mutate.

The caller preserves original private credential selection, permission reject,
cross-UID isolation, cancellation, process death and public X509 consumer.
CA-enabled execution adds actual install cancel/commit, DER+fingerprint read,
uninstall cancel, pending caller death/recreate, actual confirm-delete and exact
original trust-inventory restoration. Finally can recover only a unique nonce
DER URI absent from the baseline and then uses the real uninstall UI; no
unrelated certificate deletion or root service shortcut exists. The existing
CA policy can legitimately report 29700004; that records the actual policy
boundary and cannot substitute for CA-enabled success. A guest with enrolled
PIN/biometric requires actual original authentication UI; no fake success or
credential bypass is implemented. Root must supply that real UI input or use
the actual fresh guest no-PIN policy, and retain the raw authentication chain.

The original verify(...) still refuses every original SLICE_ONLY aggregate.
verify_observations(...) performs all raw/UI/provider/cleanup checks and returns
whole_id_closure=false/formally_closed=[]; the parent must compose the full
original-ID gate with its other real families. No ID or failed stage is closed
by source preparation, UI-node existence, an exported getter or a pass summary.
The previous 47 checks/constructor/ledger and all other Apps families remain.

DND follow-up: DND-FALLBACK.json records the actual selected HAP disassembly
functions. ConfigParseUtil and RawFileUtil catch missing optional config; the
preload path falls back to DND/SLEEP IDs and actual embedded mode data. Do not
invent etc/IntelligentScene/intelligent_scene_list.json. Actual DND first-boot
database/provider/UI behavior still needs the new package runtime gate.

Pending: parent serial source application/registry/profile/Hvigor/native build,
new package with exact selected HAPs, genuine SIM, actual CA policy/auth input,
same-boot BMS/installed hashes, real UITest/QMP business chain and independent
raw replay/cleanup, full 47 + aggregate original-ID first-artifact gate, then
remaining packages. All remain pending; this source delivery is not acceptance.
