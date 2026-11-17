# QEMU DRM mode selection (candidate)

R25 1920x1080 Settings UI requests advertised mode 13 (50 Hz); the real
composer rejects it because `DrmCrtc::SetActivieMode` accepts only ID 0.
The JS array-index / HDI mode-ID conversion is correct in this observation.

Validate the unsigned ID and connector membership before mutating CRTC state;
permit nonnegative, validated IDs instead of hard-coding zero. Keep existing
DRM atomic mode commit and its failure checks. Own the atomic request with RAII
on success and every failure, and reject missing/invalid mode blobs.

No invented modes, unconditional success, permission changes or IPC changes.
Wired into the shared pre-build patch phase for the next representative only;
not present in R25. Nine actual product TU compilations (three per ABI), 300
host source-function switches with sanitizer/failure boundaries, baseline
negative control and exact/idempotent/partial-state guards pass. Still requires
newly packaged Settings switching/restoration plus real DRM mode readback.
The independent 1920x1080 screenshot timeout is not repaired by this component.
