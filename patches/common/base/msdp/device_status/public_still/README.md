# Public stationary `still` and shared sensor lifetime

This component applies **after** `../sensor_input`. Its 14 exact upstream targets
are guarded by `manifest.json`; the two overlapping `.cpp` files must match the
previous component's final hashes. The previous component and all original source
fixtures remain unchanged. The installer refuses unknown edits, mixed states and
symlinks, validates a private candidate, and restores written files on failure.

```sh
python3 patches/common/base/msdp/device_status/sensor_input/apply.py --source-root /path/to/ohos
python3 patches/common/base/msdp/device_status/public_still/apply.py --source-root /path/to/ohos
```

API26 calls public `still` “Absolutely still”. The actual NAPI maps it to
`TYPE_STILL`; the old native backend accepted only the separately named
`TYPE_ABSOLUTE_STILL`. An independent `AlgoAbsoluteStill` instance now accepts and
reports `TYPE_STILL`. It preserves the original magnitude heuristic: five events
with `7 < sqrt(x*x+y*y+z*z) < 11` report ENTER, an out-of-range event reports EXIT.
This establishes API-to-existing-algorithm behavior, not physical immobility
accuracy. `relativeStill` remains unsupported; no mock result is introduced.

Each logical algorithm retains its own instance and callback type. One physical
accelerometer registration is shared and is released after the last logical
subscription. Actual SensorAgent failures propagate and partial registration is
rolled back. Sensor callbacks run outside registry locks. Each slot retains its
algorithm owner, disables old queued samples at unsubscribe, waits for other
threads' in-flight callbacks and allows self-unsubscribe without waiting on self.
All actual algorithm callers use `make_shared` before `Init`; unowned Init fails
via `weak_from_this().lock()` without throwing under `-fno-exceptions`.

The service manager tracks the first/last listener and requested event per type,
rolls back failed starts/death registration, and removes all a dead client's
subscriptions. Backend operations and user callbacks run outside its registry
lock. The client does not recursively acquire its ordinary mutex when obtaining
an algorithm instance. Last-type cancellation retires from service code: the
actual algorithm worker is joined before callback removal, Destroy and `dlclose`.
A failed teardown retains the mapped module; no timeout authorizes unloading.

The internal Destroy function pointer is corrected to the actual export type
`void (*)(const IMsdp*)` in both its defining handle and service loader. Public SDK
signatures are unchanged. Actual product CFI/LTO compilation and linking are
required to validate this internal call-site change; pointer size is insufficient.

Host evidence and pending product targets are in
`docs/capability-audit/parallel/system/round9-live-inputs/public-still/`.
The GNU ASan/UBSan suite compiles six actual algorithm/worker TUs and extracted
actual service methods. SensorAgent functions are fault-injection seams, and
manager Binder objects are a host scaffold. The actual manager death declaration
is extracted too. These tests do not replace the real product build or ordinary
HAP callback test on the first newly packaged ARM64 phone artifact.
