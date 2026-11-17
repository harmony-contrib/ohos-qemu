# Numeric I18n BusinessError codes

The pinned I18n NAPI helper constructs an Error with a string `code`. A normal
application actually receives `"202"` from `System.setSystemLanguage`, although
the API 26 BusinessError contract requires the number `202`. Permission denial
and unchanged system language were observed in the first packaged ARM64 phone.

Delegate the shared error helper to the already implemented
`NapiThrowBusinessError`. Retain message formatting, silent legacy paths with
`throwError=false`, and all service-side permission checks. Do not normalize
the received code in the probe or grant a normal app configuration permission.
The special `NapiThrowUndefined` helper is outside this numeric contract.

The language/region/locale/24-hour-clock setters also silently returned on a
wrong native parameter type. Reject those conversions with the documented
numeric 401, before service calls. Legacy non-throwing interfaces remain silent.

Host tests and per-product compilation are not guest acceptance. Repackage and
boot the first artifact, verify `typeof code === 'number'`, exact denial code,
unchanged language, data calls and invalid-parameter boundaries before the
remaining package matrix.
