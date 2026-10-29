# Linux Binder asynchronous sender identity

Pinned kernel project: `14c77f1541a53e814d89ad6dea5f7f211f9895a6`.
Apply with `bash apply.sh --source-root OPENHARMONY_ROOT`.

Under the existing `CONFIG_BINDER_SENDER_INFO`, capture a private referenced
`struct pid` from the actual sending task for non-reply one-way transactions.
Deliver its initial-namespace TGID through the existing trusted
`BINDER_GET_SENDER_INFO` ioctl. The asynchronous wire `sender_pid` remains zero;
`t->from` remains null, and synchronous transactions/replies retain their
existing behavior. No user-supplied Parcel or transaction PID is trusted.

Release the reference on normal, allocation/translation error, and superseded
frozen `TF_UPDATE_TXN` cleanup paths. The frozen queue has already decremented
`outstanding_txns`, so its dedicated destruction must not call the ordinary
transaction destructor and decrement the counter again.
A sender exiting before delivery does not leave a dangling task pointer.
This preserves the recorded numeric identity; it does not promise that PID
numbers can never be recycled. RS must retain token and node-ownership checks.

The preflight checks the complete pinned/repaired files, rejects partial or
foreign edits and symlinks before any mutation, and checks HEAD when project
metadata exists. Exact-hash owned compilation fixtures need no fabricated Git
metadata. This patch is not a new Binder API or a permission exception.

Object compilation alone is not runtime or package acceptance. Validate real
sync/async delivery, forged PID rejection, sender exit, malformed requests,
frozen update replacement, unfreeze delivery and frozen synchronous rejection,
then ordinary-app rendering from a newly packaged artifact.

The shared packaged probe additionally creates two owned `CLONE_NEWPID`
children without remounting proc or changing the caller's namespace. Both the
live and exited namespace-init sender have `getpid() == 1`, while proc TGID and
the trusted ioctl must equal the positive outer clone PID; one-way wire PID
must remain zero. Its 89 ordered cases do not accept the earlier 58-case
transcript. Actual three-ABI SDK compilation is not namespace execution or
RenderService permission/rendering acceptance.
