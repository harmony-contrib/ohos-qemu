# API26 Ethernet

Enable/disable belongs to the Ethernet feature, not the NetFirewall feature.
Both device profiles keep the real service implementation and permission checks.

The public `DeviceConnectionType` enum is registered using the existing native
`EthernetDeviceInfo` enum (`BUILT_IN=0`, `EXTERNAL=1`). This does not invent a
device, modify interface state, or claim that a device query has passed.
