# Knowledge holiday resource: repository facts and CN/2026 candidate

Reviewed host repository commit: `f82275e38321b10fc6429d2727d3ea9c90f8f44a`.
This is a read-only integration review plus a documentation-only data candidate.
No Docker, live source/out access, build, package, HDC or guest run occurred.
No requirement is closed and the first-artifact behavior gate remains false.

The existing implementation can install and index a legitimate calendar, but the
frozen repository contains no tracked `.ics`, `.ical` or `.ifb` resource. Its
tests contain explicitly synthetic or empty calendars. Those inputs test parsing
and provenance; they cannot supply real holiday knowledge for delivery.

The missing CN/2026 data does **not** require the user to create or supply an ICS.
There is an authoritative public source: the State Council's
[2026 holiday-arrangement notice](https://www.gov.cn/zhengce/zhengceku/202511/content_7047091.htm),
dated 2025-11-04, document number 国办发明电〔2025〕7号. The accompanying
`cn-2026-holiday-arrangements.candidate.ics` independently encodes its seven
published holiday/rest-adjustment intervals, covering 33 civil days. It is a
candidate for a future batched repair; it has not entered the current source,
build or package.

## Actual implementation and missing wiring

`scripts/prepare_qemu_knowledge_resource.py` accepts `--asset` as a real UTF-8,
non-symlink file of 1–1,048,576 bytes. It copies the original bytes into
`vendor/ohemu/virt/etc/qemu_holidays.ics`, records their SHA256 and absolute input
path in `.ohos-qemu-knowledge-calendar.json`, and installs the fixed GN target.
The final path is `/system/etc/knowledge-content/holidays.ics`; `resource.json`
declares its format, optional status and hash. Source-path/hash binding is not
publisher, jurisdiction, year or redistribution evidence. Such evidence must
travel with the chosen actual resource.

Without an asset, the installer creates only the contract and directory. It
preserves any complete previously managed asset on reapply. Therefore an unset
environment variable does not prove that a reused source checkout has no asset,
and there is currently no explicit removal CLI. The eventual source inventory
and actual image, rather than the launch environment alone, decide presence.

The inner builder already calls the installer at
`scripts/build_standard_qemu_in_docker.sh:3411` and reads `QEMU_KNOWLEDGE_ICS`.
However, the formal phone/2in1 Docker launcher
`scripts/run_2in1_full_build_docker.sh:445` never forwards that variable and has
no dedicated input mount for it. Merely setting it on the host does not select
the asset in that container. This is a definite, independently repairable wiring
gap. Keep the currently running frozen representative attempt intact; repair
this together with its collected failures.

`scripts/verify_qemu_runtime_assets_image.py` checks the asset against the source
marker, carries it in `runtime-assets-source`, verifies unique actual-image file
identity/hash, and rejects an unexpected unbound ICS. Packaging and offline
verification already invoke it. Its optional-asset success does not mean that
holiday data is populated or that a public Knowledge query succeeded. This
verifier checks bytes, not ICS syntax or factual correctness.

## Data contract and candidate scope

The actual producer in `knowledge_holiday_index/files/knowledge_holiday_index.cpp`
reads only the fixed system path. The directory and file must be owned by root
or system, must not be group/other-writable, and must not be symlinks. Accepted
inputs are Gregorian VCALENDAR VERSION 2.0 with explicit all-day VEVENT UID,
`DTSTART;VALUE=DATE`, optional exclusive `DTEND;VALUE=DATE`, and UTF-8 SUMMARY.
RRULE, RDATE, EXDATE, RECURRENCE-ID, timed/TZID entries and nested components are
rejected. Limits include 4,096 events, 20,000 expanded rows, 366 days per event,
8,192 bytes per unfolded line and 1,024 bytes per UID/name.

The candidate uses exactly the supported subset, with LF line endings expressly accepted by
the producer's `Lines()` function. Its end date is the published
last day plus one Gregorian day; it does not calculate lunar dates or convert
timestamps. Its summaries explicitly identify the published holiday/rest
arrangements. These are **not** a classification of statutory festival days:
transferred rest days and weekends inside each published interval are included.
All six published makeup workdays are recorded in the facts sidecar and excluded
from the ICS. The current producer has no holiday/workday discriminator, so
adding those workdays as VEVENTs would incorrectly label them as HOLIDAY.

This covers only the seven mainland national arrangements in that 2026 notice.
It excludes Hong Kong, Macao, Taiwan, other years, local/employer schedules,
ordinary weekends outside the intervals, and future unreviewed corrections.
`zh-Hans-CN` is a suitable product default for this explicitly scoped candidate;
it does not establish the user's jurisdiction or justify global coverage.

The notice's administrative character and its date facts provide a concrete
reuse basis under Article 5 of the
[Copyright Law published by the National Copyright Administration](https://www.ncac.gov.cn/xxfb/flfg/flfg_532/202103/t20210309_50530.html).
This is an applicability inference from the official text, not a CC0 label or a
claimed government license for our ICS. We independently format only those facts,
attribute the exact notice, and reuse no website layout, logos, images, editorial
articles or third-party dataset. The
[government website statement](https://www.gov.cn/home/2014-02/23/content_5046258.htm)
is not a blanket open-data license. The repository MIT license and patch-source
Apache notices likewise do not establish rights in unrelated calendar datasets.

`cn-2026-notice-facts.json` provides the seven intervals, exclusions, conversion
rules and rights reasoning. `public-source-receipts.json` records actual HTTPS
retrievals, timestamps and response-body hashes, plus the separate web retrieval
of the law. Original HTML was not archived; a response hash alone is not an
offline copy or a cryptographic publisher signature. No claim of a
government-published ICS is made.

## CalendarData is a separate capability

The existing CalendarData source provider and EditorUIExtension implement actual
permission-controlled personal calendar storage and a user-confirmed new-event
flow. Opening the editor does not save an event. Nothing in their current
repository components supplies an authoritative holiday calendar, and the
Knowledge producer has no CalendarData/DataShare import path.

Subscribing to user calendar events would not establish that those events are
regional holidays. Bridging them into the current system-wide holiday table
would also require an explicit selected-calendar/source contract, caller consent,
account and permission isolation, civil-date/all-day/recurrence handling, stable
identities and deletion/revocation cleanup. It would change the service's current
trust and data model. Do not add calendar permissions or copy all personal events
into HOLIDAY to satisfy this requirement. The existing trusted, scoped official
ICS route requires less new product implementation and supplies actual facts.

## Next batched repair and acceptance

1. Root can adopt the explicitly scoped official CN/2026 facts after reviewing
   this candidate, freeze its bytes and source/rights sidecar, and add a dedicated
   read-only Docker input mount plus explicit `QEMU_KNOWLEDGE_ICS` forwarding.
   Make the selected resource and provenance part of the reproducible input
   receipt. Do not depend on the host environment reaching Docker implicitly.
2. Before a future build, run the existing actual producer's parser against these
   exact candidate bytes, retaining the candidate SHA and expected seven
   intervals/33 days. This round ran only the independent Python structure/date
   check; it did not execute the C++ producer. For a write-lease preparation the
   existing narrow entry point is:

   ```sh
   python3 /work/scripts/prepare_qemu_knowledge_resource.py \
     --source-root "$OHOS_ROOT" --asset /calendar/cn-2026-holidays.ics
   ```

   This is a proposed future command, not a command run during this review.
3. Preserve publisher/document/date/scope/conversion/rights evidence alongside
   the existing actual-byte/image inventory. If adding a populated-data release
   gate, require the chosen asset/hash and declared scope explicitly; keep
   optional absent-resource behavior distinct. Consider an explicit guarded
   removal operation and factual/provenance validation, rather than hand-editing
   managed marker/GN files or treating a retained old asset as current.
4. On a newly packaged representative image, prove the actual service indexes
   this exact resource and the public field-7 query joins real visible photo
   civil dates. Test first/last and exclusive-end days, a published makeup
   workday, an out-of-scope date, hidden/trashed/deleted assets, account isolation,
   ordinary caller denial, legitimate system/READ_IMAGEVIDEO roles and permission
   revocation. Resource replacement/removal/error behavior needs actual permitted
   lifecycle evidence; there is no writable calendar update API to assume.
   Byte-identical packaging, an empty result, or host tests alone cannot pass it.

For CN/2026 seven-interval data, root can proceed with this official source without
requesting a user-created ICS. Other jurisdictions/years, a different definition
of holiday, or a private/commercial calendar need an explicit scope and a real
authoritative/licensed source; ask the user only for those unresolved choices or
materials. The public Knowledge runtime/account/permission checks and the other
Knowledge entity producers remain separate acceptance work.

`source-evidence.json` binds 18 reviewed repository files to the frozen commit.
`candidate-checks.json` records only lightweight Python structure and date checks.
No native compilation or product/runtime test is reported as passing here.
