# Optional SettingsData read

Pinned netmanager_base revision: `9831989d54f490d046a632ab13d309580d2fa710`.

Adds a separate `QueryOptional` operation without changing existing `Query`
or `Update` callers. A successful zero-row query means absent. Provider
creation, business errors, row-count errors, duplicate rows and failed column
reads remain errors. Outputs are cleared before any access and resources are
released on every path. This prevents always-on VPN from treating a broken
SettingsData provider as a successfully disabled policy.

`apply.sh` validates the pinned original/repaired bytes and is idempotent.
Host fault-injection tests cover the real patched implementation with explicit
DataShare doubles; the three-ABI compiler uses real product headers. Neither
is a substitute for SettingsData-backed packaged guest validation.
