# PixelMap NAPI function type

Build22's representative QEMU image reaches SceneBoard after the dynamic
factory repair, then aborts four times in `libimage_napi.z.so::__cfi_check` from
`CreatePixelMapFromNapiValue` while drawing icons or wallpaper.

The actual exported `OHOS_MEDIA_GetPixelMap` function returns `void*` and takes
`napi_env, napi_value`. ACE's shared alias instead erased both parameters to
`void*`, causing the indirect call to present the wrong CFI function type.

This component types the shared alias with the existing NAPI opaque pointer
types, reuses it in the drag controller, and removes the unnecessary function
pointer cast on the Android/iOS direct branch. The dynamic lookup still casts
the dlsym address to that exact function type. Library selection, return value,
ownership, null handling, allocation and CFI remain unchanged. The existing
preview conditional is unchanged; the common header adds only an opaque
`napi_env` declaration beside its existing `napi_value` declaration.

All three preimages are actual Native captures under
`r67-build22-pixelmap-source01/native`, ACE revision
`e55e178228b9f6388b15d3024e8caf125fa293d7`. The component uses the unchanged
exact apply helper: `apply.sh --source-root ROOT`. Packaging can check without
mutation using `apply.sh --source-root ROOT --require-final`.

The four literal edits were checked forward and backward as bytes. No source,
patch, guard, compiler, host test or shared resource was executed. A freshly
rebuilt representative image must pass the relevant QEMU behavior before the
remaining architecture packages are built.
