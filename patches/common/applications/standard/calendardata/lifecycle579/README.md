# Calendar typed ArkTS lifecycle successor

This keeps the complete eighteen-file lifecycle vector at the two fixed project
revisions in source_states.json. Five ETS files change after the actual72 build:
parameter errors now instantiate an Error subclass with the same code/name/message;
caught errors keep the original object with Error type; four event write paths
copy all permitted values except the same protected revision key; two self-referential
constructor bindings gain explicit class types. Thirteen product files, including
the root-composed optional-filter NAPI source, remain byte-exact.

apply.sh uses the source-pinned calendar_lifecycle579 helper. Default preparation
accepts only the complete prefix, complete legacy72, or complete typed final.
Legacy migration stages all eighteen files, checks the full staged final, replaces
only the five changed files, preserves other metadata, and rolls back only its own
known replacements on error. Mixed/unknown bytes reject without overwrite.
--require-final is read-only and never migrates. --migrate accepts only complete
legacy72 or an idempotent typed final.

The original qemu_source_prefix579 hook still calls rewind_if_final before the
original Calendar hooks. Complete legacy72 and complete new final reverse through
their exact own whole patch into the same original prefix. Pristine/earlier/unknown
states are untouched and explicitly deferred, not declared valid. All original
normal source/signing/ancestor guards and the strict final eighteen-file gate must
still complete before GN. ancestor_view requires only the new actual final and
retains the same original read-only sparse predecessor projection and postchecks.

No script, parser, SDK, compiler, host test or guest was executed for this candidate.
This repairs known source diagnostics; new-image compilation, BMS installation,
Calendar business/boundary/regression/cleanup, crossboot, original47/full82 and the
first-artifact gate remain pending.
