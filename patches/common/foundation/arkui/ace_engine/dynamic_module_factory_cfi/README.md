# Dynamic module factory CFI types

The C39 representative image aborts during appspawn ACE preloading. All four
actual fault stacks enter `libarkui_badge.z.so::__cfi_check_fail` from
`DynamicModuleHelper::GetDynamicModule`. The caller uses `DynamicModule* (*)()`;
the exported Badge function is declared `void* ()`. The actual caller and target
CFI type identifiers differ.

This component changes all 62 dynamic factories in 61 source files to return
`OHOS::Ace::DynamicModule*`, and changes the compatible loader entry to return
`OHOS::Ace::ComponentLoader*`, matching the existing caller aliases. The C names,
parameters, allocation/loader bodies, ownership, fallback behavior and CFI
instrumentation stay intact. The derived-to-base conversion occurs in each
factory, before crossing the DSO boundary.

The 62 factory names exactly cover the current OHOS helper map. All 62 file
preimages come from the actual C39 Native read-only capture
`r67-c39-ace-factory-family01/native`, at ACE revision
`e55e178228b9f6388b15d3024e8caf125fa293d7`. Source authoring independently matched
the same official revision byte for byte. `verify_source.py` only provides the
whole-file states required by the existing exact component apply helper;
`apply.sh --source-root ROOT` uses that unchanged helper. The package check
`apply.sh --source-root ROOT --require-final` only validates the final state.
It rejects partial or
unknown sources. The one CRLF source is preserved by the helper's existing
CRLF support.

The literal changes and their complete byte inverses were checked as data.
No patch, guard, compiler or host test was executed. The parent owns build
wiring and must boot and validate a freshly built representative QEMU image
before proceeding to the remaining architecture packages.
