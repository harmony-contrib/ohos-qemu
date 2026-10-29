# Source Photos certificate pins

Pin both existing Photos policy entries to the verified OS release signing
certificate used by the source-built HAP. Patch 0001 covers privileged extension
and form registration. Patch 0002 covers the unchanged six preinstall grants.
Do not add permissions, change user-cancellability, accept wildcard certificates,
or grant permissions to an ordinary caller.

The R14 real save dialog accepted the user's confirmation but its Photos service
then failed MediaLibrary operation 10007 with permission error 201: capability
policy used the new certificate while the permission policy still used the old
prebuilt certificate. Empty recent-photo results alone missed this defect.

Preparation validates both Photos entries before canonicalizing either JSON;
unknown Photos policy changes, duplicates and symlink redirection fail closed.
Unrelated entries are preserved. Packaging independently checks both policies
inside the actual system image against the validated source. A newly packaged
ordinary-app save/selection/readback test is still required for acceptance.
