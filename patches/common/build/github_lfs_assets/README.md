# GitHub mirror LFS assets

The pinned OpenHarmony 7.0 GitHub mirrors contain a small set of files whose
former Git LFS pointers were replaced by explanatory text stubs. A normal
`git lfs pull` cannot discover those files. This component restores the exact
objects identified by `assets.tsv` from the host cache before any GN/build
traversal and verifies their size, SHA-256 identity, and archive format.

The host cache is populated concurrently by
`scripts/prepare_ohos_7_0_release_lfs_cache.sh`. The map is tied to manifest
commit `f079c4ad9848f9cc4a9a4b3a3613ad8fbb142549` and does not follow master.

The map includes the exact Simplified Chinese and compatible color emoji font
objects from `global_system_resources` revision
`8cb84b3f3dd2142826e3f09cf2c171a421a06c14`. Their 213-byte explanatory pointers
otherwise pass compilation and appear as broken text in the packaged system.
`verify_font_assets_image.py` checks every packaged font directory entry, real
SFNT table bounds, and the two exact object hashes. Text rendering still needs
a newly packaged guest test; static font validation alone is not acceptance.

The boot picture ZIP and boot video are also pinned to graphic_2d revision
`81cc9ca9509bccd86c435064136fe45591d29eeb`. Packaging verifies both exact
objects extracted from system.img and rejects LFS placeholders in every staged
partition. This checks resource integrity, not successful guest playback.
