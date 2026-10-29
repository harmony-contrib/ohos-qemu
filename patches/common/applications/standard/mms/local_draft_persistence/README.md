# Persist local text drafts before wide-screen Back

Build25 showed an accepted recipient and text retained by the original process,
but no database draft after force-stop/restart. The non-phone
`CreateNewConversation.destinationBackPress` returned false before the existing
phone save path. Its `onHide` and the ability background callback did not save.

This component targets MMS project `26df98e3738f4219aa45efe6a3e7f6b1be55c051`.
It changes four files, without changing the existing phone Back or legacy service
function bodies. `apply.sh` reuses `apply_exact_component.py`; `verify_source.py`
reuses `validate_component` to reject every unknown or mixed four-file vector.
The package `mms_provider.verify` additionally requires this component's final
state after `send_data_text`.

## Product behavior

For a non-phone editor with ordinary SMS text and one valid recipient, Back is
consumed. The current VM owns one pending save and disables the editor while it
runs. The database save uses the original parameter/row builder and public data
service calls. It waits for the real detail insert callback and reads the exact
message ID, group ID, thread ID, draft state and body back. A session update must
return success with exactly one affected row. Only then does the same VM receive
the actual saved identity and original draft text, and the view awaits
`moveAbilityToBackground()`. Save or background failure keeps the application
foreground and shows the existing localized `failed` string. Repeated Back while
the same save is pending does not start a second save or background operation.

Existing drafts update/delete by message ID + group ID + thread ID + SEND_DRAFT.
Zero affected rows, a missing/replaced session, unknown/multiple draft rows,
changed original body, or a non-draft row never authorizes an insert fallback.
A process-wide queue serializes this new opt-in save path. VM generation and
snapshot checks reject old callbacks; send/delete wait for this VM's pending save
before the original operation. Release/route destruction ends the epoch. Only an
explicit new `onInit`, after any old task closes, resets its eligibility; onShow
does not revive stopped callbacks. If the detail is proven but the session update
fails, its exact identity is retained for an in-place retry.

## Deliberate bounds

This fixes the observed explicit wide-screen Back path. A fresh blank page can
return without writing. Attachments, RCS, multiple recipients, anonymous text, and
changing the recipient of an already-owned saved draft retain their original
Back route; this component does not claim persistence coverage for those paths.
No new HIDDEN/background write is added: a hidden editor must not start a stale
save after send/delete/navigation. The original PAUSED hook is retained and is
suppressed while the explicit Back save is pending, or after an editor that
opted into the new save has stopped/been invalidated. This prevents the old
PAUSED path from reinserting a rejected deleted/sent snapshot. A new onInit
epoch resets this opt-in gate; an editor that never opted in keeps its original
PAUSED behavior.

The original data provider is not turned into a cross-process transaction. The
new code does not recreate deleted/sent rows on retry; it rejects missing or
changed identities. Failure during a new session creation may leave an empty
session, and a failed final summary update is not reported as a completed save.
These error paths remain foreground for diagnosis rather than claiming success.

## Build26 compiler correction and migration

The actual Build26 log contains four concrete diagnostics (repeated in two log
sections): threadId inferred from LooseObject, an untyped Promise.resolve literal,
and two recursive then callback return inferences. The summary says ERROR:5;
this component does not invent a fifth concrete diagnostic. The correction adds
only explicit number/interface/void types. The complete C45 product behavior
above is unchanged.

The component accepts three complete four-file states: original upstream,
installed C45, or this final compiler-fixed state. Unknown and mixed vectors
reject. `--require-final` and the package guard accept only the final state.
`apply_runtime.py` uses the same project/component lock as the original shared
exact helper. Installed C45 is copied to scratch, the unchanged pinned
`legacy-installed-c45.patch` is reversed there, and the recovered upstream whole
vector is verified. The existing `apply_exact_component.prepare_stack` then
checks permitted targets, applies the new numbered patch in scratch and verifies
all final hashes. All live source bytes/modes are rechecked before replacement;
per-file same-directory atomic replacement preserves modes. Rollback restores
only files still matching this operation's own final bytes/mode.

The build/package path stays `mms/local_draft_persistence`; no shared build
script, signing policy, permission, provider helper or acceptance tool changes.

## Fixed whole-file states

| Project-relative file | Original SHA256 | Installed C45 SHA256 | Final SHA256 |
|---|---|---|---|
| `entry/src/main/ets/pages/conversation/CreateNewConversation.ets` | `97260d924faa4fcb202f6ec66df45f0da77c84f2e45dc077b97235544cd6bdb6` | `128f661daeecbbc367e5ee453f0eed187cc6552b8594638df4fa753658ad3b22` | `128f661daeecbbc367e5ee453f0eed187cc6552b8594638df4fa753658ad3b22` |
| `entry/src/main/ets/pages/conversation/CreateNewConversationViewModle.ets` | `1dcad1224c34074000c3b76fcf906b2a06a2d37338e00b0dbd50c661464a4c18` | `53445bf5faa88c2eb55edab99c4946fdcdc22ac048a8fcef65757c847a823f9a` | `7e8d705c1e25b378144b6569ca8320ec7b338d1f4a37df0941a38d8da72c10f0` |
| `entry/src/main/ets/service/ConversationListService.ets` | `7bb37ad2d705ded59226bb46df9a4f802c2d7bc430dec992ab9ead54a0cc874b` | `32dd94a34774a93126f92d829254c2eacd0670457c5d60b3b58463659d8c0acb` | `835bf3e2567d88d5af2e89bead4dca6c0331eaeb5fdd2bdd92fb073fd9461b7f` |
| `entry/src/main/ets/utils/DraftUtils.ets` | `88e7a1c9097ae3030e12657329f606366e358001d8753c32f3ba056a6db1ec43` | `615976263cb4cf94b139ebdb0e0e5b7bdf1096a86c88e6e084123ff04c07e11a` | `3484d6566418da43b05756a69f75a040949b0f61e5250b175ca3f232f608aff0` |

Full source reading copies live only in the private delivery capsule's
`source/{original,installed_c45,final}`. They are not component build inputs.
Only the six files in this component directory are intended for repository
adoption. `apply.sh`, `apply_runtime.py` and `verify_source.py` retain intended
repository mode 0755; patches and this README use 0644.

Static review only: no guard, candidate, host test, compiler, SDK, container or
QEMU was executed by this author. The next representative package and real QEMU
must check force-stop/restart recovery, repeated Back, edits, cleared drafts,
and the original phone/unsupported paths. No runtime pass is claimed.
