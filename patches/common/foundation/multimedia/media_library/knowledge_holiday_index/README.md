# Real KnowledgeContent holiday producer and bounded queries

Apply `knowledge_content/apply.sh` first, then this component's `apply.sh OHOS_ROOT`.
The installer checks the exact media_library revision and all 13 source states
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

Result iteration uses actual QueryByStep without pre-counting and verifies every
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
