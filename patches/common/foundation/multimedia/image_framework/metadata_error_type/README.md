# Numeric metadata parameter errors

Scope: only `ImageSourceNapi::ReadImageMetadataByType`'s existing failed-context
branch opts into `ImageNapiUtils::ThrowExceptionError(..., true)`. The existing
helper uses `napi_throw_business_error` for this explicit option. Its default
remains `false`; other APIs, `readImageMetadata`, error value `7700204`, message,
parameter validation, metadata parsers, permissions, asynchronous work and C++
ABI are unchanged. No new exception implementation or numeric coercion is added.

The user explicitly approved this minimal public error-type correction on
2026-10-10. Applicable upstream instructions read: `AGENTS.md`,
`docs/knowledge/api-binding-surface.md`, and
`docs/knowledge/metadata-picture-model.md`. The existing NDK constant
`IMAGE_SOURCE_INVALID_PARAMETER` and JS error conversion retain their values;
no matching `ReadImageMetadataByType` entry was found in the checked native,
CJ, ANI or Taihe bindings. This is a JS error representation repair, not a
cross-language API or parser change.

## Validation

- Patch application checked against the pinned source using read-only Docker;
  application/idempotence/drift tests and a compiled call-encoding boundary test
  are in `test_image_metadata_error_type.py`.
- The ordinary `image-metadata` HAP is mandatory in the packaged-image suite.
  Real DNG, TIFF and AVIS fixtures cover selected/default reads, negative/end
  indices and successful reads on the same source after rejection. Its verifier
  rejects the original string `"7700204"`, including after evidence is rehashed;
  it never normalizes an incorrect return type or claims public constructors.
- Full-image compilation and those runtime cases must pass on the next new
  representative archive. Host tests and an older archive are not proof of the
  production repair. The existing R27 failed run is retained as pre-fix evidence.
- Related XTS target found in the pinned tree:
  `//test/xts/acts/multimedia/image/image_ets_standard/imageExifGetModify:image_exif_get_modify_hap`,
  HAP `ActsImageExifGetModifyTest`, with
  `SUB_MULTIMEDIA_IMAGE_SOURCE_READ_IMAGE_METADATA_BY_TYPE_0001` through `0006`.
  The full XTS HAP has not been run for this change. Parser fuzz and physical
  hardware tests have not been run; parsers, Surface/DMA and display paths are
  not changed. QEMU device validation remains mandatory before delivery.

Manual review is limited to the changed call, existing helper, untouched
validation/lifecycle and error mappings. It is not a claim that the external
`stability-code-review` workflow or full XTS completed. No push is authorized or
performed; upstream's full review prerequisite remains applicable before push.
