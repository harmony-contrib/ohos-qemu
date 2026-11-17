# Shared IDL common-type outputs

Pinned OpenHarmony 7.0 `build` commit:
`5c0623072ed9c2ee93ab909a7a01f428fee95082`.

The common-type name normalization already retains an initial `I`. The old
header-output branch added another `i`, declaring `iicli_tool_data.h` although
the actual IDL emitter and CLI consumer use `icli_tool_data.h`. Declare the
normalized common header directly, just like its companion `.cpp`.

Only the common-type output rule changes. Interface and callback naming,
IDL inputs, generated wire types, compiler flags and service protocols stay
unchanged. The common pre-traversal plan applies this component to both
profiles and all three architectures, before any GN/Ninja graph generation.
Complete before/after hashes reject unknown source edits; repeated application
does not rely on patch markers. Do not fabricate the wrongly declared header.

Host fixtures and an actual pinned-GN fragment/IDL-producer check are build
proof only. They do not establish CLI execution or newly packaged guest
acceptance.
