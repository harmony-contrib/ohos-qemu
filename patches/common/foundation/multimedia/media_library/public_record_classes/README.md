# Public photo data records

Exports the SDK-declared `DefaultCoverOrderInfo`,
`PhotoViewMimeTypeFileSizeFilter`, `RecentPhotoOptions`, `RecentPhotoInfo` and
`RequestReadPermissionResult` as actual JavaScript data classes. Their fields
are caller-owned; no shared arrays, provider results, authorization or media
content are fabricated. RecentPhoto component already uses empty data classes;
the public photoAccessHelper entry was missing these names.

Keep operation defaults and validation in the existing consumers. This patch
does not change PhotoPicker, album queries, permissions, provider IPC, or the
shape of factory results. It does not implement `KnowledgeContent`, `ResultSet`
or context recovery. Constructor proof closes only the five data-class export
contracts, never any photo provider/asset behavior.

Apply after the existing photo helper patches. Exact original/repaired hashes
are pinned to media_library `564ae888e7dcc7e0ec4c17ec9c77bf780e9cb380`.
