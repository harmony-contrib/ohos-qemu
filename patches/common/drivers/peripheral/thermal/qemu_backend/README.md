# QEMU thermal backend

Pinned drivers/peripheral: `69094b77aa2200160207b1b06b3c0b586ae2157c`.
Both profiles use the same product-scoped HDI configuration on all three ABIs.
Non-QEMU products retain the upstream profile. Simulated zones remain disabled.

The QEMU kernel build applies `device/qemu/common/virt_full/kernel/patch/power.patch`,
renaming the test-power supply and its thermal zone to `battery`. The initial
two-patch component mistakenly retained the pristine-kernel `test_battery` name.
R26 ARM64 phone boot `515bc728-36ef-4112-a82e-092ca1b16df0` read the actual
`thermal_zone0|battery|2600`, but ThermalService returned no zones. Generated
ARM32, ARM64 and x86_64 kernel source trees all contain the `battery` name.

Patch 0003 selects that actual kernel zone; it does not fabricate temperature,
change thresholds, bypass permissions, or enable thermal emulation. The exact
previous two-patch state can be upgraded safely under the component lock.
Unknown or partial edits are rejected without mutation. Fresh checkouts apply
the complete numbered stack, then subsequent runs verify the final hashes.

`run_thermal_diagnostic.py` requires nonzero kernel/service agreement before and
after four real ordinary ArkTS callback lifetimes. A cool-state pass does not
prove hot transitions. This correction is not in frozen R27; it requires a new
representative package and actual guest validation before delivery.
