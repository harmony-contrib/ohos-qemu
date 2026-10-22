# External QEMU accelerometer VDI

This opt-in implementation accepts explicit external acceleration samples and
reports them through the existing Sensor HDI. It produces no readings without an
external source, no periodic constant samples, and no substitute MSDP results.
Only the implemented accelerometer is enumerated. Other sensor types remain
unsupported.

The strict installer pins `drivers/peripheral` revision
`69094b77aa2200160207b1b06b3c0b586ae2157c`. It verifies each pristine/final source
hash and new file hash before any replacement. Unknown/mixed bytes, symlinks,
wrong project revisions and foreign overlays are refused. An interrupted write
rolls back files already touched. It changes exactly the seven paths listed in
`manifest.json`; no vendor, policy, product or public runner is changed here.

```sh
bash patches/common/drivers/peripheral/sensor/qemu_external/apply.sh --source-root /path/to/ohos
```

## Product and loading integration (main agent owned)

Set `drivers_peripheral_sensor_feature_qemu_external=true` for the QEMU product.
The GN branch retains the existing `libhdi_sensor_impl.z.so` output and exports
VDI module version 1 through `WrapperSensorVdi` and `HDF_VDI_INIT`. It replaces the
original hardware HAL dependency only for this explicit feature. Other products
retain their previous implementation.

The fixed source loading chain is:

1. `vendor/ohemu/virt/hdf_config/uhdf/device_info.hcs:375` registers
   `sensor_host`, `libsensor_driver.z.so`, and `sensor_interface_service`.
2. `sensor/hdi_service_3.0/BUILD.gn:84` builds that driver from
   `sensor_if_driver.cpp`, whose Bind calls the HDI interface factory. The
   `libsensor_interface_service_3.1` implementation supplies the V3.0 interface.
3. `sensor_if_service.cpp:78` first tries `libhdi_product_sensor_impl.z.so`, then
   `libhdi_sensor_impl.z.so`. It checks VDI version 1 and obtains the module.
   `SensorInterfaceImplGetInstance:647` calls `Init`, which starts this input
   endpoint and enumerates the sensor. Failures return a null interface.
4. Register/enable/batch requests go through the real HDI service to this VDI.
   Its callback uses `HdfSensorEventsVdi`, then the existing
   `SensorCallbackVdi::OnDataEventVdi` conversion and SensorClientsManager path.
   The SensorService/SensorAgent/public Sensor API and MSDP algorithm remain the
   existing platform implementations.

The new package must include the actual `hdi_impl:libhdi_sensor_impl` target and
V3 service/driver, and must have no priority product VDI shadowing this component.
Compile/link alone cannot establish that this loading path was used at runtime.
Record loaded mappings, driver/service logs, actual enumeration and API readings.

The host generator defaults uid to hostName: `hc-gen/src/startup_cfg_gen.cpp:456`;
its generated executable is `/vendor/bin/hdf_devhost` and SELinux context is
`u:r:sensor_host:s0`. Fixed `passwd/group` map sensor_host to UID/GID 3033; the
HCS supplementary GIDs are `sensor_host` and `uhdf_driver` (3066).
`SystemInit` creates `/dev/unix/socket` as root with mode 0755. The unprivileged
driver cannot create a direct child there. Main must arrange these precise
resources before starting sensor_host:

- `/dev/unix/socket/qemu_sensor`, mode 0700, owner sensor_host:sensor_host.
- Its own SELinux directory type and exact socket type transition, granting only
  sensor_host creation/cleanup and the approved root controller connection.
- `/dev/unix/socket/qemu_sensor/input` is created by this implementation with
  mode 0600. Its peer credential check requires UID 0. No ordinary application
  input access is granted; application consumers use Sensor API permissions.

`vendor/ohemu/virt/BUILD.gn:22` already depends on
`etc:product_etc_conf`. `vendor/ohemu/virt/etc/BUILD.gn:33` demonstrates an
`ohos_prebuilt_etc` init cfg and the product_etc_conf dependency at line 42.
The main agent can install a dedicated early init job there, maintaining startup
ordering and narrow policy ownership. This component never chmods a directory or
changes process credentials/policy.

## Protocol version 1

The controller connects to the absolute pathname after public Sensor
subscription/activation is established. The server sends exactly 32 bytes:

| Offset | Bytes | Value |
| --- | --- | --- |
| 0 | 4 | ASCII `QSN1` |
| 4 | 4 | LE u32 version 1 |
| 8 | 16 | fresh random per-connection nonce |
| 24 | 4 | LE u32 sensor type 1 (accelerometer) |
| 28 | 4 | reserved zero |

Each controller frame is exactly 44 bytes:

| Offset | Bytes | Value |
| --- | --- | --- |
| 0 | 4 | ASCII `QSF1` |
| 4 | 4 | LE u32 version 1 |
| 8 | 16 | this connection's nonce |
| 24 | 8 | nonzero strictly increasing LE u64 sequence |
| 32 | 12 | LE IEEE754 float32 x/y/z in metres per second squared |

Axes are the platform Sensor API device-frame axes, transported unchanged. No
adapter swap/sign transform is applied. The existing MSDP `AlgoBase::SetData`
then performs its own documented x=data.y/y=data.x/z=-data.z transform. The
accepted per-axis limit is +/-156.9064 (16 g), below MSDP's 160 threshold. NaN,
infinity and out-of-range input are rejected. Each accepted event receives a
local guest CLOCK_MONOTONIC nanosecond timestamp; the sender cannot forge event
time. SetBatch accepts 1 ms..1 s sampling intervals and 0..1 s maximum report
latency. Delivery is immediate with rate limiting, without resampling or a
batching FIFO. No gyroscope, proximity or other capability is fabricated.

Only one controller is served at once; the kernel listen backlog is 1 and receive
buffer request is 4096 bytes. No userspace sample queue exists. Partial reads are
bounded and an incomplete/idle frame has a 5-second timeout. Bad frame/session
input disconnects that controller. A fresh connection gets a fresh nonce and
starts sequence numbers again. Enable/disable/callback registration changes
invalidate the old session and shut it down. Callbacks run outside locks;
unregister/disable from another thread waits for in-flight delivery. Callback
reentry, self-unregister, self-disable and destruction do not wait on their own
worker. Old buffered frames cannot be dispatched after these boundaries.

## Validation and external input controller

```sh
LC_ALL=C LC_CTYPE=C LANG=C python3 ci/capability-audit/batch_system_qemu_sensor.py --output /tmp/unique-sensor-host-evidence
LC_ALL=C LC_CTYPE=C LANG=C python3 -m unittest discover -s ci/capability-audit -p test_batch_system_sensor_installers.py -v
```

The 27 host scenarios execute the shipped transport/protocol over actual Unix
sockets with ASan/UBSan. The host test explicitly authorizes the host UID; the
product VDI still pins UID 0. A separate Python controller challenge proves the
wire codec across processes, with arbitrary x/y/z values chosen for that run.
This does not substitute for official HDI TU/link checks or packaged API tests.

For a new representative package, main can create an owned HDC forwarding rule
using a root/su daemon and send an externally supplied trace:

```sh
hdc -t OWNED_GUEST fport tcp:OWNED_PORT localfilesystem:/dev/unix/socket/qemu_sensor/input
python3 ci/capability-audit/batch_system_qemu_sensor_controller.py --tcp-port OWNED_PORT --input /absolute/external-trace.json --output /absolute/unique-sent.json
```

The controller accepts an explicit JSON array, each row containing exactly
`at_ms`, `x`, `y`, `z`; times increase relative to connection start, and each gap
is below 4 seconds. No canned sample generator is provided. `--unix-path` is
available for a direct local endpoint. The result records the original trace
hash, hello, nonce, sequence, wire frame and send time. A successful send is only
sender evidence. Main must compare a separately subscribed Sensor API observer
and the real MSDP absolute-still/horizontal/vertical transitions with that
challenge, including wrong/replayed sessions, disconnect/reconnect, concurrent
subscriptions, stop/restart/permission denials and absence of old queued events.

The fixed root HDC config has uid root/domain su, while its nonroot variant has
uid shell/domain hdcd. The nonroot daemon fails this component's peer UID check.
Any production transport beyond the designated QEMU debug controller requires
its own explicit access design; do not loosen the directory or application ACL.


## Independent rotation-vector source (source candidate, no runtime claim)

The original accelerometer input/header/protocol bytes and QSN1/QSF1 ABI are
unchanged. The same VDI additionally enumerates the genuine SensorAgent type259
ROTATION_VECTOR. A disjoint `Qemu::Rotation::SensorInput` uses the same complete
UID0 authorization, 0600 socket, native challenge, session generation, bounded
transfer, callback drain and thread retirement body. It listens at the already
owned `/dev/unix/socket/qemu_sensor/rotation` directory entry.

Hello is32 bytes: `QRS1`, LE32 version1, sixteen native-random nonce bytes,
LE32 type259, LE32 reserved0. Each48-byte `QRF1` frame has LE32 version1,
same nonce, LE64 strictly increasing positive sequence and four LE float32
components x/y/z/w. All components must be finite in[-1,1], and the squared
length must differ from1 by at most0.0001. Guest timestamps are native
CLOCK_MONOTONIC at actual dispatch; host time never replaces them.

The installer recognizes exactly stock, complete legacy ACCEL vector, or the
complete new vector. Unknown/mixed states fail. Legacy upgrades edit the unique
GN source-list block and the VDI, add three rotation files, and skip every
byte-identical old file. Original source inode/mtime survives unchanged files;
publish failure follows the existing complete rollback transaction.

New-image acceptance must prove independent unit quaternion consumption via
public SensorId.ROTATION_VECTOR plus public getDeviceRotationRadian, three
orientations/two caller generations, permission rejection, malformed/nonfinite/
zero/old nonce, source EOF after last unsubscribe, quiet and actual cleanup.
This source does not claim physical orientation accuracy.


HEADPOSTURE268 successor: adds independent /dev/unix/socket/qemu_sensor/headposture,
QHP1 hello32 and QHF1 frame52 (nonce/seq/positive exact-int24 order/wxyz).
The VDI emits the actual adapter's seven-float28B layout [0,order,0,w,x,y,z],
not the native20B HeadPostureData. Original ACCEL/rotation protocol and input
files remain byte-identical. New root-only stream has the same authorization,
nonce, timeout, generation and callback-drain lifecycle. Full stock/priorACCEL/
priorrotation/final vectors are explicit; unknown/mixed source is refused.
The source helper is transport-only; real HeadTracker/SET_IMU/PCM must be proved
on the newly packaged image by the Media owner. No runtime gate is granted here.
