# PhotoAccessHelper FusionAssetType export

The pinned MediaLibrary already defines `COMPATIBLE_ASSET=0` and uses this
real type in album fusion results, but its ArkTS 1.1 public module never
exports `FusionAssetType`. Register only that existing value in 0001 and forward
the real native object through `photoaccesshelperinf.js` in 0002; native
registration alone does not make the public ArkTS import usable. The helper uses
the existing checked NAPI-call pattern, creates no persistent reference and
leaves album access, providers, permissions and sync behavior unchanged.

The exact component validates the fixed project commit and complete before/
after source hashes, then supports fresh/repeated application and the exact
known 0001 prefix. Unknown or noncontiguous edits fail before source writes.
Both profiles and all ABIs use the
common patch plan before product compilation/traversal.

Host fixtures and full-TU compilation are not a new-image behavior pass.
Guest closure requires both actual typed SDK and native own-member reads
on the newly packaged image; the underlying fusion/storage/sync service
requires separate behavior evidence.
