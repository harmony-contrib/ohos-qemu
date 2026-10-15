# Native KnowledgeContent backed by the actual media database

The fixed API 26 facade declares this class but has no native implementation.
This component registers the real static native class, forwards it through the
public facade and includes its actual C++ sources in media_library's NAPI build.
It must follow the complete existing photo/enum/recent/record/ResultSet stack.

The implementation uses native AccessTokenKit checks for the process system
identity and READ_IMAGEVIDEO before parsing, on worker execution and again
before returning data. A new bound-argument QueryByStep overload preserves the
existing current-application VISITOR store, startup checks and SELinux policy.
There is no caller-selected database path, account ID, raw SQL or permission
bypass. Failure to open/query that protected store returns numeric 23800301.
The ordinary caller receives 202, system caller lacking READ_IMAGEVIDEO 201.
Actual new-package caller/ACL/revocation behavior still needs validation.

The SQL reads actual Photos, AnalysisAlbum, AnalysisPhotoMap and the portrait
nickname unique index. Every entity and nickname stays joined to a currently
visible asset; it excludes hidden, trashed, pending, temporary, critical/risk,
cleaned, non-visible sync, non-cover burst and non-image/video rows. Existing
analysis maps/indices remain owned by their real producers. No separate shadow
knowledge table, fabricated entity, cached count or image-analysis callback is
introduced. Updates/deletes are reflected by one query snapshot, even while an
analysis producer has not yet cleaned orphan map records.

Related entities use real co-occurring assets, stable underlying IDs and stored
aliases; votes count distinct assets. RANDOM_VOTE performs weighted selection
without replacement with a genuine getrandom seed. The implementation default
recommendation count is 10, and an explicit count zero selects no entities.
Search suggestions compose the seven declared time/people/city/label scenarios
from actual indexed values and count distinct matching photos, not alias rows
or a possibly stale stored album count. SQL arguments are bound ValueObjects.

This remains a candidate, not a completed SDK compatibility claim: the pinned
SDK does not fully specify default count, RANDOM_VOTE distribution or display
format. Real product acceptance must check these choices. NONE and HOLIDAY
have no indexed producer in this source; an explicit request for either returns
an internal/unavailable error instead of a successful empty answer. Automatic
semantic label/people/holiday production is not implemented by a query facade.
The whole KnowledgeContent ledger item remains unresolved.

Eight production-builder tests execute the actual parameterized SQL against a
populated persistent SQLite file, covering nonempty relations, same-name IDs,
alias uniqueness/update, all seven distinct-photo counts, visibility, orphan
maps, real deletes/reopen and SQL injection. Four installer tests check all
nine source targets, CRLF preservation, unknown/partial/link rejection and the
five prior exact source guards. They do not replace actual OHOS RDB/ACL/HAP
execution, SDK compilation, link or new-package validation.

`apply.py` validates every complete before/after byte hash before any mutation,
then preserves original line endings and rejects partial state. The numbered
patch is a canonical LF review diff checked against the installed bytes by the
regression; use apply.sh on the real CRLF source. Prior photo guards recognize
only the exact final facade hash; final preparation must still run this full
nine-file validator, so a facade line alone cannot authorize a partial install.
