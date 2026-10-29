# Public local NumberIdentity provider

The fixed OpenHarmony source is `base/telephony/number_identity` at
`50e1330646432ce166e7981c577f25f46c90e7ac`. This component retains the
repository profile path in GN and avoids dereferencing an absent diagnostic
supplier during local mark updates. It preserves the actual permission and CN
region checks, database operations, and optional remote-service boundaries.

The phone product selects the real `com.ohos.numberidentity` bundle, installed
at `/system/app/com.ohos.numberidentityability`. The separate `native_manifest`
component preserves its three C++ DataShare routes when Hvigor reads JSON5.
`patches/lib/number_identity_provider.py` authenticates the original public
profile and renews only its distribution certificate and expiry using the
existing public OS test signer. It does not add permissions or BMS grant rows.

The public files provide local mark storage, 11 number-location prefixes and
3 yellow-page entries. They do not provide a complete number reputation or
geographic dataset, SpamShield, or HSDR production configuration. The historical
aggregate-provider finding remains unsupported. Source, signing and image
checks do not establish runtime acceptance; the newly packaged image still
requires genuine callers, permission boundaries, persistence and cleanup tests.
