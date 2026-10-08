# QEMU Mesa build recipes

Run after the existing QEMU product and Mesa base installers, before product
traversal. Both builder implementations invoke the same verified historical
mapping backport after source extraction/logger repair and before Meson setup.
The 64-bit GN action explicitly depends on the helper and numbered patch.
ARMv7a's Mesa GN input change belongs to its own `third_party/mesa3d` component.

Preserve target triples, ARMv7 softfp/NEON/Thumb flags, logger PLT/ABI checks,
install names and actual native dependencies. Known before/after file hashes
support the base installer's payload refresh; unknown files fail before any
recipe mutation. The optional ARMv7 builder is patched only once its product
has been generated, never created as an empty compatibility file.
