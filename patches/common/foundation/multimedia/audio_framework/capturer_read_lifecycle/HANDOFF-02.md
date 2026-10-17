This follow-up supersedes the current candidate binding in delivery.json while
preserving that original receipt and both Linux failure batches unchanged.
The first frozen candidate had an actual HDI typo: its null check referenced the
undeclared identifier interface. Root corrected that one identifier in the E
payload before reopening this lease. This batch binds that corrected payload to
manifest.after and regenerates the complete F09 primary HDI + ALSA 0002 delta.
0001 remains the historical five-file adaptation, so it intentionally has no
primary_impl HDI hunk. The source installer accepts exact F09 unchanged-HDI plus
five-file state and the new complete six-file state. It does not bless the old
broken E candidate as another accepted installation state.

Linux host batches01/02 are preserved failures. Batch01 lacked /usr/bin/clang;
batch02's real source OHOS Clang15 lacked host Linux ASan runtime archives. The
actual capacity compiler additionally diagnosed the undeclared identifier. The
lifecycle compiler's captured output was absent from its exception display, so
there is no evidence yet to classify its C++ failure beyond a nonzero compile.
The updated test reports actual compiler argv, return code, complete stdout and
stderr, or exact launch/timeout diagnostics. It still fails before running the
harness on any compilation failure and does not retry or substitute a compiler.

The existing av_codec integrity test now reads OHOS_QA_CXX just like the lifecycle
test; ALSA uses OHOS_QA_CC. Root may explicitly provide actually verified GCC/G++
paths after checking compiler identity and real sanitizer runtime availability.
All -fsanitize=address,undefined and -fno-omit-frame-pointer flags remain. No native
product compile flags or acceptance assertions were weakened. GCC/C++ dependency
errors, if any, are intentionally left to the next complete actual host batch.

No tests, AST validation, compiler, Docker, SDK, guest, HDC, QMP or Git operation
was executed by media for this follow-up. Product native/representative runtime
remain pending, capability closure remains zero. All original lifecycle scope
gaps remain. delivery-02.json contains the current full owned-file manifest,
incremental changes, exact production hashes and immutable failure-evidence links.
Media freezes and releases its complete reopened E lease after this handoff.
