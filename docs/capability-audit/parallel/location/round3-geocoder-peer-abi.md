# Existing reverse-geocoder peer ABI

Read from the fixed source, without changing the provider or startup. A controlled
provider can use this existing service path for externally challenged GNSS fixes
and geographic data. This document is an integration request, not proof of an
installed provider.

`common_utils.h` names `const.location.geocode_service_name` and
`const.location.geocode_ability_name`. GeoConvertService checks that bundle is
installed, then ConnectAbility resolves its configured ability. Its returned
IRemoteObject receives transaction **2** (REQUEST_REVERSE_GEOCODE). The service
prepends the remote object's own interface descriptor. The remaining parcel,
from GeoConvertRequest::Marshalling, is:

1. locale String16, latitude double, longitude double, maxItems int32;
2. bundleName String16, callback IRemoteObject, transId String16, country String16.

Send results to that callback with descriptor `location.IGeocodeCallback`, code
**1** (RECEIVE_GEOCODE_INFO_EVENT), int32 error=0, int32 count, then each actual
GeoAddress::Marshalling payload. Error event **2** carries the descriptor and
int32 backend error. GeoCodeCallback forwards replies to the original locator
callback and populates the existing reverse cache.

GeoAddress wire order is latitude/longitude doubles, then String16 locale,
placeName, countryCode, countryName, administrativeArea, subAdministrativeArea,
locality, subLocality, roadName, subRoadName, premises, postalCode, phoneNumber,
addressUrl; then description count and (int32 index, String16 description)
pairs; finally isFromMock bool. Keep this exact source version. The district API
only publishes the SDK district fields from this real reply.

Exact source references:

- services/location_geocode/geocode/include/geo_convert_request.h (codes 1/2);
- services/location_geocode/geocode/source/geo_convert_request.cpp:223;
- services/location_geocode/geocode/source/geo_convert_service.cpp:136,194,455,665,707;
- interfaces/inner_api/include/i_geocode_callback.h;
- frameworks/location_common/common/source/geo_address.cpp:100,140.

A useful controlled provider accepts geographic boundary/name records from an
external challenge channel and computes which administrative polygons contain
the challenged GNSS point. Validate changed points, changed locale, outside-data,
backend failure, timeout and disconnect through the genuine locator/geocoder
services. A fixed returned district or public-API interception would not validate
this route. The parent owns provider packaging/configuration/transport and may
assign its implementation to the appropriate capability owner.
