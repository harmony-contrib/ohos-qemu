# QEMU AV panel and queued callback ownership

This exact component manages four files: the original AVVolumePanel/picker header/
picker CPP and the actual NapiAsyncCallback CPP. The unchanged async header remains
a readonly prerequisite; async CPP is no longer readonly. Source HEAD47a and all
working-tree predecessors plus both async sources/utils/GN are bound to Root's
closed r70 readonly export. No macmirror or old image is current-source evidence.

Keep8d588's per-registration shared handle cells, identity/list/modal-generation
checks, cancellation and terminal-state rules. The new async CPP creates shared
DataContext owners before submission in Call, CallWithFlag and CallWithFunc. The
task captures its owner. Submission failure releases local/task owners, and success
keeps them through actual queue/task lifetime. No raw context waits for a task to
start before obtaining an owner. All original method signatures, checks, logs,
callback/getter/validity ordering and handle-scope cleanup remain. The original
OOM diagnostic text is retained while its guard now checks the context allocation.

Fixed production diagnostics expose actual helper/ref/cell/generation and native
event submission/skip/invocation/release. Pointer values are observation identity
within the real process, not executable input or expected results. Logs use a
separate copied handle value, never a new dereference of borrowed method storage
before validity or after user callback execution. No wait, test scheduler hook,
feature/permission bypass or public API is added.

Complete four-file before, actual old553 final, known unadopted8d588 final and new
final are guarded. Old epochs include the unchanged actual async CPP. Internal
transaction classification still checks unchanged files exactly, excluding only
their equal before/after hash from the epoch vote. Complete old vectors reverse
using their own preserved full patch; normal new apply uses full0001. Unknown or
mixed states reject. require-final never migrates. Root must adopt the exact shared
count3→4 and rewind-delegation cuts in ROOT-SHARED-CUTS.json as part of the same batch.

This source candidate has not been compiled or executed. Actual new-image QEMU
queue→Off, Off→On/handle reuse, modal replacement/close, object/process death/reentry,
normal exact-once delivery, real media consumers and full cleanup remain required.
Original47/82 and first representative runtime gate remain pending.
