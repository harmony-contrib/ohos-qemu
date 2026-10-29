# Render-process connection reply

Fixed 7.0 graphic_2d revision: `81cc9ca9509bccd86c435064136fe45591d29eeb`.
Restore the **existing** client reply format: success bool, remote connection,
registered token mask. Reusing a PID returns its stored token; a failed insertion
does not pretend that a newly constructed connection was registered.

Only two server implementation files change. Client encoding, public APIs,
calling-PID ownership, permission checks, rendering backend and feature flags
remain unchanged. This internal IPC fix was explicitly approved on 2026-10-06.
Compile/fixture success is not proof of visible application rendering; the new
first package must pass screenshot and destroy/recreate regressions.
