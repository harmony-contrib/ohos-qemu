# Dynamic SpringLoadingContext class export

The pinned API 26 SDK declares `dragController.SpringLoadingContext`, but the
dynamic drag module does not export it. The dynamic frontend already binds the
real `JsDragSpringLoadingContext` class and creates callback instances with it.

Expose that same environment's frontend constructor through a read-only,
enumerable accessor. Do not invent a second class, copy native state, retain
another environment, or change spring timing, `abort`, configuration, UDMF,
permissions or drag dispatch. Before frontend registration the accessor returns
undefined, preserving non-UI module imports; once registered it resolves the
real constructor. Reject a non-function replacement rather than expose it as a
class. This is not a full drag/drop or MSDP backend repair.

KB routing: `kb_search.py spring` / `drag`, then the complete
`docs/common/interaction/Drag_Drop_Knowledge_Base_CN.md`; verified against pinned
dynamic `js_drag_function.cpp`, `jsi_view_register_impl{,_ng}.cpp` and
`interfaces/napi/kits/drag_controller/js_drag_controller.cpp`.

Host sanitizer and actual three-ABI TU compilation are preparation only.
New-package acceptance must exercise a real spring callback's class identity,
hover/configuration/abort lifecycle and cleanup; an export name alone does not
close the ledger contract. Not included in already frozen R37 build inputs.
