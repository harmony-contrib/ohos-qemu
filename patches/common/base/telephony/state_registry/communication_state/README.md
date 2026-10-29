# Modem 5A state producer and observer

Pins core_service, ril_adapter and state_registry to their fixed project HEADs
and accepts only the complete original or final byte state of all targets.
An explicit native vendor unsolicited notification carries 0/1 through HRil,
RIL V1_5 callback 162, core_service, registry IPC 14, and observer callback 13.
Neither NR registration nor network presence is interpreted as 5A.

The parent-owned drivers/interface/ril/v1_5/IRilCallback.idl extension is required:
`CommunicationStateUpdated(RilRadioResponseInfo responseInfo, boolean is5A)`.
The complete inherited HDI generation must preserve all original transactions.
This component does not patch driver projects.

The reference AT vendor accepts the exact unsolicited line `+OHOS5A: 0` or
`+OHOS5A: 1` (optional surrounding trailing whitespace). A controlled external
modem peer must deliver it over the real configured AT device. Invalid payloads
are ignored. No initial false is synthesized before a real modem update.

Dynamic on/off accepts a mandatory callback and optional slot options. Removal
is scoped to env, slot, event and callback. A deleted generation cannot dispatch
its queued work to a later registration. Env cleanup releases callbacks even
after permission revocation. Registry publication requires the actual native
telephony process plus SET_TELEPHONY_STATE; subscription and each delivery require
GET_NETWORK_INFO. The ANI bridge carries the same explicit bool/slot data flow.

Host tests exercise actual patched function boundaries with dependency doubles.
They do not replace complete platform TU, actual modem/HDI or new-package runtime
validation. No capability requirement is closed by this source patch alone.


The second patch declares access_token:libaccesstoken_sdk on the actual observer
and observer_ani_cxx GN targets. All44 complete files now have pinned original,
first-patch prefix and final states. The previous binary enum patch/CRLF bytes
are unchanged. See round8-access-token-gn.md/json for the parent full-TU failures,
real SDK public exports and remaining actual compilation/link/GN/runtime gates.

Patch3 adds consistent override specifiers to all actual proxy callbacks and
explicitly includes the service IPC identity header. The complete44-file guard
accepts original, prefix1, prefix2 and final states; mixed/unknown bytes are
rejected. It neither changes signatures nor disables the compiler warning. See
round8-native-contract-fixes.md/json for the preserved batch04 failures and
required complete-platform revalidation.
