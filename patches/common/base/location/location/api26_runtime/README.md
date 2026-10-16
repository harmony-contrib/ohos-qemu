# API 26 location runtime routes

Apply after `api26_public_enums`, using this component's `apply.sh`. The two-patch
stack adds live icon and filtered BLE search routes, preserving all existing
transactions and assigning the verified unused 65/66/67 to the three new calls.

The icon query snapshots the current account's GNSS, network and fused requests.
It excludes inactive, frozen, expired, unpermitted, passive-only and switched-off
requests, unless the real switch-ignore permission is active. Permission,
account, freeze and RDB checks run after request/permission locks are released.
Fine-only callers now produce actual ACCESS_LOCATION PrivacyKit start/stop
state, including per-pid shared use; approximate callers keep approximate use.
The service checks system API permission; reading the icon does not require
location permission. NAPI and Taihe share the IPC query. No HD provider state
exists in this fixed source, so accuracy or priority never invents HD status.

BLE public search uses the existing BleCentralManager. Its service checks
approximate permission (including firstTokenId), current account and freeze;
filters normalized device IDs and strictly greater RSSI; and propagates actual
scanner startup/stop errors. Stop releases owned registrations even after
permission revocation or account changes. Shared scanner operations recheck
current users when executing, so an old task cannot stop a newer session.
NAPI supports matching callback, omitted/undefined stop, environment cleanup,
reentrant stop and queued callback cancellation without retaining raw references
in asynchronous work.

The guard pins the location project HEAD and the complete raw bytes of all 16
upstream targets. It accepts only the original component state (after the enum
prerequisite), the complete first patch, or the final state. Unknown or mixed
edits, changed patches, missing files and source/ancestor symlinks fail before
source writes. A private full-stack preflight must produce the exact final
bytes before the guarded shared runner writes the source. Existing cooperating
patch locks remain in use; do not modify the source concurrently with patching.

Host tests execute the actual patched functions under ASan/UBSan, using explicit
scanner/NAPI boundaries. Separate guard tests exercise legal prefixes and reject
unknown bytes, mixed states, symlinks and wrong HEADs. The complete 16-file source
copies also pass real patch application and exact final hashes. These checks do
not replace full generated-IDL/TU builds or packaged GNSS/BLE/device validation.
The integrating agent owns shared wiring and representative-package acceptance.
