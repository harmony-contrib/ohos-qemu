# Knowledge HOLIDAY caller candidate

This batch prepares four real API26 source projects, external JPEG inputs, fresh
operation requests and independent raw-result checks. It does not build, sign,
install, run a guest, grant permissions or close a requirement. Root owns the
actual SDK105 build, signing, product observer and same-guest collector. The Apps
agent owns the new `batch_media_knowledge_suite.py` and artifacts adapter.

The inspected root revision was `b1aa03cbf23cb11fd97864f38f70da2492e310a4`.
Root's official CN2026-derived resource and 33-day C++ producer test are inputs to
the next guest test, not guest proof. This candidate covers only account100.

## Fixed SDK/source facts

The actual host SDK root is
`/Volumes/PSSD/qemu/validation/first-20261005/provider-sdk-26-full/26.0.0`.
`ets/oh-uni-package.json` reports `26.0.0.105`, API26 Release. In its
`ets/api/@ohos.file.photoAccessHelper.d.ts`:

- Lines 14178/14202 declare `KnowledgeContent.getRelatedEntity(topic, context,
  option?)`, singular. There is no `getKnowledgeContent` or plural
  `getRelatedEntities` declaration. Line 14225 declares `getSearchSuggestion`.
- Lines 13901/13920/13929/13938 define `topicField`, optional `rankingMethod`,
  `recommendationCount`, `suggestionFields`. DAY=6/HOLIDAY=7 are lines 13808/13817.
  The class is system/stage-only; the methods require READ_IMAGEVIDEO and expose
  201/202. NONE and invalid count are tested as actual 13900020 errors.
- Lines 5519–5561 define the ordinary, permission-free creation dialog: actual
  user acceptance returns writable media URIs; refusal returns an empty array.
  Importer writes and closes those returned URIs. It never constructs a media
  URI, creates a row, or requests broad read/write permission.
- DATE_TAKEN at 2631 is Unix seconds. DATE_DAY at 2724 is a system read field
  described as the file creation date, without an EXIF conversion guarantee.
  `PhotoAsset.set` at 1590–1591 changes only TITLE. Real DATE_DAY and DATE_TAKEN
  readback are mandatory gates; a scanner mismatch fails without correction.
- `image.PropertyKey.DATE_TIME_ORIGINAL` at 516, DATE_TIME_DIGITIZED at 1239, and
  `ImageSource` EXIF access are real SDK declarations. JPEGs contain a proper
  Exif sub-IFD (0x8769), UTC offset tags and random ImageUniqueID, plus independent
  random pixels. They are synthetic test photographs, not fake holiday facts.
- `MediaAssetChangeRequest.setHidden` at 10094 is system-only;
  `applyChanges` at 6043 requires WRITE_IMAGEVIDEO. `deleteAssets` at 10050 moves
  assets to trash; `MediaAlbumChangeRequest.recoverAssetsWithUri` / permanent
  `deleteAssetsWithUri` are lines 10978 / 11021. Curator calls these real APIs.

Current final successor source is
`patches/common/foundation/multimedia/media_library/knowledge_holiday_index/files`.
`knowledge_content_napi.cpp:54–65` first checks real system identity (202), then
the actual self token READ_IMAGEVIDEO (201); checks repeat in execution/cursor/
completion. `knowledge_content_query.cpp:24–40` excludes hidden, trash, pending,
temporary, risk and other invisible assets before joining `Photos.date_day` to
real `KnowledgeHoliday.civil_date`. Its SQL has no user_id predicate: this batch
cannot prove cross-account database selection and makes no account-isolation
claim. `knowledge_holiday_index.cpp:144–156` expands [DTSTART, DTEND) and defines
the stable entity ID from UID length, UID and instance start.

## Projects and commands

Use the Pillow-enabled host Python
`/Volumes/PSSD/qemu/validation/first-20261005/host-regression-venv/bin/python`.
Only source/data preparation and Python host checks were executed here.

```sh
python ci/capability-audit/batch_media_knowledge_project.py challenge \
  --calendar patches/resources/knowledge/cn-2026/holidays.ics \
  --provenance patches/resources/knowledge/cn-2026/provenance.json \
  --output /absolute/new/challenge
python ci/capability-audit/batch_media_knowledge_project.py project \
  --role query --challenge /absolute/new/challenge/challenge.json \
  --sdk /absolute/provider-sdk-26-full/26.0.0 --output /absolute/new/knowledge-query
```

Repeat project preparation for these four exact roles. All use module `entry`,
ability `EntryAbility`, UI button `knowledge_run`, status `knowledge_status`.

| Role/bundle suffix | Real signing role | Requested permissions |
| --- | --- | --- |
| `knowledgeimporter` | normal / hos_normal_app | none |
| `knowledgedenied` | normal / hos_normal_app | none |
| `knowledgequery` | system_basic / hos_system_app | READ_IMAGEVIDEO |
| `knowledgecurator` | system_basic / hos_system_app | READ_IMAGEVIDEO, WRITE_IMAGEVIDEO |

All bundle names start `org.harmonycontrib.`. All profiles require empty ACL and
restricted-permission arrays, the fresh guest UDID, actual Java/CMS verification,
unchanged compiled payload and actual BMS/installed-HAP binding. A normal profile
is not converted into a system identity by adding ACL. System roles are explicit
test identities. Query asks for its real user grant; curator asks for real READ
and WRITE grants. Permission denial stays a recorded failure.

`knowledge-source-manifest.json` binds every prepared source file, all fixture
bytes, exact role/run, actual host SDK declarations and challenge. The root SDK
report must inventory this manifest as well as the project files; use the normal
multi-project `source_files`/`commands`/`haps` report, preserving other-project
failures. This batch has not established actual ArkTS build success.

## Data and 22-operation protocol

`challenge.json` contains schema1, fresh 32-lowerhex `run_id`, real calendar and
provenance hashes, bounded cases (maximum64), `lifecycle_case`, scope/user100.
Each case has case_id `dYYYYMMDD`, actual JPEG path/SHA, exact title
`kh-RUN-dYYYYMMDD`, expected EXIF UTC time, expected Unix seconds, and entities
derived from the supplied calendar. First/last/exclusive-end for all seven
intervals, all six makeup dates, and dates outside the calendar's years are
covered. Same-day cases are deduplicated. Outside-calendar means outside this
resource's scope, not a claim about other years' real-world holidays.

Authoritative phase order is `batch_media_knowledge_runtime.STEPS` and
`fixtures/batch_media/knowledge_runtime/protocol.json` (22 phases, tested equal).
Call `prepare_request(challenge_path, actual_boot_id, phase, uris=None)` or:

```sh
python ci/capability-audit/batch_media_knowledge_runtime.py request \
  --challenge /absolute/challenge.json --boot-id ACTUAL-UUID --phase present \
  --uris /absolute/original-created-uri-map.json --output /absolute/fresh-request.json
```

Publish the request atomically as the actual UID's 0600 private
`filesDir/knowledge-request.json`, then click the actual `knowledge_run` node.
Request fields are schema_version/run_id/boot_id/operation_id/role/phase/action/
items. Every item has case_id/day/title/file_name/uri. Before import, URI is empty;
later it must come from the actual dialog/created journal. Present phase places
the genuine holiday lifecycle topic first, so count=0 is checked against a
nonempty topic. Importer private JPEGs must be staged under their exact filenames
and read back independently before cleanup for SHA comparison.

Raw logs are `filesDir/knowledge-RUN.jsonl`. Each complete line has:
schema_version/run_id/boot_id/operation_id/role/phase/sequence/timestamp_ms/uid/
token_id/event/api/value_json/error_code/error_message. Values/errors are actual
API returns. Constructor rejects a reused operation nonce; no original error is
turned into an empty array or success. Sequence and time coordinate evidence;
they do not replace actual returned values or identity probes.

The collector must drive actual Photos creation consent and actual permission
dialogs. It may reuse the frozen Wallpaper dynamic Photos consent and
`read_permission_node` machinery, extending real WRITE dialog handling as needed.
No guessed screen coordinates, root `bm` grants, media SQL, direct calendar/DB
mutation or fake UI receipt are allowed. Requests are synchronization only.

Curator must stay in its original singleton PID after `prepare` through cleanup:
it retains the original public PhotoAsset objects. Restart, missing owned title,
missing grant, unavailable system trash album, failed mutation or absent readback
fails. Hidden/trash exclusion, unhide/recover reappearance, permanent deletion
from active and actual trash queries, remaining-image permanent cleanup and
private JPEG cleanup are mandatory in the full raw oracle. Mid-failure cleanup
is root collector work and cannot be asserted from an unfinished journal.

## Independent validation and required binding

`verify_raw(challenge_path, {role: journal_path}, boot_id=actual_uuid)` or
`verify-raw --challenge ... --boot-id ... --importer ... --denied ... --query ...
--curator ...` recomputes every original row and all22 phases, including real
DATE_DAY/DATE_TAKEN, entity identity/name/alias, first/last/end/makeup negatives,
202, pre-grant201, NONE/count/search errors, visibility and cleanup. Missing
curator or any stage fails. Its result is explicitly raw-semantics-only:
`guest_identity_verified=false`, `ledger_closed=false`.

`verify_role_bindings(capture, challenge_path, env, command=actual_command,
output=fresh_dir)` independently reuses the existing SDK report checker and real
Java/OpenSSL verifier. It checks all prepared source/fixture bytes, actual
signed-to-unsigned payload equality, BMS identity/unique hapPath, installed HAP
bytes, journal UID/token, initial/final native token results and private JPEG
readback SHA. Root supplies actual `command(argv,label)`; no signature check was
executed by this agent.

Capture contract:

```text
capture: run_id, boot_id, archive_sha256, archive descriptor,
         guest_calendar descriptor, signer {dist, jar descriptor}, roles
roles[role]: sdk {sdk_project, source_project, sdk_evidence descriptor,
                 source_manifest descriptor, unsigned_hap descriptor},
             signed_hap descriptor, installed_hap descriptor, installed_remote,
             bms descriptor, journal descriptor,
             token_initial descriptor, token_final descriptor,
             private_source_readbacks {case_id: descriptor} (only importer)
env: user_id=100, boot_id, archive_sha256, udid
```

Artifact descriptors are absolute regular-file path plus SHA256. The raw SDK
report, actual signed profile and all commands/logs remain unchanged. Root must
still independently validate same-guest HDC command capture, its exact archive /
acceptance boot, installed observer ELF and actual product DSO/CFI/mappings. This
function deliberately reports `transport_guest_binding_verified=false` and
`observer_product_ABI_verified=false`. There is no full-guest success shortcut.
The Apps collector is responsible for composing those checks with the raw oracle.

## Product observer candidate

`knowledge_runtime/knowledge_token_query.cpp` needs actual product AccessToken
innerkit headers and `libaccesstoken_sdk.z.so`, preserving actual CFI/libc++ ABI.
Root registers/builds it; it was not compiled here. CLI:
`knowledge_token_query RUN UID BUNDLE`, root execution, only the four fixed
bundles/account100. It uses GetHapTokenID/GetHapTokenInfo plus real twice-checked
VerifyAccessToken; no grant/revoke/mutation operations.

Single-line output: schema_version1, api=`AccessTokenKit::VerifyAccessToken`,
run_id/boot_id/bundle/uid/user_id100/token_id/READ_IMAGEVIDEO/before_ns/after_ns.
WRITE_IMAGEVIDEO is actually queried only for curator; other roles report null,
meaning not queried. Initial native READ must be -1 for all four fresh roles;
final normal READ remains -1, query/curator READ=0, curator WRITE changes -1→0.
Bind these probes to actual BMS UID/token, actual phase commands and observer
ELF/DSO provenance. Self token journal values alone do not establish identity.

## Remaining gaps

- Actual SDK105 four-project compilation, exact signing, product observer build,
  actual permission dialogs, new-package EXIF/date indexing and22-phase guest run.
- Actual collector command/boot/observer-DSO binding and failure cleanup by root /
  Apps. Candidate getters cannot certify these outside their own process.
- Cross-account isolation, populated people/label/city analysis and weighted
  ranking distribution. TIME_PEOPLE is recorded as a real empty query on this
  controlled corpus; it does not prove a nonempty analysis producer.
- Calendar resource replacement/deletion/version changes are separate product
  tests. A fixed official resource is not a writable guest calendar endpoint.

No package build, SDK/Java/native compilation, strip, signature, Docker, source/
out access or VM action was executed by this batch. Host tests use synthetic
raw journals solely as protocol/oracle counterexamples; they are not guest proof.
