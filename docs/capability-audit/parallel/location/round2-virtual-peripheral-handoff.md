# Virtual peripheral continuation handoff

2026-10-16, fixed source inspected read-only in
`ohos-qemu-parallel-source-20261016-02:/ohos`. This is an implementation proposal
and exact entry-point handoff, not peripheral/runtime proof. No files outside the
approved location target set were changed. The integrating agent owns QEMU,
device/vendor adapters, transport exposure, product configuration and startup.
The location agent resumes business APIs after this scheduled slot handoff.

| Route | Confirmed fixed-source entry | Next adapter boundary |
| --- | --- | --- |
| GNSS | `drivers/peripheral/location/gnss/hdi_service/location_vendor_interface.cpp:32,73-83` loads `vendorGnssAdapter.so`, resolves exported `GnssVendorInterface` (`GnssVendorDevice`) and calls `getGnssInterface()` | Supply a QEMU vendor module implementing the real ABI in `location_vendor_lib.h:643-721`; externally received measurements call the registered `GnssBasicCallbackIfaces::locationUpdate`, NMEA, status and satellite callbacks. Respect enable/disable/start/stop/category/config and disconnect errors. |
| GNSS service | `base/location/location/services/location_gnss/gnss/source/gnss_ability.cpp` uses `IGnssInterface::Get()` (e.g.563,582), and existing `gnss_event_callback.cpp` forwards HDI reports | Keep this path intact. QEMU measurement changes must appear through real locator callbacks/cache, permissions, timeout and switch behavior, then the pending district/fence/track implementations. Do not use location mock APIs. |
| BLE HCI | `drivers/peripheral/bluetooth/hci/hdi_service/implement/bt_hal_constant.h:27-28` loads `libbt_vendor.z.so`/`BLUETOOTH_VENDOR_LIB_INTERFACE`; `vendor_interface.cpp:75-90` obtains an fd through `BT_OP_HCI_CHANNEL_OPEN` and wraps a single channel in the real `H4Protocol` | Implement the vendor transport ABI and bridge an owned UART/virtio channel to a controlled HCI controller endpoint. Reply to controller initialization/scan commands; emit standard LE advertising reports only while commanded scan state is active. The genuine Bluetooth stack and BleCentralManager must parse those reports before this batch's service filters/public NAPI. |
| RIL/modem | `base/telephony/ril_adapter/services/hril_hdf/src/hril_hdf.c:30,48-65,156-205` selects `const.sys.radio.vendorlib.path`, dlopens it and registers `RilInitOps(&g_reportOps)` with real HRil | Prefer reusing the existing AT vendor against an externally driven virtual modem. Its `services/vendor/src/vendor_adapter.c:47-50,345-370` reads `const.telephony.ril.attty.path`, opens a tty and executes `ATStartReadLoop`/`ModemInit`. A guest UART/virtio tty and host AT state machine can supply challenged SIM, registration, calls, SMS and data state through real HRil/core services. Configure the vendor library property and actual tty path; do not synthesize public API return values. |
| Existing virtual-modem selector | `hril_hdf.c:31,55-60` recognizes `const.booster.virtual_modem_switch=true` only with `const.telephony.slotCount=0`, selecting `libril_msgtransfer.z.so` | This selector exists; the library's presence, protocol and usability were not established in this bounded read. Do not enable it on the assumption that it implements a modem. |
| IMS/RTT | `base/telephony/cellular_call/services/ims_service_interaction/src/ims_call_client.cpp:77-114` resolves `TELEPHONY_IMS_SYS_ABILITY_ID`, casts `ImsCoreServiceInterface`, requests `PROXY_IMS_CALL` and registers the real callback | An AT modem alone cannot satisfy RTT. A controlled IMS service/peer must implement the actual interfaces/call lifecycle, consume session/mode/text requests and report peer-produced RTT payload/modify/error callbacks. Root can own service/transport startup; location agent owns needed cellular/call-manager business integration. |

Proposed challenge transport: separate uniquely named guest channels for GNSS,
HCI and modem; externally supplied sequence/timestamp/payload and session IDs;
acknowledgement at peripheral-command boundaries; bounded length and parser
validation; no host-supplied direct API result field. GNSS can use a versioned
framed measurement stream with position/velocity/time/accuracy/validity; BLE
should retain standard H4 packets; modem should retain the existing vendor's AT
protocol. Record external input and independently assert public payloads, changed
inputs, absent-device and malformed/disconnect cases. Fixed coordinates, canned
SIM results and unconditional RTT success are unacceptable substitutes.

A controlled local IMS endpoint can validate registration, call identifiers,
mode negotiation, text transfer and unsolicited peer errors through the genuine
service graph. Carrier interoperability, real network authentication/provisioning
and commercial IMS certification remain separate external scope and must not be
claimed from a local protocol endpoint. The SDK communication boolean means 5A
state; do not substitute generic call state. Its exact modem/radio producer must
still be implemented before observer on/off can be accepted.

Pending business work remains: district current-fix/reverse-geocoder/cache
orchestration, fusion fence capability/add/remove/transition ownership, skiing
post-processing history/retention/cursors, communication 5A producer and
subscription ownership, and positive GNSS/modem/RTT/BLE package evidence. All 22
assigned requirements remain open in result.json. The next runtime build must
follow the batched representative-package gate before six-package delivery.
