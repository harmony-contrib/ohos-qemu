# Standard account table format

The fixed 7.0 init passwd record for `cloud_disk_service` has six fields,
not the required seven. Add only the missing empty home field so `/bin/false`
is the shell, preserving UID/GID 6161 and the empty home. No service privilege,
group membership, provider, credential or cloud functionality is added.

Run in both profiles before source traversal, after the Fusion account patch.
The fixed HEAD and complete original/Fusion composition are checked before
writing. Unknown edits, aliases and symlinked targets fail without replacement.
Repeat application is supported in either known complete table composition.
