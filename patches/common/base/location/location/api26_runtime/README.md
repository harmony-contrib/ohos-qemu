# API 26 location runtime routes

Apply after `api26_public_enums`, using this component's `apply.sh`. The seven-patch
stack adds live icon, filtered BLE search, district, skiing-track and fusion-fence routes.
Transactions 65 through 75 are appended while all original numbers are preserved.

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

District queries use an owned real one-shot request (including its permitted
recent cache), a total deadline and the actual reverse-geocoder provider/cache.
They stop requests, recheck fine/approximate access/current user/switch, and
publish only the SDK district fields. Skiing mode is transported through a new
explicit IPC argument while old RequestConfig parcel bytes stay unchanged. Real
permitted GNSS reports feed accuracy-aware smoothing, derived speed/bearing and
UID/token/delegated-token history with 24h retention and incremental cursors.
The cache fast paths retain actual permission-use ownership through stop retries.
See `docs/capability-audit/parallel/location/round3-business.md` in this repository
for the algorithm, authorization, compatibility and centralized build details.

The guard pins the location project HEAD and the complete raw bytes of all 27
upstream targets. It accepts only the original component state (after the enum
prerequisite), the complete first/second/third/fourth/fifth/sixth patch prefixes, or the final state. Unknown or mixed
edits, changed patches, unexpected new-header bytes, missing existing files and source/ancestor symlinks fail before
source writes. A private suffix preflight must produce the exact final
bytes and revalidate the source snapshot before atomic owned-file replacement.
An explicitly absent original fusion header is supported. Do not modify the
source concurrently with patching.

Host tests execute the actual patched functions under ASan/UBSan, using explicit
scanner/NAPI boundaries. Separate guard tests exercise legal prefixes and reject
unknown bytes, mixed states, symlinks and wrong HEADs. The complete 27-target source
copies also pass real patch application and exact final hashes. These checks do
not replace full generated-IDL/TU builds or packaged GNSS/BLE/device validation.
The integrating agent owns shared wiring and representative-package acceptance.


Fusion fences use real owner GNSS requests, fine-use accounting, actual WLAN
scans and fresh CoreServiceClient cell information. Lifecycle RPC75 checks the
original callback object, protecting later same-id registrations. Expiry and
permission/account/switch changes stop consumers even with a silent provider;
failed permission stops retain ownership for retry. Unsupported BLE bitmap8
returns801 because this SDK has no BLE matching payload. See round4-fusion-
communication.md and round4-platform-build-request.json for supported behavior,
remaining provider/runtime gates, all new targets and complete build requests.


The fifth patch removes production-generated dummy satellite reports and preserves
all real measurement fields/counts. It bounds every satellite input vector and
value-initializes normal/cache HDI configuration. Normal intervals come from the
fastest actual WorkRecord (seconds converted to ms); HDI configuration failures
prevent starts, and active interval updates must configure successfully. See
round5-gnss.md, round5-freeze-inputs.json and round5-platform-build-request.json
for the actual generated POD contract, regression reproduction, and two added
complete platform TU requirements. The external vendor/driver bridge is owned
by the integrating/system agents and is not modified by this component.


The sixth patch passes an owned identity copy to the actual shared mutable-reference
account helper, keeping the fusion fence owner immutable. Fixed header declarations
and the unchanged account helper call chain are exercised by host regression; the
previous const caller is required to fail compilation against that declaration.
See round6-account-contract.md and round6-platform-build-request.json for the
parent-reported full-platform failure and the remaining complete-TU gate.

The seventh patch rejects normal HDI location reports without measured latitude,
longitude and horizontal-accuracy validity bits, nonfinite or out-of-range
coordinates, and invalid horizontal accuracy. An optional UTC field disciplines
the clock only with its actual validity bit and a positive timestamp. Raw
measurement fields and validity bits are otherwise preserved. Fusion WLAN
snapshots now use monotonically increasing scan-completion timestamps; replayed
or older completions cannot overwrite newer inside/outside evidence. Individual
AP timestamps still control freshness and may repeat across a new completed
scan. See `round21-coordinated/HANDOFF.md` for regression and new-package gates.
