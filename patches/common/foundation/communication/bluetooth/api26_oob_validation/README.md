# API26 OOB input validation follow-up

Apply after `api26_oob_pairing` at the same pinned framework revision. Both
provided OOB objects are independently validated before choosing P256. The P256
object uses its own value so P192 optional fields cannot leak into it.

The fixed SDK file `interface/sdk-js/api/@ohos.bluetooth.connection.d.ts`
SHA256 `b77b7d6e432cc51811efc8cfbd05126c7ccc42a6fd6a7d62dc0b2fb2ca52e170`
lines 265–268 explicitly specifies that P256 takes effect when both are supplied.
The pre-existing IPC therefore remains one `BluetoothOobData` containing a
7-byte address/type, a 16-byte confirmation hash, an optional 16-byte randomizer
and `oobDataType` P192=1/P256=2. No dual-curve negotiation contract is invented.

Actual parser regression executes malformed P192/P256 with the other valid,
undefined slots, invalid transport, asynchronous capture and real result-code
propagation through explicit native doubles. Actual controller/peer OOB remains
unverified and requires the separate service candidate and new package tests.
