# Online camera capture completion

The fixed-release V4L2/USB driver can lose or duplicate capture-end notifications:
same-timestamp messages from different captures are combined, duplicate peers
poison aggregation, cancellation/result/stop can each emit a final message, and
a DROP result returns early without retiring its in-transit entry.

This component repairs the common online driver, not the public API, camera
permissions, offline capture or image contents. Valid distinct-stream peer
aggregation is retained. A request-local, owner-stream end guard is shared by
all three end paths; it is not global and does not suppress normal continuous
frames or a genuinely new request using the same capture ID. Dropped buffers
remain DROP, return exactly once and still retire/complete their real request.

The exact-state guard rejects unknown, partial and symlinked inputs before any
write. The normal Docker recipe applies the whole component before traversal.

```sh
python3 -m unittest discover -s ci/capability-audit -p test_camera_capture_end.py
```

The host regression compiles whole actual message/request TUs and the exact
three stream method bodies with explicit platform/pipeline fixtures. It covers
original failures, post-dispatch duplicates, 64-thread cancellation, 1,000
result/cancel interleavings, DROP, normal EOS, continuous request reuse, restart
and composite peers under ASan/UBSan. It does not claim leak, hardware, guest
or package acceptance. Actual complete modified TUs have additionally been
compiled using the three products' real Ninja flags/headers. Normal newly
packaged guest validation, actual JPEG/preview, stop/restart and full-suite
regressions remain mandatory; the original probe is not relaxed.
