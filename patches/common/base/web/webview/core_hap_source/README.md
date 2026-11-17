# Complete source-built ArkWebCore

Select and install the complete signed M144 HAP for the actual QEMU ABI before
product-profile evaluation and GN traversal. ARMv7a, ARM64 and x86_64 have separate
source-built engine, renderer, adapter, crashpad, FFmpeg and runtime resources.
There is no ARM64 fallback for x86_64 and no V8-only substitute.

`apply.sh --source-root ROOT --artifact-root ARTIFACTS --product PRODUCT` verifies
the fixed 156-project release graph, private API-26 SDK, frozen native/package
patches, successful native and official HAP build, final ELF ABI/resources and
SDK signature-verification evidence. Unknown existing files are preserved and
rejected. Official prebuilt HAPs are left intact; later LFS restoration cannot
overwrite the managed `qemu-core` inputs.

These checks establish dependency provenance only. They do not prove Web API,
renderer startup, visible presentation or first-artifact behavior acceptance.
