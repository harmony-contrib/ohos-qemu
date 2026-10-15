# API 26 location runtime routes

Apply after `api26_public_enums`. This component adds API routes to actual
locator/BLE state and preserves existing transaction numbers.

The icon query reads the current account's GNSS, network and fused requests under
the request/permission locks. It excludes inactive, frozen, expired, unpermitted,
passive-only and switched-off requests, unless the real switch-ignore permission
is active. The system API check runs in the service, without requiring location
permission just to read the icon. Both NAPI and Taihe use this same IPC query.
This source contains no HD provider state; requested priority or numeric accuracy
is never presented as `HD_LOCATING_STARTED`.

The host icon test executes the new query plus the fixed source's existing
availability guard with ASan/UBSan. It is not GNSS/device or packaged-runtime
validation. Shared build wiring and representative package acceptance remain
owned by the integrating agent.
