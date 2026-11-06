# OpenGL ES 1.x / 2.0 wrapper hook-table sharing with libEGL.so

In OpenHarmony 7.0 `frameworks/opengl_wrapper`, `libGLESv3.so` resolves
`GetHookTable` and `GetHookTableKey` from `libEGL.so`, whereas `libGLESv2.so`
(`ndk`/`llndk`) and `libGLESv1.so` compiled private copies of
`src/thread_private_data_ctl.cpp` whose private `ThreadPrivateDataCtl::tableKey_`
is never populated by `libEGL.so`. Any NDK binary linking `-lGLESv2` failed
every direct GLES2 entry point (`gl* is invalid.`).

This component aligns `GLESv1` and `GLESv2` with `GLESv3` by dropping the
duplicate `thread_private_data_ctl.cpp` translation unit and resolving
`GetHookTable` / `GetHookTableKey` from `libEGL.so`.
