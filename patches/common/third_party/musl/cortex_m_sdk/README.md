# Cortex-M SDK musl porting

OpenHarmony 7.0 Release runs `third_party/musl/scripts/porting.sh` through
`/bin/sh`, but the script used Bash's `==` test operator. On Ubuntu 22.04,
dash rejects that comparison and the Cortex-M-specific empty `crtplus.c` does
not replace the Linux implementation. The resulting `crtplus.o` adds ARM EHABI
personality references to `crtn.o`, which makes the SDK build fail on
`__aeabi_unwind_cpp_pr0`.

This component changes the architecture comparison to the POSIX `=` operator.
It preserves the intended Cortex-M behavior and works with both dash and Bash.

```sh
bash patches/common/third_party/musl/cortex_m_sdk/apply.sh \
  --source-root /path/to/openharmony
```
