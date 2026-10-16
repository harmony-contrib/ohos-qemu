# District and skiing business routes

Base: `4b329553506a1ba71a33c5c4ad631f6e4fe51513`. Source project HEAD remains
`5a0c49c2adb0623fdac73f76e4f98f2e57674c00`. The third runtime patch changes
17 upstream files, adds 6 targets to the previous 16-file location component,
and keeps 22 assigned requirements open until new-package behavior is accepted.

`getCurrentDistrict` is Promise-only. Its optional/undefined request uses the SDK
5000ms default and strict int32 timeout parsing. The service authorizes valid
fine or approximate permission, firstTokenId, current account and switch before
starting an owned one-shot request. Existing StartLocatingProcess provides its
permitted recent cache (25s) or a new fix through the same callback. The native
consumer accepts finite/ranged coordinates and boot-time age at most 30s,
stops the request on every started path, then requests one actual reverse-geocoder
result. A single steady-clock deadline covers the work. The existing geocoder
cache includes locale and distance in its key. Default locale uses the location
country-code service's `persist.global.locale` key. Final service access and
deadline checks clear results after permission/account/switch changes. Reverse
area-query failure uses the SDK 3301500 code.

New transactions 68/69/70/71 are StartDistrictLocating,
StartLocatingWithSportsType, GetPostProcessingTrack and CheckDistrictAccess.
Original transactions including 65/66/67 are preserved. RequestConfig's original
ten parcel fields remain unchanged; sports mode is a separate int argument in
new transaction 69. In-memory copy/equality and client callback restoration retain
the mode; old unmarshalling resets it to zero. The mode is effective only for
SDK UserActivityScenario.SPORT. SKIING selects genuine GNSS input and fine privacy
usage, including callers who hold both fine and approximate grants.

The skiing history consumes the existing permitted real report callback route,
with active-request/fine-use snapshot checks under request/permission locks.
AccessToken checks happen outside those locks. Non-GNSS, mocked, out-of-order,
invalid, future and expired samples are excluded. Processing uses reported
accuracy and elapsed time for adaptive variance smoothing, handles the
antimeridian, derives speed/bearing from processed geometry, and rejects
teleports beyond 120m/s or stated uncertainty. A gap above 60s resets the filter.
History is scoped by UID/token/firstTokenId, expires after 24h of monotonic GNSS
time, and advances a sequence cursor on reads. Consumed samples are released;
last filter state remains until retention expires. Query authorization, switch,
sport and owner checks precede reading the cursor. No tracking data produces a
service error; a successfully drained real history returns an empty next batch.

The cache quick paths now use actual fine/approximate PrivacyKit state, retain the
Request through asynchronous stop, and retry a failed stop with that same state.
A failed cache read cannot decrement another active request. Approximate stop
failure restores the count before a retry. Real report accounting selects the
permission actually in use. New API client boundaries preserve legitimate public
201/202/203/401/801 errors while still decoding internal IPC errors; the shared
CommonUtils mapper remains unchanged.

The exact source guard covers 22 complete targets and the original, first-patch,
second-patch and final byte states at the fixed project HEAD. Full copied source
and bounded harness fixtures both apply the real patch stack. Host execution
covers actual native/service/NAPI/config/history/cache functions under ASan/UBSan.
Boundary doubles represent scanner, AccessToken, PrivacyKit, NAPI and IPC/device
interfaces; these are host tests and provide no modem/GNSS/geocoder package proof.

Required centralized compilation: regenerate locator_interface and its proxy/stub;
compile the previously listed location TUs plus
`frameworks/base_module/source/request_config.cpp` (`frameworks/base_module:lbsbase_module`),
`frameworks/js/napi/source/napi_util.cpp` (`frameworks/js/napi:geolocationmanager`),
and `services/location_locator/locator/source/report_manager.cpp`
(`services/location_locator/locator:lbsservice_locator`). Rebuild all consumers
of RequestConfig with the same headers. Freeze all entries in
round2-freeze-inputs.json, now expanded for the third patch.

Fusion fences and the 5A producer/observer remain implementation work. No fence
header or driver target has been added in this commit. The reserved follow-up
fence header must be included only when an actual implementation changes it.
