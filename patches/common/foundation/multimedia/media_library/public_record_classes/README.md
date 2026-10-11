# Public photo data records

Exports the SDK-declared `DefaultCoverOrderInfo`,
`PhotoViewMimeTypeFileSizeFilter`, `RecentPhotoOptions`, `RecentPhotoInfo` and
`RequestReadPermissionResult` as actual JavaScript data classes. Their fields
are caller-owned; no shared arrays, provider results, authorization or media
content are fabricated. RecentPhoto component already uses empty data classes;
the public photoAccessHelper entry was missing these names.

Also exports `ContextRecoveryInfo`, initializing only the seven defaults
explicitly documented in the pinned API26 SDK: empty albumUri/displayName/
sortRule and zero time/recommendationType/selectedRecommendationType/fileSize.
Version and gridLevel have no documented default and remain caller-owned,
unset fields. The constructor does not invent a restored picker session or
assert a provider protocol version. All instances have separate own fields.

Keep operation defaults and validation in the existing consumers. This patch
does not change PhotoPicker, album queries, permissions, provider IPC, or the
shape of factory results. It does not implement `KnowledgeContent`, `ResultSet`
or picker context recovery. Constructor proof closes only the six data-class export
contracts, never any photo provider/asset behavior.

Apply after the existing photo helper patches. Exact original/repaired hashes
are pinned to media_library `564ae888e7dcc7e0ec4c17ec9c77bf780e9cb380`.
