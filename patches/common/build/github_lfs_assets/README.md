# GitHub mirror LFS assets

The pinned OpenHarmony 7.0 GitHub mirrors contain a small set of files whose
former Git LFS pointers were replaced by explanatory text stubs. A normal
`git lfs pull` cannot discover those files. This component restores the exact
objects identified by `assets.tsv` from the host cache before any GN/build
traversal and verifies their size, SHA-256 identity, and archive format.

The host cache is populated concurrently by
`scripts/prepare_ohos_7_0_release_lfs_cache.sh`. The map is tied to manifest
commit `f079c4ad9848f9cc4a9a4b3a3613ad8fbb142549` and does not follow master.
