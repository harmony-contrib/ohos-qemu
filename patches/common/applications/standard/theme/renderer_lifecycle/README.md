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

The second patch aligns the renderer with the captured wallpaper manager
revision `42256bdeaa504da4ae4d038c24d42a4601e3a6cf`: its registered base module is
`WallpaperExtensionAbility`, and native startup calls `onCreate` followed by
`createWallpaperWin`; wallpaper updates call `onWallpaperChange`. The renderer
overrides the explicit window hook and starts at most one owned creation per
generation, instead of also inheriting the base module's default window builder.
The existing late-completion and PixelMap ownership checks remain in place.

Apply after `source_provider` on a private source checkout. A clean pinned source
replays `0001` then `0002`. The component-local upgrade handles the already
patched Build22 state only when both phone/pad files have SHA-256
`84cde2fbed244e1e6e3562096f66d5948d9124c4030e7d1bd54b3fa39e761dac`.
Under the shared exact component lock, it checks the fixed `0002` patch in a
temporary copy, verifies the complete new state, rechecks the real legacy pair,
then applies and verifies the new pair. Unknown or mixed states are rejected;
the shared helper still verifies clean replay and complete current replay.

Build22 recorded the unresolved old module import and `parent class is not
constructor` JS crash. The source fix has not yet been compiled or validated in
a newly packaged QEMU image. No host tests were run for this change. Product
build, extension startup, visible wallpaper and change/stop/restart behavior
remain runtime validation requirements.
