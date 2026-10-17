# Root observer ABI repair

The complete Linux04 batch compiled all methods, then the strict /proc syscall observer failed before executing control actions for both baseline and candidate. A separate diagnostic preserved unchanged baseline/Futex methods and logged the actual wait: declared x86 syscall 202, real kernel syscall 98, identical futex address. Docker Engine reports aarch64. The amd64 container is translated on that kernel.

Only the host observer now maps root-supplied OHOS_QA_KERNEL_ARCH from the recorded Docker Engine Architecture to its kernel futex ABI. Both observer checks still require the exact syscall and exact owned mutex/futex address. Production FutexTool still invokes its original __NR_futex. No actual method, sanitizer, baseline counterexample, lifecycle assertion or payload changed. Missing environment retains native compiled ABI; unknown architecture fails.

Root must rerun the entire sanitized Linux batch. This repair and the diagnostic are not test success, native build, package or runtime acceptance. Historical deliveries and Linux04 logs remain immutable.
