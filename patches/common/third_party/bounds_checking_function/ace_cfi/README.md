# Fixed ACE sec-static CFI variant

Actual491 proves libsec_static.a has39 real C members without CFI. C-only code may still be an indirect-call target. A new fixed libsec_static_ace_cfi target reuses the original libsec_sources, all seven flags and public configuration, with official cfi/cfi_cross_dso sanitizer policy. The original global static target, shared target and Lite logic are preserved byte-for-byte; only the new OHOS standard branch is added.

The ACE smartlayout component alone selects this target via an exact GN deps label, retaining the original path for other platforms. It does not invent a public innerkit declaration or alter all system sec-static consumers. The native guard admits the variant only in smartlayout and joins its actual archive members to real compiled objects. Apply this component after qrcode CFI and before ACE coverage. New GN/target/image/runtime proof remains pending.
