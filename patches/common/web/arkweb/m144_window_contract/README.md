# M144 private WindowAdapter mirror

Pinned ArkWeb: `f3d904432cc1c57468f2b7fe01979d25e0157581` (OpenHarmony 7.0 Release).
The fixed release WebView and the pinned TPC WebView dependency already declare
`WindowAdapter::SetWindowNodeIdAndRSHandle`, including its default fallback. The
previous master-based private NDK mirror omitted it. Its include guard can shadow the canonical header,
so the normally generated `ArkWindowAdapterWrapper` cannot compile its existing
override. This was reproduced by the actual full-engine ARM64 build.

The unified release source already contains the slot. Validate it rather than
applying the obsolete master-only patch. The real generated
override continues to forward through the existing C ABI to the release system
adapter, which sets `delegate_node_id` and `delegate_connect_to_render`. Do not
remove the override or hand-edit generated bridge files to suppress the error.
No release public interface, C ABI table, token permission, rendering backend,
or existing method signature changes.

Reapply through the official post-prepare hook and rebuild the actual engine.
The entry explicitly applies the existing shared API26 compiler/runtime and
prepare-path adaptations before full-core GN. A prior successful V8-only build
is not required to have silently initialized these inputs.
Compilation or the presence of this method does not prove visible Web rendering;
the new packaged guest still must pass the Web/Window regression gate.
