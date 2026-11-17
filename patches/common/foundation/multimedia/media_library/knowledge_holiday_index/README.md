# Real KnowledgeContent holiday producer and bounded queries

Apply `knowledge_content/apply.sh` first, then this component's `apply.sh --source-root OHOS_ROOT`.
The installer checks the exact media_library revision and all 14 source states
before writing. It permits a complete original before state, the exact previous
complete overlay, or the complete current after state; unknown/partial/symlink
inputs fail before mutation. The predecessor installer
recognizes this complete forward state so the full stack remains repeatable.
The review patch uses LF; the installer preserves existing CRLF hook files.

The service consumes only `/system/etc/knowledge-content/holidays.ics`, owned by
root/system and not writable by group/other; the directory and file cannot be
symlinks. No HAP path, arbitrary SQL, writable calendar provider or root SQL
injection tool is added. The parent owns optional real calendar asset packaging
and its external provenance/hash binding. No invented holiday dates are shipped.
An absent optional resource produces a real empty table. ENOENT replaces an old
index with the absent version. Permission, I/O, invalid or unsupported calendar
errors preserve the previous complete rows and resource hash and log an error.
A new database still gains the schema, allowing legitimate no-data queries.

Input is an explicit all-day ICS subset: VCALENDAR VERSION:2.0, Gregorian,
VEVENT UID, DTSTART;VALUE=DATE, optional exclusive DTEND;VALUE=DATE, and SUMMARY
with TEXT escaping/folding and strict UTF-8. Missing DTEND means one civil day.
SUMMARY LANGUAGE is accepted. Gregorian dates use YYYYMMDD, matching actual
Photos.date_day; no UTC/local timestamp conversion guesses are made. Multi-day,
leap-day and cross-year instances expand to civil rows. Identical duplicate UID
instances collapse; conflicting duplicates reject the whole resource. RRULE,
RDATE, EXDATE, RECURRENCE-ID, timed/TZID events and nested components fail as an
unsupported resource rather than silently dropping dates. Limits are 1 MiB,
8192 bytes per unfolded line, 4096 events, 20000 expanded rows, 366 days per
instance, and 1024 bytes per UID/name. This is not a full RFC5545 implementation.
It changes no public I18N ABI.

The actual service-owned MediaLibrary RDB stores KnowledgeHoliday civil rows and
KnowledgeHolidayResource schema/version/SHA256/presence/count in one native
IMMEDIATE transaction. The resource is loaded inside that transaction, preventing
older concurrent snapshots from committing after a newer import. SQL identifiers
are fixed, and every resource value is bound. Entity identity is length-prefixed
UID plus occurrence start, stable across names/date-span changes. Resource version
is acknowledged only on a complete commit. Single-statement asset queries retain
one database snapshot while concurrent resource replacement commits a new one.

Both service Init overloads synchronize on creation, legacy open/upgrade and
reopen. The service-owned observer rechecks the fixed read-only resource every
five seconds, avoiding inotify invalidation/absent-directory/replacement races.
Unchanged successfully imported hash/presence avoids repeat writes. This is an
observer of system configuration, not an update interface or a bypass of the
read-only system policy. Stop cancels and joins before releasing the static DB;
thread state holds a weak RDB and a temporary shared RDB only during import.
No raw service/store pointer survives a call. Concurrent external stops wait for
the retiring worker; a reentrant worker Stop cancels and defers its own join to
the next external Stop/Init or owner teardown. Lifecycle mutexes are not held
across RDB calls or join. Individual wrapper destruction does not stop the static
shared service database. Poll wait is immediately cancellable; an in-flight
native DB call must finish before external Stop completes.

The fixed SDK defines optional integer count and RANDOM_VOTE but does not define
a count default, exact vote formula or display punctuation. Project semantics:
count omitted returns the full candidate set within the response budget; zero
returns none; positive count caps the result. Weighted exponential-race sampling
uses distinct eligible-asset votes without replacement. Search display joins
actual component names with a single space; count is distinct visible assets.
NONE is a sentinel, rejected with parameter error 13900020 when passed as a query
field. Default topic/suggestion fields are the eight real producer fields.
Holiday field 7 joins the real index to Photos.date_day and the existing
account/visibility/permission constraints. Ordinary/system/READ_IMAGEVIDEO token
checks, current-account VISITOR access, hidden/trashed/pending/temp/critical/cloud
filters and revocation checks remain in the native path. Actual service Visitor
ACL and three caller roles still require product runtime evidence.

The original visitor iteration used QueryByStep without pre-counting and verified every
cursor return/access check. It bounds strings to 64 KiB and accumulated response
to 8 MiB; excess returns an error with no partial-success result. Omitted count
therefore does not create an unbounded native result vector. The whole native
NAPI/query/helper/producer TUs and actual link remain mandatory product checks.

Host tests execute the full production producer TU with ASan/UBSan, real OpenSSL
SHA256 and persistent SQLite transactions behind controlled NativeRdb adapters.
The filesystem tests redirect only the fixed path and inject explicit ownership,
permission/I/O/mutation faults. They prove producer parsing, transaction/rollback,
legacy schema, source replacement/removal, cursor snapshot, lifecycle and query
joins. Native cursor tests execute real NAPI-boundary function bodies with
controlled cursor/token/NAPI dependencies. These are not actual NativeRdb pool,
Visitor ACL, OHOS service scheduling, HAP or device/backend acceptance. Test ICS
is an independent generated input challenge, not a real-world holiday dataset.

The exact previous complete e0d1137 overlay is also a recognized upgrade input;
previous/current mixed files still fail before mutation. The current overlay
uses actual media_log.h and declares AccessTokenKit/IPCSkeleton's direct
access_token:libaccesstoken_sdk and ipc:ipc_core GN dependencies for the native
photoaccesshelpernative target, rather than relying on transitive headers or
manually patched compiler include options.

Round5 GN integration: photoaccesshelpernative directly depends on
relational_store:rdb_data_share_adapter because media_asset_rdbstore.h includes
its exported rdb_utils.h. medialibrary_data_extension already directly depends
on openssl:libcrypto_shared; actual crypto_config_public exports source and
generated include directories. Derive these declared configs in actual GN
compilation; do not compensate with arbitrary compiler include flags.
The exact thirteen-file guard accepts both previous complete e0d1137 and
caeaf60 states as upgrades, preserving mixed/unknown source rejection.

Round7 keeps the actual product -fno-exceptions option. The observer uses
explicit pthread error returns, nothrow state allocation and independent
state ownership; no std::thread construction or try/catch remains. Worker
self-stop cancels and defers joining; external stops wait outside RDB locks,
join failure preserves the generation for retry, and self-owned destruction
detaches only its independently retained state. Host full-TU tests compile
with -fno-exceptions plus ASan/UBSan and exercise actual return-failure cleanup.
The complete previous a5fe432 source state is an additional exact upgrade input.
Parent actual full product TU/link and new-package runtime remain mandatory.

F media-owner query successor
----------------------------
The completed E public baseline granted READ_IMAGEVIDEO, read the real request
from ApplicationContext.filesDir and obtained count=0 from getAssets, then
getRelatedEntity failed with 23800301. The former NAPI only tried a visitor RDB;
getAssets can instead use the real DataShare owner. The exact visitor-open vs
SQL-prepare cause was not disambiguated by that old generic message.

The successor removes the public caller's visitor/path dependency. A fixed
internal URI under MEDIALIBRARY_DATA_URI receives only a bounded typed protocol,
never SQL or a DB path. The real service checks IPC caller system-app identity
and READ_IMAGEVIDEO before decoding and querying its own existing RDB. Native
self-token checks at request, each row and completion remain. No grant, ACL, APL,
SELinux, root caller, extra provider or fabricated empty result is introduced.
The same query generator is compiled into both targets; only the service builds
the SQL for execution. Existing visible-Photos joins and real holiday producer
remain unchanged.

Actual DataShare GoToRow returns E_ERROR=1001 for both normal out-of-range and
OnGo failures, and both set rowPos=rowCount. Neither a nonzero status nor IsEnded
can prove EOF. DataShare itself needs GetRowCount. The service appends a LIMIT
with one sentinel row, derived conservatively from the existing 8MiB per-row
Account budget. Client count must succeed, be nonnegative and fit that limit;
a sentinel/oversize result fails rather than becoming truncated success. It then
reads exactly that many rows; any nonzero step/column/close status is an error.
This bounds the inherent DataShare pre-count and preserves the 8MiB byte check.
Zero is accepted only from a successful real count on a real result set.

Client helper creation, business errors, count, step and close retain their real
return codes in phase-specific messages. A service null RDB/query emits its exact
phase with underlying_rc=unavailable, because QueryByStep exposes no error code
in that return path. This is a preserved diagnostic limitation, not a zero code.
The QA Query page records the actual active public API and keeps an original
API failure when helper release also fails. SDK/source binding requires fresh
Knowledge roles; manifests include all fixture hashes.

The whole former E state is an explicit upgrade prefix, never the new final.
A separate actual-E upstream fixture guards the newly touched service source;
historical original fixtures remain unchanged. Patch 0001 retains its bytes;
0002 is the exact E-to-F review diff. Both base and complete history upgrade to
the new 14-file state; unknown/mixed states remain failures.

service-query-provenance.json pins actual E source/interface exports 14/15/19.
Host counterexamples cover server 202/201, malformed/raw-SQL wire, null RDB/query,
count failure/negative/over-budget, generic 1001 before expected EOF, revocation
and original field/byte budgets. They are not IPC, native-build, SDK or guest
proof. Root must compile the real affected native targets and all four QA HAPs,
then validate the new representative package through the unchanged full public
Knowledge suite, including baseline, consent/import, query/holiday boundaries,
hide/unhide, trash/recover, permanent deletion and owned cleanup.


Namespace repair after the first final-F compilation
--------------------------------------------------
The service TU is in OHOS::AbilityRuntime and does not import DataManager's
OHOS::RdbDataShareAdapter namespace. Its one bridge call therefore uses explicit
OHOS::RdbDataShareAdapter::RdbUtils. This changes no protocol, authorization,
SQL, error code, close or response budget behavior. Patch0003 follows unchanged
historical0001/0002; the original service-query-provenance.json records that
historical service-routed parent. namespace-repair-provenance.json describes this
source-only successor and its exact parent/final whole-file hashes.

The complete prior F fourteen-member after vector is an explicit upgrade input.
The service transform replaces only its exact old block; it does not replay
include/query hooks. All historical complete vectors remain, and unknown/mixed
sources still fail before writes. New/final/legacy repeats retain the original
CRLF mode of each hook file. The stricter host service fixture declares the real
OHOS::RdbDataShareAdapter and distinct DataShare::ResultSetBridge types, with no
global RdbUtils alias, and retains permission/SQL/null/close counterexamples.
Its negative namespace compile and whole-state upgrade cases are regression
source only until root executes them; a host pass cannot replace real GN TU,
link, new package or public Knowledge runtime acceptance.
