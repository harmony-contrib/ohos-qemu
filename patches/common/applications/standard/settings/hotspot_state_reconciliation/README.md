# Hotspot timeout state reconciliation

R31 actual Settings submits `startSharing` successfully but the asynchronous AP
operation fails. The five-second watchdog only reports an event; the toggle can
remain checked while actual `isHotspotActive`/SA 1121 stays false.

At the existing timeout, read the actual public hotspot state and synchronize
both the internal state and visible toggle. Retire the completed pending-action
flag and timer ID. Query failure still reports the original fault and does not
invent an enabled/disabled result. Do not issue a retry, add permissions, change
the Wi-Fi API or interpret successful request submission as an active AP.

This phone Settings source correction is not a backend fix or a 2in1 capability
claim. A newly rebuilt archive must validate successful transitions, backend
failure, subsequent retry and final restoration. The already-frozen R32 does
not contain this patch.
