# Metadata FetchResult public contract

Fixed player source: `3d3b1231db27561e8978652d7ae867c12f488d9a`.
Expose the three public FetchResult constants matching the existing metadata
server and JS callback protocol: failure 0, success 1 and cancellation 2.
Check every new NAPI operation and propagate registration failure through the
real media module initializer. Existing players, metadata fetch implementation,
feature gates, callbacks, permissions and their numeric values are unchanged.

Host registration/error fixtures and TU compilation are not metadata extraction
or guest acceptance. The complete original regular-enum collector must read
the actual packaged public module on a new archive; frame fetch behavior needs
its own real media/provider proof.
