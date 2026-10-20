Source-only QEMU reference RIL wiring candidate. No compilation, image boot,
parser, HDC or runtime validation was performed by this child.

The actual current QEMU HCS has no RIL host, although the actual arm64 package
already contains libril_driver.z.so, libril_service_1.5.z.so, libhril_hdf.z.so,
libhril.z.so, libhril_innerkits.z.so and libril_vendor.z.so in vendor/lib64.
This component starts the existing driver in host riladapter_host, with the
existing radio UID, HDI group and existing SELinux domain/service type. preload=0
selects boot loading in the actual hc-gen startup_cfg_gen.cpp. No RIL callback,
registry API, IMS implementation or policy bypass is introduced.

The existing packaged telephony.para gains the vendor SONAME and explicit default
AT path. LoadVendor uses its actual dlopen(SONAME) branch when realpath cannot
resolve that SONAME; the runtime must prove the mapped packaged vendor pathname.
An absolute lib64 path would incorrectly bake a 64-bit ABI into all QEMU builds.
This component must be selected ONLY by the parent's QEMU build hook. The para
file belongs to core_service and is shared source; do not enable this component
for non-QEMU products or apply it outside the parent's serialized source batch.

Preimages come byte-for-byte from the sole actual running build CID exported by
the parent in root-communications578-init-current and root-ril578-hdi-current.
The two-file complete vector rejects unknown or mixed source states. Keep this
component independent of the six-file CallManager RTT boundary component.

The next freshly packaged representative image must prove generated init entry
(vendor hdf_devhost executable, radio identity, riladapter_host domain), packaged
library mappings, genuine RIL FD to the owned PTY, ModemInit AT traffic, and the
entire +OHOS5A -> vendor -> HRil/HDI -> core -> registry -> public observer chain.
An absent or blocked PTY/MAC/provider path is a real failure to preserve; never
substitute an IPC/callback injection or change SELinux enforcing mode. The PTY
fixture presents no SIM, no registered network, no data bearer and no IMS call.

The generator's output init filename is not guessed here. The root adapter must
use the actual packaged init path and verify its riladapter_host service entry.
No QEMU hardware flags are required for the same-guest devpts fixture; real
devpts availability and service access remain mandatory new-image checks.
