# Bounded real screen modes and complete IPC replies

Pinned window_manager: `c9e0c375301ef3fc5cb08d4e5ab69bc7fe04bf73`.

Actual R21 QEMU reports 26 DRM/RenderService modes. `ScreenInfo` rejects more
than 20 when serializing. The SceneBoard stub logs failure but reports successful
IPC; its client ignores the decode failure and returns DM_OK with an empty list.
This prevents the real Settings refresh-rate page from reading screen modes.

The component keeps all actual modes, with a finite maximum of 256 (4 KiB of
mode entries per screen). Before writing, reject an oversized list or null mode.
Before decoding mode entries, require both the maximum and enough parcel bytes.
The SceneBoard stub returns an IPC error for serialization failure; its proxy
requires an actual service status and a completely decoded temporary vector
before publishing any result. Existing service errors are preserved.

No public API, permission, token, screen ownership, rendering backend, mode ID,
refresh rate, resolution or actual hardware mode is replaced or fabricated.
Both image profiles and all architectures use this shared component. Old images
are not certified by a new client's host tests.

Exact whole-file hashes reject unrelated and partial modifications. The two
original CRLF files retain their byte format; the shared exact patch runner only
adapts scratch patch line endings for the explicitly declared files.

Validation (not yet new-image acceptance):

- Five host tests: exact/idempotent/unknown/partial states; real serializer body
  at 0/1/20/21/26/255/256 modes, 257/UINT_MAX rejection, every truncated byte,
  null entries and injected write failures; real proxy body under seven transport
  and service conditions for 64 cycles. Host Parcel/transport stand-ins are only
  dependency fault injection, never real IPC evidence. ASan/UBSan enabled.
- Actual parcel/proxy/stub translation units compiled with real pinned product
  flags for ARM64, ARMv7a and x86_64: nine successful compilations in
  `screen-mode-three-abi-r23-01/evidence.json`; original source/out read-only.
- `r21-display-service-diagnostic-02` preserves actual DRM mode list,
  RenderService's 26 modes, active 1280x800 at 75 Hz, and old-client empty result.
  DMS is SA 4607 (3308 is display power, not the screen information service).

The next representative package must still prove complete real mode readback,
Settings page rendering/selection, normal application denial and regressions.
