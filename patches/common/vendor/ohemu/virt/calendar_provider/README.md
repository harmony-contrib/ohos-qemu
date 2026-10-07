# CalendarData source signing policy

Pin only com.ohos.calendardata to the certificate already used by its existing
system-core OS-integration Calendardata.p7b and the normal GN platform signing
key. The public SHA-256 fingerprint is
8E93863FC32EE238060BF69A9B37E2608FFFB21F93C862DD511CBAC9F30024B5.
Remove the unrelated prebuilt certificate, but keep both privilege flags,
every other bundle entry, all permission checks, and the exact original ACLs.
No wildcard, unsigned installation, system-app permission bypass, or automatic
user permission grant is introduced. Actual BMS installation/identity and
permission boundaries remain part of newly packaged guest validation.

The pristine fixed file uses compact JSON/CRLF, while SceneBoard rewrites it
with two-space JSON. Validate the exact original/already-repaired CalendarData
entry and reject duplicate JSON keys first, then canonicalize all values
unchanged before applying the one-fingerprint diff. This works before profile
traversal as well as on an existing build; unknown certificates, privilege
changes and duplicate entries fail without rewriting the input.
