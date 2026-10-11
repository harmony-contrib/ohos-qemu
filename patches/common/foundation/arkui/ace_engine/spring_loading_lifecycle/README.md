# Abort without cancellation notification

User approved the three minimum SpringLoadingContext contract repairs.
The pinned dynamic SDK explicitly says abort does not produce CANCEL callbacks.

Both real BEGIN and UPDATE paths now cancel their pending timer and silently
enter the existing completed internal state. The existing detector already
suppresses further movement inside a completed target, and resets on boundary
exit / new target. No new state number, object-layout field, public API,
permission, UDMF or backend is introduced. A real release/interruption of a
non-aborted hover still follows the original CANCEL path.

Exact-state checks bind all three files to the fixed 7.0 ace_engine commit.
Sanitizers / three-ABI TU compilation are preparation, not guest acceptance.
Real input must prove abort silence, boundary re-entry, normal END, ordinary
CANCEL, removal, lifecycle cleanup and no data leakage before closure.

KB/source routing matches the companion spring_loading_context component.
Not included in already frozen R37 build inputs.
