# Read-only Wallpaper build-witness review

Two deterministic false-accept boundaries were reported to root. Root repaired
them while this review was being recorded. No shared script, product source,
build output or system setting was modified by this agent.

1. `compile_check` originally required flag presence, without applying Clang's
   ordering. The actual frozen ARM64 Wallpaper compile query, with only the new
   QEMU macro inserted into parser input when absent, remained accepted after
   appending each of `-fno-sanitize=cfi`, `-fno-sanitize=all`, `-fno-lto`,
   `-fexceptions`, and `-frtti`. A service-level exported `__cfi_check` cannot by
   itself attest protection in these two individual translation units. The real
   command legitimately disables generic CFI **before** enabling vcall/icall, so
   banning every occurrence of `-fno-sanitize=cfi` would reject valid product flags.
2. `selected_args` independently searched for the theme_service heading and any
   Current value=false line. A block where theme_service=true followed by another
   argument=false was accepted. The check needs a unique corresponding argument
   block and the actual theme_service query argv binding.

`parser-replay.json` preserves both original accepts and root's corrected
behavior: the five cancelling suffixes and unrelated false block now reject;
the actual valid compiler order and selected false block still accept.
`replay.py` runs only these pure functions. It never runs the actual compiler,
GN, Ninja, Docker, image tools or guest. The prior actual query is SHA-bound.
Its injected QEMU macro is explicitly parser input, not evidence that a new
GN graph was selected or a product was rebuilt.

The reviewed initial whole script SHA was observed before root's repair. Root
changed it before a full-byte copy could be made. `reviewed-guard.txt` therefore
contains only the two exact original predicate functions from the observed tool
output, plus equivalent constant declarations. Its separate excerpt SHA is
recorded; it is not misrepresented as the full original script. The frozen actual
compile query is copied unchanged from the earlier platform diagnostic.

## Build/package/verification and fixed source

No deterministic normal-path blocker was found in the three script connections:
begin runs before the real non-load-only phone/2in1 build, after source/load
preflight; finish follows successful full images build under the shell's pipefail;
package uses the current system.img and writes wallpaper-native; full package
verification consumes that same inventory and actual ext4 DSO bytes. The witness
preserves and removes only the two owned fallback objects, linked/unstripped/
staged Wallpaper DSOs and previous witness to require fresh outputs. Image
matching plus a real defined CFI symbol is correctly distinct from actual AMS
connection behavior, which remains a runtime requirement handled by Apps/root.

Actual source inspection confirmed `wallpaper.gni` default false unless the real
Theme manager part is present; the QEMU renderer component only adds its macro
for the three actual virt product names with theme_service=false. The source
hashes in the guard agree with that component's two patched files and the two
unchanged gni/connection files. The actual current graph contains the expected
service/connection object paths and solink edge. It is a mixed diagnostic out,
not archive proof or a newly generated patched graph. Its current missing QEMU
macro before actual full source preparation is not reported as a product defect.

The prior `/ohos` gn args failure used generated absolute
`/Volumes/PSSD/qemu/openharmony` paths under a different alias. Root's complete
build uses the real absolute mount path. That diagnostic alias mismatch is not a
product or guard bug and was not rerun here.

## Resource observation, without changing protection flags

Read-only fixed source `build/config/compiler/BUILD.gn:567–617` shows the enabled
ThinLTO branch setting LLD `--thinlto-jobs=16`, or non-LLD
`-plugin-opt,jobs=16`, as literal values. `use_thin_lto`,
`use_thinlto_cache`, `thin_lto_enable_optimizations` and
`thinlto_cache_policy` are enable/cache/optimization controls, not a thread-count
argument in this code. `build/toolchain/BUILD.gn:17–18` uses
`link_pool.depth=concurrent_links`; root's `concurrent_links=1` limits simultaneous
link commands but not one linker's internal16 ThinLTO tasks. No GN argument,
CFI/LTO flag or resource limit was changed by this agent. Root separately owns
the active M144 link lease and its recorded resource adjustment.

Only the explicitly inspected pure `test_qemu_wallpaper_build_witness` module was
run; no broad discovery or native test was started. Actual full build/witness,
image package, real AMS fallback connection and first-package behavior gate
remain pending. This review closes no capability requirement.
