# Existing GNSS plugin: Linux host lifetime validation

The bounded GNU/Linux batch passes: 35 existing provider cases and 24 bridge
before/after cases, with all twelve repaired bridge cases passing. The existing
callback_cleanup case now supports `--same-process-reload`: cleanup from a vendor
callback returns without self-join, a non-provider reaper joins the worker before
unload, a retiring session cannot be replaced, then the same process reloads the
DSO. A first-generation wire frame is rejected against the fresh nonce, and a
second-generation location reaches the callback. Two actual unload destructor
markers are required. No default source-generated fix is accepted.

Only four existing test files changed. Product/provider/bridge source and its
manifest remain unchanged. The initial frozen GNU run exposed a missing explicit
`<atomic>` and GCC indentation warnings, plus a GNU-unique C++ template symbol
that kept the test DSO mapped after dlclose. The host diagnostic uses
`-fno-gnu-unique` to make real unloading happen; its final ELF has no UNIQUE
symbols. ASan, UBSan, Linux leak detection, Werror and all lifecycle assertions
remain enabled. This host-only GNU binding adjustment does not change the
Clang/libc++ OHOS target.

Sources were frozen with git archive and mounted read-only in the single
approved container (CPU2/memory5GiB, networking disabled, root filesystem
read-only, executable private /tmp). Compiler was /usr/bin/g++11.4. The ARM64
macOS host ran an x86_64 Linux container image; this is a host test, not an OHOS
ARM64 guest. The container was removed and its heavy lease returned before
reporting/committing. Raw binaries, source archives and full outputs remain at
the private path recorded in result.json.

Root's existing R52 proof was checked read-only: four actual product objects and
two linked AArch64 CFI/LTO DSOs were already reported passing. Their binary hashes,
SONAMEs, real GnssVendorInterface data export and CFI symbols match that evidence.
This GNU host batch does not execute those DSOs in a fresh OHOS guest or prove
guest CFI dispatch. Public GNSS/location/fusion-fence, permission, init/DAC/SELinux
and complete representative new-package behavior gates remain pending. All ten
system requirements remain open and this hardware subtask closes no location ID.
