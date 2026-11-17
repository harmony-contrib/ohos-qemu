# Recent Photos public contract

Applies after the exact Fusion/Photo/source-search enum composition on fixed
MediaLibrary revision `564ae888e7dcc7e0ec4c17ec9c77bf780e9cb380`.

The real R14 package reproduced `getRecentPhotoInfo()` returning 401 when its
optional argument was omitted, and mutation of a caller-provided options object.
The wrapper also failed to await its RPC result, abandoned cold service starts
after 330 ms, and never disconnected its own service connections. The repair
normalizes a private copy, awaits the actual result, uses the connection callback
with a bounded 10-second deadline, and retires each connection/Parcel exactly
once on success, failure, timeout and partial allocation failure. Empty results
remain distinct from the existing unavailable-provider sentinel; no data is
invented and the real Photos service, token and permission paths are unchanged.

PhotoViewPicker parameter validation also returned filesystem error 13900020
for a fractional maximum, although the fixed API26 SDK specifies 401. This
component repairs the parameter/type boundary without changing valid selection
or cancellation behavior or granting access to images.

Whole-source host regression uses explicitly named RPC/context fixtures. It is
not guest acceptance, positive media-data/FA-card proof, cloud-provider support,
or evidence that all PhotoAccessHelper behavior is complete. A rebuilt package
and real ordinary-app regressions remain required.
