# Single shared SyncFence owner

Pinned graphic_surface revision: `bd80c28b14d74226533e25e11176eee140aa9567`.

Issue #20 is reproducible in the R6 ARM64 phone package with an empty C main
linked `-lavplayer -ludmf`: 3/3 executions exit 139. Debugger breakpoints show
two cleanup callbacks, from `libsync_fence.z.so` and `libsurface.z.so`, releasing
the same `SyncFence::INVALID_FENCE` global. Matching library build IDs and the
generated GN link inputs corroborate the duplicate owner.

`surface_static` already depends on the shared fence library, but FrameReport's
transitive **static** fence dependency also embeds a second implementation into
libsurface. Change only that dependency to the existing shared provider.
No wait/merge, FD ownership, allocation, IPC, scheduling, permission, public
header, or exported Native Fence API behavior changes. Do not suppress teardown
or retain leaked globals. Keep the NDK provider and its native_fence symlink.

Acceptance requires fresh GN, actual linked ELF ownership/dependencies, and all
empty-main link orders/repetitions in a newly packaged guest. Host fixtures or a
successful link alone do not close this issue.

Relink the whole system dependency graph, not only the library pair. The R6 NDK
Pixelmap imports `SyncFence::InvalidFence()` but its as-needed link retained only
libsurface, which previously embedded that method. Replacing just Surface in a
private directory produces a real loader error, not an exit regression result.
The generated normal Pixelmap link already includes the shared fence provider;
its relink against the non-duplicating Surface must retain that direct dependency.
The image guard therefore also checks Pixelmap's actual imports and DT_NEEDED.
Do not restore static duplication, change namespace policy or suppress cleanup.
