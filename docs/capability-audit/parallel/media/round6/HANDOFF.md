# Media round 6: actual ArkTS throw constraint

Base 63395d37424f03d6894d83fb3e1fd8b335d5527f. Only the existing media ETS,
owned host fixtures/tests and reports change; all native/product payloads and
25 cumulative upstream targets remain unchanged. All7 IDs remain open,0 closures.
No Docker, HAP build, product build, QEMU or HDC was used.

Root's actual official six-persona HAP batch passed Capture/Recorder/RecorderDenied
and rejected event-revoke/event-owner/event-contender at the same3 raw
`throw error` statements with TS87 arkts-limited-throw. The prior host strict TS
helper check did not enforce this ArkTS restriction. Original complete HAP
failure logs and frozen input remain under r52-six-media-ordinary-HAP-roles-01;
arkts-throw-fix.json records their paths/hashes and exact current source hashes.

Each catch now casts the actual rejection to BusinessError for inspection and
throws a newly constructed Error. Its message explicitly retains the original
name, code, message, stack and optional data as JSON; successive conversion does
not discard the original details. Existing startup_failed evidence, failed
state, actual native abort, stop and unsubscribe paths are preserved. Ordinary
Error failures also remain actual failures. No compiler checks were disabled.

The official API26 helper type compile plus actual-helper cleanup test passes
(background-host-01.log). Eight controlled service scenarios include3 new plain
BusinessError rejections at evidence open, readiness read and background Start.
They require an actual Error instance, lossless original fields after unwrapping,
and original native abort/cleanup behavior. These are controlled service callouts,
not actual guest MIC/notification/task behavior.

A focused guard uses the actual installed SDK TypeChecker to reject unknown/any
or non-Error throw expression types; the current extracted helper passes while
raw catch unknown, string and any negative cases are rejected. This covers the
reported constraint for this candidate but is not the complete ArkTS compiler.
Root must rerun the3 actual official event HAP personas with unchanged checker
settings. Signed HAP contracts and new representative-image behavior remain the
final gates. Native SDK links were not repeated because their source bytes did
not change.

Permission clarification from root's fixed actual
permission_constraint_check.cpp::IsAclSatisfied review: ACL/provision checks run
only when policy.apl is below the permission availableLevel. Both HAP and
KEEP_BACKGROUND_RUNNING are normal, so no extra ACL or restricted-profile
exception is needed. Retain the existing normal signer and ACL[]. Declare the
normal permission and audioRecording ability mode, then independently verify
actual install/query-background is GRANTED. Real notification enable consent
when disabled and each ordinary MIC user grant still apply. Round5's suggestion
of an additional profile allowance is superseded by this actual service rule.
