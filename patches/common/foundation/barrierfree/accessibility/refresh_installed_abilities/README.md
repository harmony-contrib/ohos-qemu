# Refresh installed accessibility extension abilities from BMS

In `AccessibilityAccountData`:

1. `ChangeAbility(bundleName)` previously returned early without calling
   `AddAbility(bundleName)` whenever `installedAbilities` was empty, so
   updating an installed bundle (`hdc install -r`) on an image without a
   preinstalled screen reader failed to register its
   `AccessibilityExtensionAbility`.
2. `EnableAbility(name, capabilities)` returned `RET_ERR_NOT_INSTALLED` (`4010`)
   without re-querying `GetInstalledAbilitiesFromBMS()` if a bundle-added event
   was missed.

This component refreshes `AddAbility(bundleName)` on empty `ChangeAbility` and
re-queries `GetInstalledAbilitiesFromBMS()` once on `RET_ERR_NOT_INSTALLED`.
