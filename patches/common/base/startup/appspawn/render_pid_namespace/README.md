# Renderer termination in a PID namespace

The pinned M144 renderer implements `terminateRenderProcess()` by sending
`SIGTERM` to `getpid()`. QEMU's sandboxed renderer is PID 1 in its own PID
namespace. Linux ignores SIGTERM's default disposition for namespace init, so
the call succeeds without terminating anything or emitting `onRenderExited`.

Install an explicit SIGTERM exit handler for **renderers which are namespace
init**, before renderer seccomp and entry. Preserve existing explicit handlers;
reject a deliberately ignored signal or a failed installation. Other process
types and ordinary PIDs are unchanged. No namespace, UID, permission, token or
seccomp isolation is disabled. The handler uses only async-signal-safe `_exit`.

Host tests and three-product compilation do not prove Chromium leaves this
handler installed. A newly packaged guest must demonstrate actual renderer
exit, callback delivery and subsequent document/proxy/WebGL recovery before
this item can pass the first-artifact gate.
