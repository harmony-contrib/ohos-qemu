# Dedicated Fusion service identities

The newly packaged R14 guest's real `SAMGR::LoadSystemAbility(8631)` reached init
under UID 6067, then failed **before exec**: `setcon(u:r:fusion_ranging:s0)` returned
EINVAL because the fixed Release policy has no such domain. The partner service
likewise names an absent `partner_device_agent` domain in its init configuration.
This is separate from the repaired passwd/group entries.

Add those two dedicated `sadomain` identities, distinct SA labels for 8631/8630,
and registration rules for each service's own SA. Keep init identities, tokens,
capabilities, public API permissions and the product's SELinux mode unchanged.
Do not alias either service to init, root or an unrelated domain, add permissive
declarations, or bypass `setcon`. No global policy/neverallow/whitelist changes.

Full policy compilation and a newly packaged boot must verify the result.
Successful SA activation alone does not establish Fusion ranging hardware or
peer connectivity support.
