# Ethernet global control

Pinned netmanager_ext: `8c41289750820fb2ddb347b1205cee9a7b527388`.

Do not publish a successful enable/disable before the registered interfaces'
actual administrative flags and the changed SettingsData policy have been
read back. Netsys currently discards several ioctl/config errors, so a transport
success or an empty flags vector is not proof that an interface is disabled.
Require exactly one of `up`/`down`, the requested interface identity, and the
desired administrative state. Carrier/running is independent of the global
switch and is not required to enable an unplugged interface.

Snapshot each actual prior interface state. Failed device/config/policy steps
return the existing internal error and attempt rollback of every saved state;
failed rollback stays an error, never a successful transition. An unavailable
backend can prevent rollback; this does not claim an atomic kernel transaction
or successful recovery from permanently unavailable devices/providers.

Serialize global transitions, hot-add configuration, startup retries and policy
reads. Release the device-map lock before Netsys/DataShare/DHCP/service calls.
Startup retries stop after disable/removal, and sleep outside the control lock.
Cleanup uses the existing false-link transition to stop DHCP and withdraw the
supplier, instead of announcing its previous true link state. The pinned
DataAbility observer uses asynchronous Binder notification; interface config
uses ioctl rather than joining callback dispatch.

No public SDK, service IPC, caller permission, raw-node mode, configuration
layout or device profile change. The additional mutex is private to the
uniformly rebuilt service. True interface toggles, application calls, traffic,
permissions, hot-add, restart and all three ABI builds still require actual
new-package verification. Host sanitizer fixtures or isolated TU objects alone
cannot close the Ethernet API/behavior audit findings or release five packages.

The new three-role API26 HAP reads `/sys/class/net/eth0/flags` without writing
nodes or granting test-only access, and compares IFF_UP with the public global
getter after repeated/idempotent controls. It restores the enabled policy via
the same permission-checked caller even if TCP HDC drops. Missing or denied
kernel reads are failures, not skipped proof. Ordinary and system-without-
permissions roles require numeric 202/201 for all three methods; the system
role requires a real old-PID exit and a different caller PID on restart.
Strict raw/log/signature/source replay is required by the new-package gate.
These checks close only the three public control exports after actual guest
success, not traffic, hotplug, service restart or all Ethernet functionality.
