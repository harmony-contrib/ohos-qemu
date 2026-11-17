# Immutable VPN callback origins and revocable listeners

Apply after the complete `openvpn_session` component at fixed project revision
`8c41289750820fb2ddb347b1205cee9a7b527388`. Exactly
`services/vpnmanager/{include/networkvpn_service.h,src/networkvpn_service.cpp}`
change; existing public IPC signatures, permission checks, account checks and
other protocol controller APIs remain intact. Predecessor guards accept only
this complete exact successor and all unaffected predecessor files.

Every actual controller gets a private callback bound to its validated setup
owner, account, creator UID/PID, VPN id and object lifetime. Successful setup
publishes its service object before committing that origin. The single serial
FFRT queue may wait for this internal decision without holding service locks;
failed setup, service stop and destruction cancel pending waits. A committed
replacement retires the previous origin so late old events cannot reach the new
connection. Immutable state and separate copies per listener preserve the real
owner/routes/DNS; no asynchronous task borrows an IPC worker's calling identity.
Multi events likewise carry the source owner, with the original account filter.

Registration retains existing public permission gates and gains a revocable
listener identity. Unregister, kernel death and stop deactivate it before
removing the real registration. A new registration never inherits queued events.
Only the initial atomic admission can remain in flight when unregister returns;
no service or callback-list lock is held while invoking the external callback,
so getter/registration/unregistration reentry can complete. Remote system clients
also install actual death recipients. Kernel death cleanup uses captured
UID/PID/account/owner and the matching actual controller instead of the death
worker's IPC identity. Actual destroy errors remain errors and retain their
trace outcomes. Nonowners cannot tear down a newer controller through a stale
listener death.

Foreground changes are checked at dispatch and listener admission; a trusted
USER_SWITCHED event also advances the queued epoch, covering a switch away and
back before drain. Stop advances that epoch, cancels pending waits and clears
listeners. A same-process restart reactivates only live committed origins that
have not been retired; already queued old epochs remain invalid. Backend state
and actual connection status remain separate from listener delivery.

Fixed FFRT revision `bcaabdb891e2be0c3e004c6db87d0c6e79515886`,
`interfaces/kits/cpp/queue.h` SHA256
`89dde36b8553581792918cb04223c131b150cd2d6081550a221b553f79fc623d`
provides `submit_h` with a null-on-failure contract. Creation/registration health
probes return internal failure before success if submission fails. Subsequent
internal `IVpnConnStateCb` methods are void: submission/account/snapshot/remote
RPC failures are explicitly logged and counted in Dump's `Callback delivery
failures`, without inventing a connection failure or claiming delivery success.

Host command:

```sh
LC_ALL=C LC_CTYPE=C LANG=C PYTHONPATH=ci/capability-audit python -m unittest test_batch_network_vpn_callbacks -v
```

This executes the actual new dispatch structs, functions, getter, registration,
unregistration, death cleanup and destructor with explicit FFRT/account/IPC/
backend doubles and real host threads. Tests cover pending setup, getter and
registration reentry, ordering, unregister/re-register epochs, copied state,
worker identity, wrong account, account round-trip, replacement/late events,
real return-code failure handling, stop/restart and pending-worker teardown.
The exact full predecessor chain is replayed and unknown/partial states reject.

Emit a separate actual-function probe that uses real native FFRT instead:

```sh
LC_ALL=C LC_CTYPE=C LANG=C python ci/capability-audit/batch_network_emit_vpn_callback_native.py --output PRIVATE_DIR/vpn-callback-native.cpp
```

Parent must compile it with the actual target OHOS C++ ABI and
`-Ifoundation/resourceschedule/ffrt/interfaces/kits`, link the real `libffrt`,
and run it with a bounded process timeout. It uses real FFRT scheduling,
`ffrt::shared_mutex`, pending decisions, serial order, reentry, revocation,
stop/restart and destruction. Other platform account/IPC/backend doubles remain
explicit; it is not an end-to-end VPN or access-token test. This agent emitted
but did not SDK-compile or run that native probe because the heavy lease belongs
to the parent. Full real service TU/linking, native FFRT execution, actual IPC
and new-package real TLS peer/permission/account tests remain required. No audit
requirement closes from this candidate.
