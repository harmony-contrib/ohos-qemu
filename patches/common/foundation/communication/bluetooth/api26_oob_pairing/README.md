# API 26 OOB pairing entrypoint

Pinned Bluetooth framework: `1727fa05c457f697f7cf80f290c82c663f1c3aab`.
Apply `apply.sh --source-root OPENHARMONY_ROOT`; the existing API 23
`pairDeviceOutOfBand` entrypoint and its three-argument parser are preserved.

API 26 `startPairOutOfBand(deviceId, transport, p192Data?, p256Data?)` gets its
own export, parser and actual asynchronous `BluetoothRemoteDevice` request.
The independent deviceId selects the pair target; the OOB object's existing
raw AddressInfo/confirmation/randomizer validation remains in the common parser.
The new parser accepts omitted/undefined OOB slots, requires at least one OOB
object, prefers P256, rejects extra arguments and fractional/invalid transports,
and uses copied native values in the asynchronous worker. A null work allocation
fails before native dispatch. Native permission/off/unsupported/failure results
are returned through the real promise work path.

Host tests execute the actual new function bodies with explicit NAPI/native
async doubles. They check the target/raw-peer distinction, optional selection,
invalid inputs, immutable capture after JS inputs change, creation failure and
201/202/801/off/internal error propagation. They do not establish real permission
checks or OOB pairing: the fixed BluetoothHostServer currently rejects all OOB
requests with 801, and its local-OOB generator returns NO_ERROR without data.
That genuine service/adapter/GAP/HCI implementation is a separate required batch,
as are controller/vendor transport and a real peer challenge in a new package.
No missing requirement is closed by this NAPI component alone.
