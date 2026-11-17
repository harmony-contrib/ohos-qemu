# QEMU CPU YUV DMA-buffer storage

The fixed QEMU GBM wrapper requests an 8-bit DRM dumb buffer for YUV, while
Linux virtio GPU only accepts 32-bit dumb allocations. Real ordinary AVCodec
decode therefore fails with EINVAL before producing pixels.

For the actual `virtio_gpu` driver only, CPU-accessible planar/semiplanar YUV
uses a 32-bit storage resource with four bytes packed per storage pixel.
Logical YUV format, dimensions and actual byte stride remain unchanged.
This does not advertise YUV KMS scanout or protected-buffer support. Non-virtio
devices and 32-bit RGB storage keep their existing geometry. Zero, odd chroma
dimensions and overflow are rejected; failed allocations/destruction release
their local bookkeeping. No kernel ABI, permissions or loader policy change.

The numbered patch and exact fixed-commit preflight are owned by this component.
Call `bash apply.sh --source-root ROOT` before GN/product input traversal.
Host geometry tests and compiler checks are not guest pixel acceptance; freshly
packaged ordinary C++ AVCodec pixel/PTS/IDR/EOS/recreation tests remain required.
