# Existing dynamic curve enum export

Restore the already declared `curves.Curve` through the actual dynamic JSI module.
The thirteen values use existing DOM curve-name constants, exactly as the fixed
`jsEnumStyle.js` global Curve and `CreateBuiltinCurve` parser do. They are string
curve identifiers, not invented numeric positions. No SDK declaration, interpolation
algorithm, animation scheduling, global Curve, permissions or public signature changes.

Each module initializer owns a fresh object. Failed allocation/type/property creation
is propagated as a null module; no global reference or partially built Curve is exported.
Host mock-runtime tests and real product TU compilation are only preflight evidence.
A fresh ordinary HAP must additionally read all members and compare actual interpolation
at endpoints, interior and clamped times to the corresponding existing cubic/linear
curves, across fresh objects and both generations before this finding can close.

