# QEMU virtual vibrator VDI component

The QEMU board builds a product VDI named
`libhdi_product_vibrator_impl.z.so`. The existing vibrator HDI service prefers
that product VDI over the physical HDF implementation.

The implementation models one local, time-based vibrator. It keeps observable
running/deadline state for one-shot, preset, and composite time effects. It
intentionally reports intensity, frequency, and HD haptics as unsupported.
There is no fake GPIO or I2C device.

The device-part bundles explicitly declare both the vibrator interface and
peripheral components. This keeps OpenHarmony's compile-standard dependency
check enabled for arm, arm64, and x86_64 instead of bypassing it.
