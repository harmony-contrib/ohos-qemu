# Preserve LazyDynamicLayout during algorithm updates

The pinned model replaced the pattern on every update, dropping the scroll
view-position layout constraint and main-tree attachment state. The ordinary
API26 runtime diagnostic showed valid initial lazy callbacks, then no helper or
visible-index callbacks after changing the custom algorithm.

Reuse the existing pattern/layout property and update its algorithm parameter.
Keep the installed visible-index callback unless the new parameter supplies one.
A null parameter clears the algorithm; a changed axis on an attached node runs
the existing parent/axis validator again. Frame and child identities are retained.

This exact-source candidate is not runtime or first-package acceptance. The
full typed caller still requires real scrolling, geometry, callbacks, reset,
removal, recreation and cleanup on the newly built representative artifact.
