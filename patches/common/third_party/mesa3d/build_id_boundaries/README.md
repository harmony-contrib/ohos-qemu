# Historical Mesa ELF note boundaries

The actual QEMU Mesa 21.3.3 callback dereferences the next note before checking
the remaining PT_NOTE length. It also accepts GNU build IDs without checking
whether their descriptor is present. A complete final non-GNU note reproduces
an ASAN heap-buffer-overflow in the original callback.

The patch validates the header, name, descriptor and their padding before
reading or advancing. Subtraction checks also avoid 32-bit size overflow.
Valid padded OHOS notes from the pinned musl crtbrand assembly and GNU notes
remain supported; malformed notes end traversal of that segment. Unaligned
data cannot escape as a struct that consumers dereference.

The LLVM consumer stages this guarded helper and numbered patch for all three
QEMU architectures. GN inputs, the consumer cache key and package provenance
include both files. Existing known hooks can be restored before upgrading;
unknown source changes are preserved and rejected. The release Mesa checkout
is not patched: only the extracted historical source is changed.

The callback regression uses bounded synthetic ELF mappings with ASAN/UBSAN.
Final acceptance still requires the complete newly packaged guest tests.
