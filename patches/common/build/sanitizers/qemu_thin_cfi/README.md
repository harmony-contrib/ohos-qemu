# Preserve CFI with bounded QEMU ThinLTO

The actual representative578-02 link command selected -flto=thin globally,
then cfi_cross_dso_release appended -flto, selecting monolithic LTO again.
libace_compatible.z.so consumed the cgroup budget and was killed; actual
memory.events records oom_kill=1. The original attempt is preserved.

Add a default-false QEMU argument and use -flto=thin for CFI compile and link
when that product preparation explicitly enables it. All -fsanitize=cfi,
cross-DSO, trap function, blocklist and CFI symbol-export options remain intact;
no sanitizer or optimization level is disabled. Other products retain -flto.
The separate compiler component bounds ThinLTO backends and LLD threads to2.

Clang supports CFI with -flto=thin; this is implementation direction, not
proof that this product works. Only the next actual compiled artifact and
new-QEMU runtime/CFI/ABI/boundary regressions can validate it.

Primary references:
- https://releases.llvm.org/15.0.0/tools/clang/docs/ControlFlowIntegrity.html
- https://clang.llvm.org/docs/ThinLTO.html
