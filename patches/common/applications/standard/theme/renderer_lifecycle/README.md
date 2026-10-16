# Wallpaper renderer lifetime repair

Pinned `applications/standard/theme` revision:
`a436a43f1c0948fa12df6d520ec695ae4388a057`. This component modifies only
the existing phone/pad WallpaperExtAbility.ts files. It retains both real
wallpaper rendering extensions and adds no settings UI, manifest route,
permission, profile or build metadata.

The old error path referenced undefined Log/TAG/name identifiers. The replacement
logs the actual error and owns each created window. Recreate/destroy invalidates
earlier creation, load and show completions; a late-created window is closed and
an old failure can never close a newer window. Owned window destruction is
idempotent. PixelMap callbacks reject older image generations, errors, undefined
data and completion after destruction. getPixelMap and all async window failures
are caught; no successful rendering is claimed on failure.

Apply after `source_provider` on a private source checkout. Exact component
hashes reject partial edits and allow complete replay. Host tests execute the
actual extracted renderer with controlled window/PixelMap completion; they are
not official SDK or runtime acceptance. The old extension/window APIs still
require full product API26 compilation, install/boot/window/image verification.
The missing real wallpaper settings UI, expired profile renewal, feature-only
BMS/device compatibility and the native Launcher fallback remain root-owned
integration/runtime gaps.
