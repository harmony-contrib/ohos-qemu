# `third_party/libpng` ARM64-Only NEON Guard

Guards `-DPNG_ARM_NEON` with `if (target_cpu == "arm64")` in `third_party/libpng/BUILD.gn` for `armv7a_virt` / `x86_64_virt` compatibility.
