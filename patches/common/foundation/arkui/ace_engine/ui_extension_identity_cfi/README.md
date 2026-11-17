# Native UIExtension carrier CFI

The actual ARM64 phone command collected by inventory354 compiles the complete
`ui_extension_pattern.cpp` with ThinLTO and no RTTI, without CFI. The exact
`build_component_ng` template emits that source set without `sanitize`. Its final
`libace_compatible` target enables integer/bounds sanitizers but omits CFI as
well. Adding command-line flags to a replay would misrepresent the original GN
command. This component changes the production GN configuration instead.

The source-set change applies only to `ui_extension_pattern_ng`, platform
`ohos`, current OS `ohos`. Other component targets, `ohos_ng`, cross-platform
builds, and host tools retain their original policy. The final
`ohos_shared_library("libace_compatible")` gets `cfi` and `cfi_cross_dso` inside
its existing `is_ohos` sanitizer block; its existing integer/bounds/debug
settings are preserved. The existing build sanitizer template still decides
whether CFI applies through `use_cfi`, ASan/TSan and product policy. This patch
neither disables those gates nor overrides compiler commands. Actual required
CFI absent after GN regeneration remains a validation failure.

The configuration covers this target for ARMv7, ARM64 and x86_64 through the
existing OHOS sanitizer machinery. None of those ABIs is claimed compiled or
run by the host checks. ARM64 phone must first regenerate GN, retain the exact
new target command, compile the whole real translation unit, link the final
DSO with CFI and cross-DSO flags, and prove image bytes and the actual loaded
role. The other five profile/ABI packages are gated by that representative
package's complete runtime acceptance. This narrow change does not assert that
all ArkUI source files are CFI-instrumented.

The two complete original files were exported read-only from actual source
volume revision `e55e178228b9f6388b15d3024e8caf125fa293d7` in
`r60-GN-target-vector-375-01`. Original/final fixtures and exact whole-file
hashes support initial apply, replay and partial/unknown-state rejection.
The parent owns active patch-plan/build entry wiring and actual resources.
