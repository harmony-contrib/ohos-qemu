# QEMU QoS manager component

This component wires OpenHarmony's existing `qos_auth` common module into the
QEMU kernel copy and merges a small, auditable Kconfig fragment. It keeps
`QOS_AUTHORITY` enabled so the existing resource-schedule services remain the
authority source instead of turning QoS into an unrestricted ioctl.

The component-owned `qos_auth.patch` connects the module to the copied
kernel's `drivers/Kconfig` and `drivers/Makefile`. The package verifier requires
the final kernel configuration to retain every setting in `qos.config`.
