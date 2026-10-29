# Fixed dynamic location enum contracts

Restore five already declared geoLocationManager enum objects and all fifteen members
from interface/sdk-js@43e34facc58b9c0f15c58571554ddd7eaa004455, API26.
LocationIconStatus also matches the actual location Taihe declaration.
These are public SDK constants: do not mistake FusionFenceType bit values for implemented
GNSS/Wi-Fi/cellular/Bluetooth fusion providers. In particular the original source does
not implement the four newer fence enum types as native provider classes.

Only the geoLocationManager initializer is changed, not the legacy geolocation module,
service methods, GNSS, geofence parsing, permission checks, callbacks or hardware.
Every NAPI allocation/property status propagates; failed module initialization returns null.
The fixed wire values and complete public member reads require a new ordinary HAP proof.
Provider behavior remains unresolved until a real new-image backend regression passes.

