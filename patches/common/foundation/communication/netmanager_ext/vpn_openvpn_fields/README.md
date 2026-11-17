# Preserve stored OpenVPN forwarding routes

Fresh R39 real three-variant storage validation found forwardingRoutes empty
only in OpenVPN. Database and IPC already retain it; unlike the IPsec/L2TP
conversion, the OpenVPN bean conversion omitted this existing common field.
Copy the stored field without changing layout, schema, credentials, tunnel
execution, signature, permissions or unrelated conversion fields.

Requires the complete exact earlier VPN store repair. Both profiles/all ABIs
apply it before GN/traversal. The parent store recognizes only this exact
complete child plus its other exact final files on rerun. New-package CRUD,
replacement, list/read, restart and denial regressions remain required.
