# Fixed OpenHarmony 7.0 libjpeg-turbo 3.1.0

Apply `apply.sh --source-root ROOT` before GN/load/build traversal. The guard
requires libjpeg repository `19603e5c6d67d7bf73cfafe097182f6d029ac571`, the
fixed 3.1.0 archive, and whole-file known original/repaired hashes. Unknown
edits, revision/archive drift and source-file symlinks are rejected.

- `0001` ports the LoongArch floating-point test selection to the two actual
  3.1.0 branches and scopes the platform-supplied INT32 to LiteOS, retaining
  the standard public typedef. It keeps the two native alignment changes and
  explicit stdlib include. Java's already upstream overflow tests, 3.1.0
  JNI `size_t`/zero-error convention, and native tj3 overflow tests remain
  unchanged; the old patch duplicated/reverted or broke them.
- `0002` checks the archive and makes extraction/patch failures fatal. Each
  patch is validated without fuzz before applying; failed patches do not
  publish generated headers. Upstream generated-header publication remains
  an explicit source write, so isolated compilers must own their input copy.
- `0003` corrects the injected configuration's stale 2.1.4 version metadata
  and enables actual compiler thread-local error storage instead of a process
  global error string. The platform's other GN configuration remains intact.
- `0004` fixes the archive's stale generated version header using its own
  fixed 3.1.0 template and copyright year, and corrects the invalid cjpeg
  lossless preprocessor condition. The new archive compatibility patch is
  a declared GN action input and participates in fatal patch validation.

`ci/capability-audit/check_libjpeg_release.py` checks the actual pinned source
in a disposable owned copy, repeats patching, runs the real installer,
compiles both header modes, builds/runs upstream native/JNI tests using the
upstream CMake host configuration (not the OHOS GN platform configuration), and injects a
real rejected patch to verify failure propagation. These checks do not prove
the Camera/image API works in a packaged guest; that requires the first-package
boot gate and ordinary-app preview/photo/decode tests.
