# Valid wallpaper module identifiers

Actual product SDK attempt 02 rejected the historical hyphenated module names.
Migrate only the internal module identifiers to phone_wallpaper and pad_wallpaper
in each manifest, the project module graph and source GN assemble selections.
Bundle com.ohos.wallpaper, WallpaperExtAbility, feature type, original device
labels, all permissions and profiles remain unchanged. No fake MainAbility or
entry module is added. Apply after source_provider and before assembling a HAP.
The original SDK failures remain preserved; complete HAP/BMS/runtime validation
is required after the migration.
