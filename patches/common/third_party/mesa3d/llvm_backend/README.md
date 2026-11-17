# QEMU Mesa with the fixed M144 LLVM dependency

The QEMU-only Mesa consumer uses LLVM 10 from the locked M144 SwiftShader tree.
It composes with the existing Mesa logger, KMS mapping and import-lifetime
backports and bounded ELF build-ID note parsing. Other products keep their
original Mesa builder. Both build-ID helper and patch are GN inputs and part
of the consumer cache/provenance identity.

Prepare one dependency with `scripts/build_qemu_mesa_llvm_in_docker.sh
arm64_virt` (also `armv7a_virt` or `x86_64_virt`). The wrapper freezes its inputs,
checks the main Release and M144 source locks, and reads the source/output
volumes without writing to them. Generated musl is preferred; a fresh tree can
use the exact pinned API 26 Release native SDK sysroot. Artifacts live under
`$CACHE_ROOT/artifacts/qemu-mesa-llvm/<recipe>/<product>`.

`apply_backend.py` verifies each complete archive/header manifest, stages it
under a versioned source directory and replaces only the QEMU Mesa GN actions.
The regular Docker dependency preparation and full build scripts invoke this
path. `--restore-hooks` restores the exact known base before parent backport
installers run; unknown edits fail before replacing those edits.

The consumer enables real llvmpipe, retains softpipe, uses private static LLVM
and exports `mesa-llvm-build-provenance.json` beside its six libraries. Full
packages require `verify_mesa_llvm_image.py` to match all six actual image
libraries to those outputs and include the checked manifests in
`mesa-llvm-source/`. Offline package verification reads the included provenance
and checks the image bytes again. An older LLVM recipe is rejected.

These manifests explicitly have no runtime acceptance authority. The fresh
package still has to pass boot stability, ordinary display/compositor behavior,
the native GLES LLVM shader lifecycle probe, complete Vulkan and every other
first-artifact behavior gate. Surfaceless EGL and QEMU user-mode diagnostics
cannot satisfy that gate.
