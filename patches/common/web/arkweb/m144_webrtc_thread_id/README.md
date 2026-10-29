# M144 WebRTC OHOS thread identity

Pinned WebRTC: `8f3537ef5b85b4c7dabed2676d4b72214c69c494`.

The real full-engine API26 build reaches the generic NaCl/Solaris fallback in
CurrentThreadId. OHOS pthread_t is an unsigned-long handle, not its pid_t kernel
thread ID. reinterpret_cast to an integer is ill-formed; truncation would also
return the wrong identity. Select the existing OHOS gettid() API, as Chromium
and V8's OHOS platforms already do. All three OHOS ABIs use that pid_t contract.

Keep CurrentThreadRef/IsThreadRefEqual on pthread_self/pthread_equal. Do not
change public types, scheduler/permission behavior, unrelated platform branches,
thread naming or WebRTC feature selection. Apply before official prepare/GN and
again through the post-prepare hook. Host and root diagnostic thread checks are
not an ArkWeb page/WebRTC session or first-package acceptance result.
