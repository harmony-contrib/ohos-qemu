# Fusion service account registration

Fixed 7.0 fusion init requires `fusion_ranging` and `partner_device_agent`; the
fixed passwd/group only register the separate HDF `fusion_host` account. Register
two distinct non-root, non-login users/groups in the standard 0-6999 passwd range.
6067/6068 are QEMU-local reserved IDs, checked unused in both fixed account tables.
Do not reuse root/system, share the radio driver's UID, or add grants/capabilities.

Before applying the independent numbered patch, check exact init/fusion HEADs,
unchanged service configurations/authority and the whole known account-table
transformation. Preserve/reject collisions, symlinks and unknown edits.
Apply before source metadata traversal for both profiles and all three ABIs.

New-package validation must inspect the actual installed users/groups, directory
ownership, successful on-demand SA activation and ordinary-app rejection/grant
boundaries. Service registration alone does not prove Bluetooth/Nearlink ranging
or peer connectivity. This late candidate is not present in the frozen R6 input.
