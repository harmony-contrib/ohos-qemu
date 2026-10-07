# QEMU virtual vibrator VDI component

The QEMU board builds a product VDI named
`libhdi_product_vibrator_impl.z.so`. The existing vibrator HDI service prefers
that product VDI over the physical HDF implementation.

The implementation models one local, time-based vibrator. It keeps observable
running/deadline state for one-shot, preset, and composite time effects. It
intentionally reports intensity, frequency, and HD haptics as unsupported.
There is no fake GPIO or I2C device.

Only the pinned SDK's `haptic.clock.timer` preset is advertised and executed.
Unknown nonempty names query as unsupported with zero duration, and attempts
to start them fail without changing an existing effect. Empty names remain
invalid; arbitrary strings are not claimed as working vendor effects.

Custom JSON effects use the upstream decoder and `TransformTime` fallback.
Only `isSupportTimeDelay` is enabled: primitive mapping and HD waveforms remain
unsupported. Composite delays are relative to the preceding event's start;
the final zero-duration item is accepted as the upstream stop marker. Invalid
or overflowing sequences are rejected without changing an active effect.
The observable deadline is the last event end (including the stop marker),
not the sum of all delays and durations. A zero-time stop clears the state.

`ci/capability-audit/test_virtual_vibrator.py` executes the real class with a
controlled clock under ASan/UBSan. It checks timing, cancellation, device IDs,
invalid input and unsupported capabilities; this is not guest E2E evidence.

The product library is a VDI, not an HDF driver DSO. It therefore deliberately
does not use `shlib_type = "hdi"`: that template's version script hides
`hdfVdiDesc`, while the HDF VDI loader must resolve that symbol with `dlsym`.

The device-part bundles explicitly declare both the vibrator interface and
peripheral components. This keeps OpenHarmony's compile-standard dependency
check enabled for arm, arm64, and x86_64 instead of bypassing it.
