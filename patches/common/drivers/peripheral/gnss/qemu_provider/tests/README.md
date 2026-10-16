# Actual OHOS GNSS ABI/CFI consumer

`ohos_abi_consumer.cpp` is compiled for `aarch64-linux-ohos` with the actual
product target's complete CFI/LTO/compiler options. It includes the actual
generated `IGnssInterface`/types, `gnss_interface_impl.h`, patched loader header,
and unchanged full `location_vendor_lib.h`. It links the existing real HDI DSO
and real RefBase/runtime libraries. It does not implement replacement platform
headers, IPC objects, parameter storage, logging, or a GNSS backend.

The tested chain is:

```
real OHOS musl loader + 13 actual ARM64 DSOs
  -> consumer's sptr<IGnssInterface> holding the real GnssInterfaceImpl
  -> actual public configuration / normal start / normal stop virtual methods
  -> LocationVendorInterface and its lifetime-protected vendor table
  -> dlopen(vendorGnssAdapter.so), OBJECT symbol GnssVendorInterface
  -> actual 11-function vendor ABI and actual provider
  -> actual proxy callback trampoline -> typed consumer OnLocation callback
```

The observation callback is registered through the actual vendor table; the
consumer does **not** exercise public `EnableGnss`'s `hdi_objcast`, generated
IPC callback object, Binder transport, Locator, or a normal application. It
does not replace those paths with test objects. These remain full guest checks.

The consumer verifies device/table/layout sizes, genuine callback storage
ownership, public configuration after enable, silence without external input,
callback-reentrant cleanup, actual provider unmapping, same-process reload,
rejection of an old generation frame followed by a new connection/nonce, two
new-input callbacks, and silence after normal stop and final cleanup. The
short no-input/stop observation is not a substitute for longer concurrent
queue/lifecycle stress or ordinary-app permission tests.

`validate_ohos_abi.py` runs only in a root-approved, private leased Linux
container. Required read-only mounts are actual `/ohos`, `/ohos/out`, immutable
R52 artifacts at `/r52`, and the frozen repository at `/frozen`. `/work` is a
private output mount; `/tmp` is executable. The container-private
`/dev/unix/socket/qemu_gnss` directory is exactly `1022:1022`, mode `0700`.
No host or product paths/permissions are changed. The provider creates its
actual `0600` input socket; the diagnostic process and external peer run as
root inside this isolated container. This does not prove the deployed
`location_host` UID/domain/SELinux boundary.

After obtaining that lease, run once with a fresh output path:

```sh
python3 /frozen/patches/common/drivers/peripheral/gnss/qemu_provider/tests/validate_ohos_abi.py \
  --output /work/attempt01
```

The script checks original source/patch hashes, the exact prior product link
evidence and DSO hashes, derives a bounded real runtime dependency closure,
compiles one consumer and invokes QEMU-user once. Every compiler/linker/QEMU
process has a 120-second timeout. It preserves commands, true ELF metadata,
all compiler header hashes, full syscall/stdout logs, exact input frame/nonce
bytes and hashes, and both binaries' provenance. Missing runtime dependencies
or real OS services cause an honest failure or remain visible diagnostics;
there are no substitutes. Run failure evidence is never overwritten.

The controller supplies explicitly identified external **protocol test vectors**
with chosen coordinates and current test UTC. These are not real-world GNSS
measurements and must not be used to claim positioning accuracy or capability
closure. The product provider itself still emits nothing without input. For
product acceptance use a legitimate live measurement/replay source and observe
the full public service and normal-app paths in the newly packaged guest.

Round 6 evidence is in
`docs/capability-audit/parallel/system/round6-ohos-abi/`. The first attempt failed
because this new consumer configured before enabling. Its full failure is
retained. The corrected test passed against unchanged product DSOs. Positive
calls execute in a genuine cross-DSO CFI build; deliberate wrong-type CFI
rejection was not tested. QEMU-user uses a Linux kernel and is not a boot of
the representative package or its runtime gate.
